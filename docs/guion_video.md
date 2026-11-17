# Guion del video (máximo 3 minutos)

Cada parte explica **por qué** se tomó una decisión y **por qué** salió ese resultado. El código no se explica; se muestran las figuras de `results/entrega/` o las tablas de los notebooks.

---

### 1. El problema (0:00–0:20)
**Pantalla:** título del README.

> "Quiero saber si se puede anticipar qué comunas de Chile van a crecer en población. Lo planteé como una clasificación: ¿crecerá la comuna al menos 1% anual en el período siguiente, sí o no? No intento predecir el número exacto de habitantes, sino identificar dónde habría que planificar más vivienda, colegios o transporte."

### 2. Los datos y por qué se limpiaron así (0:20–0:45)
**Pantalla:** notebook 01, tabla de calidad y tabla de comunas excluidas.

> "Usé los censos de 1992, 2002, 2017 y 2024 del INE. El principal problema de calidad no eran los valores faltantes, que no hay, sino el territorio. Entre censos se crearon comunas y se movieron límites. Si Alto Hospicio se separa de Iquique, Iquique 'pierde' población sin que nadie se haya ido. Por eso excluí las 30 comunas afectadas: prefiero menos datos a medir crecimientos falsos. Quedan 314 comunas comparables."

### 3. Lo que mostró el análisis exploratorio (0:45–1:15)
**Pantalla:** `eda_persistencia.png`, luego la tabla regional.

> "El hallazgo central es que **el mejor indicador de crecimiento futuro es el crecimiento pasado**: la correlación de Spearman es 0,65, aunque en el período siguiente baja a 0,42. Tiene sentido, porque las causas del crecimiento (suelo disponible, empleo, migración) cambian lento. La edad aporta algo: las comunas envejecidas crecen menos probablemente porque nacen menos niños y los jóvenes se van. El tamaño casi no importa.
>
> Pero también vi algo que después explica los errores: **el crecimiento cambió de lugar**. Entre 2002 y 2017 crecían sobre todo la Región Metropolitana y Valparaíso. Entre 2017 y 2024 crecieron el centro-sur: en Ñuble se pasó de 11% a 84% de comunas creciendo."

### 4. Por qué este diseño de experimento (1:15–1:40)
**Pantalla:** `exp_seleccion_cv.png`.

> "Entrené con el período 2002–2017 y evalué en el período siguiente, 2017–2024, porque así se usaría en la realidad: con el pasado se predice el futuro. Comparé árboles, Random Forest y regresión logística. La métrica fue F1 macro, porque las clases están desbalanceadas, y la exactitud premiaría a un modelo que dice siempre 'no crece'.
>
> Además usé una línea base honesta: **suponer que cada comuna repite lo del período anterior**. Si un modelo no le gana a eso, no aporta.
>
> En la validación cruzada ganó un Random Forest, con F1 de 0,76. La prueba más clara de lo que dijo el análisis exploratorio: el mismo modelo **sin** el crecimiento previo cae a 0,57."

### 5. Por qué los resultados salieron así (1:40–2:25)
**Pantalla:** `exp_matrices_confusion.png`, luego `exp_errores.png`.

> "En el período de prueba, el F1 bajó de 0,76 a 0,64. **¿Por qué baja?** Porque el modelo aprendió el patrón de 2002–2017, y en 2017–2024 el crecimiento se movió de región. Ningún modelo entrenado con un solo período puede anticipar ese desplazamiento.
>
> Esto se ve en los errores. La mayoría son falsas alertas: comunas que crecieron, pero menos de 1%, o comunas de la periferia de Santiago que venían creciendo fuerte y se frenaron. Las omisiones son comunas del sur que antes no crecían y empezaron a hacerlo. Además, muchos errores están muy cerca del umbral de 1%, donde cualquier corte duro se equivoca.
>
> **¿Por qué el modelo tiene tantas falsas alertas y pocas omisiones?** Porque entrenó con un período donde solo 31% de las comunas crecía, y le di pesos balanceados para que no ignorara esa clase. Eso lo vuelve 'alarmista': detecta 130 de las 150 comunas que crecieron, a cambio de dar 89 falsas alertas."

### 6. Por qué elijo este modelo (2:25–2:50)
**Pantalla:** tabla de comparación del README.

> "En la prueba, la regresión logística y la línea base de continuidad sacan un F1 un poco mayor, pero la diferencia es menor a 0,03; con la continuidad, el intervalo bootstrap de la diferencia incluye el cero. No cambio de modelo después de ver la prueba, porque eso sería hacer trampa con los datos de evaluación. Me quedo con el Random Forest, que fue el mejor en la validación y además el que **menos comunas en crecimiento omite**: 130 detectadas contra 73 de la continuidad. Para planificar, omitir una comuna que crece cuesta más que revisar una falsa alerta.
>
> La conclusión es que la historia de crecimiento sí permite anticipar, pero un solo período de entrenamiento no alcanza para captar cambios de ciclo. Ese es el próximo paso."

---

## Cómo grabar
- OBS Studio (`sudo apt install obs-studio`), o la grabación de pantalla de GNOME con `Ctrl+Shift+Alt+R`, que guarda un `.webm`. Para pasarlo a MP4: `ffmpeg -i video.webm -c:v libx264 -c:a aac video.mp4`.
- Sube el video a YouTube como **no listado** y pega el enlace en Campus Virtual junto con el del repositorio.
