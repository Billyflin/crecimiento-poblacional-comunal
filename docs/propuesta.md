# Propuesta v2: clasificación de crecimiento comunal con historia censal

Proyecto individual tutorado con **Pablo Valenzuela**, seguimiento por correo y entrega anticipada. La fecha concreta y la aprobación académica quedan por acordar.

## Objetivo y utilidad que se investiga

Clasificar si una comuna crecerá al menos 1% anual en el período siguiente, usando información disponible al inicio: población, estructura de edades y crecimiento previo.

La aplicación integra un **clasificador supervisado entrenado**, compara sus alternativas y mide errores. Se investiga su utilidad para identificar comunas que podrían crecer rápido como apoyo inicial a revisión y planificación. La salida no estima habitantes exactos ni es una proyección oficial.

El modelo también se compara con continuar la tendencia anterior. Los desacuerdos se muestran, sin tratar coincidencias o puntajes como garantía.

## Datos y recuperación territorial

Se utilizan tabulados agregados del INE de 1992, 2002, 2017 y 2024, con residentes habituales y comuna identificada. Fuentes crudas, parámetros y hashes se conservan. No se utilizan registros privados, proyecciones como respuestas ni cifras de 2012 para entrenar.

La unidad es una comuna-período. Hay 314 comunas para entrenamiento y comparación con v1, más **Temuco y Padre Las Casas como aplicaciones individuales adicionales**. El modelo futuro se ajusta con 630 ejemplos de dos períodos; no son 630 territorios independientes.

REDATAM ya entrega Temuco y Padre Las Casas por separado en 1992. El [INE publicó la actualización de las bases de 2002 a nueva DPA](https://www.ine.gob.cl/sala-de-prensa/prensa/general/noticia/2019/09/16/ine-actualiza-informaci%C3%B3n-de-censo-2017-a-la-nueva-divisi%C3%B3n-pol%C3%ADtica-administrativa-incorporando-la-nueva-regi%C3%B3n-de-%C3%B1uble). La [Ley 19.391](https://www.bcn.cl/leychile/Navegar?idNorma=30758) creó Padre Las Casas en 1995 y la [Ley 20.578](https://www.bcn.cl/leychile/navegar?idNorma=1038291) cambió su límite con Freire en 2012. Se utiliza el tabulado actual de 2002, sin sumar personas manualmente; 1992 queda fuera de su historia utilizada.

La recuperación es preliminar y requiere completar auditoría cartográfica. La reconstrucción de residencia de 2017 coincide con otra publicación oficial en las 346 comunas. La residencia identificada puede diferir del lugar de empadronamiento; no respuesta y cobertura limitan las tasas.

## Entrenamiento, selección y temporalidad

Se registraron diez candidatos antes del entrenamiento v2: Decision Tree, Random Forest y Logistic Regression con variantes de complejidad y entradas. Se investigaron seis entradas; ganó un Random Forest con población inicial, dos proporciones de edades y crecimiento anterior.

Las entradas de entrenamiento proceden de 1992/2002; la respuesta es crecimiento 2002–2017. Se comparan cinco particiones estratificadas de las 314 comunas, reservando cada una una vez. Los transformadores se ajustan dentro de cada partición. La elección usa media de F1 macro, exactitud balanceada y simplicidad; se guarda antes de reevaluar 2024.

El modelo histórico elegido se ajusta con esas 314 respuestas hasta 2017. La reevaluación utiliza entradas 2002/2017 y respuesta de 2024. **2024 ya fue observado en v1: esta segunda evaluación es exploratoria, no una prueba final nueva e independiente.** La ampliación del modelo nace de ese diagnóstico, aunque la elección mecánica de configuración no usa etiquetas de 2024.

Para el escenario 2024–2031 se conserva la configuración y se entrena otro modelo con respuestas hasta 2024: 314 ejemplos de 2002–2017 más 316 de 2017–2024. La evaluación histórica no acredita precisión de ese ajuste en 2031.

## Evidencia y límites de utilidad

| Mismas 314 comunas, reevaluación 2017–2024 | F1 macro | Aciertos |
| --- | ---: | ---: |
| Random Forest v1 | 0,528 | 169 |
| Random Forest v2 | **0,642** | **205** |
| Continuidad anterior | **0,663** | **213** |

V2 mejora frente a v1, pero no supera la referencia. Detecta 130 de las 150 comunas de crecimiento alto, frente a 73 de continuidad, a cambio de 89 falsas alertas frente a 24. Puede interesar para detectar casos que revisar; no demuestra superioridad general ni utilidad futura. El intervalo exploratorio pareado de diferencia de F1 respecto a continuidad contiene cero.

Se documentan precision, recall y F1 por clase, exactitud balanceada, matriz de confusión y comparación pareada. El umbral y los parámetros no se cambian por los resultados de la reevaluación.

## Aplicación, entregables y revisión

La aplicación ofrece 316 comunas en comparación histórica y escenario futuro, incluyendo consultas individuales de Temuco y Padre Las Casas. Muestra entradas, clasificación, referencia de continuidad, resultado histórico revelable, procedencia territorial y diferencias entre los dos ajustes.

Se dispone de protocolo, selección cerrada, diez candidatos registrados, notebook ejecutado en kernel real, datos y calidad, clasificadores histórico/futuro separados, comparación, visualización y pruebas científicas/API. La primera prueba se conserva.

Pocos intervalos, dependencia por comuna, duraciones distintas, cobertura y geografía parcialmente auditada limitan el estudio. La validación interna es entre comunas de una etapa. El escenario futuro no tiene resultado observado.

La técnica de clasificación está entre las permitidas por la consigna. Pablo Valenzuela debe revisar pertinencia, alcance y calendario. La consigna exige aprobación en P0; el prototipo no acredita esa aprobación. La propuesta se registró en la planilla del curso el 13 de octubre de 2026, con Billy Jhon Martinez Cofre como único integrante y estado «Pendiente de revisión».

## Ajuste adicional documentado

Se añadieron 19 configuraciones de Random Forest, Logistic Regression y Gradient Boosting con nueve cortes sobre el score. El umbral de la respuesta sigue siendo crecimiento anual ≥1%. Se usa validación anidada de cinco partes externas y cuatro internas: las comunas externas quedan fuera de la elección de parámetros y corte. La elección final se realizó con respuestas hasta 2017 y se guardó antes de reevaluar 2024.

El intento obtuvo F1 macro externo 0,749, frente a 0,759 del Random Forest v2 fijo. En la reevaluación temporal exploratoria, el ajuste elegido obtuvo 193/314 aciertos y F1 0,614; v2 conserva 205/314 y F1 0,642. Cambiar solo el corte de v2 obtuvo 201/314 y F1 0,606. La continuidad conserva 213/314 y F1 0,663.

Se conserva v2 en la aplicación. El resultado negativo es parte del proceso de modelado, sin interpretar scores como certeza ni continuar ajustando contra 2024. La reevaluación sigue siendo exploratoria y el escenario 2031 no está verificado. Búsqueda reproducible, particiones, tablas de las 171 combinaciones y notebook ejecutado en `experiments/estudio_tuning_crecimiento.ipynb` y `results/tuning_crecimiento/`.
