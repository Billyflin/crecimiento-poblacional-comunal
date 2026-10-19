# Propuesta de explorador de corresistencia canina

Se propone una aplicación web educativa para estudiar asociaciones entre resultados de laboratorio de E. coli canina de origen urinario. El proyecto se desarrolla de forma individual y tutorada con Pablo Valenzuela, con seguimiento por correo y entrega anticipada. La fecha concreta queda pendiente de documentar.

## Problema y público

Un antibiograma contiene varios resultados por muestra. Estudiantes de veterinaria e investigadores pueden necesitar explorar qué resistencias aparecen juntas y con cuánto respaldo, sin confundir una asociación fuerte con una predicción infalible. La aplicación reúne las reglas seleccionadas, sus métricas y la procedencia de los datos en una consulta interpretable.

Su posible reutilización en CliniPets sería un módulo educativo para explorar datos públicos. La utilidad clínica adicional permanece abierta; no se cuenta actualmente con registros reales de esa aplicación.

## Función principal

La persona selecciona antibióticos con resultado R según el protocolo del estudio y consulta otros resultados que aparecen asociados en la cohorte. La respuesta muestra el antecedente, el consecuente, las familias, los recuentos, soporte, confianza, lift, intervalos descriptivos y períodos de evaluación. Los elementos no seleccionados se consideran desconocidos.

Una consulta sin reglas muestra que la configuración seleccionada no aporta reglas para esos elementos. La aplicación no infiere susceptibilidad, mecanismo genético ni tratamiento a partir de esa ausencia.

## Datos y técnica

Se usa [FDA Vet-LIRN 2017–2024](https://www.fda.gov/animal-veterinary/science-research/veterinary-laboratory-investigation-and-response-network). Cada transacción es un identificador de muestra, con ítems de resistencia determinables en seis antibióticos. La cohorte inicial tiene 3.933 muestras de 25 laboratorios, tras aplicar un panel común y excluir ensayos ausentes o ambiguos.

La técnica es reglas de asociación, con Apriori y comparación de umbrales de soporte y confianza. Se usan cortes históricos documentados, no una guía clínica vigente. El origen urinario no confirma infección, por lo que la aplicación de los cortes elegidos constituye una hipótesis metodológica explícita.

## Evidencia de factibilidad y decisiones

La primera prueba produjo reglas dominadas por relaciones dentro de la misma familia. El segundo experimento restringe el consecuente a una familia ausente del antecedente y compara dos configuraciones con los mismos controles posteriores. Descubre en 2017–2021, selecciona con 2022 y examina 2023–2024 después de cerrar la selección. Estos últimos años ya fueron vistos en la prueba preliminar, de modo que la comprobación es exploratoria.

La configuración conservadora dejó dos reglas elegibles de 14 candidatas. Ambas describen una dirección entre familias: gentamicina hacia enrofloxacino o marbofloxacino. En 2022 se apoyan en solo 18 antecedentes; los dos consecuentes son de una misma familia. El prototipo comunica esa incertidumbre y no presenta los hallazgos como independientes ni como descubrimientos clínicos novedosos.

La selección compara cobertura de direcciones entre familias y proporción de reglas que mantienen evidencia temporal y por laboratorio. Se conservan todas las candidatas descartadas para fundamentar la elección. Los notebooks y scripts permiten reproducir el análisis y el modelo integrado.

## Alcance y revisión académica

El producto principal es un explorador de asociaciones históricas. No predice eficacia terapéutica: la fuente carece de desenlaces, historial de tratamiento e identificación de animales repetidos. Los datos son de vigilancia de Estados Unidos y no representan la población de Chile.

La propuesta debe revisarse con Pablo Valenzuela para confirmar la técnica, el alcance y el calendario individual. La consigna general establece aprobación en P0 y requisitos específicos de entregas por separado. El trabajo realizado aporta evidencia y un prototipo para esa revisión; no acredita por sí mismo aprobación ni cumplimiento de documentos de entrega que aún no constan.
