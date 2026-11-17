"""Genera el video de la entrega: láminas 1920x1080 + narración Piper + ffmpeg."""
import subprocess, wave, json
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.image import imread
import imageio_ffmpeg

HERE = Path(__file__).parent
REPO = Path.home() / 'crecimiento-poblacional-comunal'
FIG = REPO / 'results/entrega'
OUT = HERE / 'build'; OUT.mkdir(exist_ok=True)
FF = imageio_ffmpeg.get_ffmpeg_exe()
BG, INK, MUTED, ACC = '#FBFAF7', '#1F2430', '#5B6170', '#C44E52'
plt.rcParams['font.family'] = 'DejaVu Sans'

# ---------- figura regional adicional
perf = pd.read_csv(REPO / 'results/crecimiento_v2/perfiles_censales.csv')
p = {y: perf[perf.year == y].set_index('code') for y in (2002, 2017, 2024)}
t1 = (p[2017].population / p[2002].population) ** (1 / 15) - 1
t2 = (p[2024].population / p[2017].population) ** (1 / 7) - 1
reg = pd.DataFrame({'2002–2017': (t1 >= .01).groupby(p[2002].region).mean() * 100,
                    '2017–2024': (t2 >= .01).groupby(p[2017].region).mean() * 100})
short = {'Libertador General Bernardo O\'Higgins': "O'Higgins", 'Metropolitana de Santiago': 'Metropolitana',
         'Aysén del General Carlos Ibáñez del Campo': 'Aysén', 'Magallanes y de la Antártica Chilena': 'Magallanes',
         'Arica y Parinacota': 'Arica y Parinacota'}
reg.index = [short.get(i, i) for i in reg.index]
reg = reg.sort_values('2017–2024')
fig, ax = plt.subplots(figsize=(9, 6.2))
y = np.arange(len(reg))
ax.barh(y + .2, reg['2002–2017'], .4, color='#8C8C8C', label='2002–2017')
ax.barh(y - .2, reg['2017–2024'], .4, color='#4C72B0', label='2017–2024')
ax.set_yticks(y, reg.index); ax.set_xlabel('% de comunas que crecieron ≥ 1% anual')
for s in ('top', 'right'): ax.spines[s].set_visible(False)
ax.legend(frameon=False, loc='lower right'); plt.tight_layout()
plt.savefig(OUT / 'regiones.png', dpi=150); plt.close()

# ---------- láminas: (título, texto o imagen, narración)
S = [
 dict(kind='title', title='¿Qué comunas de Chile van a crecer?',
      sub='Clasificación del crecimiento poblacional comunal\ncon los censos del INE, 1992–2024',
      say='Quiero saber si se puede anticipar qué comunas de Chile van a crecer en población. '
          'Lo planteé como una clasificación: ¿crecerá la comuna al menos un uno por ciento anual en el período siguiente, sí o no? '
          'La idea es saber dónde planificar vivienda, colegios o transporte.'),
 dict(kind='bullets', title='Datos: el problema era el territorio',
      bullets=['Censos INE 1992, 2002, 2017 y 2024', 'Sin faltantes ni duplicados; 2017 verificado con el INE',
               'Comunas creadas o con límites cambiados → crecimiento falso', '30 comunas excluidas · 314 comparables'],
      say='Usé los censos de mil novecientos noventa y dos, dos mil dos, dos mil diecisiete y dos mil veinticuatro. '
          'El problema de calidad era el territorio: entre censos se crearon comunas y se movieron límites. '
          'Si Alto Hospicio se separa de Iquique, Iquique pierde población sin que nadie se haya ido. '
          'Por eso excluí treinta comunas: prefiero menos datos a medir crecimientos falsos. Quedan trescientas catorce.'),
 dict(kind='image', title='El crecimiento pasado anticipa el futuro', img=FIG / 'eda_persistencia.png',
      note='Spearman 0,65, luego 0,42 · las comunas envejecidas crecen menos · el tamaño casi no importa',
      say='El hallazgo central es que el mejor indicador del crecimiento futuro es el crecimiento pasado, con una correlación de cero coma sesenta y cinco. '
          'Aunque en el período siguiente baja a cero coma cuarenta y dos. '
          'Las comunas envejecidas crecen menos, y el tamaño casi no importa.'),
 dict(kind='image', title='…pero el crecimiento cambió de lugar', img=OUT / 'regiones.png',
      note='Ñuble: 11 % → 84 % de comunas creciendo · Metropolitana: 54 % → 40 %',
      say='Pero el crecimiento cambió de lugar. Entre dos mil dos y dos mil diecisiete crecían sobre todo la Región Metropolitana y Valparaíso. '
          'Entre dos mil diecisiete y dos mil veinticuatro creció el centro sur: en Ñuble se pasó de un once a un ochenta y cuatro por ciento de comunas creciendo. '
          ''),
 dict(kind='image', title='Selección por validación cruzada (2002–2017)', img=FIG / 'exp_seleccion_cv.png',
      note='Métrica: F1 macro · línea base: repetir la clase del período anterior',
      say='Entrené con el período dos mil dos a dos mil diecisiete, y evalué en el siguiente, como se usaría en la realidad. '
          'Comparé árboles, Random Forest y regresión logística, con efe uno macro porque las clases están desbalanceadas, '
          'contra una línea base: que cada comuna repita lo del período anterior. '
          'Ganó un Random Forest, con cero coma setenta y seis. Sin el crecimiento previo, cae a cero coma cincuenta y siete.'),
 dict(kind='image', title='Prueba temporal 2017–2024', img=FIG / 'exp_matrices_confusion.png',
      note='Random Forest: 205/314 aciertos · detecta 130 de 150 comunas que crecieron',
      say='En la prueba bajó a cero coma sesenta y cuatro. ¿Por qué? Porque aprendió el patrón de dos mil dos a dos mil diecisiete, '
          'y después el crecimiento se movió de región. Un solo período no basta para anticipar ese desplazamiento. '
          'Y como solo el treinta y uno por ciento crecía en el entrenamiento, le di pesos balanceados. '
          'Eso lo vuelve alarmista: detecta ciento treinta de las ciento cincuenta comunas que crecieron, a cambio de ochenta y nueve falsas alertas.'),
 dict(kind='image', title='¿Dónde se equivoca?', img=FIG / 'exp_errores.png',
      note='Falsas alertas: periferia de Santiago que se frenó · Omisiones: comunas del sur que despegaron',
      say='Se ve en los errores. Hay falsas alertas en la periferia de Santiago, que venía creciendo y se frenó, '
          'y omisiones en comunas del sur que empezaron a crecer.'),
 dict(kind='table', title='Modelo seleccionado: Random Forest',
      rows=[['', 'F1 macro CV', 'F1 prueba', 'Detecta crecimiento'],
            ['Random Forest (elegido)', '0,762', '0,642', '130 / 150'],
            ['Regresión logística', '0,758', '0,667', '117 / 150'],
            ['Continuidad (base)', '0,759', '0,663', '73 / 150'],
            ['Clase mayoritaria', '0,409', '0,343', '0 / 150']],
      note='Diferencias en prueba < 0,03 · elegido sin mirar la prueba',
      say='En la prueba, la logística y la continuidad sacan un efe uno levemente mayor, pero la diferencia es menor a tres centésimas. '
          'Cambiar de modelo después de ver la prueba sería hacer trampa. '
          'Me quedo con el Random Forest: fue el mejor en validación y el que menos comunas en crecimiento omite. '
          'Para planificar, omitir una comuna que crece cuesta más que revisar una falsa alerta.'),
 dict(kind='title', title='Conclusión',
      sub='La historia de crecimiento sí permite anticipar.\nUn solo período de entrenamiento no alcanza\npara captar cambios de ciclo.',
      footer='github.com/Billyflin/crecimiento-poblacional-comunal',
      say='En resumen: la historia de crecimiento sí permite anticipar, pero un solo período de entrenamiento no alcanza para captar los cambios de ciclo.'),
]

def slide(i, s):
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100, facecolor=BG)
    fig.text(.97, .03, f'{i + 1}/{len(S)}', ha='right', color=MUTED, fontsize=16)
    if s['kind'] == 'title':
        fig.text(.5, .62, s['title'], ha='center', fontsize=60, weight='bold', color=INK)
        fig.text(.5, .40, s['sub'], ha='center', va='center', fontsize=32, color=MUTED, linespacing=1.5)
        fig.add_artist(plt.Line2D([.4, .6], [.54, .54], color=ACC, lw=4))
        if 'footer' in s: fig.text(.5, .12, s['footer'], ha='center', fontsize=22, color=MUTED)
    else:
        fig.text(.06, .88, s['title'], fontsize=46, weight='bold', color=INK)
        fig.add_artist(plt.Line2D([.06, .16], [.855, .855], color=ACC, lw=4))
        if s['kind'] == 'bullets':
            for k, b in enumerate(s['bullets']):
                fig.text(.08, .68 - k * .13, '•  ' + b, fontsize=34, color=INK)
        elif s['kind'] == 'image':
            im = imread(s['img']); h, w = im.shape[:2]
            box_w, box_h = .88, .64; r = min(box_w * 19.2 / w, box_h * 10.8 / h)
            ww, hh = w * r / 19.2, h * r / 10.8
            ax = fig.add_axes([.5 - ww / 2, .17 + (box_h - hh) / 2, ww, hh]); ax.imshow(im); ax.axis('off')
        elif s['kind'] == 'table':
            ax = fig.add_axes([.08, .3, .84, .45]); ax.axis('off')
            t = ax.table(cellText=s['rows'][1:], colLabels=s['rows'][0], loc='center', cellLoc='center')
            t.auto_set_font_size(False); t.set_fontsize(26); t.scale(1, 3.6)
            for (r, c), cell in t.get_celld().items(): cell.set_width([.32, .2, .2, .28][c])
            for (r, c), cell in t.get_celld().items():
                cell.set_edgecolor('#DDDAD2'); cell.set_facecolor(BG)
                if r == 0: cell.set_text_props(weight='bold', color=MUTED)
                if r == 1: cell.set_facecolor('#F3E3E3'); cell.set_text_props(weight='bold')
        if 'note' in s: fig.text(.5, .08, s['note'], ha='center', fontsize=26, color=ACC)
    path = OUT / f's{i:02d}.png'; fig.savefig(path, facecolor=BG); plt.close(fig); return path

def tts(i, text, scale):
    wav = OUT / f'a{i:02d}.wav'
    subprocess.run([str(HERE / '.venv/bin/python'), '-m', 'piper', '-m', str(HERE / 'es_MX-claude-high.onnx'),
                    '-f', str(wav), '--length-scale', str(scale), '--sentence-silence', '0.25'],
                   input=text.encode(), check=True, capture_output=True)
    with wave.open(str(wav)) as w: return wav, w.getnframes() / w.getframerate()

if __name__ == '__main__':
    import sys
    scale = float(sys.argv[1]) if len(sys.argv) > 1 else 1.0
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
    final = HERE / 'video_entrega.mp4'
    subprocess.run([FF, '-y', '-f', 'concat', '-safe', '0', '-i', str(OUT / 'lista.txt'), '-c', 'copy', str(final)],
                   check=True, capture_output=True)
    print('listo', final)
