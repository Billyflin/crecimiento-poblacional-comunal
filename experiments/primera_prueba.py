"""Prueba reproducible de corresistencia en E. coli canina, FDA Vet-LIRN.

Ejecutar desde cualquier directorio:
    python experiments/primera_prueba.py

Requiere pandas, numpy y openpyxl. Conserva el archivo oficial sin modificarlo.
Las categorías R son operativas según un protocolo histórico; no clínicas.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import platform
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "experiments/protocolo_primera_prueba.json"
OUTPUT = ROOT / "results/primera_prueba"


def normalize(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().str.casefold()


def resistance_status(sign, mic, resistant_min: float):
    """1=R, 0=por debajo de R (incluye I), None=indeterminable.

    No convertimos '<=16' en '16'. Clasificamos solo cuando todo el intervalo
    de MIC compatible con el resultado está del mismo lado del corte R.
    No asumimos que los valores censurados son diluciones discretas.
    """
    if pd.isna(mic) or pd.isna(sign):
        return None
    try:
        value = float(mic)
    except (ValueError, TypeError):
        return None
    if not math.isfinite(value) or value <= 0:
        return None
    operator = str(sign).strip().replace("≤", "<=").replace("≥", ">=")
    if operator == "=":
        return int(value >= resistant_min)
    if operator == "<=":
        return 0 if value < resistant_min else None
    if operator == "<":
        return 0 if value <= resistant_min else None
    if operator in (">", ">="):
        return 1 if value >= resistant_min else None
    return None


def verify_interval_handling():
    # Límites que pueden alterar un hallazgo científico si se imputan mal.
    examples = [
        ("<=", 16, 16, None), ("<", 16, 16, 0),
        (">", 8, 16, None), (">=", 16, 16, 1),
        ("=", 8, 16, 0), ("=", 16, 16, 1),
        ("<=", 4, 16, 0), (">", 8, 8, 1),
        ("", 16, 16, None), ("=", float("nan"), 16, None),
    ]
    for sign, mic, threshold, expected in examples:
        actual = resistance_status(sign, mic, threshold)
        assert actual == expected, (sign, mic, threshold, actual, expected)
    return len(examples)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_source(protocol):
    path = ROOT / protocol["source_file"]
    actual_hash = sha256_file(path)
    if actual_hash != protocol["source_sha256"]:
        raise ValueError("El archivo oficial cambió; revisar la procedencia antes de ejecutar.")
    return pd.read_excel(path, sheet_name=protocol["source_sheet"])


def prepare_cohort(raw, protocol):
    required = ["Sample Id", "Genus", "Host Species", "Collection Source**",
                "Plate", "Year", "Drug Name", "Drug Code", "Sign", "MIC", "LAB", "State"]
    missing = set(required) - set(raw.columns)
    if missing:
        raise ValueError(f"Faltan columnas: {sorted(missing)}")
    # Conflictos se revisan en todo el archivo, antes de filtrar antibióticos.
    normalized = pd.DataFrame({
        "sample_id": raw["Sample Id"].astype("string").str.strip(),
        "genus": normalize(raw["Genus"]),
        "host": normalize(raw["Host Species"]),
        "source": normalize(raw["Collection Source**"]),
        "plate": normalize(raw["Plate"]),
        "year": pd.to_numeric(raw["Year"], errors="coerce"),
        "lab": raw["LAB"].astype("string"),
    }, index=raw.index)
    group = normalized.groupby("sample_id", dropna=False)
    inconsistencies = group[["genus", "host", "source", "year", "lab"]].nunique(dropna=False)
    conflicting = set(inconsistencies.index[inconsistencies.gt(1).any(axis=1)])
    valid_id = normalized["sample_id"].notna() & normalized["sample_id"].ne("")
    dog_ecoli = (valid_id & normalized["genus"].eq(protocol["cohort"]["genus"])
                 & normalized["host"].eq(protocol["cohort"]["host"]))
    urinary = dog_ecoli & normalized["source"].isin(protocol["cohort"]["collection_sources"])
    panel = urinary & normalized["plate"].eq(protocol["cohort"]["plate"])
    safe = panel & ~normalized["sample_id"].isin(conflicting)
    records = raw.loc[safe].copy()
    records["sample_id"] = normalized.loc[safe, "sample_id"]
    records["year"] = normalized.loc[safe, "year"]
    records["source_normalized"] = normalized.loc[safe, "source"]
    names = {drug["name"]: code for code, drug in protocol["drugs"].items()}
    selected = records[records["Drug Name"].isin(names)].copy()
    selected["item"] = selected["Drug Name"].map(names)
    if selected.duplicated(["sample_id", "item"]).any():
        raise ValueError("Hay ensayos duplicados por muestra/antibiótico; revisar sin deduplicar automáticamente.")
    assert selected["Drug Code"].eq(selected["item"]).all(), "Nombre y código no coinciden."
    selected["R"] = pd.array([
        resistance_status(sign, mic, protocol["drugs"][item]["resistant_min"])
        for sign, mic, item in selected[["Sign", "MIC", "item"]].itertuples(index=False, name=None)
    ], dtype="Int64")
    selected["status"] = selected["R"].map({1: "R", 0: "por_debajo_de_R"}).fillna("indeterminado")
    items = list(protocol["drugs"])
    eligible_ids = records["sample_id"].unique()
    wide = selected.pivot(index="sample_id", columns="item", values="R").reindex(
        index=eligible_ids, columns=items)
    missing_test = wide.isna()  # Incluye ensayo ausente y MIC indeterminada.
    complete = wide.notna().all(axis=1)
    metadata = records.drop_duplicates("sample_id").set_index("sample_id")[
        ["year", "LAB", "State", "Collection Source**"]].rename(
            columns={"LAB": "lab", "State": "state", "Collection Source**": "source_original"})
    metadata["year"] = metadata["year"].astype(int)
    cohort = metadata.join(wide.rename(columns=lambda c: "R_" + c)).loc[complete].copy()
    for code in items:
        cohort["R_" + code] = cohort["R_" + code].astype(int)
    sample_audit = metadata.copy()
    sample_audit["included"] = complete
    sample_audit["unknown_or_missing_items"] = missing_test.apply(
        lambda row: "|".join(row.index[row]), axis=1)
    counts = {
        "raw_assay_rows": len(raw),
        "raw_sample_ids": int(normalized.loc[valid_id, "sample_id"].nunique()),
        "dog_ecoli_sample_ids": int(normalized.loc[dog_ecoli, "sample_id"].nunique()),
        "urinary_sample_ids": int(normalized.loc[urinary, "sample_id"].nunique()),
        "fixed_panel_sample_ids_before_quality_filter": int(normalized.loc[panel, "sample_id"].nunique()),
        "excluded_conflicting_sample_ids_in_panel": int(normalized.loc[panel, "sample_id"].isin(conflicting).groupby(normalized.loc[panel, "sample_id"]).any().sum()),
        "fixed_panel_sample_ids_after_quality_filter": len(eligible_ids),
        "excluded_incomplete_or_indeterminate": int((~complete).sum()),
        "included_complete_sample_ids": len(cohort),
        "all_source_conflicts_by_field": {c: int(inconsistencies[c].gt(1).sum()) for c in inconsistencies},
    }
    per_drug = []
    for code in items:
        tests = selected[selected["item"] == code]
        per_drug.append({"item": code, "drug": protocol["drugs"][code]["spanish"],
                         "tested_samples": len(tests), "R": int(tests["R"].eq(1).sum()),
                         "below_R": int(tests["R"].eq(0).sum()),
                         "indeterminate_tests": int(tests["R"].isna().sum()),
                         "absent_tests": len(eligible_ids) - len(tests)})
    audit = {"counts": counts, "per_drug": per_drug,
             "included_by_year": {str(k): int(v) for k, v in cohort.groupby("year").size().items()},
             "included_laboratories": int(cohort["lab"].nunique()),
             "source_labels_by_year": {str(year): {str(label): int(count) for label, count in group.groupby("source_original").size().items()}
                                      for year, group in sample_audit.groupby("year")}}
    return cohort, selected, sample_audit, audit


def apriori_counts(matrix, items, min_support, max_size):
    """Apriori: poda candidatos cuyos subconjuntos no son frecuentes."""
    n = len(matrix)
    min_count = math.ceil(min_support * n)
    frequent, considered = {}, {}
    previous = set()
    for size in range(1, max_size + 1):
        current = set()
        tested = 0
        for candidate in itertools.combinations(items, size):
            if size > 1 and any(subset not in previous for subset in itertools.combinations(candidate, size - 1)):
                continue
            tested += 1
            count = int(matrix.loc[:, list(candidate)].all(axis=1).sum())
            if count >= min_count:
                frequent[candidate] = count
                current.add(candidate)
        considered[str(size)] = {"tested_candidates": tested, "frequent_itemsets": len(current)}
        previous = current
    return frequent, considered


def rule_metrics(matrix, antecedent, consequent):
    a = matrix.loc[:, list(antecedent)].all(axis=1).to_numpy()
    b = matrix[consequent].to_numpy(dtype=bool)
    n = len(matrix)
    n_a, n_b, n_joint = int(a.sum()), int(b.sum()), int((a & b).sum())
    support = n_joint / n if n else None
    baseline = n_b / n if n else None
    confidence = n_joint / n_a if n_a else None
    lift = confidence / baseline if baseline and confidence is not None else None
    ci_low, ci_high = wilson_interval(n_joint, n_a)
    return {"n": n, "antecedent_count": n_a, "consequent_count": n_b,
            "joint_count": n_joint, "support": support, "baseline": baseline,
            "confidence": confidence, "lift": lift,
            "confidence_ci95_low": ci_low, "confidence_ci95_high": ci_high}


def wilson_interval(successes, total):
    if not total:
        return None, None
    z = 1.959963984540054
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def mine_rules(cohort, protocol):
    items = list(protocol["drugs"])
    matrix = cohort[["R_" + code for code in items]].rename(columns=lambda c: c[2:]).astype(bool)
    discovery = matrix.loc[cohort["year"].isin(protocol["cohort"]["discovery_years"])]
    validation = matrix.loc[cohort["year"].isin(protocol["cohort"]["validation_years"])]
    assert len(discovery) > 0 and len(validation) > 0
    assert set(discovery.index).isdisjoint(validation.index)
    assert len(discovery) + len(validation) == len(cohort)
    all_rules, comparisons = [], []
    for config in protocol["rule_search"]["configurations"]:
        counts, candidate_audit = apriori_counts(discovery, items, config["min_support"],
                                                 protocol["rule_search"]["max_itemset_size"])
        current_rules = []
        for itemset, count in counts.items():
            if len(itemset) < 2 or count < protocol["rule_search"]["min_joint_count"]:
                continue
            for consequent in itemset:
                antecedent = tuple(item for item in itemset if item != consequent)
                train = rule_metrics(discovery, antecedent, consequent)
                if train["confidence"] < config["min_confidence"] or train["lift"] < protocol["rule_search"]["min_lift"]:
                    continue
                val = rule_metrics(validation, antecedent, consequent)
                classes = {protocol["drugs"][item]["class"] for item in itemset}
                consequent_class = protocol["drugs"][consequent]["class"]
                # Una regla mixta puede seguir siendo obvia si incluye en el
                # antecedente otro fármaco de la misma clase del consecuente.
                same_class_proxy = any(protocol["drugs"][item]["class"] == consequent_class for item in antecedent)
                stable = (val["confidence"] is not None and val["lift"] is not None
                          and val["support"] >= config["min_support"]
                          and val["confidence"] >= config["min_confidence"]
                          and val["lift"] >= protocol["rule_search"]["min_lift"]
                          and val["joint_count"] >= protocol["rule_search"]["min_joint_count"])
                rule = {"configuration": config["name"], "rule": " + ".join(antecedent) + " -> " + consequent,
                        "antecedent": "|".join(antecedent), "consequent": consequent,
                        "same_class_only": len(classes) == 1,
                        "consequent_has_same_class_in_antecedent": same_class_proxy,
                        "strictly_cross_class": not same_class_proxy,
                        "passes_thresholds_in_validation": stable}
                rule.update({"discovery_" + k: v for k, v in train.items()})
                rule.update({"validation_" + k: v for k, v in val.items()})
                current_rules.append(rule)
        all_rules.extend(current_rules)
        comparisons.append({"configuration": config["name"], "min_support": config["min_support"],
                            "min_confidence": config["min_confidence"], "discovery_n": len(discovery),
                            "validation_n": len(validation), "rules_found": len(current_rules),
                            "same_class_only_rules": sum(r["same_class_only"] for r in current_rules),
                            "strictly_cross_class_rules": sum(r["strictly_cross_class"] for r in current_rules),
                            "passes_all_thresholds_in_validation": sum(r["passes_thresholds_in_validation"] for r in current_rules),
                            "apriori_candidates": candidate_audit})
    rules = pd.DataFrame(all_rules)
    if not rules.empty:
        rules = rules.sort_values(["configuration", "discovery_confidence", "discovery_joint_count"], ascending=[True, False, False]).reset_index(drop=True)
        # Recuento independiente por conjuntos de Sample Id, sin usar máscaras
        # del minador, para contrastar las métricas de cada regla emitida.
        for rule in all_rules:
            a_ids = set(validation.index)
            for item in rule["antecedent"].split("|"):
                a_ids &= set(validation.index[validation[item]])
            b_ids = set(validation.index[validation[rule["consequent"]]])
            assert len(a_ids) == rule["validation_antecedent_count"]
            assert len(a_ids & b_ids) == rule["validation_joint_count"]
    prevalence = []
    for code in items:
        prevalence.append({"item": code, "drug": protocol["drugs"][code]["spanish"],
                           "class": protocol["drugs"][code]["class"],
                           "discovery_R_count": int(discovery[code].sum()), "discovery_n": len(discovery),
                           "discovery_R_rate": float(discovery[code].mean()),
                           "validation_R_count": int(validation[code].sum()), "validation_n": len(validation),
                           "validation_R_rate": float(validation[code].mean())})
    # No elegimos configuración por los resultados de validación.
    return rules, comparisons, pd.DataFrame(prevalence), discovery, validation


def run(protocol_path=PROTOCOL, output=OUTPUT):
    protocol = json.loads(Path(protocol_path).read_text(encoding="utf-8"))
    interval_checks = verify_interval_handling()
    print("Leyendo y verificando el archivo oficial...", flush=True)
    raw = load_source(protocol)
    cohort, assays, sample_audit, audit = prepare_cohort(raw, protocol)
    rules, comparisons, prevalence, discovery, validation = mine_rules(cohort, protocol)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    cohort.to_csv(output / "cohorte.csv", index_label="sample_id")
    sample_audit.to_csv(output / "auditoria_muestras.csv", index_label="sample_id")
    assays[["sample_id", "year", "Drug Name", "item", "Sign", "MIC", "R", "status"]].to_csv(output / "ensayos_clasificados.csv", index=False)
    rules.to_csv(output / "reglas.csv", index=False)
    prevalence.to_csv(output / "prevalencia.csv", index=False)
    pd.DataFrame([{k: v for k, v in c.items() if k != "apriori_candidates"} for c in comparisons]).to_csv(output / "comparacion_configuraciones.csv", index=False)
    summary = {"generated_at_utc": datetime.now(timezone.utc).isoformat(),
               "protocol": protocol, "environment": {"python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__},
               "audit": audit, "comparison": comparisons,
               "checks": {"source_hash_verified": True, "censored_MIC_boundary_checks": interval_checks,
                          "discovery_validation_sample_ids_disjoint": True,
                          "emitted_rule_validation_counts_verified_by_set_intersections": len(rules)},
               "limitations": [
                   "Se cuentan muestras/aislados; no se pueden distinguir muestras repetidas del mismo animal.",
                   "R significa superar un corte histórico de laboratorio; por debajo de R incluye intermedios y no equivale a susceptible.",
                   "Origen urinario no confirma infección urinaria: el contexto de los cortes debe revisarse con un veterinario antes de un uso clínico.",
                   "Muestreo de vigilancia de EE. UU.; no representa prevalencia de Chile ni de CliniPets.",
                   "Validación temporal interna de la misma red, no validación clínica externa. Las reglas no demuestran causalidad.",
                   "Las reglas de la misma clase pueden reflejar fenómenos ya conocidos; se señalan por separado.",
                   "Los intervalos Wilson son descriptivos y asumen muestras independientes; no corrigen múltiples comparaciones ni dependencia por animal/laboratorio.",
                   "Las seis variables y los filtros definen una prueba de factibilidad, no un modelo clínico validado ni el proyecto semestral completo."
               ]}
    (output / "resumen.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(audit["counts"], ensure_ascii=False, indent=2))
    print(pd.DataFrame([{k: v for k, v in c.items() if k != "apriori_candidates"} for c in comparisons]).to_string(index=False))
    print(f"Resultados: {output}")
    return summary, rules, prevalence


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    run(output=args.output)
