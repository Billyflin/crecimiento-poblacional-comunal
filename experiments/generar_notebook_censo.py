"""Genera y ejecuta las celdas del notebook censal con el intérprete Python."""
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import platform
import uuid

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'experiments/estudio_censo_2024.ipynb'

def md(source):
    return {'cell_type':'markdown','id':uuid.uuid4().hex[:8],'metadata':{},'source':source.strip()+'\n'}

def py(source):
    return {'cell_type':'code','id':uuid.uuid4().hex[:8],'metadata':{},'source':source.strip()+'\n','execution_count':None,'outputs':[]}

cells = [
md('''
# Acceso digital y condiciones habitacionales: Censo 2024

**Pregunta:** ¿qué condiciones del hogar y de su vivienda aparecen asociadas
con disponer o no disponer de internet fija y computador, y cómo cambian sus
frecuencias entre regiones?

La unidad es un **hogar particular**, identificado por `(id_vivienda, id_hogar)`.
La unión con viviendas se hace por `id_vivienda`, muchos a uno. Se utilizan todos
los casos completos del país: no se recorta la base a unos miles de filas.

Fuentes: [portal oficial del INE](https://censo2024.ine.gob.cl/resultados/),
[manual y diccionario](https://censo2024.ine.gob.cl/wp-content/uploads/2025/12/manual_uso_microdatos_censo2024.pdf).
El manual documenta códigos, universos y llaves. El XLSX enlazado en el catálogo
respondió 404 durante la descarga; se conserva esa incidencia en el manifiesto.
Las bases CSV y el manual sí están disponibles y sus hashes se verifican.

Las proporciones son descriptivas del censo. No estiman pobreza, causas,
conectividad actual ni elegibilidad para beneficios.
'''),
py('''
from pathlib import Path
import hashlib
import json
import sys
import numpy as np
import pandas as pd

root = next(p for p in [Path.cwd(), *Path.cwd().parents] if (p / 'experiments/protocolo_censo_2024.json').exists())
sys.path.insert(0,str(root / 'experiments'))
import censo_2024 as study
REGENERAR = False  # True vuelve a procesar las bases CSV oficiales completas.
if REGENERAR:
    study.main()
    import verificar_recuento_censo
    verificar_recuento_censo.main()
out = root / 'results/censo_2024'
model = json.loads((out / 'modelo.json').read_text())
audit = json.loads((out / 'calidad_datos.json').read_text())
protocol = json.loads(study.PROTOCOL.read_text())
counts = np.load(out / 'conteos_perfiles.npz')['counts']
for f in model['source']['files']:
    if f.get('available',True):
        assert hashlib.file_digest((root / f['file']).open('rb'),'sha256').hexdigest() == f['sha256']
assert hashlib.file_digest(study.PROTOCOL.open('rb'),'sha256').hexdigest() == model['protocol_sha256']
print('Fuentes originales y protocolo: hashes verificados.')
print('Descarga:',model['source']['retrieved_at'])
print('Archivos oficiales:',[(f['nombre'], f.get('bytes',f.get('http_status'))) for f in model['source']['files']])
'''),
md('''
## Variables y preparación

Se filtra `tipo_operativo == 2`. Las filas de colectivos y personas en situación
de calle representan otro operativo; no se cuentan como hogares particulares.
La fuente de agua y el índice de hacinamiento provienen de la vivienda y se
asignan a cada hogar que comparte esa vivienda. No se utilizan sus componentes
para minar reglas que reproduzcan la fórmula del hacinamiento.

Área, tenencia, tipología, agua y hacinamiento pueden integrar antecedentes;
computador e internet fija son los consecuentes. Se excluye mezclar categorías
de una misma variable, usar los identificadores como características o hacer
reglas entre las dos respuestas de acceso digital. Se conservan las categorías
originales del diccionario, con etiquetas abreviadas.
'''),
py('''
variables = pd.DataFrame([{'Variable':g[2], 'Nombre':g[1], 'Categorías':len(g[3]), 'Papel':'Antecedente' if j < 5 else 'Consecuente'} for j,g in enumerate(study.GROUPS)])
print(variables.to_string(index=False))
print('\\nCategorías y códigos:')
print(pd.DataFrame(model['items'])[['source_variable','value','label']].to_string(index=False))
'''),
md('''
## Tamaño, llaves y datos faltantes

NA, -99 y cualquier código ajeno al diccionario se consideran no utilizables;
no se transforman en una respuesta «No». Se trabaja con casos completos en
las siete variables. Las exclusiones por variable se solapan y no deben sumarse.
Se comprueba la unicidad de la clave de hogar, la referencia a vivienda y la
coincidencia de región, área y operativo después de la unión.
'''),
py('''
for key in ['household_file_rows','excluded_other_operations','private_households','complete_households','excluded_incomplete','dwelling_file_rows','private_household_dwellings','duplicate_households','join_unmatched']:
    print(key,':',format(audit[key],','))
print(f"Excluidos por caso incompleto: {audit['excluded_incomplete']/audit['private_households']:.3%}")
print('\\nNo utilizables por variable, antes del filtro conjunto:')
print(pd.Series(audit['missing_by_variable']).to_string())
regional = pd.DataFrame(model['regions'])
regional['excluidos'] = regional.private_households - regional.complete_households
regional['pct_exclusion'] = regional.excluidos / regional.private_households * 100
print('\\nCalidad por región:')
print(regional.to_string(index=False))
assert counts[:,0].sum() == model['sample_count']
assert np.array_equal(counts[:,0],counts[:,1:].sum(axis=1))
'''),
md('''
## Análisis exploratorio de frecuencias y posible sesgo de exclusión

Las marginales previas al filtro permiten comparar cada variable entre quienes
la respondieron y quienes además respondieron las otras variables. Estas dos
proporciones tienen denominadores distintos. Una diferencia pequeña no descarta
sesgo en perfiles específicos, ni errores de cobertura o respuesta del censo.
'''),
py('''
rows = []
for item in model['items']:
    marginal = audit['marginals_before_complete_case_exclusion'][item['source_variable']]
    valid_n = sum(int(marginal.get(str(v),0)) for v in range(1,len(next(g[3] for g in study.GROUPS if g[0] == item['group']))+1))
    before = int(marginal.get(str(item['value']),0))
    after = study.item_count(counts[:,0].sum(axis=0),[item['code']])
    rows.append({'Categoría':item['label'],'Respuesta válida':before,'Casos completos':after,
                 'Pct respuesta válida':100*before/valid_n,'Pct casos completos':100*after/model['sample_count']})
print(pd.DataFrame(rows).round(3).to_string(index=False))
print('\\nPerfiles no vacíos:',int(np.count_nonzero(counts[:,0].sum(axis=0))))
print('Los conteos ponderados conservan exactamente el número de hogares, sin expandir una matriz one-hot.')
'''),
md('''
## Experimento y criterios previos

El protocolo se escribió antes de ejecutar la minería. Se separan viviendas,
mediante hash determinista, en 70% descubrimiento, 15% selección y 15% prueba.
Los hogares de una misma vivienda permanecen juntos. Esta partición es interna
y transversal: no es una predicción del futuro ni validación con otra fuente.

Se compara Apriori con soporte/confianza mínimos 0,5%/40% y 2%/60%; el lift de
descubrimiento debe ser >=1,2. Para una regla de dos condiciones, la confianza
debe superar en al menos 5 puntos porcentuales a cada condición aislada.
La selección usa soporte >=0,3%, lift >=1,15, al menos 1.000 antecedentes,
una confianza no inferior al umbral de su configuración menos 5 puntos, y
variación absoluta de confianza <=5 puntos respecto al descubrimiento.

Primero se compara cobertura de categorías consecuentes; luego retención de
candidatas, menor longitud media del antecedente y mayor soporte mínimo. La
configuración y el orden quedan guardados antes de calcular la prueba.
'''),
py('''
print('Hogares por partición:',model['split_counts'])
print(pd.DataFrame(model['comparison']).to_string(index=False))
print('Configuración elegida:',model['selected_configuration'])
decision = json.loads((out / 'seleccion_cerrada.json').read_text())
assert decision['rule_ids'] == [r['id'] for r in model['rules']]
print('Ambas configuraciones cubren 4 categorías y retienen todas sus candidatas. La amplia gana por menor longitud media del antecedente (1,479 frente a 1,529).')
print('Este desempate es una decisión del protocolo, no evidencia de superioridad universal.')
'''),
md('''
## Prueba interna y resultados descriptivos

Se calculan las métricas de prueba de todas las reglas elegidas sin filtrarlas
ni reordenarlas. Los soportes usan todos los hogares completos de cada partición;
la confianza usa los hogares que cumplen el antecedente y el lift compara con
la frecuencia basal del consecuente. No hay etiqueta objetivo para calcular
accuracy o F1. Tampoco se muestran intervalos de muestreo como si esta base fuera
una encuesta probabilística.
'''),
py('''
table = pd.read_csv(out / 'reglas.csv')
print(table[['rule_id','test_antecedent_count','test_joint_count','test_support','test_confidence','test_lift']].to_string(index=False))
summary = json.loads((out / 'resumen.json').read_text())
print('\\nLift mínimo en prueba:',summary['test_min_lift'])
print('Máxima diferencia de confianza entre descubrimiento y prueba:',summary['test_max_confidence_drift'])
rule = next(r for r in model['rules'] if set(r['antecedent']) == {'area:2','tipologia:1'} and r['consequent'] == 'internet:2')
print('\\nEjemplo: hogares rurales unipersonales → sin internet fija')
print(json.dumps(rule['population'],ensure_ascii=False,indent=2))
print('La ausencia de internet fija no informa por sí sola sobre internet móvil o satelital.')
'''),
md('''
## Heterogeneidad territorial y contraste independiente

Una regla nacional puede tener menor lift, o incluso lift <1, en una región.
La comparación usa la frecuencia basal del propio territorio. Este contraste
descriptivo ayuda a detectar dependencia del contexto geográfico; no es un
ajuste causal ni una demostración automática de paradoja de Simpson.

El script `verificar_recuento_censo.py` vuelve a leer los CSV y realiza un merge
pandas independiente para la regla rural/unipersonal, sin utilizar los conteos
de perfiles. Verifica antecedentes y coincidencias en Chile y las 16 regiones.
'''),
py('''
local = pd.read_csv(out / 'reglas_por_region.csv')
reversed_lift = local[(local.antecedent_count >= 100) & (local.lift < 1)]
print('Reglas nacionales con lift <1 en al menos una región:',reversed_lift.rule_id.nunique())
print(reversed_lift[['rule_id','region','antecedent_count','confidence','baseline','lift']].to_string(index=False))
verification = json.loads((out / 'verificacion_independiente.json').read_text())
verified_rule = next(r for r in model['rules'] if r['id'] == verification['rule_id'])
for region, measured in verification['by_region'].items():
    expected = verified_rule['population'] if region == '0' else verified_rule['by_region'][region]
    assert measured['antecedent_count'] == expected['antecedent_count']
    assert measured['joint_count'] == expected['joint_count']
print('\\nContraste independiente:',verification['method'])
print('Regla:',verification['rule_id'])
print('Chile:',verification['by_region']['0'])
print('Territorios comprobados:',len(verification['by_region']))
'''),
md('''
## Aplicación, alcance y reproducibilidad

La aplicación consulta antecedentes exactos de una o dos condiciones, con región
opcional. Muestra reglas nacionales seleccionadas y métricas sobre todos los
casos completos del territorio. Las consultas regionales requieren al menos
100 antecedentes. Una combinación sin reglas no indica ausencia de asociación.

Puede servir para explorar patrones de acceso digital y preparar preguntas de
investigación o comparaciones territoriales. No decide dónde intervenir ni quién
debe recibir un beneficio; no incorpora ingresos, calidad de conexión o causas.
Los millones de filas aportan respaldo descriptivo, pero no garantizan utilidad
ni novedad. La revisión de pertinencia con el profesor sigue pendiente.

Reproducción: `descargar_censo.py`, `censo_2024.py`, `verificar_recuento_censo.py`,
`generar_notebook_censo.py`, y `python -m unittest discover -s tests -v`.
Se utiliza Python 3.12, pandas 2.2.3 y NumPy 2.3.5. Cada celda se ejecutó con el
intérprete y captura de stdout al generar este notebook; no mediante un kernel
Jupyter. Los originales permanecen intactos. Los datos y sus derivados llevan
atribución INE y licencia CC BY-SA 4.0; no se intenta reidentificar personas.
''')]

def main():
    namespace = {'__name__':'__notebook__'}
    number = 0
    for cell in cells:
        if cell['cell_type'] != 'code':
            continue
        number += 1
        capture = StringIO()
        with redirect_stdout(capture):
            exec(compile(cell['source'],str(TARGET),'exec'),namespace)
        cell['execution_count'] = number
        cell['outputs'] = [{'output_type':'stream','name':'stdout','text':capture.getvalue()}]
    notebook = {'nbformat':4,'nbformat_minor':5,'cells':cells,
                'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},
                            'language_info':{'name':'python','version':platform.python_version()},
                            'execution_method':'Python exec + redirect_stdout; no Jupyter kernel'}}
    TARGET.write_text(json.dumps(notebook,ensure_ascii=False,indent=2))
    print(f'Notebook generado: {TARGET}; {number} celdas ejecutadas.')

if __name__ == '__main__':
    main()
