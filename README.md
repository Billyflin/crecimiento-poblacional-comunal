# Clasificar crecimiento poblacional: versión 2

Proyecto individual tutorado con **Pablo Valenzuela**, usando tabulados oficiales de los censos 1992, 2002, 2017 y 2024 del INE. La aplicación clasifica si una comuna tendrá crecimiento medio de **al menos 1% anual**. El umbral es una decisión del proyecto; no se predice un número exacto de habitantes ni se ofrece una proyección oficial.

Esta versión incorpora crecimiento previo, compara diez configuraciones y recupera **Temuco y Padre Las Casas como comunas individuales**. La recuperación territorial es preliminar. La primera prueba permanece conservada.

## Qué mejoró y qué no

La comparación utiliza las mismas 314 comunas de v1. Las dos recuperadas son aplicaciones adicionales y no cambian el denominador.

| Reevaluación 2017–2024 | F1 macro | Aciertos / 314 |
| --- | ---: | ---: |
| Random Forest v1, sin crecimiento previo | 0,528 | 169 |
| Random Forest v2, con crecimiento previo | **0,642** | **205** |
| Continuar la clase de crecimiento anterior | **0,663** | **213** |
| Clase mayoritaria | 0,343 | 164 |

Se ganan **36 aciertos frente a v1**, pero no se supera la continuidad de tendencia. La diferencia de F1 respecto a esa referencia es −0,021; el intervalo exploratorio por remuestreo de regiones es aproximadamente [−0,113; 0,091], por lo que no acredita ventaja clara.

El tipo de error sí cambia:

| Detección de crecimiento alto | Random Forest v2 | Continuidad |
| --- | ---: | ---: |
| Comunas detectadas entre las 150 que realmente crecieron alto | **130** | 73 |
| Comunas de crecimiento alto omitidas | 20 | 77 |
| Falsas alertas de crecimiento alto | **89** | 24 |

Esa mayor detección puede interesar para revisar casos, a cambio de más falsas alertas. Es una interpretación exploratoria del resultado, no un cambio posterior del criterio de selección ni una demostración de utilidad futura.

**2024 ya fue observado en v1.** La nueva selección de configuración utiliza datos anteriores, pero el diseño de v2 está informado por el diagnóstico anterior. Su evaluación sobre 2024 se llama reevaluación exploratoria, nunca nueva prueba final independiente.

## Abrir la aplicación

Después de clonar el repositorio, entrar en su carpeta y ejecutar:

~~~bash
python3 app/iniciar.py --port 8787
~~~

Abrir [la aplicación local](http://127.0.0.1:8787/). Para consultar las salidas incluidas basta Python 3; las dependencias de `requirements.txt` se necesitan para reproducir los experimentos y las pruebas. El servidor queda en segundo plano; utiliza biblioteca estándar y salidas precalculadas de los clasificadores. Después de reiniciar el computador hay que ejecutar el comando nuevamente. Registros en .runtime/servidor-8787.log.

Pulsar **Probar Temuco** o **Probar Padre Las Casas**, o buscar una comuna. La búsqueda admite tildes, palabras, región, clic y teclado. El texto libre debe convertirse en una opción elegida; las 30 comunas todavía excluidas no se ofrecen. Hay 316 comunas disponibles en ambos modos.

La comparación histórica muestra las cuatro entradas, la clasificación y la continuidad anterior. Se puede revelar el resultado de 2024. Cuando los enfoques difieren, la interfaz lo señala; cuando coinciden, no presenta esa coincidencia como garantía.

El escenario **2024–2031** utiliza otro ajuste, con respuestas conocidas hasta 2024. No tiene resultado observado de 2031 ni precisión futura demostrada. El puntaje interno se presenta sin calibración, no como porcentaje de certeza.

## Entradas, entrenamiento y selección

Se evaluaron seis posibles entradas:

1. Logaritmo de la población inicial.
2. Proporción de menores de 15 años.
3. Proporción de personas de 65 o más.
4. Crecimiento anual del intervalo anterior.
5. Cambio anual de la proporción de menores de 15.
6. Cambio anual de la proporción de 65 o más.

Ganó el **Random Forest con las cuatro primeras**. Los cambios de composición etaria no mejoraron la elección. Código, nombre, región, población final y respuesta del período no ingresan al clasificador.

| Paso | Datos utilizados | Ejemplos |
| --- | --- | ---: |
| Construir entradas del entrenamiento | 1992 y 2002 | 314 comunas |
| Respuesta de entrenamiento | Crecimiento 2002–2017 | 314 |
| Validación para elegir | Cinco particiones de esa etapa | Cada comuna reservada una vez |
| Ajuste del modelo histórico elegido | Todas las respuestas hasta 2017 de esa etapa | 314 |
| Reevaluación temporal | Entradas 2002/2017; respuesta de 2024 | 314 de comparación + 2 adicionales |
| Ajuste separado para el escenario futuro | Respuestas hasta 2024, misma configuración | 630 |

La respuesta conserva la fórmula: (P_final/P_inicial) elevado a 1/años, menos 1; clase positiva si la tasa es al menos 0,01.

El protocolo v2 se registró antes de entrenar esta versión. Sus diez candidatos incluyen Decision Tree, Random Forest y **Logistic Regression usada como clasificador**. Se prueban variantes con tres, cuatro y seis entradas, regularización y límites de complejidad. El Random Forest ganador tiene 300 árboles, profundidad máxima 5, mínimo 8 ejemplos por hoja y ponderación de clases.

La selección usa media de F1 macro en cinco particiones estratificadas; desempates: media de exactitud balanceada, menos entradas, menor complejidad y orden de inscripción. El escalado logístico se ajusta dentro de cada partición, mediante Pipeline. La elección se guarda antes de reevaluar 2024; no se modifican los parámetros con esa reevaluación.

Esta validación es entre comunas de un período, no entre futuros períodos. Las 314 observaciones no se convierten en 1.570 muestras independientes por pasar cinco veces por CV.

El modelo futuro se ajusta con 314 ejemplos de 2002–2017 y 316 de 2017–2024. Las comunas se repiten entre intervalos. Se conserva por separado el modelo histórico; las métricas de su reevaluación no son métricas del modelo futuro en 2031.

## Recuperación de las dos comunas

Las fuentes son [INE, censos y REDATAM](https://www.ine.gob.cl/estadisticas-por-tema/demografia-y-poblacion/censo-de-poblacion-y-vivienda), [actualización de DPA de 2002 y 2017 comunicada el 12-09-2018](https://www.ine.gob.cl/sala-de-prensa/prensa/general/noticia/2019/09/16/ine-actualiza-informaci%C3%B3n-de-censo-2017-a-la-nueva-divisi%C3%B3n-pol%C3%ADtica-administrativa-incorporando-la-nueva-regi%C3%B3n-de-%C3%B1uble), [Ley 19.391](https://www.bcn.cl/leychile/Navegar?idNorma=30758) y [Ley 20.578](https://www.bcn.cl/leychile/navegar?idNorma=1038291).

REDATAM ya entrega ambas comunas separadas en 1992. Padre Las Casas fue creada legalmente en 1995; la tabla es retrospectiva. La Ley 20.578 trasladó un sector desde Freire en 2012. Se usa la publicación actual de 2002 y las observaciones de 2017/2024. **No se usa 1992 en la historia de Padre Las Casas**, ni se suman habitantes de San Ramón manualmente.

La publicación del INE apoya la recuperación con DPA actualizada; esto no sustituye una auditoría cartográfica exhaustiva. El documento territorial del MMA de 2015 se conserva como evidencia de límites, **sin usar cifras de 2012 como observaciones del modelo**.

Se utiliza población residente habitual con comuna identificada. En 2017 puede diferir de las personas censadas físicamente en un lugar. Padre Las Casas tiene **74.911 residentes identificados** en la tabla de comparación, frente a 76.126 personas censadas allí. En 2024 la tabla oficial utilizada entrega 80.656. Cobertura y no respuesta importan, especialmente cerca del umbral. No se imputan personas sin comuna conocida.

Temuco y Padre Las Casas no se usaron para ajustar o elegir el modelo histórico. Ambas reciben clasificaciones individuales. En la reevaluación adicional el Random Forest falla en Temuco y acierta en Padre Las Casas; son solo dos casos, no una validación local suficiente.

## Reproducir y verificar

Entorno probado: Python 3.12.14 y dependencias fijadas en requirements.txt.

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python experiments/descargar_crecimiento.py
python experiments/descargar_fuentes_v2.py
python experiments/crecimiento_v2.py
python experiments/generar_notebook_crecimiento_v2.py
python -m unittest discover -s tests -v
~~~

La tubería v2 requiere los perfiles y calidad de la primera prueba conservados en results/crecimiento_censal/. En una reconstrucción completamente limpia, ejecutar primero el protocolo original con experiments/crecimiento_censal.py. Eso reproduce decisiones fijadas; no autoriza ajustar v1 con el resultado final ya conocido.

Los descargadores reutilizan archivos existentes, registran parámetros y hashes y conservan los tabulados. No se descargan datos privados ni proyecciones para construir respuestas. El manifiesto de evidencia territorial es independiente del manifiesto censal.

El notebook v2 ejecuta CV del ganador, reproduce el ajuste histórico y el futuro por separado y contrasta ambos con sus clasificadores guardados. Incluye todos los candidatos, fuentes, EDA, recuperación y errores. Con la aplicación activa:

~~~bash
node tests/test_availability.mjs
~~~

Las pruebas verifican temporalidad de entradas, reserva por comuna, selección por CV, escalado dentro del ajuste, reproducción de ambos modelos, métricas independientes, residencia oficial de 2017, recuperación individual, hashes y consultas inválidas. El script Node consulta las 316 comunas en ambos modos y rechaza las excluidas.

## Archivos y estado

- experiments/protocolo_crecimiento_v2.json: decisiones de esta versión.
- experiments/estudio_crecimiento_v2.ipynb: notebook ejecutado.
- results/crecimiento_v2/: datos, selección, modelos, comparación y auditoría.
- results/crecimiento_v2/clasificador_historico.joblib: ajuste con respuestas hasta 2017.
- results/crecimiento_v2/clasificador_futuro.joblib: ajuste con respuestas hasta 2024.
- docs/propuesta.md: propuesta académica actualizada.
- docs/licencia_datos.md: atribución y transformaciones.

La recuperación cartográfica completa, la utilidad futura y la revisión académica están pendientes. El trabajo sigue individual y tutorado, con fecha de entrega anticipada por acordar. La propuesta se registró en la planilla del curso el 13 de octubre de 2026; ese registro no constituye aprobación del profesor.

V1 está conservada en archive/crecimiento_v1/; su notebook y resultados originales permanecen en experiments/estudio_crecimiento_censal.ipynb y results/crecimiento_censal/. Para abrir su interfaz: python3 archive/crecimiento_v1/app/server.py --port 8789. Las asociaciones anteriores se conservan en archive/censo_asociaciones/ y la prueba veterinaria en archive/veterinaria/.

## Intento de tuning adicional

Se registró otra búsqueda después de observar v1 y v2: 19 configuraciones de Random Forest, Logistic Regression y Gradient Boosting, con nueve cortes de clasificación (171 combinaciones). La respuesta sigue siendo crecimiento ≥1% anual. Selección y ajuste del corte utilizan únicamente respuestas hasta 2017; no se interpreta el score como certeza individual.

La validación anidada utiliza cinco particiones externas y cuatro internas. Cada comuna externa queda fuera del ajuste y de la elección de parámetros de su partición. F1 macro conjunto externo: tuning 0,749, v2 fijo 0,759, continuidad 0,759. Es una comparación entre comunas de 2002–2017, no una prueba temporal futura, y estos datos ya participaron en versiones previas.

La elección final por cinco particiones fue un Random Forest de 300 árboles, profundidad máxima 8, hoja mínima 5, sin pesos de clase, con corte de score 0,45. La elección quedó guardada antes de reevaluar 2024. El corte del Random Forest v2, como alternativa predefinida que solo cambia ese corte, quedó en 0,65.

| Enfoque | Aciertos en las mismas 314 comunas | F1 macro |
|---|---:|---:|
| V2 conservado | 205 | 0,642 |
| Parámetros y corte ajustados | 193 | 0,614 |
| Solo corte de v2 | 201 | 0,606 |
| Continuidad anterior | 213 | 0,663 |

El tuning no mejoró. La aplicación conserva las predicciones v2 e incorpora el informe de este intento. No se siguen ajustando otros parámetros después de conocer esta reevaluación, que permanece exploratoria porque 2024 ya había sido observado. El modelo experimental de tuning para 2031 se guarda por separado; no reemplaza el modelo futuro v2 ni se considera verificado.

Reproducir búsqueda y notebook:

```bash
.venv/bin/python experiments/tuning_crecimiento.py
.venv/bin/python experiments/generar_notebook_tuning.py
.venv/bin/python -m unittest discover -s tests -p 'test_tuning.py' -v
```

Protocolo: `experiments/protocolo_tuning_crecimiento.json`. Notebook: `experiments/estudio_tuning_crecimiento.ipynb`. Tablas de las 171 combinaciones, scores fuera del ajuste, particiones anidadas, selección cerrada y clasificadores separados: `results/tuning_crecimiento/`. Hashes de los artefactos v2 conservados: `procedencia_v2.json`.

Método: [ajuste del corte con validación, scikit-learn 1.7](https://scikit-learn.org/1.7/modules/classification_threshold.html). La selección interna y la evaluación externa tienen funciones distintas; mejorar la métrica interna no demuestra una mejora temporal.
