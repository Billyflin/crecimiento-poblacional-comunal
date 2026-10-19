# Anticipar crecimiento poblacional con censos de Chile

Primera prueba de **clasificación supervisada con separación temporal**, usando tabulados oficiales de los censos 1992, 2002, 2017 y 2024 del INE. Proyecto individual tutorado con **Pablo Valenzuela**, seguimiento por correo y entrega anticipada; fecha por acordar.

La pregunta es: **¿una comuna crecerá al menos 1% anual durante el período siguiente, a partir de su población y estructura por edades iniciales?** El umbral es una decisión del proyecto, no una clasificación oficial.

El modelo aprende relaciones entre tres entradas del censo inicial y una respuesta observada en el censo posterior. Puede equivocarse y sus errores se miden en otro período. Es una reconstrucción retrospectiva; no se emitieron estos pronósticos en 2017.

## Primera prueba: resultado y alcance

| Etapa | Entradas | Respuesta conocida para esa etapa | Ejemplos |
| --- | --- | --- | ---: |
| Entrenamiento | Censo 1992 | Crecimiento hasta 2002 | 314 |
| Validación y elección | Censo 2002 | Crecimiento hasta 2017 | 314 |
| Prueba posterior a la elección | Censo 2017 | Crecimiento hasta 2024 | 314 |

Cada ejemplo es una comuna en un período. Son **314 comunas repetidas en tres intervalos**, no 942 territorios independientes ni millones de habitantes usados como ejemplos. Después de elegir, se reentrenó solo la alternativa elegida con 628 ejemplos anteriores a la prueba.

Se compararon un árbol de decisión y un bosque aleatorio. El bosque ganó por F1 macro de validación: **0,551**, frente a **0,483** del árbol. Se congeló esa decisión antes de calcular las etiquetas de prueba de 2024.

| Evaluación final 2017–2024 | F1 macro | Aciertos / 314 |
| --- | ---: | ---: |
| Bosque elegido | **0,528** | **169** |
| Predecir siempre la clase mayoritaria | 0,343 | 164 |
| Continuar la clase de crecimiento anterior | **0,663** | **213** |

**Esta versión no mejora la continuidad de tendencia.** La referencia dispone del crecimiento del intervalo anterior, mientras que los clasificadores reciben solo población y edades de un censo. La comparación mide utilidad práctica; no demuestra que el algoritmo sea inferior en general. No se alteraron el umbral, las entradas o la configuración para mejorar el resultado de 2024.

La aplicación incluye un escenario **2024→2031** producido por el mismo modelo entrenado antes de la prueba. Es una demostración sin resultado observado ni validación futura. El modelo clasifica el crecimiento; **no calcula una cifra futura de habitantes** ni entrega una proyección oficial.

## Abrir la aplicación

Desde esta carpeta:

~~~bash
python3 app/iniciar.py --port 8787
~~~

Abrir [la aplicación local](http://127.0.0.1:8787/). El servidor queda en segundo plano y usa la biblioteca estándar de Python y resultados previamente calculados. No requiere instalar las bibliotecas de entrenamiento. Tras reiniciar el computador, ejecutar el comando nuevamente. Registros en .runtime/servidor-8787.log.

Pulsar **Probar Valdivia** o buscar una comuna, elegir una opción y generar la predicción. La prueba histórica muestra las entradas conocidas en 2017 y la clasificación; **Revelar el resultado de 2024** permite comprobar el acierto o error. El texto escrito debe convertirse en una selección válida. La búsqueda admite palabras sin tildes, región, clic, flechas y Enter. Las comunas excluidas no se ofrecen.

La interfaz explica el entrenamiento, la selección, la prueba, ambas clases y la matriz de confusión. El score interno se presenta como salida no calibrada, nunca como porcentaje de certeza. Los resultados agregados de prueba están visibles aunque se oculte inicialmente la respuesta individual.

## Datos y preparación

Fuentes: [censos y REDATAM del INE](https://www.ine.gob.cl/estadisticas-por-tema/demografia-y-poblacion/censo-de-poblacion-y-vivienda), [tablas del Censo 2024](https://censo2024.ine.gob.cl/resultados/) y [nota técnica sobre comparación entre censos](https://censo2024.ine.gob.cl/wp-content/uploads/2025/04/N3_Nota_Tecnica_Comparacion_Poblacion_CPV2024.pdf).

Los HTML y XLSX crudos permanecen intactos en data/raw/ine/crecimiento/. El manifiesto fuentes.json incluye enlaces, parámetros de consulta, bytes y SHA-256. Se descargaron tabulados agregados, sin registros privados de CliniPets ni microdatos individuales para este experimento.

- **1992 y 2002:** edad por comuna de residencia habitual, variable VIVEHAB.
- **2017:** suma de residentes censados en su comuna (P10=1 o 2) y residentes censados en otra comuna, agrupados por P10COMUNA. La reconstrucción coincide exactamente con otra publicación oficial en las **346 comunas**.
- **2024:** población y edades por comuna; el censo usa residencia habitual.

Se excluyen categorías sin comuna identificada; no se imputa residencia. El guion de una celda de frecuencia de REDATAM se interpreta como cero casos. Se comprueban las sumas por edad. La etiqueta anómala 85–99 de 2017 se documenta: al sumar todas las categorías de 65 o más, no se duplican recuentos.

La unión utiliza códigos comprobados y equivalencias ortográficas explícitas. Se excluyen comunas nuevas y sus territorios de origen, cambios de límites conocidos y Caldera/Calera por una etiqueta duplicada en 1992. **Quedan 314 comunas tras 32 exclusiones. Falta certificar todos los límites con cartografías históricas**, por lo que la equivalencia territorial es preliminar. No se atribuyen divisiones administrativas conocidas a crecimiento demográfico.

## Modelo y entrenamiento

Las entradas son log(1 + población inicial), proporción de menores de 15 y proporción de 65 o más. Nombre, código, región, año final, población final y crecimiento del período no ingresan al clasificador. No se necesitan imputación o escalado; no se ajusta una transformación con datos futuros.

La respuesta es:

~~~text
tasa_anual = (poblacion_final / poblacion_inicial) ** (1 / años) - 1
clase = 1 si tasa_anual >= 0.01; clase = 0 en otro caso
~~~

Los períodos duran 10, 15 y 7 años. La anualización da una unidad común, pero no elimina diferencias entre épocas y horizontes.

Alternativas definidas antes del entrenamiento:

- Árbol: profundidad máxima 3, mínimo 15 ejemplos por hoja, ponderación de clases.
- Bosque: 300 árboles, profundidad máxima 5, mínimo 8 por hoja, ponderación de clases.
- Semilla 2024 en ambos; selección por F1 macro de validación, exactitud balanceada y simplicidad en caso de empate.

El árbol aprende umbrales sobre las entradas. El bosque combina árboles entrenados con muestras y subconjuntos de variables. El ajuste utiliza las respuestas históricas; la aplicación consulta las salidas del clasificador entrenado. La comparación contiene también las referencias mayoritaria y de persistencia. Se reportan exactitud, F1 macro, exactitud balanceada, precisión/recall/F1 por clase y matriz de confusión.

El protocolo está en experiments/protocolo_crecimiento.json. Su hash y la elección se conservan en results/crecimiento_censal/seleccion_cerrada.json. La tabla de 2024 se descargó previamente, pero sus etiquetas no se calcularon para seleccionar el modelo. La identidad comunal publicada en 2024 se usa como metadato de unión. Se utiliza la publicación disponible hoy para una evaluación retrospectiva; no se afirma reproducir todos los datos que estaban publicados en 2017.

## Reproducir

Entorno probado: Python 3.12.14; versiones fijadas en requirements.txt. Crear un entorno propio:

~~~bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python experiments/descargar_crecimiento.py
python experiments/crecimiento_censal.py
python experiments/generar_notebook_crecimiento.py
python -m unittest discover -s tests -v
~~~

El descargador reutiliza los archivos existentes y registra sus hashes. Las consultas REDATAM se realizan secuencialmente porque el servicio genera archivos temporales. El procesamiento reproduce el protocolo original; **2024 ya fue observado**, por lo que una nueva selección tras ver sus resultados sería exploratoria y requeriría otra estrategia de evaluación.

El notebook experiments/estudio_crecimiento_censal.ipynb está ejecutado con un kernel Python real. Contiene EDA, fuentes, exclusiones, separación temporal, entrenamiento de las dos alternativas, comparación y resultados. Por defecto carga los datos procesados y reproduce la comparación de validación; REGENERAR=False evita volver a ejecutar toda la tubería.

Las pruebas contrastan las salidas publicadas con el clasificador guardado, comprueban las tasas y métricas con cálculos independientes, las exclusiones, la selección congelada y las consultas HTTP. Con la aplicación activa:

~~~bash
node tests/test_availability.mjs
~~~

Este comando consulta las 314 comunas en ambos modos y comprueba que las excluidas sean rechazadas.

## Archivos y continuación

- experiments/estudio_crecimiento_censal.ipynb: notebook ejecutado.
- results/crecimiento_censal/resumen.json: comparación y métricas.
- results/crecimiento_censal/clasificador.joblib: bosque entrenado.
- results/crecimiento_censal/modelo.json: resultados que consume la aplicación.
- results/crecimiento_censal/perfiles_censales.csv: perfiles de los cuatro censos.
- results/crecimiento_censal/calidad_datos.json: verificación de 2017 y exclusiones.
- results/crecimiento_censal/evaluacion.png: comparación y matriz.
- results/crecimiento_censal/arbol_comparacion.txt: árbol didáctico de la alternativa; no explica el bosque elegido.
- docs/propuesta.md: propuesta para revisión académica.
- docs/licencia_datos.md: atribución y transformaciones.

La primera prueba aporta un proceso reproducible y evidencia de sus límites. Una próxima versión podría incorporar crecimiento previo, más períodos y variables pertinentes. Antes habría que fijar otro protocolo y otra evaluación; reutilizar 2024 para ajustar y comprobar no sería una prueba final independiente. La aprobación de P0 y el calendario individual deben acordarse con Pablo Valenzuela; no se han enviado comunicaciones.

La versión de asociaciones se conserva en archive/censo_asociaciones/ y sus scripts/resultados originales permanecen disponibles. Para abrir su interfaz: python3 archive/censo_asociaciones/app/server.py --port 8788. La versión veterinaria se conserva en archive/veterinaria/ y puede abrirse en otro puerto. El proyecto activo es la clasificación temporal de crecimiento.
