> Copia histórica de la propuesta veterinaria anterior. El tema activo ahora es el Censo 2024 y se describe en el README de la raíz. Para abrir esta interfaz conservada, ejecutar desde la raíz `python3 archive/veterinaria/app/server.py --port 8788`. Las instrucciones y métricas siguientes describen el estado anterior.

# Explorador de corresistencia canina

Aplicación académica para consultar asociaciones entre resultados de resistencia de E. coli canina de origen urinario. Usa datos públicos de FDA Vet-LIRN y permite seleccionar antibióticos con resultado R para explorar reglas relacionadas, con sus recuentos, soporte, confianza, lift e incertidumbre.

La primera versión funciona localmente y muestra dos reglas seleccionadas entre aminoglucósidos y fluoroquinolonas. Es un estudio exploratorio con cortes históricos de laboratorio; no predice eficacia de tratamiento. El proyecto se desarrolla individualmente, en modalidad tutorada con Pablo Valenzuela.

## Abrir la aplicación

Desde la raíz del repositorio, con Python 3:

```bash
python3 app/server.py --port 8787
```

Abrir <http://127.0.0.1:8787> y pulsar «Probar ejemplo con gentamicina». El servidor usa la biblioteca estándar y el modelo ya generado: no requiere instalar bibliotecas para consultar la aplicación. Si el puerto está ocupado, elegir otro con `--port`.

Se consideran conocidas únicamente las resistencias seleccionadas. Los ítems sin marcar permanecen desconocidos. Una consulta sin reglas comunica que no existen reglas seleccionadas para esa combinación, sin inferir ausencia de resistencia. El servidor escucha solo en la interfaz local y no almacena datos de pacientes.

## Reproducir los análisis

El entorno de análisis probado es Python 3.12.14, pandas 2.2.3, NumPy 2.3.5 y openpyxl 3.1.5. En un entorno de Python 3.12, instalar `requirements.txt` y ejecutar:

```bash
python -m pip install -r requirements.txt
python experiments/primera_prueba.py
python experiments/generar_notebook.py
python experiments/estudio_corresistencia.py
python experiments/generar_notebook_estudio.py
python -m unittest discover -s tests -v
```

Los generadores ejecutan las celdas Python con captura de stdout y guardan notebooks compatibles con Jupyter. No requieren un kernel Jupyter para generar los archivos. Los notebooks cargan resultados existentes por defecto; `REGENERAR = True` vuelve a ejecutar el análisis correspondiente.

La prueba preliminar conserva su protocolo y resultados en `results/primera_prueba/`. El nuevo experimento tiene protocolo propio y escribe en `results/estudio_v1/`. Se verifican los hashes del archivo oficial, del protocolo original y de la cohorte antes del estudio. El archivo oficial permanece sin modificar.

## Datos y unidad de análisis

La fuente es el [archivo oficial de FDA Vet-LIRN 2017–2024](https://www.fda.gov/media/190321/download?attachment), documentado en la [página del programa](https://www.fda.gov/animal-veterinary/science-research/veterinary-laboratory-investigation-and-response-network). La copia se conserva en `data/raw/fda/`; su procedencia y SHA-256 están registrados en los protocolos.

El archivo contiene 550.795 ensayos de antibióticos y 27.472 identificadores de muestra. El análisis selecciona E. coli, especie canina, panel COMPGN1F y las etiquetas de origen `Urine` y `Urinary tract`. La agrupación de esas etiquetas permite incluir el cambio de nomenclatura de 2024. Tras excluir ensayos ausentes o MIC indeterminables, quedan 3.933 muestras de 25 laboratorios.

Cada transacción corresponde a un `Sample Id`. No equivale a un perro distinto. No hay identificador de paciente, desenlace ni historial terapéutico para evaluar tratamientos. La selección por casos completos puede introducir sesgo y los datos de vigilancia de Estados Unidos no representan Chile ni CliniPets.

Los cortes R se transcribieron de la tabla 30 del [informe USDA APHIS de 2020](https://usbiotechnologyregulation.mrp.usda.gov/sites/default/files/2020_APHIS_AMR_PilotProject_EOY_Report.pdf), página impresa 35, basada en CLSI VET01S 2020. Son un protocolo histórico fijo. La tabla presupone infección urinaria, mientras la base solo permite identificar origen urinario; esa diferencia es una hipótesis metodológica explícita. Los operadores de MIC se conservan: `<=16` no se sustituye por `=16`. Por debajo del corte R incluye resultados intermedios.

## Experimento y selección

La prueba preliminar descubrió reglas muy fuertes que incluían relaciones dentro de una misma familia. El estudio posterior excluye consecuentes de una familia presente en el antecedente, compara dos configuraciones de Apriori y comprueba sensibilidad al laboratorio.

| Etapa | Años | Muestras |
| --- | --- | ---: |
| Descubrimiento | 2017–2021 | 2.193 |
| Selección | 2022 | 585 |
| Comprobación exploratoria posterior | 2023–2024 | 1.155 |

Se compararon 20 reglas candidatas de la configuración amplia y 14 de la conservadora. Ambas dejaron dos reglas elegibles, que representan una dirección entre familias. Se seleccionó la conservadora por su mayor proporción de reglas que superan los mismos criterios de 2022 y laboratorio. El procedimiento se definió antes de ejecutar este estudio y no utiliza 2023–2024 para filtrar ni ordenar reglas.

En 2022, ambas reglas tienen 10 coincidencias de 18 antecedentes. En 2023–2024, gentamicina R aparece junto con enrofloxacino R en 26 de 37 antecedentes, y con marbofloxacino R en 27 de 37. Los consecuentes pertenecen a una misma familia y no son hallazgos independientes. Los intervalos son amplios: el respaldo sigue siendo limitado. Todos esos años ya se habían revisado en la prueba preliminar, por lo que esta comprobación no es una evaluación inédita ni externa.

## Archivos principales

- `experiments/primera_prueba.ipynb`: calidad de datos, cohortes y prueba inicial.
- `experiments/estudio_corresistencia.ipynb`: alternativas, criterios, reglas descartadas, selección y laboratorio.
- `experiments/protocolo_estudio_v1.json`: decisiones congeladas para el estudio.
- `results/estudio_v1/modelo.json`: modelo agregado que consume la aplicación.
- `results/estudio_v1/reglas_completas.json`: candidatas de ambas configuraciones, incluidas las descartadas.
- `results/estudio_v1/reglas_por_laboratorio.csv`: métricas por centro.
- `results/estudio_v1/exclusion_de_laboratorio.csv`: sensibilidad al excluir cada centro.
- `app/server.py` y `app/static/`: API de consulta e interfaz.
- `tests/test_contracts.py`: controles de intervalos MIC, métricas, Apriori y consultas HTTP.
- `docs/propuesta.md`: alcance para revisión del profesor.

## Estado y trabajo pendiente

Están ejecutados el estudio y los notebooks, e integrada la configuración seleccionada en un prototipo local funcional. Sigue pendiente revisar la propuesta con Pablo Valenzuela, documentar el calendario de entrega anticipada y adaptar el trabajo a los requisitos específicos de las entregas, que no están incluidos en la consigna general recibida.

La utilidad adicional para CliniPets aún debe investigarse. También falta una evaluación con datos nuevos o externos si se quiere sostener generalización, y revisar criterios vigentes y contexto clínico antes de cualquier ampliación de alcance. La primera versión permite investigar y enseñar asociaciones históricas.
