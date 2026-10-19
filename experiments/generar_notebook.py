"""Genera y ejecuta las celdas Python del notebook de interpretación.

Usa exec y captura stdout, sin depender de Jupyter en este entorno.
El notebook resultante también se puede abrir y ejecutar en Jupyter.
"""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "experiments/primera_prueba.ipynb"


def markdown(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip() + "\n"}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None,
            "outputs": [], "source": text.strip() + "\n"}


cells = [
    markdown("""
# Primera prueba: corresistencia en E. coli de perros

**Datos reales y públicos; proyecto exploratorio, sin uso clínico.**

La pregunta es si existen asociaciones entre resultados de laboratorio que se
mantengan en años posteriores. Usamos muestras de origen urinario de perros y
un panel común de seis antibióticos. La unidad es `Sample Id`: **no podemos
asegurar que las muestras correspondan a animales distintos**.

Este notebook muestra resultados del pipeline ya ejecutado y permite
regenerarlos. No se construyó todavía la aplicación web del proyecto.

Fuentes: [FDA Vet-LIRN](https://www.fda.gov/animal-veterinary/science-research/veterinary-laboratory-investigation-and-response-network),
[archivo oficial 2017–2024](https://www.fda.gov/media/190321/download?attachment) y
[USDA APHIS, informe 2020](https://usbiotechnologyregulation.mrp.usda.gov/sites/default/files/2020_APHIS_AMR_PilotProject_EOY_Report.pdf),
tabla 30, página impresa 35. Los cortes son históricos (CLSI VET01S 2020),
no una guía clínica vigente. La tabla presupone infección urinaria canina;
el archivo de FDA solo permite seleccionar el origen de la muestra.
"""),
    code("""
from pathlib import Path
import json
import sys
import pandas as pd

candidates = [Path.cwd(), *Path.cwd().parents]
root = next((p for p in candidates if (p / "experiments/protocolo_primera_prueba.json").is_file()), None)
if root is None:
    raise RuntimeError("Abrir Jupyter desde este proyecto o indicar root manualmente.")
sys.path.insert(0, str(root / "experiments"))
import primera_prueba as trial

# Cambiar a True para leer otra vez el XLSX oficial y regenerar el experimento.
REGENERAR = False
if REGENERAR:
    trial.run()

output = root / "results/primera_prueba"
summary = json.loads((output / "resumen.json").read_text(encoding="utf-8"))
protocol = json.loads((root / "experiments/protocolo_primera_prueba.json").read_text(encoding="utf-8"))
assert summary["protocol"] == protocol, "El protocolo cambió: regenerar resultados."
assert trial.sha256_file(root / protocol["source_file"]) == protocol["source_sha256"]
cohort = pd.read_csv(output / "cohorte.csv", dtype={"sample_id": str})
rules = pd.read_csv(output / "reglas.csv")
prevalence = pd.read_csv(output / "prevalencia.csv")
assert cohort["sample_id"].is_unique
assert len(cohort) == summary["audit"]["counts"]["included_complete_sample_ids"]
print("Datos y protocolo verificados.")
print("Pipeline ejecutado (UTC):", summary["generated_at_utc"])
print("Entorno:", summary["environment"])
"""),
    markdown("""
## 1. Población y decisiones de limpieza

Seleccionamos E. coli, especie canina, panel COMPGN1F y origen `Urine` o
`Urinary tract`, normalizando espacios y mayúsculas. En 2024 se usa la segunda
etiqueta; su agrupación es una decisión explícita del protocolo.

Excluimos muestras con metadatos contradictorios, ensayos ausentes o MIC que no
permiten decidir si superan el corte R. No contamos cada ensayo de antibiótico
como una muestra nueva. El análisis usa casos completos en los seis fármacos.
"""),
    code("""
labels = {
    "raw_assay_rows": "Ensayos en el archivo oficial",
    "raw_sample_ids": "Muestras en todo el archivo",
    "dog_ecoli_sample_ids": "Muestras caninas de E. coli",
    "urinary_sample_ids": "Origen Urine/Urinary tract, todos los paneles",
    "fixed_panel_sample_ids_before_quality_filter": "Con panel COMPGN1F",
    "excluded_conflicting_sample_ids_in_panel": "Excluidas por metadatos contradictorios",
    "excluded_incomplete_or_indeterminate": "Excluidas por ensayo ausente/MIC ambigua",
    "included_complete_sample_ids": "Muestras finales"
}
counts = summary["audit"]["counts"]
print(pd.DataFrame([{"Etapa": text, "Cantidad": counts[key]} for key, text in labels.items()]).to_string(index=False))
print("\\nMuestras finales por año:")
print(cohort.groupby("year").size().rename("n").to_string())
print("\\nLaboratorios incluidos:", summary["audit"]["included_laboratories"])
print("\\nCobertura antes de exigir casos completos:")
print(pd.DataFrame(summary["audit"]["per_drug"]).to_string(index=False))
"""),
    markdown("""
## 2. Qué significa R en esta prueba

**R = MIC inequívocamente igual o superior al corte histórico elegido.**
Por debajo de R incluye resultados intermedios: no significa automáticamente
«susceptible». Solo se aprende la presencia del ítem R, sin inferir eficacia.

La MIC censurada se conserva como intervalo. Por ejemplo, amikacina `<=16`
no permite decidir R; `=16` sí. No sustituimos el operador por una igualdad.
Ampicilina y amoxicilina/clavulánico quedan fuera por falta de cortes I/R en
la tabla elegida. No atribuimos mecanismos genéticos como BLEE.
"""),
    code("""
thresholds = pd.DataFrame([
    {"Código": c, "Antibiótico": d["spanish"], "Familia": d["class"], "Corte R (µg/mL)": d["resistant_min"]}
    for c, d in protocol["drugs"].items()
])
print(thresholds.to_string(index=False))
print("\\nCasos de borde comprobados:", trial.verify_interval_handling())
examples = [("<=", 16, 16), ("<", 16, 16), ("=", 16, 16), (">", 8, 16)]
for sign, mic, threshold in examples:
    result = trial.resistance_status(sign, mic, threshold)
    meaning = {1: "R", 0: "por debajo de R", None: "indeterminado"}[result]
    print(f"MIC {sign}{mic}, corte R >= {threshold}: {meaning}")
"""),
    markdown("""
## 3. Descubrimiento y validación temporal

Se buscan reglas con Apriori en **2017–2022**, con un máximo de dos ítems en
el antecedente y uno en el consecuente. Se miden sin reentrenar en **2023–2024**.
Los mismos `Sample Id` no aparecen en ambos períodos. Esto no impide que un
animal no identificable contribuya más de una muestra.

Comparamos dos configuraciones de soporte/confianza definidas en el protocolo.
Ambas requieren lift >=1,2 y al menos 30 coincidencias en descubrimiento. No
seleccionamos una configuración ganadora por los resultados posteriores.

- **Soporte:** fracción de todas las muestras con antecedente y consecuente.
- **Confianza:** fracción de muestras con el antecedente que también tienen el consecuente.
- **Lift:** confianza dividida por la frecuencia del consecuente en ese período.

Son métricas de asociación; no son precisión de un diagnóstico.
"""),
    code("""
discovery = cohort[cohort["year"].isin(protocol["cohort"]["discovery_years"])]
validation = cohort[cohort["year"].isin(protocol["cohort"]["validation_years"])]
assert set(discovery["sample_id"]).isdisjoint(validation["sample_id"])
print("Descubrimiento:", len(discovery), "| Validación:", len(validation))
comparison = pd.DataFrame([
    {k: v for k, v in c.items() if k != "apriori_candidates"}
    for c in summary["comparison"]
])
print(comparison.to_string(index=False))
unique_counts = rules.groupby("rule")["configuration"].nunique()
print("\\nReglas distintas:", rules["rule"].nunique())
print("Reglas presentes en ambas configuraciones:", int(unique_counts.eq(2).sum()))
print("\\nFrecuencia de R en la cohorte seleccionada, no prevalencia poblacional:")
table = prevalence[["drug", "discovery_R_count", "validation_R_count"]].copy()
table["R % 2017–2022"] = (prevalence["discovery_R_rate"] * 100).round(2)
table["R % 2023–2024"] = (prevalence["validation_R_rate"] * 100).round(2)
print(table.to_string(index=False))
"""),
    markdown("""
## 4. Reglas y su posible redundancia

Una regla con tres fármacos puede parecer cruzar familias y aun así repetir
la relación entre dos de la misma familia. Por eso marcamos si el antecedente
ya incluye un fármaco de la familia del consecuente. Consideramos estrictamente
entre familias solo las reglas sin esa relación.

Todas las reglas de esta ejecución tienen esa relación de familia. La ausencia
de otras reglas significa que no pasan estos umbrales, no que no exista ninguna
asociación en los datos.
"""),
    code("""
chosen = rules[rules["configuration"].eq("exploratoria")].copy()
table = chosen[["rule", "same_class_only", "strictly_cross_class", "discovery_joint_count", "validation_joint_count"]].copy()
table["Confianza % descubrimiento"] = (chosen["discovery_confidence"] * 100).round(2)
table["Confianza % validación"] = (chosen["validation_confidence"] * 100).round(2)
table["Lift validación"] = chosen["validation_lift"].round(2)
print(table.to_string(index=False))
print("\\nReglas estrictamente entre familias:", int(chosen["strictly_cross_class"].sum()))
"""),
    code("""
# Ejemplos fáciles de interpretar, sin seleccionar un tratamiento.
for antecedent, consequent in [("EFX", "MAR"), ("FOV", "CPD")]:
    row = chosen[(chosen["antecedent"] == antecedent) & (chosen["consequent"] == consequent)].iloc[0]
    a = protocol["drugs"][antecedent]["spanish"]
    b = protocol["drugs"][consequent]["spanish"]
    print(f"\\nR en {a} -> R en {b} (según cortes del protocolo)")
    print(f"2023–2024: {int(row['validation_joint_count'])}/{int(row['validation_antecedent_count'])} muestras con el antecedente.")
    print(f"Confianza: {row['validation_confidence']:.1%}; soporte: {row['validation_support']:.1%}; lift: {row['validation_lift']:.2f}.")
    print(f"Frecuencia basal del consecuente: {row['validation_baseline']:.1%}.")
    print(f"Intervalo Wilson descriptivo 95% de confianza: {row['validation_confidence_ci95_low']:.1%}–{row['validation_confidence_ci95_high']:.1%}.")

# Contraste independiente de los recuentos de validación de todas las reglas.
for _, row in chosen.iterrows():
    a_ids = set(validation["sample_id"])
    for item in row["antecedent"].split("|"):
        a_ids &= set(validation.loc[validation["R_" + item].eq(1), "sample_id"])
    b_ids = set(validation.loc[validation["R_" + row["consequent"]].eq(1), "sample_id"])
    assert len(a_ids) == row["validation_antecedent_count"]
    assert len(a_ids & b_ids) == row["validation_joint_count"]
print("\\nRecuentos verificados por intersección de identificadores.")
"""),
    markdown("""
## 5. Qué podemos concluir

**La prueba de factibilidad funciona:** hay suficientes muestras para un
experimento acotado, se manejan los resultados censurados y se obtienen reglas
que también aparecen en años posteriores. Las dos configuraciones producen
las mismas 12 reglas, por lo que estos umbrales todavía no diferencian alternativas.

**La utilidad adicional para CliniPets sigue abierta:** los hallazgos fuertes
de esta prueba incluyen fármacos de la misma familia y pueden reflejar relaciones
ya conocidas. Una confianza alta por sí sola no prueba novedad ni utilidad clínica.

Un alcance justificable sería un explorador educativo de corresistencia con
recuentos y procedencia. El siguiente experimento deberá estudiar reglas menos
redundantes, sensibilidad a paneles y umbrales, y estabilidad por laboratorio.
Si se modifican parámetros tras mirar esta validación, ese trabajo será
exploratorio y requerirá una evaluación nueva para afirmar generalización.

El dato es de vigilancia en EE. UU.; no estima lo que ocurre en Chile. No hay
tratamientos, desenlaces, dosis ni identificación de pacientes para predecir
qué antibiótico funcionará. La selección por casos completos puede introducir
sesgo. Los intervalos mostrados no corrigen dependencia entre muestras ni
búsqueda de múltiples reglas.

## Reproducción y archivos

Desde la raíz del proyecto:

```bash
python -m pip install -r requirements.txt
python experiments/primera_prueba.py
python experiments/generar_notebook.py
```

Se verifica el SHA-256 del archivo oficial antes de analizarlo. El protocolo
incluye fuentes, cortes, cohortes y configuraciones. Los CSV en
`results/primera_prueba/` conservan la cohorte, ensayos interpretados, auditoría,
frecuencias y reglas. `resumen.json` registra parámetros, entorno y controles.
El script de generación ejecuta estas celdas Python con captura de stdout;
no necesita un kernel Jupyter para generar este archivo.
"""),
]

namespace = {"__name__": "__main__"}
execution_count = 0
for index, cell in enumerate(cells):
    cell["id"] = f"primera-prueba-{index + 1:02d}"
    if cell["cell_type"] != "code":
        continue
    execution_count += 1
    stream = StringIO()
    with redirect_stdout(stream):
        exec(compile(cell["source"], str(TARGET) + f":cell-{index + 1}", "exec"), namespace)
    cell["execution_count"] = execution_count
    if stream.getvalue():
        cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": stream.getvalue()}]

document = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": platform.python_version()},
        "execution_method": "Python exec + redirect_stdout; pipeline fuente ejecutado previamente por CLI",
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
TARGET.write_text(json.dumps(document, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(f"Notebook generado: {TARGET}; {execution_count} celdas Python ejecutadas sin errores.")
