# Atribución y reutilización de datos censales

Fuente: **Instituto Nacional de Estadísticas de Chile (INE), Censos de Población y Vivienda 1992, 2002, 2017 y 2024**. Los experimentos predictivos utilizan tabulados agregados de [REDATAM](https://redatam-ine.ine.cl/) y [tablas oficiales del Censo 2024](https://censo2024.ine.gob.cl/resultados/). Archivos, enlaces, consultas, bytes y hashes constan en data/raw/ine/crecimiento/fuentes.json.

Las [condiciones de uso y licencia de datos abiertos del INE](https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos) establecen atribución bajo **Creative Commons Atribución-CompartirIgual 4.0 Internacional** ([CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)) y prohíben intentar identificar o reidentificar a personas o entidades presentes en los datos.

Al compartir derivados corresponde reconocer al INE, enlazar la licencia, indicar los cambios y mantener la misma licencia para las adaptaciones de datos. No debe sugerirse respaldo institucional.

## Transformaciones del estudio activo

Se reconstruyó la residencia habitual de 2017 sumando dos tabulados; se agruparon edades, aplicaron equivalencias ortográficas explícitas y unieron censos por identidad comunal comprobada. Se excluyeron categorías sin comuna identificada y comunas con cambios territoriales conocidos o identidad ambigua. Se calcularon tasas anuales, clases de crecimiento, entradas numéricas, predicciones y métricas. No se imputaron residentes desconocidos ni se usaron proyecciones como observaciones.

Los **derivados de datos de results/crecimiento_censal/** llevan atribución bajo CC BY-SA 4.0. La procedencia y transformaciones se muestran en la aplicación y el notebook. Esta declaración cubre datos y derivados; no establece por sí sola una licencia para el código.

Atribución breve: «Fuente: INE, Censos de Población y Vivienda 1992, 2002, 2017 y 2024. Procesamiento propio: reconstrucción de residencia, unión de tabulados, exclusiones, tasas y clasificación. Derivados de datos bajo CC BY-SA 4.0. Proyecto académico independiente».

## Estudio anterior conservado


## Versión 2 y evidencia territorial

Se añadió crecimiento anterior y cambios anuales de proporciones de edad como entradas candidatas, comparación por validación entre comunas, recuperación preliminar de Temuco y Padre Las Casas y ajuste separado de un modelo futuro. Los derivados censales de results/crecimiento_v2/ mantienen atribución INE bajo CC BY-SA 4.0. La base anterior no se reemplaza.

Los documentos del INE, BCN y MMA usados para verificar geografía se identifican como fuentes de evidencia en data/raw/ine/crecimiento/fuentes_territoriales_v2.json. La declaración de licencia de datos del INE no se extiende automáticamente a documentos de otros organismos. El documento MMA se utiliza solo como antecedente territorial; sus cifras de 2012 no forman parte del modelo.
