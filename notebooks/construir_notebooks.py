"""Construye y ejecuta los dos notebooks de la entrega final.

Uso (desde la raíz del repositorio):
    .venv/bin/python notebooks/construir_notebooks.py
"""
from pathlib import Path

import nbformat
from nbclient import NotebookClient

HERE = Path(__file__).resolve().parent
md = nbformat.v4.new_markdown_cell
code = nbformat.v4.new_code_cell

SETUP = r'''
from pathlib import Path
import json
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

ROOT = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()
FIG = ROOT / 'results/entrega'
FIG.mkdir(parents=True, exist_ok=True)
pd.set_option('display.max_columns', 30)
pd.set_option('display.width', 160)
plt.rcParams.update({'figure.dpi': 110, 'axes.spines.top': False, 'axes.spines.right': False})

perfiles = pd.read_csv(ROOT / 'results/crecimiento_v2/perfiles_censales.csv')
calidad = json.loads((ROOT / 'results/crecimiento_v2/calidad_datos.json').read_text())
UMBRAL = 0.01

def tasa_anual(p0, p1, anios):
    return (np.asarray(p1, float) / np.asarray(p0, float)) ** (1 / anios) - 1

def anio(y):
    return perfiles[perfiles.year == y].set_index('code').sort_index()
'''

# ---------------------------------------------------------------- EDA
eda = [
md('''# 1. Análisis exploratorio: crecimiento poblacional comunal en Chile

**Técnica asignada: clasificación.**

**Pregunta.** Con lo que se sabe de una comuna al inicio de un período intercensal (su tamaño, su estructura de edades y cuánto creció antes), ¿se puede clasificar si crecerá **al menos 1% anual** durante el período siguiente?

- Clase positiva (1): tasa anual ≥ 1%, es decir, *crecimiento alto*.
- Clase negativa (0): tasa anual < 1%, que incluye las comunas estancadas o que pierden población.

Tasa anual = (P_final / P_inicial)^(1/años) − 1. El umbral de 1% es una decisión del proyecto: está cerca de la mediana de las tasas y separa con claridad a las comunas que crecen de las estancadas o en declive.

Este notebook documenta la procedencia de los datos, su calidad, sus características y patrones, y las decisiones de limpieza, transformación y selección de variables. El experimento comparativo está en `02_experimento_clasificacion.ipynb`.'''),
code(SETUP),
md('''## 1.1 Procedencia

Todos los datos son **tabulados oficiales del INE** (Instituto Nacional de Estadísticas de Chile):

| Censo | Fuente | Archivo en `data/raw/ine/crecimiento/` |
|---|---|---|
| 1992 | REDATAM INE, población por comuna y edad | `edad_residencia_1992.html` |
| 2002 | REDATAM INE, población por comuna y edad (DPA actualizada) | `edad_residencia_2002.html` |
| 2017 | REDATAM INE, residentes habituales por comuna y edad | `edad_residencia_2017.html`, `residentes_2017.xlsx` |
| 2024 | Resultados oficiales Censo 2024 | `poblacion_2024.xlsx` |

Los archivos crudos están versionados en el repositorio junto con su manifiesto de descarga (URL, fecha y hash SHA-256). Los scripts `experiments/descargar_crecimiento.py` y `experiments/descargar_fuentes_v2.py` los vuelven a descargar. `experiments/crecimiento_censal.py` y `experiments/crecimiento_v2.py` construyen la tabla integrada `results/crecimiento_v2/perfiles_censales.csv`, que es la que se analiza aquí.'''),
code(r'''fuentes = json.loads((ROOT / 'data/raw/ine/crecimiento/fuentes.json').read_text())
print('Editor:', fuentes['publisher'], '| licencia:', fuentes['license'], '| descargado:', fuentes['retrieved_at'][:10])
pd.DataFrame([{'archivo': f['file'], 'base': f.get('params', {}).get('BASE', ''), 'url': f['url'],
               'sha256': str(f.get('sha256', ''))[:16] + '…'} for f in fuentes['files']])'''),
md('''## 1.2 Estructura de la tabla integrada

Cada fila es una **comuna en un año censal**, con población total, menores de 15 años (`young`) y personas de 65 o más (`old`).'''),
code(r'''display(perfiles.head())
print(perfiles.dtypes)
display(perfiles.groupby('year').agg(comunas=('code', 'nunique'), poblacion_total=('population', 'sum'),
                                     mediana_comuna=('population', 'median'), minimo=('population', 'min'),
                                     maximo=('population', 'max')))'''),
md('''## 1.3 Calidad de los datos

Se revisan valores faltantes, duplicados, coherencia interna, comunas excluidas y concordancia con una publicación independiente del INE.'''),
code(r'''chequeos = {
    'valores faltantes': int(perfiles.isna().sum().sum()),
    'filas duplicadas (code, year)': int(perfiles.duplicated(['code', 'year']).sum()),
    'menores + mayores > población': int((perfiles.young + perfiles.old > perfiles.population).sum()),
    'población <= 0': int((perfiles.population <= 0).sum()),
    'comunas incluidas': calidad['included_communes'],
    'comunas excluidas': len(calidad['exclusions']),
    'comunas contrastadas en 2017 con publicación independiente': calidad['independent_2017_check']['compared_communes'],
    'diferencias encontradas en ese contraste': len(calidad['independent_2017_check']['differences']),
}
pd.Series(chequeos, name='resultado').to_frame()'''),
md('''No hay faltantes, duplicados ni conteos incoherentes. El contraste con la publicación independiente del INE de residentes 2017 no encontró diferencias.

El principal problema de calidad es **territorial**: entre 1992 y 2024 se crearon comunas y se movieron límites. Si se comparara una comuna cuyo territorio cambió, se mediría un "crecimiento" falso. Por eso se excluyen **30 comunas** afectadas (ver la tabla siguiente). Temuco y Padre Las Casas se recuperaron con fuentes legales y la publicación del INE con DPA actualizada; de Padre Las Casas no se usa el dato de 1992.'''),
code(r'''excl = pd.DataFrame(calidad['exclusions'])[['code', 'name', 'region', 'reason']]
display(excl.groupby('reason').name.apply(lambda s: ', '.join(s)).to_frame('comunas'))
print('Faltantes por año (comunas sin dato):')
print(316 - perfiles.groupby('year').code.nunique())'''),
md('''## 1.4 Construcción de la variable objetivo

Se calculan las tasas anuales de los tres períodos intercensales.'''),
code(r'''p92, p02, p17, p24 = anio(1992), anio(2002), anio(2017), anio(2024)
tasas = pd.DataFrame({
    '1992-2002': tasa_anual(p92.population, p02.population.reindex(p92.index), 10),
}, index=p92.index).reindex(p02.index)
tasas['2002-2017'] = tasa_anual(p02.population, p17.population, 15)
tasas['2017-2024'] = tasa_anual(p17.population, p24.population, 7)
tasas.insert(0, 'region', p02.region)
tasas.insert(0, 'comuna', p02.name)
display(tasas.describe().T)
balance = (tasas[['1992-2002', '2002-2017', '2017-2024']] >= UMBRAL).apply(lambda c: c[tasas[c.name].notna()].value_counts()).T
balance.columns = ['< 1% (0)', '≥ 1% (1)']
balance['% positiva'] = (100 * balance['≥ 1% (1)'] / balance.sum(axis=1)).round(1)
balance'''),
code(r'''fig, axes = plt.subplots(1, 3, figsize=(13, 3.4), sharey=True)
for ax, col in zip(axes, ['1992-2002', '2002-2017', '2017-2024']):
    v = 100 * tasas[col].dropna().clip(-4, 8)
    ax.hist(v, bins=40, color='#4C72B0', alpha=.85)
    ax.axvline(100 * UMBRAL, color='#C44E52', ls='--', label='umbral 1%')
    ax.set_title(f'Tasa anual {col}')
    ax.set_xlabel('% anual (recortado a [-4, 8])')
axes[0].set_ylabel('comunas'); axes[0].legend()
plt.tight_layout(); plt.savefig(FIG / 'eda_distribucion_tasas.png', bbox_inches='tight'); plt.show()'''),
md('''**Lectura.**
- El **balance de clases cambia** entre períodos: 40% de comunas positivas en 1992–2002, **31% en 2002–2017** (el período de entrenamiento) y **48% en 2017–2024** (el de prueba). Por ese desbalance moderado y cambiante, el experimento usa **F1 macro** y pesos de clase balanceados en lugar de la exactitud simple.
- Las tasas se concentran entre 0 y 2% anual. Muchas comunas quedan cerca del umbral, lo que hace difícil clasificarlas.
- Hay colas de comunas en fuerte declive y otras de crecimiento muy rápido.'''),
md('''## 1.5 Patrones relevantes

### Persistencia del crecimiento
¿Las comunas que crecieron en el período anterior siguen creciendo?'''),
code(r'''fig, axes = plt.subplots(1, 2, figsize=(11, 4.2))
for ax, (a, b) in zip(axes, [('1992-2002', '2002-2017'), ('2002-2017', '2017-2024')]):
    d = tasas[[a, b]].dropna() * 100
    d = d.clip(-4, 8)
    ax.scatter(d[a], d[b], s=10, alpha=.5)
    ax.axvline(1, color='#C44E52', ls='--', lw=1); ax.axhline(1, color='#C44E52', ls='--', lw=1)
    r = tasas[[a, b]].corr().iloc[0, 1]
    ax.set_title(f'{a} vs {b}  (r = {r:.2f})'); ax.set_xlabel(f'% anual {a}'); ax.set_ylabel(f'% anual {b}')
plt.tight_layout(); plt.savefig(FIG / 'eda_persistencia.png', bbox_inches='tight'); plt.show()

for a, b in [('1992-2002', '2002-2017'), ('2002-2017', '2017-2024')]:
    d = tasas[[a, b]].dropna()
    t = pd.crosstab(d[a] >= UMBRAL, d[b] >= UMBRAL, rownames=[f'{a} ≥1%'], colnames=[f'{b} ≥1%'])
    display(t)'''),
md('''El crecimiento pasado está **correlacionado** con el siguiente (Spearman 0,65 entre 1992–2002 y 2002–2017), pero muchas comunas cambian de clase. Entre 2002–2017 y 2017–2024, **77 comunas pasaron a crecer ≥1%** aunque antes no lo hacían, y 24 dejaron de hacerlo. Esto justifica usar el crecimiento previo como variable, y también compararse contra una línea base de *continuidad* (predecir la misma clase del período anterior).

### Tamaño y estructura etaria'''),
code(r'''base = p02.copy()
base['tasa_siguiente'] = tasas['2002-2017']
base['log_pob'] = np.log10(base.population)
base['prop_menores_15'] = base.young / base.population
base['prop_65_mas'] = base.old / base.population
base['clase'] = (base.tasa_siguiente >= UMBRAL).astype(int)
fig, axes = plt.subplots(1, 3, figsize=(13, 3.6))
for ax, col, lab in zip(axes, ['log_pob', 'prop_menores_15', 'prop_65_mas'],
                        ['log10 población 2002', 'proporción < 15 años, 2002', 'proporción 65+, 2002']):
    for c, color, name in [(0, '#8C8C8C', '< 1%'), (1, '#4C72B0', '≥ 1%')]:
        ax.hist(base.loc[base.clase == c, col], bins=25, alpha=.6, color=color, label=name, density=True)
    ax.set_xlabel(lab)
axes[0].legend(title='crecimiento 2002-2017'); axes[0].set_ylabel('densidad')
plt.tight_layout(); plt.savefig(FIG / 'eda_variables_por_clase.png', bbox_inches='tight'); plt.show()
display(base.groupby('clase')[['log_pob', 'prop_menores_15', 'prop_65_mas']].median())'''),
md('''- La **proporción de 65 años o más** es la variable de un solo censo que más separa las clases: las comunas envejecidas crecen menos (Spearman −0,25 con la tasa siguiente).
- El **tamaño** tiene una relación positiva pero débil (Spearman 0,18).
- La proporción de menores de 15 años casi no separa las clases (0,03).
- Ninguna variable de un solo censo es tan informativa como el **crecimiento previo** (0,65). Esto anticipa que el modelo sin historia rendirá poco.

### Envejecimiento general y diferencias regionales'''),
code(r'''edad = perfiles.groupby('year')[['population', 'young', 'old']].sum()
edad['% < 15'] = 100 * edad.young / edad.population
edad['% 65+'] = 100 * edad.old / edad.population
display(edad[['population', '% < 15', '% 65+']].round(1))
reg = tasas.groupby('region')[['2002-2017', '2017-2024']].apply(lambda d: (d >= UMBRAL).mean() * 100).round(0)
reg.columns = ['% comunas ≥1% 2002-17', '% comunas ≥1% 2017-24']
reg.sort_values('% comunas ≥1% 2017-24', ascending=False)'''),
md('''**Cambio de régimen regional.** El crecimiento se desplazó entre períodos. En Ñuble, el 11% de las comunas creció ≥1% en 2002–2017 y el 84% en 2017–2024; algo parecido ocurrió en Maule, O'Higgins y Los Ríos. En la Región Metropolitana la proporción bajó de 54% a 40%. Un modelo entrenado con un único período no puede anticipar ese desplazamiento, lo que será la principal fuente de error.'''),
code(r'''corr = base[['log_pob', 'prop_menores_15', 'prop_65_mas', 'tasa_siguiente']].copy()
corr['crecimiento_previo'] = tasas['1992-2002']
corr.corr(method='spearman').round(2)'''),
md('''## 1.6 Decisiones de limpieza, transformación y selección de variables

**Limpieza**
- Se excluyen 30 comunas con cambios territoriales (creaciones o modificaciones de límites) entre censos: compararlas mediría cambios de límites, no crecimiento. No se imputan poblaciones ni se reparten habitantes por conjetura.
- Se usa la población **residente habitual** con comuna identificada, la definición comparable entre censos. No se imputan personas sin comuna conocida.

**Transformación**
- Tasa **anualizada** (geométrica), porque los períodos duran 10, 15 y 7 años y solo así son comparables.
- **Logaritmo** de la población, porque va de 27 a más de 500 mil habitantes y el logaritmo reduce la asimetría.
- **Proporciones** de menores de 15 años y de 65 o más, en lugar de conteos, para separar la estructura etaria del tamaño.
- Objetivo **binario** con umbral 1%: la pregunta práctica es si una comuna crecerá de forma sostenida, no el número exacto de habitantes.

**Selección de variables (candidatas)**
1. `log_poblacion` al inicio del período.
2. `proporcion_menores_15` al inicio.
3. `proporcion_65_mas` al inicio.
4. `crecimiento_previo`: la tasa anual del período anterior.
5. y 6. Cambio anual de las dos proporciones etarias en el período anterior.

**Excluidas a propósito:** el código y el nombre de la comuna (son identificadores, no información), la región (con tan pocos casos por región se memorizaría) y la población final o la tasa del propio período (eso es la respuesta, y usarlas sería *filtración de información*). Todas las entradas usan solo censos **anteriores o iguales** al inicio del período.

El experimento decide si las variables 5 y 6 aportan.'''),
]

# ---------------------------------------------------------------- EXPERIMENT
exp = [
md('''# 2. Experimento comparativo: clasificación de crecimiento ≥ 1% anual

## Diseño

| Paso | Datos | n |
|---|---|---|
| Entradas del entrenamiento | censos 1992 y 2002 | 314 comunas |
| Respuesta del entrenamiento | crecimiento 2002–2017 | 314 |
| Selección del modelo | validación cruzada estratificada de 5 particiones sobre el entrenamiento | 314 |
| Evaluación temporal (prueba) | entradas de 2002 y 2017, respuesta 2017–2024 | 314 |

El modelo se elige **solo con la validación cruzada** y luego se evalúa en un período futuro (2017–2024) que no se usó para entrenar. Las mismas 314 comunas aparecen en ambas etapas, pero cada etapa corresponde a un período distinto.

**Métrica principal: F1 macro**, que promedia el F1 de ambas clases con igual peso. Las clases están casi balanceadas (164 frente a 150 en la prueba), pero equivocarse en cualquiera de las dos importa, y la exactitud por sí sola podría premiar a un modelo que favorezca la clase mayoritaria. Como medidas complementarias se reportan la exactitud balanceada y la exactitud.

**Alternativas comparadas:** 10 configuraciones de Árbol de decisión, Random Forest y Regresión logística, con 3, 4 o 6 variables. Además hay dos líneas base: la clase mayoritaria y la *continuidad* (predecir que la comuna repite la clase del período anterior).

Las configuraciones se fijaron de antemano en `experiments/protocolo_crecimiento_v2.json`.'''),
code(SETUP + r'''
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import StratifiedKFold
from sklearn.inspection import permutation_importance
from sklearn.metrics import (f1_score, balanced_accuracy_score, accuracy_score, confusion_matrix,
                             classification_report, ConfusionMatrixDisplay)

protocolo = json.loads((ROOT / 'experiments/protocolo_crecimiento_v2.json').read_text())
CANDIDATOS = protocolo['alternatives']
NOMBRES = ['< 1% anual', '≥ 1% anual']
NUCLEO = sorted(set(anio(1992).index) & set(anio(2024).index) - {9101, 9112})
print('comunas del núcleo de comparación:', len(NUCLEO))

def entradas(prev, ini, codigos):
    a, b = anio(prev).loc[codigos], anio(ini).loc[codigos]
    t = ini - prev
    return pd.DataFrame({
        'log_poblacion': np.log1p(b.population),
        'proporcion_menores_15': b.young / b.population,
        'proporcion_65_mas': b.old / b.population,
        'crecimiento_previo': tasa_anual(a.population, b.population, t),
        'cambio_menores_15_anual': (b.young / b.population - a.young / a.population) / t,
        'cambio_65_mas_anual': (b.old / b.population - a.old / a.population) / t,
    }, index=codigos)

def respuesta(ini, fin, codigos):
    r = tasa_anual(anio(ini).loc[codigos].population, anio(fin).loc[codigos].population, fin - ini)
    return pd.Series((r >= UMBRAL).astype(int), index=codigos), pd.Series(r, index=codigos)

def modelo(c):
    clases = {'DecisionTreeClassifier': DecisionTreeClassifier, 'RandomForestClassifier': RandomForestClassifier,
              'LogisticRegression': LogisticRegression}
    cols = ColumnTransformer([('x', 'passthrough', c['features'])], remainder='drop')
    esc = StandardScaler() if c['algorithm'] == 'LogisticRegression' else 'passthrough'
    return Pipeline([('cols', cols), ('esc', esc), ('clf', clases[c['algorithm']](**c['params']))])

def metricas(y, p):
    return {'F1 macro': f1_score(y, p, average='macro'), 'exactitud balanceada': balanced_accuracy_score(y, p),
            'exactitud': accuracy_score(y, p), 'aciertos': int((np.asarray(y) == np.asarray(p)).sum()), 'n': len(y)}

X_tr = entradas(1992, 2002, NUCLEO); y_tr, r_tr = respuesta(2002, 2017, NUCLEO)
X_te = entradas(2002, 2017, NUCLEO); y_te, r_te = respuesta(2017, 2024, NUCLEO)
print('entrenamiento:', y_tr.value_counts().to_dict(), '| prueba:', y_te.value_counts().to_dict())'''),
md('''## 2.1 Selección por validación cruzada (solo datos de entrenamiento)

El escalado de la regresión logística se ajusta **dentro** de cada partición mediante un `Pipeline`, para no filtrar información de la partición de validación. Criterio: mayor media de F1 macro por partición. Si hay empate, se prefiere mayor exactitud balanceada, luego menos variables y luego menor complejidad.'''),
code(r'''val = protocolo['validation']
folds = list(StratifiedKFold(n_splits=val['n_splits'], shuffle=val['shuffle'],
                             random_state=val['random_state']).split(X_tr, y_tr))
filas = []
for i, c in enumerate(CANDIDATOS):
    f1s, bas = [], []
    for tr, va in folds:
        p = modelo(c).fit(X_tr.iloc[tr], y_tr.iloc[tr]).predict(X_tr.iloc[va])
        f1s.append(f1_score(y_tr.iloc[va], p, average='macro')); bas.append(balanced_accuracy_score(y_tr.iloc[va], p))
    filas.append({'id': c['id'], 'algoritmo': c['algorithm'].replace('Classifier', ''), 'n_variables': len(c['features']),
                  'F1 macro (media CV)': np.mean(f1s), 'desv. est.': np.std(f1s, ddof=1),
                  'exactitud balanceada (media CV)': np.mean(bas), '_orden': (-len(c['features']), -c['complexity'], -i)})
# líneas base en CV
maj = np.zeros(len(y_tr), int)
for tr, va in folds: maj[va] = np.bincount(y_tr.iloc[tr]).argmax()
cont = (X_tr.crecimiento_previo >= UMBRAL).astype(int)
for nombre, p in [('mayoría (base)', maj), ('continuidad (base)', cont)]:
    filas.append({'id': nombre, 'algoritmo': 'línea base', 'n_variables': 0,
                  'F1 macro (media CV)': np.mean([f1_score(y_tr.iloc[va], np.asarray(p)[va], average='macro') for _, va in folds]),
                  'desv. est.': np.std([f1_score(y_tr.iloc[va], np.asarray(p)[va], average='macro') for _, va in folds], ddof=1),
                  'exactitud balanceada (media CV)': np.mean([balanced_accuracy_score(y_tr.iloc[va], np.asarray(p)[va]) for _, va in folds]),
                  '_orden': (0, 0, 0)})
cv = pd.DataFrame(filas)
modelos_cv = cv[cv.algoritmo != 'línea base']
ganador_id = max(modelos_cv.itertuples(), key=lambda r: (round(r[4], 12), round(r[6], 12), r[7])).id
ganador = next(c for c in CANDIDATOS if c['id'] == ganador_id)
print('Configuración seleccionada por CV:', ganador_id, '\n', ganador['params'], '\n', ganador['features'])
cv.drop(columns='_orden').sort_values('F1 macro (media CV)', ascending=False).round(3).reset_index(drop=True)'''),
code(r'''d = cv.sort_values('F1 macro (media CV)')
colores = ['#C44E52' if i == ganador_id else ('#8C8C8C' if a == 'línea base' else '#4C72B0') for i, a in zip(d.id, d.algoritmo)]
fig, ax = plt.subplots(figsize=(8, 4.5))
ax.barh(d.id, d['F1 macro (media CV)'], xerr=d['desv. est.'], color=colores, alpha=.9, capsize=2)
ax.set_xlabel('F1 macro, media de 5 particiones (±1 desv. est.)'); ax.set_xlim(0, 1)
ax.set_title('Selección por validación cruzada (2002–2017)')
plt.tight_layout(); plt.savefig(FIG / 'exp_seleccion_cv.png', bbox_inches='tight'); plt.show()'''),
md('''**Lectura de la validación cruzada**
- **El crecimiento previo es la variable clave**: el Random Forest sin historia (`bosque_sin_historia`) cae a F1 ≈ 0,57, mientras que con historia (`bosque_tendencia`) sube a ≈ 0,76.
- Los cambios de proporciones etarias (6 variables) no mejoran a las variantes de 4 variables.
- Random Forest con 4 variables (0,762) y la logística con 4 variables (0,758) quedan prácticamente empatados, y la continuidad (0,759) también está muy cerca. Gana el Random Forest según el criterio fijado de antemano.

## 2.2 Evaluación temporal en 2017–2024

Se comparan en el período de prueba el modelo seleccionado, el mejor modelo de cada familia y las dos líneas base.'''),
code(r'''def mejor_de(alg):
    sub = modelos_cv[modelos_cv.algoritmo == alg]
    return sub.sort_values('F1 macro (media CV)', ascending=False).id.iloc[0]
comparar = [ganador_id] + [i for i in (mejor_de('LogisticRegression'), mejor_de('DecisionTree')) if i != ganador_id]
pred, res = {}, []
for cid in comparar:
    c = next(x for x in CANDIDATOS if x['id'] == cid)
    m = modelo(c).fit(X_tr, y_tr)
    pred[cid] = pd.Series(m.predict(X_te), index=NUCLEO)
    if cid == ganador_id: final = m
pred['continuidad (base)'] = (X_te.crecimiento_previo >= UMBRAL).astype(int)
pred['mayoría (base)'] = pd.Series(np.bincount(y_tr).argmax(), index=NUCLEO)
tabla = pd.DataFrame({k: metricas(y_te, p) for k, p in pred.items()}).T
tabla.round(3)'''),
code(r'''fig, axes = plt.subplots(1, 3, figsize=(13, 3.8))
for ax, k in zip(axes, [ganador_id, comparar[1], 'continuidad (base)']):
    ConfusionMatrixDisplay(confusion_matrix(y_te, pred[k]), display_labels=NOMBRES).plot(ax=ax, cmap='Blues', colorbar=False)
    ax.set_title(f'{k}\nF1 macro {f1_score(y_te, pred[k], average="macro"):.3f}')
    ax.set_xlabel('predicho'); ax.set_ylabel('real')
plt.tight_layout(); plt.savefig(FIG / 'exp_matrices_confusion.png', bbox_inches='tight'); plt.show()'''),
md('''### Resultados por clase'''),
code(r'''for k in [ganador_id, comparar[1], 'continuidad (base)']:
    print(f'=== {k} ===')
    print(classification_report(y_te, pred[k], target_names=NOMBRES, digits=3))'''),
md('''## 2.3 Importancia de las variables del modelo seleccionado

Importancia por permutación en el período de prueba: cuánto cae el F1 macro si se desordena cada variable.'''),
code(r'''imp = permutation_importance(final, X_te, y_te, scoring='f1_macro', n_repeats=30, random_state=2025)
imp = pd.Series(imp.importances_mean, index=X_te.columns).loc[ganador['features']].sort_values()
ax = imp.plot.barh(figsize=(6, 2.8), color='#4C72B0'); ax.set_xlabel('caída media de F1 macro al permutar')
plt.tight_layout(); plt.savefig(FIG / 'exp_importancia.png', bbox_inches='tight'); plt.show()'''),
md('''## 2.4 Análisis de errores del modelo seleccionado'''),
code(r'''err = pd.DataFrame({'comuna': anio(2017).loc[NUCLEO, 'name'], 'region': anio(2017).loc[NUCLEO, 'region'],
                    'poblacion_2017': anio(2017).loc[NUCLEO, 'population'],
                    'tasa_previa_%': 100 * X_te.crecimiento_previo, 'tasa_real_%': 100 * r_te,
                    'real': y_te, 'predicho': pred[ganador_id],
                    'score': final.predict_proba(X_te)[:, 1]}, index=NUCLEO)
err['tipo'] = np.select([(err.real == 1) & (err.predicho == 1), (err.real == 0) & (err.predicho == 0),
                         (err.real == 0) & (err.predicho == 1)], ['VP', 'VN', 'FP (falsa alerta)'], 'FN (omitida)')
display(err.tipo.value_counts().to_frame('comunas'))
err['dist_umbral_pp'] = (err['tasa_real_%'] - 1).abs()
print('Mediana de distancia al umbral (puntos porcentuales), según acierto:')
display(err.assign(acierto=err.real == err.predicho).groupby('acierto').dist_umbral_pp.median().round(2))
print('Falsas alertas con mayor score (el modelo esperaba crecimiento alto y no ocurrió):')
display(err[err.tipo == 'FP (falsa alerta)'].sort_values('score', ascending=False).head(8).round(2))
print('Crecimientos altos omitidos:')
display(err[err.tipo == 'FN (omitida)'].sort_values('score').round(2))'''),
code(r'''fig, ax = plt.subplots(figsize=(7.5, 4.5))
for t, c in [('VP', '#4C72B0'), ('VN', '#8C8C8C'), ('FP (falsa alerta)', '#DD8452'), ('FN (omitida)', '#C44E52')]:
    d = err[err.tipo == t]
    ax.scatter(d['tasa_previa_%'].clip(-4, 8), d['tasa_real_%'].clip(-4, 8), s=14, c=c, label=f'{t} ({len(d)})', alpha=.75)
ax.axhline(1, color='k', lw=.8, ls='--'); ax.axvline(1, color='k', lw=.8, ls=':')
ax.set_xlabel('% anual 2002–2017 (entrada)'); ax.set_ylabel('% anual 2017–2024 (real)')
ax.set_title('Errores del modelo seleccionado'); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig(FIG / 'exp_errores.png', bbox_inches='tight'); plt.show()
print('Falsas alertas por región (top 6):'); display(err[err.tipo == 'FP (falsa alerta)'].region.value_counts().head(6))'''),
md('''**Qué muestran los errores**
- Los errores tienden a estar **más cerca del umbral** que los aciertos (mediana de 0,51 contra 0,69 puntos porcentuales de distancia a 1%). Parte del error es inevitable con un corte binario.
- **89 de los 109 errores son falsas alertas.** De ellas:
  - **62 crecieron, pero por debajo del umbral** (entre 0 y 1% anual), y **27 perdieron población**. Entre estas últimas hay comunas pequeñas o aisladas con caídas fuertes que la historia no anticipaba (Isla de Pascua, Putre, Juan Fernández).
  - Solo **24** venían creciendo ≥1% en 2002–2017 y se desaceleraron, por ejemplo Calera de Tango, Huechuraba, El Monte y Tiltil, en la periferia de Santiago (la RM aporta 20 falsas alertas en total). Las otras 65 venían creciendo menos de 1%, y el modelo igual las clasificó como positivas.
- Las **20 omisiones** son, en su mayoría, comunas del centro-sur (Los Lagos, La Araucanía, Ñuble, Maule) que antes crecían menos de 1% y pasaron a superarlo por poco (1,0–1,7%). Es el desplazamiento regional que se vio en el EDA.
- Además, el modelo marca como positivas más comunas de las que lo eran en el entrenamiento (219 predicciones positivas contra 31% de positivos en 2002–2017). Eso se debe a los pesos de clase balanceados: favorecen el recall de la clase minoritaria a costa de su precisión.

## 2.5 Selección y justificación'''),
code(r'''g, c = tabla.loc[ganador_id], tabla.loc['continuidad (base)']
fn = lambda k: int(((y_te == 1) & (pred[k] == 0)).sum()); fp = lambda k: int(((y_te == 0) & (pred[k] == 1)).sum())
resumen = pd.DataFrame({
    ganador_id: [g['F1 macro'], g['aciertos'], int(((y_te == 1) & (pred[ganador_id] == 1)).sum()), fn(ganador_id), fp(ganador_id)],
    'continuidad (base)': [c['F1 macro'], c['aciertos'], int(((y_te == 1) & (pred['continuidad (base)'] == 1)).sum()), fn('continuidad (base)'), fp('continuidad (base)')],
}, index=['F1 macro', 'aciertos / 314', 'crecimientos altos detectados (de 150)', 'crecimientos altos omitidos', 'falsas alertas'])
display(resumen.round(3))
# intervalo exploratorio por remuestreo de comunas para la diferencia de F1 macro
rng = np.random.default_rng(2025); difs = []
yy, pm, pc = y_te.to_numpy(), pred[ganador_id].to_numpy(), pred['continuidad (base)'].to_numpy()
for _ in range(2000):
    i = rng.integers(0, len(yy), len(yy))
    difs.append(f1_score(yy[i], pm[i], average='macro') - f1_score(yy[i], pc[i], average='macro'))
print(f'Diferencia F1 macro (modelo − continuidad): {g["F1 macro"] - c["F1 macro"]:+.3f}; '
      f'IC 95% bootstrap [{np.percentile(difs, 2.5):+.3f}; {np.percentile(difs, 97.5):+.3f}]')'''),
md('''**Modelo seleccionado: Random Forest** (`bosque_tendencia`) con 300 árboles, profundidad máxima 5, mínimo 8 ejemplos por hoja y pesos de clase balanceados. Usa 4 variables: log de la población, proporción de menores de 15, proporción de 65 o más y crecimiento previo.

**Justificación**
1. **Fue el mejor en la validación cruzada** (F1 macro ≈ 0,76), que es el criterio fijado antes de mirar la prueba. Supera a los árboles de decisión, a la logística con 6 variables y a su propia versión sin historia.
2. **En la prueba temporal 2017–2024** obtiene F1 macro 0,642 (205/314 aciertos). Supera con amplitud al árbol (0,442) y a la clase mayoritaria (0,343). La logística de 4 variables obtiene un valor algo mayor (0,667), y la continuidad, 0,663.
3. **Las diferencias entre los tres mejores no son concluyentes.** Frente a la continuidad, el intervalo bootstrap de la diferencia de F1 macro incluye el cero. Cambiar ahora a la logística porque ganó en la prueba sería elegir el modelo *con los datos de prueba*, y la evaluación dejaría de ser válida; por eso se mantiene la elección por validación cruzada. Lo que sí distingue claramente a los modelos es el *tipo de error*: el Random Forest detecta **130 de las 150** comunas de crecimiento alto (recall 0,87), contra 117 de la logística (0,78) y 73 de la continuidad (0,49), a cambio de más falsas alertas.
4. Para el uso que motiva el proyecto (identificar comunas que podrían necesitar planificar más vivienda, servicios o transporte), **omitir una comuna que sí crece es más costoso** que revisar una falsa alerta. Por eso se prefiere el Random Forest, que además ofrece un score continuo para priorizar la revisión.

**Limitaciones**
- Solo hay **un período para entrenar** y uno para evaluar, y el cambio de ritmo de crecimiento entre ambos genera la mayoría de las falsas alertas.
- La validación cruzada es *entre comunas* de un mismo período, no entre períodos futuros.
- 2024 ya se había observado en una versión anterior del proyecto (v1). Esta evaluación es una **reevaluación temporal exploratoria**, no una prueba ciega nueva.
- El score del modelo no está calibrado y no debe leerse como una probabilidad.'''),
]


def build(name, cells):
    nb = nbformat.v4.new_notebook()
    nb.cells = cells
    nb.metadata['kernelspec'] = {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'}
    NotebookClient(nb, timeout=600, kernel_name='python3', resources={'metadata': {'path': str(HERE)}}).execute()
    nbformat.write(nb, HERE / name)
    print('ok', name)


if __name__ == '__main__':
    build('01_analisis_exploratorio.ipynb', eda)
    build('02_experimento_clasificacion.ipynb', exp)
