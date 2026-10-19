"""Construye el notebook del estudio ejecutando sus celdas con Python."""

from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import platform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "experiments/estudio_corresistencia.ipynb"


def md(source):
    return {"cell_type": "markdown", "source": source.strip() + "\n", "metadata": {}}


def py(source):
    return {"cell_type": "code", "source": source.strip() + "\n", "metadata": {},
            "execution_count": None, "outputs": []}


cells = [
    md("""
# Estudio de corresistencia entre familias de antibióticos

Este experimento amplía la prueba preliminar conservando su cohorte de E. coli
canina de origen urinario y sus seis variables. La pregunta es qué reglas entre
familias superan controles temporales y de laboratorio y pueden mostrarse en un
explorador educativo. Excluir fármacos de la misma familia reduce redundancia;
**no demuestra novedad clínica**.

Los parámetros y criterios se escribieron en `protocolo_estudio_v1.json` antes
de ejecutar este estudio. Todos los años ya se habían inspeccionado en la prueba
preliminar: **la comprobación de 2023–2024 es exploratoria, no una prueba inédita**.

Se mantienen las fuentes [FDA Vet-LIRN](https://www.fda.gov/animal-veterinary/science-research/veterinary-laboratory-investigation-and-response-network)
y [USDA APHIS 2020](https://usbiotechnologyregulation.mrp.usda.gov/sites/default/files/2020_APHIS_AMR_PilotProject_EOY_Report.pdf).
R usa los cortes históricos del protocolo original. Por debajo de R incluye
intermedios y no equivale a susceptible. No hay predicción de tratamiento.
"""),
    py("""
from pathlib import Path
import json
import sys
import pandas as pd

root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / "experiments/protocolo_estudio_v1.json").exists())
sys.path.insert(0, str(root / "experiments"))
import estudio_corresistencia as study

REGENERAR = False  # True vuelve a ejecutar el estudio desde la cohorte verificada.
if REGENERAR:
    study.run()
protocol, original, cohort, matrix, splits = study.load_inputs()
output = root / "results/estudio_v1"
summary = json.loads((output / "resumen.json").read_text(encoding="utf-8"))
model = json.loads((output / "modelo.json").read_text(encoding="utf-8"))
rules = json.loads((output / "reglas_completas.json").read_text(encoding="utf-8"))
assert summary["protocol"] == protocol
print("Hashes de cohorte, protocolo original y archivo oficial verificados.")
print("Muestras:", len(cohort), "| Laboratorios:", cohort["lab"].nunique())
print("Estado de la evaluación:", protocol["evaluation_status"])
"""),
    md("""
## Separación temporal y alternativas

Descubrimiento usa 2017–2021; selección de configuración usa 2022. La publicación
se decide con esos datos y luego se calculan métricas de 2023–2024 sin filtrar
ni ordenar por ellas. Los identificadores de muestra son disjuntos entre etapas.
No podemos descartar que un animal contribuya muestras en varias etapas.

Apriori admite conjuntos de hasta tres ítems. El consecuente pertenece a una
familia ausente del antecedente y el antecedente tiene como máximo un fármaco
por familia. Se exigen al menos 20 coincidencias y 30 antecedentes en descubrimiento.
"""),
    py("""
print(pd.DataFrame([
    {"Etapa": name, "Años": ", ".join(map(str, protocol["periods"][name])), "Muestras": len(part)}
    for name, part in splits.items()
]).to_string(index=False))
print("\\nConfiguraciones de búsqueda:")
print(pd.DataFrame(protocol["search"]["configurations"]).to_string(index=False))
print("\\nCriterios comunes para evaluar 2022:")
print(json.dumps(protocol["selection"]["common_2022_thresholds"], indent=2))
print("\\nControles de laboratorio en descubrimiento:")
print(json.dumps(protocol["selection"]["lab_thresholds_on_discovery"], indent=2))
"""),
    md("""
## Comparación y elección de configuración

Primero se compara la cantidad de direcciones entre familias respaldadas por
reglas elegibles. Luego, la proporción de candidatas que cumple los controles.
Se resuelve un empate completo con la configuración conservadora. Estos criterios
valoran cobertura de patrones y estabilidad, en vez de maximizar confianza sola.

Una regla es elegible si en 2022 tiene confianza >=0,50, lift >=1,5, al menos
8 coincidencias y 10 antecedentes; además, al menos 3 laboratorios aportan
5 antecedentes cada uno en descubrimiento y el lift al excluir cada laboratorio
permanece >=1,2. Los umbrales son decisiones exploratorias, no garantías clínicas.
"""),
    py("""
comparison = pd.DataFrame(model["comparison"])
print(comparison.to_string(index=False))
print("\\nConfiguración elegida:", summary["winner"])
print("Reglas publicadas:", summary["published_rules"])
rows = [{"Regla": r["id"], "Configuración": r["configuration"],
         "Pasa 2022": r["passes_selection_2022"], "Pasa laboratorios": r["passes_lab_checks"],
         "Elegible": r["eligible"], "Confianza 2022": r["selection"]["confidence"],
         "Coincidencias 2022": r["selection"]["joint_count"]} for r in rules]
print("\\nSe conservan también las candidatas descartadas:")
print(pd.DataFrame(rows).to_string(index=False))
"""),
    md("""
## Resultados seleccionados y comprobación posterior

Las dos reglas publicadas parten de gentamicina y terminan en enrofloxacino o
marbofloxacino. Representan **una misma dirección entre familias**; los consecuentes
pertenecen a la misma familia, de modo que no son dos hallazgos independientes.

La confianza de selección se apoya en solo 18 antecedentes de 2022. Se muestran
los recuentos y los intervalos Wilson para hacer visible esa incertidumbre.
Los intervalos son descriptivos y no corrigen dependencia ni comparaciones múltiples.
"""),
    py("""
for rule in model["rules"]:
    print("\\n", rule["id"], "|", rule["family_direction"])
    for stage in ["discovery", "selection", "confirmation"]:
        m = rule[stage]
        print(f"{stage}: {m['joint_count']}/{m['antecedent_count']}; confianza {m['confidence']:.1%}; soporte {m['support']:.1%}; lift {m['lift']:.2f}; intervalo {m['confidence_ci95_low']:.1%}–{m['confidence_ci95_high']:.1%}")
    for year, m in rule["confirmation_by_year"].items():
        print(f"{year}: {m['joint_count']}/{m['antecedent_count']}; confianza {m['confidence']:.1%}")
"""),
    md("""
## Sensibilidad al laboratorio

Se calcula la regla por laboratorio y se vuelve a calcular en descubrimiento
excluyendo cada laboratorio. Esto comprueba si la asociación agrupada desaparece
al retirar un centro. No asegura estabilidad clínica, ni que todos los laboratorios
observen el mismo patrón. Muchos centros tienen pocos antecedentes.
"""),
    py("""
local = pd.read_csv(output / "reglas_por_laboratorio.csv", dtype={"lab": str})
for rule in model["rules"]:
    print("\\n", rule["id"])
    print(json.dumps(rule["lab_audit"], ensure_ascii=False, indent=2))
    table = local[(local["rule_id"] == rule["id"]) & (local["antecedent_count"] >= 5)]
    print(table[["lab", "n", "antecedent_count", "joint_count", "confidence", "lift"]].to_string(index=False))

# Contraste independiente de los recuentos publicados, a partir de los IDs.
for rule in model["rules"]:
    for stage, part in splits.items():
        a_ids = set(part.index)
        for code in rule["antecedent"]:
            a_ids &= set(part.index[part[code]])
        b_ids = set(part.index[part[rule["consequent"]]])
        assert len(a_ids) == rule[stage]["antecedent_count"]
        assert len(a_ids & b_ids) == rule[stage]["joint_count"]
print("\\nRecuentos publicados comprobados por intersección de Sample Id.")
"""),
    md("""
## Integración en la aplicación

La aplicación carga `results/estudio_v1/modelo.json`, permite seleccionar ítems
R y devuelve reglas cuyos antecedentes están en esa selección. Omite consecuentes
que el usuario ya seleccionó. No interpreta ítems no marcados como susceptibles.
Una consulta sin reglas comunica ausencia de reglas seleccionadas, no ausencia
de resistencia ni de asociaciones en general.

Se muestran confianza, soporte, lift, recuentos, intervalos, períodos, procedencia
y limitaciones. Solo se ofrecen reglas de la configuración elegida que cumplen
los controles. No se almacenan registros de pacientes.

Reproducir desde la raíz del proyecto:

```bash
python experiments/primera_prueba.py
python experiments/estudio_corresistencia.py
python experiments/generar_notebook_estudio.py
python -m unittest discover -s tests -v
python app/server.py --port 8787
```

La selección es prometedora para un explorador académico y sigue teniendo respaldo
limitado. El proyecto requiere revisión de Pablo Valenzuela y las especificaciones
de las entregas. Una futura evaluación externa y nuevos datos serían necesarios
para sostener generalización fuera de esta red de vigilancia.
"""),
]

namespace = {"__name__": "__main__"}
count = 0
for index, cell in enumerate(cells):
    cell["id"] = f"estudio-{index + 1:02d}"
    if cell["cell_type"] != "code":
        continue
    count += 1
    stream = StringIO()
    with redirect_stdout(stream):
        exec(compile(cell["source"], str(TARGET) + f":cell-{index + 1}", "exec"), namespace)
    cell["execution_count"] = count
    cell["outputs"] = [{"output_type": "stream", "name": "stdout", "text": stream.getvalue()}]

notebook = {"cells": cells, "nbformat": 4, "nbformat_minor": 5,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python", "version": platform.python_version()},
                         "execution_method": "Python exec + redirect_stdout; estudio ejecutado previamente por CLI"}}
TARGET.write_text(json.dumps(notebook, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
print(f"Notebook generado: {TARGET}; {count} celdas ejecutadas sin errores.")
