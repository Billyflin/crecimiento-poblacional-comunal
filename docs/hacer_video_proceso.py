"""Video 2: el proceso. Muestra fragmentos reales del código y explica por qué está escrito así."""
import subprocess, sys, wave
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.image import imread
from pygments import highlight
from pygments.lexers import PythonLexer, JsonLexer, BashLexer
from pygments.formatters import ImageFormatter
import imageio_ffmpeg

HERE = Path(__file__).parent
OUT = HERE / 'build_proceso'; OUT.mkdir(exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
BG, INK, MUTED, ACC = '#FBFAF7', '#1F2430', '#5B6170', '#C44E52'
plt.rcParams['font.family'] = 'DejaVu Sans'

S = [
 dict(kind='title', title='Cómo se construyó el análisis',
      sub='El código y el porqué de cada decisión\nClasificación del crecimiento poblacional comunal',
      say='En este video muestro el proceso: qué hace el código y, sobre todo, por qué está escrito así. '
          'Cada decisión busca lo mismo: que el resultado sea verificable y que el modelo no haga trampa.'),
 dict(kind='code', title='1 · Datos trazables', file='data/raw/ine/crecimiento/fuentes.json', lexer=JsonLexer,
      code='''{
  "publisher": "Instituto Nacional de Estadísticas de Chile",
  "license": "CC BY-SA 4.0",
  "retrieved_at": "2026-10-05T10:24:08+00:00",
  "files": [
    { "file": "edad_residencia_1992.html",
      "url": "https://redatam-ine.ine.cl/redbin/RpWebStats.exe/CrossTab?",
      "params": { "BASE": "CENSO_1992", ... },
      "sha256": "a6dd2b414fb0466bec4519d698d56216..." },
    ...''',
      say='Primero, los datos. No los copié a mano: un script los descarga del INE y guarda en este manifiesto la dirección, '
          'la consulta exacta, la fecha y un hash de cada archivo. ¿Por qué? Porque así cualquiera puede comprobar que '
          'los archivos del repositorio son exactamente los que publicó el INE.'),
 dict(kind='code', title='2 · Revisar la calidad antes de modelar', file='notebooks/01_analisis_exploratorio.ipynb  (extracto simplificado)', lexer=PythonLexer,
      code='''chequeos = {
  'faltantes':  perfiles.isna().sum().sum(),
  'duplicados': perfiles.duplicated(['code', 'year']).sum(),
  'edades > población':
      (perfiles.young + perfiles.old > perfiles.population).sum(),
  'población <= 0': (perfiles.population <= 0).sum(),
  'comunas excluidas': len(calidad['exclusions']),            # 30
  'diferencias 2017 vs INE':
      len(calidad['independent_2017_check']['differences']),  # 0
}''',
      say='Antes de modelar, reviso la calidad: faltantes, duplicados y conteos imposibles, como más niños y adultos mayores que población total. '
          'Todo da cero. Lo importante fue la exclusión de treinta comunas con cambios de límites: cada exclusión queda registrada con su motivo, '
          'para que no sea una decisión arbitraria.'),
 dict(kind='code', title='3 · La variable objetivo', file='notebooks/02_experimento_clasificacion.ipynb  (extracto simplificado)', lexer=PythonLexer,
      code='''UMBRAL = 0.01

def tasa_anual(p0, p1, anios):
    return (p1 / p0) ** (1 / anios) - 1

def respuesta(ini, fin, codigos):
    r = tasa_anual(anio(ini).population, anio(fin).population, fin - ini)
    return (r >= UMBRAL).astype(int)''',
      say='La respuesta es la tasa anual compuesta. ¿Por qué anual? Porque los períodos duran diez, quince y siete años, '
          'y sin anualizar no serían comparables. Uso la fórmula geométrica porque la población crece como el interés compuesto. '
          'Luego la convierto en sí o no con el umbral del uno por ciento.'),
 dict(kind='code', title='4 · Solo información del pasado', file='notebooks/02_experimento_clasificacion.ipynb  (extracto simplificado)', lexer=PythonLexer,
      code='''def entradas(prev, ini, codigos):
    a, b = anio(prev).loc[codigos], anio(ini).loc[codigos]
    return pd.DataFrame({
        'log_poblacion':         np.log1p(b.population),
        'proporcion_menores_15': b.young / b.population,
        'proporcion_65_mas':     b.old / b.population,
        'crecimiento_previo':    tasa_anual(a.population, b.population, ini - prev),
        ...
    })

X_tr = entradas(1992, 2002, NUCLEO);  y_tr = respuesta(2002, 2017, NUCLEO)
X_te = entradas(2002, 2017, NUCLEO);  y_te = respuesta(2017, 2024, NUCLEO)''',
      say='Esta es la función más importante. Las entradas se calculan solo con censos anteriores o iguales al inicio del período. '
          'Nunca entra la población final, ni el nombre, ni la región. ¿Por qué? Porque eso sería filtrar la respuesta, '
          'y el modelo parecería bueno sin serlo. Uso logaritmo porque la población va de decenas a medio millón, '
          'y proporciones para separar la edad del tamaño.'),
 dict(kind='code', title='5 · Las alternativas se fijaron antes', file='experiments/protocolo_crecimiento_v2.json', lexer=JsonLexer,
      code='''"alternatives": [
  { "id": "bosque_tendencia", "algorithm": "RandomForestClassifier",
    "features": ["log_poblacion", "proporcion_menores_15",
                 "proporcion_65_mas", "crecimiento_previo"],
    "params": { "n_estimators": 300, "max_depth": 5,
                "min_samples_leaf": 8, "class_weight": "balanced_subsample" } },
  { "id": "logistica_tendencia", "algorithm": "LogisticRegression", ... },
  { "id": "bosque_sin_historia", ... },   ... 10 configuraciones
],
"selection": ["Mayor media de F1 macro por pliegue", ...]''',
      say='Las diez configuraciones y el criterio para elegir se escribieron en este protocolo antes de entrenar. '
          '¿Por qué? Para no probar cosas hasta que algo salga bien. Incluí a propósito un Random Forest sin crecimiento previo, '
          'para medir cuánto aporta esa variable. Los árboles son poco profundos y con hojas mínimas porque hay solo trescientas catorce comunas.'),
 dict(kind='code', title='6 · Validación sin filtración', file='notebooks/02_experimento_clasificacion.ipynb  (extracto simplificado)', lexer=PythonLexer,
      code='''def modelo(c):
    esc = StandardScaler() if c['algorithm'] == 'LogisticRegression' \\
          else 'passthrough'
    return Pipeline([('cols', cols),
                     ('esc', esc),          # se ajusta dentro de cada partición
                     ('clf', clases[c['algorithm']](**c['params']))])

folds = StratifiedKFold(n_splits=5, shuffle=True, random_state=2025)
for tr, va in folds.split(X_tr, y_tr):
    p = modelo(c).fit(X_tr.iloc[tr], y_tr.iloc[tr]).predict(X_tr.iloc[va])
    f1s.append(f1_score(y_tr.iloc[va], p, average='macro'))''',
      say='Para elegir uso validación cruzada estratificada de cinco partes, solo con datos de entrenamiento. Estratificada, '
          'para que cada parte tenga la misma proporción de comunas que crecen. El escalado de la logística va dentro de un pipeline: '
          'así se ajusta solo con la parte de entrenamiento de cada partición, y la de validación nunca se filtra.'),
 dict(kind='code', title='7 · Una prueba, y contra una base honesta', file='notebooks/02_experimento_clasificacion.ipynb  (extracto simplificado)', lexer=PythonLexer,
      code='''m = modelo(ganador).fit(X_tr, y_tr)            # elegido solo por CV
pred[ganador_id] = m.predict(X_te)              # se evalúa una vez en 2017-2024

pred['continuidad (base)'] = (X_te.crecimiento_previo >= UMBRAL).astype(int)
pred['mayoría (base)']     = np.bincount(y_tr).argmax()

for _ in range(2000):                           # ¿la diferencia es real?
    i = rng.integers(0, len(yy), len(yy))
    difs.append(f1_score(yy[i], pm[i], average='macro')
                - f1_score(yy[i], pc[i], average='macro'))''',
      say='El modelo elegido se evalúa una sola vez en el período siguiente. Lo comparo contra una base muy simple: '
          'que cada comuna repita lo que hizo antes. Si un modelo no le gana a eso, no aporta. '
          'Y como las diferencias fueron pequeñas, uso remuestreo bootstrap para ver si son reales o ruido.'),
 dict(kind='code', title='8 · Reproducible de punta a punta', file='README.md', lexer=BashLexer,
      code='''git clone https://github.com/Billyflin/crecimiento-poblacional-comunal.git
cd crecimiento-poblacional-comunal
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

python notebooks/construir_notebooks.py      # re-ejecuta EDA y experimento
python -m unittest discover -s tests -v      # 21 pruebas de integridad''',
      say='Finalmente, todo es reproducible: versiones fijadas, semillas fijas, y un script que vuelve a ejecutar los dos notebooks desde cero. '
          'Además hay veintiuna pruebas automáticas que verifican, por ejemplo, que ninguna entrada use datos del futuro.'),
]


def code_img(i, s):
    png = highlight(s['code'], s['lexer'](), ImageFormatter(font_name='DejaVu Sans Mono', font_size=30, line_numbers=False,
                                                               style='friendly', image_pad=28, line_pad=8))
    path = OUT / f'c{i:02d}.png'; path.write_bytes(png); return path


def slide(i, s):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=BG)
    fig.text(.97, .03, f'{i + 1}/{len(S)}', ha='right', color=MUTED, fontsize=16)
    if s['kind'] == 'title':
        fig.text(.5, .62, s['title'], ha='center', fontsize=60, weight='bold', color=INK)
        fig.add_artist(plt.Line2D([.4, .6], [.54, .54], color=ACC, lw=4))
        fig.text(.5, .40, s['sub'], ha='center', va='center', fontsize=32, color=MUTED, linespacing=1.5)
    else:
        fig.text(.05, .89, s['title'], fontsize=44, weight='bold', color=INK)
        fig.add_artist(plt.Line2D([.05, .15], [.865, .865], color=ACC, lw=4))
        fig.text(.05, .80, s['file'], fontsize=20, color=MUTED, family='DejaVu Sans Mono')
        im = imread(code_img(i, s)); h, w = im.shape[:2]
        bw, bh = .90, .68; r = min(bw * 1920 / w, bh * 1080 / h, 1.25)
        ww, hh = w * r / 1920, h * r / 1080
        ax = fig.add_axes([.05, .76 - hh, ww, hh]); ax.imshow(im); ax.axis('off')
    path = OUT / f's{i:02d}.png'; fig.savefig(path, facecolor=BG); plt.close(fig); return path


def tts(i, text, scale):
    wav = OUT / f'a{i:02d}.wav'
    subprocess.run([str(HERE / '.venv/bin/python'), '-m', 'piper', '-m', str(HERE / 'es_MX-claude-high.onnx'),
                    '-f', str(wav), '--length-scale', str(scale), '--sentence-silence', '0.25'],
                   input=text.encode(), check=True, capture_output=True)
    with wave.open(str(wav)) as w: return wav, w.getnframes() / w.getframerate()


if __name__ == '__main__':
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 0.87
    segs = []
    for i, s in enumerate(S):
        img = slide(i, s); wav, d = tts(i, s['say'], scale)
        seg = OUT / f'v{i:02d}.mp4'
        subprocess.run([FF, '-y', '-loop', '1', '-i', str(img), '-i', str(wav), '-af', 'apad=pad_dur=0.6',
                        '-c:v', 'libx264', '-tune', 'stillimage', '-pix_fmt', 'yuv420p', '-r', '30',
                        '-c:a', 'aac', '-b:a', '160k', '-ar', '44100', '-t', f'{d + 0.6:.2f}', str(seg)],
                       check=True, capture_output=True)
        segs.append(seg); print(f'lámina {i + 1}: {d:.1f}s')
    (OUT / 'lista.txt').write_text(''.join(f"file '{p}'\n" for p in segs))
    final = HERE / 'video_proceso.mp4'
    subprocess.run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', str(OUT / 'lista.txt'), '-c', 'copy', str(final)],
                   check=True, capture_output=True)
    print('listo', final)
