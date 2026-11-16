# Guion del video (máximo 3 minutos)

Duración total aproximada: 2:45 minutos. Se graba la pantalla con los notebooks abiertos y la voz en off. Las figuras están en `results/entrega/`.

| Tiempo | Pantalla | Qué decir |
|---|---|---|
| 0:00–0:20 | README, título y pregunta | "Mi proyecto es de clasificación. La pregunta es si, con lo que sabemos de una comuna al inicio de un período entre censos (su tamaño, sus edades y cuánto creció antes), podemos clasificar si va a crecer al menos 1% anual en el período siguiente." |
| 0:20–0:45 | Notebook 01: tabla de fuentes y tabla de calidad | "Uso los censos 1992, 2002, 2017 y 2024 del INE. Los archivos originales están en el repositorio, con sus URL y hashes. No hay faltantes ni duplicados, y el 2017 coincide con una publicación independiente del INE. Excluí 30 comunas que cambiaron de límites, porque ahí mediría cambios territoriales y no crecimiento. Quedan 314 comunas comparables." |
| 0:45–1:15 | `eda_persistencia.png` y tabla regional | "Lo más importante del análisis: el crecimiento previo es la mejor señal, con correlación 0,65. Las comunas envejecidas crecen menos. Pero el crecimiento se desplazó entre períodos: en Ñuble pasó de 11% a 84% de comunas creciendo sobre 1%, mientras que en Santiago bajó. Las clases además cambian de 31% a 48% de positivos, por eso uso F1 macro." |
| 1:15–1:45 | Notebook 02: `exp_seleccion_cv.png` | "Entreno con el período 2002–2017 y comparo 10 configuraciones de árbol, Random Forest y regresión logística, más dos líneas base. Elijo solo con validación cruzada de 5 particiones. Gana un Random Forest de 4 variables, con F1 macro 0,76. Sin el crecimiento previo cae a 0,57." |
| 1:45–2:15 | `exp_matrices_confusion.png` y reporte por clase | "Lo pruebo en el período siguiente, 2017–2024. El Random Forest logra F1 macro 0,64 y 205 de 314 aciertos. La logística y la continuidad quedan a menos de 0,03, una diferencia no concluyente. Lo que lo distingue es que detecta 130 de las 150 comunas que realmente crecieron, contra 73 de la continuidad." |
| 2:15–2:35 | `exp_errores.png` | "La mayoría de los errores son falsas alertas: comunas que crecieron, pero menos de 1%, o comunas de la periferia de Santiago que se desaceleraron. Las omisiones son comunas del sur que empezaron a crecer. Es el cambio regional que se vio en el análisis exploratorio." |
| 2:35–2:50 | README, sección de justificación | "Me quedo con el Random Forest porque fue el mejor en validación y porque, para planificar, omitir una comuna que crece cuesta más que revisar una falsa alerta. Su límite: hay un solo período para entrenar. Todo el código y los datos están en el repositorio." |

## Cómo grabar

- **Linux:** OBS Studio (`sudo apt install obs-studio`), o la grabación de pantalla de GNOME con `Ctrl+Shift+Alt+R`, que guarda un `.webm`. Para pasarlo a MP4: `ffmpeg -i video.webm -c:v libx264 -c:a aac video.mp4`.
- Antes de grabar, abre `jupyter lab notebooks/` y deja cada figura a la vista.
- Sube el video a YouTube como **no listado** y pega el enlace en Campus Virtual junto con el enlace del repositorio.
