"""Estudio exploratorio entre familias con selección temporal y auditoría por LAB."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from primera_prueba import ROOT, apriori_counts, rule_metrics, sha256_file

PROTOCOL = ROOT / "experiments/protocolo_estudio_v1.json"
OUTPUT = ROOT / "results/estudio_v1"


def load_inputs():
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    for key in ("input_cohort", "input_protocol"):
        if sha256_file(ROOT / protocol[key]) != protocol[key + "_sha256"]:
            raise ValueError(f"Cambió {key}; revisar el protocolo antes de analizar.")
    original = json.loads((ROOT / protocol["input_protocol"]).read_text(encoding="utf-8"))
    if sha256_file(ROOT / original["source_file"]) != original["source_sha256"]:
        raise ValueError("El archivo oficial no coincide con la procedencia documentada.")
    cohort = pd.read_csv(ROOT / protocol["input_cohort"], dtype={"sample_id": str, "lab": str}).set_index("sample_id")
    assert cohort.index.is_unique and len(cohort) == 3933
    items = list(original["drugs"])
    assert cohort[["R_" + c for c in items]].isin([0, 1]).all().all()
    matrix = cohort[["R_" + c for c in items]].rename(columns=lambda c: c[2:]).astype(bool)
    splits = {name: matrix.loc[cohort["year"].isin(years)] for name, years in protocol["periods"].items()}
    assert sum(len(m) for m in splits.values()) == len(matrix)
    for name, m in splits.items():
        assert len(m) > 0
        assert all(set(m.index).isdisjoint(other.index) for n, other in splits.items() if n != name)
    return protocol, original, cohort, matrix, splits


def family_direction(antecedent, consequent, drugs):
    return " + ".join(sorted(drugs[c]["class"] for c in antecedent)) + " -> " + drugs[consequent]["class"]


def check_lab_dependence(matrix, labs, antecedent, consequent, rule_id):
    rows, loo_rows = [], []
    all_labs = sorted(labs.loc[matrix.index].unique())
    for lab in all_labs:
        mask = labs.loc[matrix.index].eq(lab)
        local = rule_metrics(matrix.loc[mask], antecedent, consequent)
        rows.append({"rule_id": rule_id, "lab": str(lab), **local})
        remaining = rule_metrics(matrix.loc[~mask], antecedent, consequent)
        loo_rows.append({"rule_id": rule_id, "excluded_lab": str(lab), **remaining})
    valid_lifts = [r["lift"] for r in loo_rows if r["lift"] is not None]
    antecedent_total = sum(r["antecedent_count"] for r in rows)
    summary = {
        "discovery_labs_total": len(all_labs),
        "labs_with_at_least_5_antecedents": sum(r["antecedent_count"] >= 5 for r in rows),
        "largest_lab_antecedent_share": max(r["antecedent_count"] for r in rows) / antecedent_total,
        "leave_one_lab_out_min_lift": min(valid_lifts) if len(valid_lifts) == len(loo_rows) else None,
        "leave_one_lab_out_min_confidence": min(r["confidence"] for r in loo_rows if r["confidence"] is not None),
    }
    return summary, rows, loo_rows


def passes_common_selection(metrics, lab_summary, protocol):
    c = protocol["selection"]["common_2022_thresholds"]
    l = protocol["selection"]["lab_thresholds_on_discovery"]
    temporal = (metrics["confidence"] is not None and metrics["lift"] is not None
                and metrics["confidence"] >= c["min_confidence"]
                and metrics["lift"] >= c["min_lift"]
                and metrics["joint_count"] >= c["min_joint_count"]
                and metrics["antecedent_count"] >= c["min_antecedent_count"])
    lab = (lab_summary["leave_one_lab_out_min_lift"] is not None
           and lab_summary["leave_one_lab_out_min_lift"] >= l["min_leave_one_lab_out_lift"]
           and lab_summary["labs_with_at_least_5_antecedents"] >= l["min_labs_with_5_antecedent_samples"])
    return bool(temporal), bool(lab)


def run():
    protocol, original, cohort, matrix, splits = load_inputs()
    drugs = original["drugs"]
    items = list(drugs)
    search = protocol["search"]
    discovery, selection = splits["discovery"], splits["selection"]
    lab_cache, details, leave_one_out = {}, [], []
    rules, comparison = [], []
    for config in search["configurations"]:
        frequent, candidate_audit = apriori_counts(discovery, items, config["min_support"], search["max_itemset_size"])
        config_rules = []
        for itemset, count in frequent.items():
            if len(itemset) < 2 or count < search["min_joint_count"]:
                continue
            for consequent in itemset:
                antecedent = tuple(c for c in itemset if c != consequent)
                families = [drugs[c]["class"] for c in antecedent]
                if drugs[consequent]["class"] in families or len(set(families)) != len(families):
                    continue
                d = rule_metrics(discovery, antecedent, consequent)
                if (d["antecedent_count"] < search["min_antecedent_count"]
                        or d["confidence"] < config["min_confidence"] or d["lift"] < search["min_lift"]):
                    continue
                identifier = "-".join(antecedent) + "__" + consequent
                if identifier not in lab_cache:
                    lab_info, local, loo = check_lab_dependence(discovery, cohort["lab"], antecedent, consequent, identifier)
                    lab_cache[identifier] = lab_info
                    details.extend(local)
                    leave_one_out.extend(loo)
                s = rule_metrics(selection, antecedent, consequent)
                temporal, lab = passes_common_selection(s, lab_cache[identifier], protocol)
                rule = {"id": identifier, "configuration": config["name"],
                        "antecedent": list(antecedent), "consequent": consequent,
                        "family_direction": family_direction(antecedent, consequent, drugs),
                        "discovery": d, "selection": s, "lab_audit": lab_cache[identifier],
                        "passes_selection_2022": temporal, "passes_lab_checks": lab,
                        "eligible": temporal and lab}
                config_rules.append(rule)
        eligible = [r for r in config_rules if r["eligible"]]
        comparison.append({"configuration": config["name"], "min_support": config["min_support"],
                           "min_confidence": config["min_confidence"], "candidate_rules": len(config_rules),
                           "passes_2022": sum(r["passes_selection_2022"] for r in config_rules),
                           "eligible_rules": len(eligible),
                           "eligible_family_directions": len({r["family_direction"] for r in eligible}),
                           "retention_rate": len(eligible) / len(config_rules) if config_rules else 0,
                           "apriori_candidates": candidate_audit})
        rules.extend(config_rules)

    ranked = sorted(comparison, key=lambda c: (c["eligible_family_directions"], c["retention_rate"], c["configuration"] == "conservadora"), reverse=True)
    winner = ranked[0]["configuration"] if ranked and ranked[0]["eligible_rules"] else None
    published = [r for r in rules if r["configuration"] == winner and r["eligible"]]
    # Preferir reglas simples y ordenarlas con evidencia anterior a 2023.
    published.sort(key=lambda r: (len(r["antecedent"]), -r["selection"]["confidence_ci95_low"], -r["discovery"]["joint_count"], r["id"]))

    # La selección está cerrada antes de calcular confirmación; no se usa para
    # filtrar reglas, escoger configuración ni ordenar la aplicación.
    for rule in rules:
        rule["confirmation"] = rule_metrics(splits["confirmation"], rule["antecedent"], rule["consequent"])
        rule["confirmation_by_year"] = {
            str(year): rule_metrics(matrix.loc[cohort["year"].eq(year)], rule["antecedent"], rule["consequent"])
            for year in protocol["periods"]["confirmation"]}
        for stage in ("discovery", "selection", "confirmation"):
            m = splits[stage]
            a_ids = set(m.index)
            for code in rule["antecedent"]:
                a_ids &= set(m.index[m[code]])
            b_ids = set(m.index[m[rule["consequent"]]])
            assert len(a_ids) == rule[stage]["antecedent_count"]
            assert len(a_ids & b_ids) == rule[stage]["joint_count"]

    aggregate = []
    for year, group in cohort.groupby("year"):
        for code, drug in drugs.items():
            aggregate.append({"year": int(year), "item": code, "drug": drug["spanish"],
                              "sample_count": len(group), "R_count": int(group["R_" + code].sum()),
                              "R_rate": float(group["R_" + code].mean())})
    model = {
        "title": "Corresistencia canina",
        "subtitle": "Explorador de asociaciones entre familias de antibióticos",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "exploratory", "selected_configuration": winner,
        "selection_explanation": "Se comparan direcciones entre familias y proporción de reglas que cumplen los mismos controles de 2022 y de laboratorio; desempate conservador.",
        "sample_count": len(cohort), "laboratories": int(cohort["lab"].nunique()),
        "periods": {stage: {"years": protocol["periods"][stage], "n": len(m)} for stage, m in splits.items()},
        "drugs": [{"code": code, **drug} for code, drug in drugs.items()],
        "rules": published,
        "comparison": [{k: v for k, v in c.items() if k != "apriori_candidates"} for c in comparison],
        "source": {"title": "FDA Vet-LIRN 2017–2024", "url": original["source_page"], "sha256": original["source_sha256"]},
        "threshold_reference": original["threshold_reference"],
        "limitations": [
            "R usa cortes históricos de laboratorio de 2020; no predice eficacia ni indica un tratamiento.",
            "Origen urinario no confirma infección urinaria; aplicar estos cortes es una hipótesis metodológica.",
            "Se cuentan muestras, no perros distintos. No hay identificación de pacientes ni desenlaces.",
            "Datos de vigilancia de EE. UU.; no representan Chile ni registros de CliniPets.",
            protocol["evaluation_status"],
            "Excluir una familia compartida reduce redundancia; no demuestra que la asociación sea novedosa o útil clínicamente.",
            "Los intervalos Wilson son descriptivos: no corrigen dependencia entre muestras ni comparaciones múltiples.",
            "La auditoría por laboratorio es una comprobación de sensibilidad; no una validación clínica externa."
        ],
    }
    OUTPUT.mkdir(parents=True, exist_ok=True)
    def save_json(name, value):
        (OUTPUT / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    save_json("modelo.json", model)
    save_json("reglas_completas.json", rules)
    save_json("resumen.json", {"protocol": protocol, "comparison": comparison,
                               "winner": winner, "published_rules": len(published),
                               "checks": {"hashes_verified": True, "disjoint_periods": True,
                                          "counts_verified_by_id_intersection": len(rules) * 3}})
    flat_rules = []
    for rule in rules:
        row = {"rule_id": rule["id"], "configuration": rule["configuration"],
               "antecedent": "|".join(rule["antecedent"]), "consequent": rule["consequent"],
               "family_direction": rule["family_direction"], "eligible": rule["eligible"]}
        for stage in ("discovery", "selection", "confirmation"):
            row.update({stage + "_" + key: value for key, value in rule[stage].items()})
        row.update(rule["lab_audit"])
        flat_rules.append(row)
    pd.DataFrame(flat_rules).to_csv(OUTPUT / "reglas.csv", index=False)
    pd.DataFrame(details).to_csv(OUTPUT / "reglas_por_laboratorio.csv", index=False)
    pd.DataFrame(leave_one_out).to_csv(OUTPUT / "exclusion_de_laboratorio.csv", index=False)
    pd.DataFrame(aggregate).to_csv(OUTPUT / "frecuencias_por_anio.csv", index=False)
    pd.DataFrame(model["comparison"]).to_csv(OUTPUT / "comparacion.csv", index=False)
    print(pd.DataFrame(model["comparison"]).to_string(index=False))
    print("Configuración seleccionada:", winner, "| Reglas para aplicación:", len(published))
    for r in published:
        print(r["id"], "2022", r["selection"]["joint_count"], "/", r["selection"]["antecedent_count"],
              "2023–2024", r["confirmation"]["joint_count"], "/", r["confirmation"]["antecedent_count"],
              "lift", round(r["confirmation"]["lift"], 2))
    return model


if __name__ == "__main__":
    run()
