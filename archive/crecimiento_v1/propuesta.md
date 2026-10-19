# Propuesta: clasificación temporal de crecimiento poblacional comunal

Proyecto individual tutorado con **Pablo Valenzuela**, seguimiento por correo y entrega anticipada. La fecha concreta y la aprobación académica quedan por acordar.

## Pregunta y objetivo

¿Podemos anticipar si una comuna tendrá un crecimiento medio de al menos 1% anual durante el siguiente período intercensal, usando su población y estructura por edades iniciales?

Se propone un modelo de **clasificación supervisada**, integrado como función central de una aplicación web. El objetivo académico es preparar datos reales, definir entradas y respuesta, entrenar dos alternativas, elegir con validación temporal y medir sus errores en un período posterior reservado. La utilidad que se investiga es identificar territorios que podrían crecer más rápido como apoyo inicial a planificación. Esa utilidad necesita demostrarse frente a referencias simples.

El modelo entrega una de dos clases: crecimiento de al menos 1% anual o crecimiento menor que 1% anual, incluido decrecimiento. El umbral es un criterio operativo del proyecto fijado antes del entrenamiento. No se predice el número exacto de habitantes ni se ofrece una proyección oficial.

## Datos y unidad

Fuentes oficiales: [INE, censos y REDATAM](https://www.ine.gob.cl/estadisticas-por-tema/demografia-y-poblacion/censo-de-poblacion-y-vivienda), [resultados 2024](https://censo2024.ine.gob.cl/resultados/) y [nota técnica de comparabilidad](https://censo2024.ine.gob.cl/wp-content/uploads/2025/04/N3_Nota_Tecnica_Comparacion_Poblacion_CPV2024.pdf).

Cada ejemplo es una **comuna en un intervalo censal**. Las mismas 314 comunas aparecen en tres etapas: 942 ejemplos temporales en total, con dependencia por territorio. No se cuentan habitantes como muestras independientes.

Se utilizan residentes habituales con comuna identificada de 1992, 2002, 2017 y 2024. La reconstrucción de residencia de 2017 coincide con una segunda publicación oficial en las 346 comunas. Se documentan códigos, equivalencias ortográficas, ausencias y agregaciones de edades. Se excluyen 32 comunas por cambios territoriales conocidos o identidad ambigua; todavía debe completarse la auditoría de cartografías históricas. Se conservan datos crudos, parámetros y hashes.

## Entrenamiento, selección y prueba

Entradas: logaritmo de población inicial, proporción de menores de 15 y proporción de 65 o más. La población posterior se utiliza únicamente para construir la respuesta. Identificadores, nombres y etiquetas posteriores quedan fuera del modelo.

| Etapa | Período de crecimiento | Ejemplos |
| --- | --- | ---: |
| Entrenamiento | 1992–2002 | 314 |
| Validación para seleccionar | 2002–2017 | 314 |
| Prueba posterior a la elección | 2017–2024 | 314 |

Se comparan árbol de decisión y bosque aleatorio con configuraciones predefinidas. Se elige por F1 macro de validación, con exactitud balanceada y simplicidad como desempates. La elección se guarda antes de calcular las etiquetas de prueba de 2024. El elegido se reentrena con los 628 ejemplos de entrenamiento y validación.

Se incluyen dos referencias: clase mayoritaria y continuidad de la clase de crecimiento anterior. Esta última dispone de una tasa histórica adicional que los clasificadores de esta primera versión no reciben; su comparación permite evaluar utilidad práctica, sin concluir superioridad general de un algoritmo.

Se reportan F1 macro, exactitud balanceada, exactitud, precisión/recall/F1 por clase y matriz de confusión. La división es cronológica, sin mezcla aleatoria de años. La evaluación mide generalización temporal en comunas conocidas.

## Evidencia de la primera prueba

El bosque obtuvo F1 macro de validación 0,551 frente a 0,483 del árbol. En prueba obtuvo **0,528 y 169 aciertos de 314**. La continuidad obtuvo **0,663 y 213 aciertos**. El clasificador no supera esa referencia; la propuesta no afirma utilidad predictiva demostrada.

El resultado se conserva sin modificar entradas, umbral o parámetros a partir de la prueba. Una segunda versión requeriría otro protocolo y evaluación: el resultado de 2024 ya es conocido y no puede presentarse otra vez como prueba final intacta después de ajustar decisiones con él.

## Aplicación y entregables

La función principal permite seleccionar una comuna incluida, ver las entradas censales iniciales y generar la clasificación del modelo entrenado. La persona puede revelar después la población y clase realmente observadas para identificar el error. El selector admite búsqueda y teclado; las comunas excluidas no se ofrecen.

La interfaz muestra entrenamiento, selección, prueba, modelos comparados, referencias y errores por clase. El escenario 2024–2031 se presenta como demostración no verificada, usando el mismo modelo anterior a la prueba. Su score no es una probabilidad calibrada.

Entregables locales: notebook ejecutado en kernel Python, scripts reproducibles, protocolo y selección guardada, modelo entrenado, métricas, tablas de datos y calidad, visualización y aplicación funcional. Los tabulados y derivados incluyen atribución INE y transformaciones documentadas.

## Límites y revisión académica

Hay pocos intervalos, dependencia entre observaciones de una misma comuna, duraciones distintas, cambios metodológicos, cobertura/no respuesta y geografía parcialmente auditada. Anualizar expresa una unidad común, pero no elimina estos problemas. Esta es una reconstrucción con publicaciones actuales; no se afirma haber pronosticado 2024 en 2017.

La técnica de clasificación está entre las permitidas por la consigna. Deben revisarse pertinencia, alcance y calendario con Pablo Valenzuela. La consigna exige aprobación en P0; este prototipo documenta factibilidad y límites, sin acreditar esa aprobación ni sustituir los requisitos específicos de entrega.
