# Propuesta: acceso digital y condiciones habitacionales de hogares chilenos

Se propone una aplicación web para explorar asociaciones entre el acceso a internet fija y computador y las condiciones del hogar y su vivienda, usando microdatos oficiales del Censo 2024 del INE. El proyecto se desarrolla individualmente, en modalidad tutorada con **Pablo Valenzuela**, con seguimiento por correo y entrega anticipada. La fecha concreta queda pendiente de documentar.

## Pregunta y utilidad

¿Qué condiciones habitacionales aparecen asociadas con disponer o no disponer de internet fija y computador, y cómo cambia esa relación entre regiones?

La aplicación permite a estudiantes, investigadores y personas interesadas en datos públicos consultar contextos definidos por una o dos condiciones, con evidencia cuantitativa y procedencia. Su utilidad prevista es explorar diferencias de acceso digital y formular preguntas para estudios posteriores. Esa utilidad debe revisarse académicamente; no se afirma novedad por el tamaño de la base.

Se estudian dos dimensiones específicas del acceso digital. No disponer de internet fija no equivale a carecer de internet móvil o satelital, y el censo no permite inferir automáticamente calidad de conexión ni motivos de uso.

## Datos y unidad de análisis

Se utilizan las [bases oficiales de hogares y viviendas](https://censo2024.ine.gob.cl/resultados/) y el [manual de uso de microdatos](https://censo2024.ine.gob.cl/wp-content/uploads/2025/12/manual_uso_microdatos_censo2024.pdf). Cada transacción es un hogar particular identificado por `(id_vivienda, id_hogar)`. La unión con viviendas se hace por `id_vivienda`, muchos a uno, con controles de llaves y geografía.

De 6.596.527 hogares particulares quedan **6.581.257 casos completos** en siete variables, distribuidos en las 16 regiones. Se excluyen 15.270 hogares por información incompleta. Se revisan área urbana/rural, tenencia, tipología del hogar, fuente de agua, hacinamiento de la vivienda, disponibilidad de computador e internet fija. Se distinguen no respuesta y respuestas negativas.

No se requieren registros reales de CliniPets. El trabajo veterinario anterior queda conservado como prueba histórica y deja de ser el tema activo.

## Técnica y evaluación

La técnica es **reglas de asociación**, mediante Apriori, comparando dos configuraciones de soporte y confianza. Las cinco variables de contexto integran antecedentes de hasta dos condiciones; las dos variables de acceso digital integran consecuentes. Se evita minar relaciones entre componentes de un indicador y su propia fórmula.

El protocolo se fijó antes del experimento. Se divide por vivienda en descubrimiento, selección y prueba interna, manteniendo juntos a hogares que comparten vivienda. La configuración se elige por cobertura de categorías consecuentes, proporción de reglas estables y simplicidad. La evaluación usa soporte, confianza, lift, recuentos y pertinencia, con auditoría territorial. La prueba no interviene en la elección ni el orden de reglas.

La comparación inicial produjo 48 candidatas para la configuración amplia y 17 para la conservadora; ambas mantuvieron todas sus reglas en selección y cubrieron cuatro categorías consecuentes. Se eligió la amplia por el desempate predefinido de menor longitud media del antecedente. Los resultados se mantuvieron próximos en la partición de prueba, con variación máxima de confianza de 0,94 puntos porcentuales.

Esta prueba procede del mismo censo y es transversal. No acredita validez causal ni generalización a otros años. Ocho reglas nacionales tienen lift menor que 1 en alguna región; por eso se muestran métricas del territorio seleccionado y su frecuencia basal.

## Función principal y resultados

La persona busca y elige una combinación disponible de una o dos condiciones del hogar o la vivienda y un territorio. Un combobox con búsqueda por palabras muestra cada condición completa y conserva visible el contexto elegido. Las combinaciones se obtienen de las reglas publicadas y solo se ofrecen aquellas con resultados en el territorio; las regiones también se limitan según la combinación actual. La aplicación devuelve las reglas nacionales seleccionadas para ese antecedente exacto, con métricas calculadas sobre todos los hogares completos del territorio, junto con la evidencia de las tres particiones nacionales.

Un ejemplo: de 194.148 hogares rurales unipersonales completos, 172.325 declararon no disponer de internet fija. El prototipo muestra tanto ese 88,8% como la frecuencia basal del resultado, el soporte y el lift, para evitar confundir una proporción alta con un patrón generalizable a cualquier región.

La interfaz permite seleccionar únicamente combinaciones y territorios con reglas disponibles. Las consultas regionales requieren al menos 100 antecedentes. La aplicación no asigna etiquetas de pobreza ni decide acceso a beneficios o prioridades de intervención.

## Entregables y revisión pendiente

Se dispone de notebook ejecutado de EDA y experimento, protocolo, fuentes con hashes, comparación de configuraciones, resultados agregados, contraste independiente de una regla y aplicación local funcional. Las pruebas verifican la lógica científica y las consultas HTTP.

Los datos y derivados llevan atribución INE, indicación de cambios y licencia CC BY-SA 4.0. Se respetan las condiciones oficiales de no reidentificación. La aplicación muestra resultados agregados.

La propuesta queda lista para **revisión de Pablo Valenzuela** sobre técnica, pertinencia, alcance y calendario individual. La consigna general exige aprobación en P0 y remite a requisitos específicos de entregas que aún no están disponibles. Este prototipo aporta evidencia de factibilidad; no sustituye esa aprobación.
