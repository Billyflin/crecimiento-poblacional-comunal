# Hogares de Chile: acceso digital y condiciones habitacionales

Aplicación académica para explorar asociaciones entre las condiciones de los hogares y sus viviendas y la disponibilidad de internet fija y computador. Usa microdatos oficiales del **Censo 2024 del INE**, con **6.581.257 hogares particulares utilizables** de las 16 regiones. El proyecto se desarrolla individualmente en modalidad tutorada con **Pablo Valenzuela**.

La aplicación muestra 48 reglas seleccionadas mediante una comparación de dos configuraciones de Apriori. Permite consultar una o dos condiciones y cambiar entre Chile y una región, con recuentos, soporte, confianza, frecuencia basal y lift del territorio. Son resultados descriptivos de 2024.

## Abrir la aplicación

Desde la raíz, con Python 3:

```bash
python3 app/iniciar.py --port 8787
```

Abrir <http://127.0.0.1:8787/>. Buscar «rural unipersonal» y elegir la combinación, o pulsar «Probar un ejemplo». El servidor usa la biblioteca estándar y el modelo generado; no necesita instalar las bibliotecas de análisis. Escucha exclusivamente en la interfaz local.

El comando deja el servidor en segundo plano, separado de la terminal que lo inicia. Si ya está activo, reutiliza la aplicación. Los registros se guardan en `.runtime/servidor-8787.log`. Después de reiniciar el computador, ejecutar el comando de nuevo. Para trabajar con el servidor en primer plano, usar `python3 app/server.py --port 8787` y mantener esa terminal abierta.

Una consulta usa un antecedente exacto de una o dos categorías de variables diferentes. El combobox permite buscar varias palabras en cualquier orden, con o sin tildes; muestra cada condición completa en su propia fila. Solo ofrece combinaciones con resultados en el territorio, incluidas aquellas que solo existen para dos condiciones juntas. También se deshabilitan regiones sin resultados para la combinación actual. Escribir no cambia la selección: hay que elegir una opción con un clic o con las flechas y Enter; Escape cierra la lista. El contexto elegido queda visible completo. Las otras condiciones quedan sin especificar. Las reglas se eligieron a nivel nacional; el filtro regional recalcula sus métricas desde los agregados de cada región, sin afirmar que una regla nacional conserve el mismo sentido en todas ellas. Se requieren al menos 100 antecedentes para mostrar una regla regional.

El comportamiento de teclado y las referencias ARIA se basan en el [patrón de combobox de W3C/WAI](https://www.w3.org/WAI/ARIA/apg/patterns/combobox/). La búsqueda filtra opciones publicadas; el texto libre no se envía al modelo.

## Datos y preparación

Fuentes: [resultados oficiales del Censo 2024](https://censo2024.ine.gob.cl/resultados/) y [manual de uso y diccionario](https://censo2024.ine.gob.cl/wp-content/uploads/2025/12/manual_uso_microdatos_censo2024.pdf). Se descargaron las bases CSV comprimidas de hogares y viviendas, conservadas intactas en `data/raw/ine/`. El manifiesto `fuentes.json` registra enlaces, fecha, bytes reales y SHA-256. Los tamaños anunciados por el catálogo pueden diferir de los archivos actuales.

El XLSX del diccionario enlazado en el catálogo respondió 404 durante la descarga. Se utilizó el diccionario incluido en el manual PDF oficial; la incidencia quedó registrada y no impidió procesar los CSV.

| Paso | Registros |
| --- | ---: |
| Filas del archivo de hogares | 6.622.597 |
| Operativos distintos de vivienda particular, excluidos | 26.070 |
| Hogares particulares, `tipo_operativo == 2` | 6.596.527 |
| Hogares excluidos por información incompleta | 15.270 |
| Hogares completos utilizados | **6.581.257** |

Cada transacción es un hogar identificado por `(id_vivienda, id_hogar)`. No equivale a una persona ni a una vivienda: distintas familias pueden compartir una vivienda. La base de viviendas contiene 7.664.466 registros, incluidos identificadores de otros operativos. La unión es muchos a uno por `id_vivienda`, con verificación de unicidad, referencia, región, área y operativo. No se detectaron hogares duplicados ni referencias sin vivienda.

Se usan siete variables:

| Variable | Procedencia | Uso |
| --- | --- | --- |
| `area` | Hogares | Área urbana o rural |
| `p12_tenencia_viv` | Hogares | Tenencia de la vivienda |
| `tipologia_hogar` | Hogares | Tipo de hogar |
| `p6_fuente_agua` | Viviendas | Fuente principal de agua |
| `indice_hacinamiento` | Viviendas | Índice censal de hacinamiento |
| `p15b_serv_compu` | Hogares | Disponibilidad de computador |
| `p15d_serv_internet_fija` | Hogares | Disponibilidad de internet fija |

Las cinco primeras variables pueden formar antecedentes y las dos últimas son consecuentes. Se conservan las categorías del diccionario. NA, -99 y otros valores fuera del rango válido se excluyen mediante filtro conjunto de casos completos; no se convierten en «No». Las ausencias por variable se solapan. Los resultados corresponden a esos casos completos, no automáticamente a todos los hogares del país.

No se minan asociaciones entre componentes y el indicador derivado de hacinamiento, ni entre las dos preguntas de acceso digital. No se utilizan identificadores, ingresos inferidos ni registros personales de CliniPets.

## Experimento y resultados

El [protocolo](experiments/protocolo_censo_2024.json) se definió antes de ejecutar la minería. La división se hace mediante hash determinista de vivienda, manteniendo juntos a los hogares de una misma vivienda:

| Etapa | Hogares |
| --- | ---: |
| Descubrimiento, aproximadamente 70% | 4.606.525 |
| Selección, aproximadamente 15% | 988.197 |
| Prueba interna, aproximadamente 15% | 986.535 |

Apriori cuenta perfiles categóricos ponderados de todos los hogares, sin expandir millones de filas a una matriz de indicadores. La poda excluye conjuntos de categorías mutuamente incompatibles y limita el antecedente a dos variables. Una segunda condición debe mejorar la confianza al menos 5 puntos frente a cada condición por separado.

| Configuración | Soporte mínimo | Confianza mínima | Candidatas | Superan selección |
| --- | ---: | ---: | ---: | ---: |
| Amplia | 0,5% | 40% | 48 | 48 |
| Conservadora | 2% | 60% | 17 | 17 |

Se exige lift de descubrimiento >=1,2. En selección, soporte >=0,3%, lift >=1,15, al menos 1.000 antecedentes, confianza a no más de 5 puntos por debajo del umbral de su configuración y diferencia de confianza <=5 puntos respecto al descubrimiento.

Ambas configuraciones cubrieron las cuatro categorías de acceso digital y retuvieron todas sus candidatas. La amplia ganó el desempate predefinido por menor longitud media del antecedente: 1,479 frente a 1,529. Es una elección metodológica del protocolo, no una demostración de superioridad general. La elección y el orden de reglas quedaron guardados antes de calcular métricas de prueba.

La máxima variación absoluta de confianza entre descubrimiento y prueba fue de **0,94 puntos porcentuales**. El lift mínimo de prueba fue 1,1999. Ninguna regla se filtró ni reordenó con esa prueba. Todas las particiones pertenecen al mismo censo; esta evaluación no acredita generalización temporal ni externa.

Como ejemplo descriptivo, entre **194.148 hogares rurales unipersonales completos**, **172.325 no disponían de internet fija**: confianza 88,8% y lift nacional 2,50. Su ausencia no implica ausencia de internet móvil o satelital. Un recuento independiente mediante merge de los CSV originales confirmó esa regla para Chile y las 16 regiones.

Ocho reglas nacionales tienen lift <1 en al menos una región con 100 o más antecedentes. Esta diferencia fundamenta mostrar frecuencias basales y resultados territoriales. No prueba una explicación causal ni una paradoja de Simpson.

## Reproducir el estudio

Entorno probado: Python 3.12.14, pandas 2.2.3, NumPy 2.3.5 y openpyxl 3.1.5. Usar un entorno virtual propio; no modificar entornos compartidos.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python experiments/descargar_censo.py
python experiments/censo_2024.py
python experiments/verificar_recuento_censo.py
python experiments/generar_notebook_censo.py
python -m unittest discover -s tests -v
```

Los ZIP oficiales ocupan aproximadamente 101 MB en conjunto; se leen directamente por bloques. No se descargó la base de personas. El procesamiento no toma una muestra reducida: utiliza todos los hogares completos. Los ZIP se excluyen de Git y pueden descargarse de nuevo con el script.

El notebook `experiments/estudio_censo_2024.ipynb` contiene procedencia, EDA, calidad, exclusiones, variables, alternativas, selección, prueba y heterogeneidad regional. Sus siete celdas Python fueron ejecutadas al generarlo mediante `exec` y captura de stdout, sin kernel Jupyter. Por defecto carga resultados existentes; `REGENERAR = True` vuelve a ejecutar el procesamiento completo.

Las 11 pruebas verifican métricas con ejemplos manuales, Apriori frente a búsqueda exhaustiva, separación por vivienda, coherencia de agregados, consultas nacionales y regionales, combinaciones inválidas y límites de archivos de la API. El contraste independiente de CSV está en un script adicional, reproducible.

Con la aplicación activa, `node tests/test_availability.mjs` verifica que todas las opciones habilitadas devuelvan reglas y que las deshabilitadas no las devuelvan: 544 consultas, 32 combinaciones y 17 territorios. Esta comprobación de la interfaz requiere Node.js con soporte de `fetch`; se ejecutó con Node.js 24.21.0.

## Archivos principales

- `experiments/protocolo_censo_2024.json`: decisiones previas de comparación y selección.
- `experiments/estudio_censo_2024.ipynb`: notebook ejecutado del estudio.
- `results/censo_2024/modelo.json`: reglas y agregados que consume la aplicación.
- `results/censo_2024/calidad_datos.json`: control de llaves, exclusiones y marginales.
- `results/censo_2024/seleccion_cerrada.json`: decisión sin usar la prueba.
- `results/censo_2024/reglas_candidatas.json`: todas las candidatas de ambas configuraciones.
- `results/censo_2024/reglas_por_region.csv`: métricas territoriales de reglas seleccionadas.
- `results/censo_2024/verificacion_independiente.json`: contraste contra los CSV crudos.
- `app/` y `tests/`: aplicación activa y sus pruebas.
- `docs/propuesta.md`: alcance para revisión académica.
- `docs/licencia_datos.md`: atribución y condiciones de reutilización.

## Alcance y estado académico

La primera versión censal está procesada, documentada e integrada en una aplicación local. Puede servir para explorar contextos de acceso digital y formular preguntas de investigación. No determina pobreza, necesidades de una persona, calidad de conexión ni prioridades de intervención. La cantidad de registros no garantiza utilidad o novedad, y la exclusión de casos incompletos puede sesgar perfiles particulares.

La propuesta debe revisarse con Pablo Valenzuela para confirmar técnica, alcance y calendario individual de entrega anticipada. La consigna exige aprobación en P0; el prototipo no acredita aprobación ni cumplimiento de documentos específicos de entregas que aún no constan.

El trabajo veterinario anterior permanece como prueba histórica: scripts, notebooks, fuentes y resultados originales se conservan. Su interfaz, propuesta y README se guardaron en `archive/veterinaria/`. Para abrir esa versión: `python3 archive/veterinaria/app/server.py --port 8788`. Para ejecutar sus pruebas: `python -m unittest discover -s archive/veterinaria/tests -v`. El tema activo pasó a hogares del Censo 2024.
