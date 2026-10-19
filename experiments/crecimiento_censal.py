"""Primera prueba temporal de clasificación de crecimiento poblacional."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from hashlib import sha256
from io import StringIO
import json
from pathlib import Path
import re
import unicodedata

import numpy as np
import pandas as pd
from openpyxl import load_workbook
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import classification_report, confusion_matrix, balanced_accuracy_score, f1_score, accuracy_score
from sklearn.tree import DecisionTreeClassifier, export_text

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/ine/crecimiento'
OUT = ROOT / 'results/crecimiento_censal'
PROTOCOL = ROOT / 'experiments/protocolo_crecimiento.json'
FEATURES = ['log_poblacion', 'proporcion_menores_15', 'proporcion_65_mas']
LABELS = ['Menor que 1% anual', 'Al menos 1% anual']

# Equivalencias ortográficas explícitas; nunca emparejar automáticamente por
# similitud. El control independiente de 2017 usa el código comunal del INE.
ALIASES = {'coihaique': 'coyhaique', 'aisen': 'aysen', 'cisne': 'cisnes',
           'treguaco': 'trehuaco', 'paiguano': 'paihuano', 'navarino': 'cabodehornos'}

# Exclusión conservadora de comunas nuevas y sus territorios de origen, más
# transferencias de límites documentadas. No se atribuye una caída administrativa
# a un cambio demográfico. No es una certificación cartográfica exhaustiva.
EXCLUSION_GROUPS = [
    ('Creación o división comunal 1994–1996; geografía histórica pendiente de certificar',
     ['Concón', 'Viña del Mar', 'Padre Hurtado', 'Peñaflor', 'Chillán Viejo', 'Chillán',
      'San Rafael', 'Pelarco', 'San Pedro de La paz', 'Chiguayante', 'Concepción', 'Padre Las Casas', 'Temuco']),
    ('Creación de comunas en 2004 y sus comunas de origen',
     ['Alto Hospicio', 'Iquique', 'Hualpén', 'Talcahuano', 'Cholchol', 'Nueva Imperial', 'Alto Biobío', 'Santa Bárbara']),
    ('Cambios de límites de Ley 20.578 (2012)',
     ['Punitaqui', 'Combarbalá', 'Puerto Varas', 'Puerto Montt', 'Padre Las Casas', 'Freire', 'Puente Alto', 'La Pintana']),
    ('Cambio de límite de Ley 20.721 (2014)', ['Vicuña', 'Paihuano']),
    ('Dos etiquetas Caldera en REDATAM 1992; no corregir ni unir por conjetura', ['Caldera', 'Calera']),
]


def dump(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')


def normalize(value):
    ascii_text = unicodedata.normalize('NFD', str(value)).encode('ascii', 'ignore').decode().lower()
    key = re.sub('[^a-z0-9]', '', ascii_text)
    return ALIASES.get(key, key)


def integer(value):
    # REDATAM representa una celda sin casos como guion, no como dato faltante.
    text = str(value).strip()
    if text in ('-', '–'):
        return 0
    if not re.fullmatch(r'[0-9\s,]+', text):
        raise ValueError(f'Recuento no interpretable: {value!r}')
    return int(re.sub(r'[\s,]', '', text))


def territories():
    # Esta función solo lee identidad y metadatos; no lee cifras de 2024.
    workbook = load_workbook(RAW / 'poblacion_2024.xlsx', read_only=True, data_only=True)
    rows = []
    for row in workbook['2'].iter_rows(min_row=6, values_only=True):
        if isinstance(row[4], int) and row[4] > 0:
            rows.append({'code': row[4], 'name': row[5], 'region': row[1], 'region_code': row[0], 'key': normalize(row[5])})
    workbook.close()
    assert len(rows) == 346 and len({r['key'] for r in rows}) == 346
    return {r['key']: r for r in rows}


def redatam(year, local=False):
    path = RAW / (f'edad_local_{year}.html' if local else f'edad_residencia_{year}.html')
    table = pd.read_html(StringIO(path.read_text(encoding='utf-8-sig')), thousands=',')[0]
    header = next(i for i in table.index if (table.loc[i].astype(str) == '0-4').any())
    start = next(c for c in table.columns if str(table.at[header, c]) == '0-4')
    columns = [c for c in table.columns if c >= start and re.match(r'^\d+', str(table.at[header, c]))]
    records = []
    for i in range(header + 1, len(table)):
        name = table.at[i, start - 1]
        if pd.isna(name) or str(name) == 'Total':
            continue
        values = table.loc[i, columns]
        if values.isna().any():
            continue
        if str(name).startswith(('Fuente:', 'Procesado con', '2017. CELADE', '1992. CELADE', '2002. CELADE')):
            continue
        counts = [integer(v) for v in values]
        total = sum(counts)
        # En CrossTab el último campo es el total; comprobación independiente de
        # la suma. AreaList tiene solamente categorías de edad.
        if not local:
            assert total == integer(table.at[i, max(columns) + 1]), (year, name)
        young = sum(n for c, n in zip(columns, counts) if int(re.match(r'\d+', str(table.at[header, c])).group()) < 15)
        old = sum(n for c, n in zip(columns, counts) if int(re.match(r'\d+', str(table.at[header, c])).group()) >= 65)
        key = str(int(name)) if year == 2002 else normalize(name)
        records.append({'key': key, 'source_name': str(name), 'population': total, 'young': young, 'old': old})
    return records


def historical_profiles(meta):
    by_code = {str(v['code']): k for k, v in meta.items()}
    audit = {'source_scope': 'Residentes habituales con comuna identificada; no se imputa residencia desconocida.',
             'source_notes': ['REDATAM 2017 rotula el grupo 85–89 como 85–99. Para esta prueba se suman todas las categorías de 65 o más, sin solaparlas.',
                              'REDATAM 1992 repite Caldera; se excluyen Caldera y Calera en vez de adivinar una corrección.'],
             'years': {}}
    profiles = {}
    for year in (1992, 2002, 2017):
        records = redatam(year)
        if year == 2017:
            records += redatam(year, local=True)
        mapped = {}
        unmatched = []
        for r in records:
            key = by_code.get(r['key']) if year == 2002 else r['key']
            if key not in meta:
                unmatched.append({'label': r['source_name'], 'count': r['population']})
                continue
            if key in mapped and year != 2017:
                # Guardar la ambigüedad para exclusión; no sumar etiquetas repetidas.
                mapped[key]['ambiguous'] = True
                continue
            if key not in mapped:
                mapped[key] = {'population': 0, 'young': 0, 'old': 0, 'ambiguous': False}
            for field in ('population', 'young', 'old'):
                mapped[key][field] += r[field]
        profiles[year] = mapped
        audit['years'][str(year)] = {'mapped_territories': len(mapped), 'identified_residents': sum(r['population'] for r in mapped.values()), 'unmatched_categories': unmatched}

    # Verificar la reconstrucción con otra publicación oficial, comuna por comuna.
    workbook = load_workbook(RAW / 'residentes_2017.xlsx', read_only=True, data_only=True)
    errors = []
    count = 0
    for row in workbook['2'].iter_rows(min_row=6, values_only=True):
        if isinstance(row[4], int) and row[4] in {v['code'] for v in meta.values()}:
            key = by_code[str(row[4])]
            actual = profiles[2017].get(key, {}).get('population')
            if actual != row[7]:
                errors.append({'code': row[4], 'name': row[5], 'reconstructed': actual, 'official': row[7]})
            count += 1
    workbook.close()
    audit['independent_2017_check'] = {'compared_communes': count, 'differences': errors}
    dump(OUT / 'calidad_datos.json', audit)
    if errors or count != 346:
        raise ValueError('La reconstrucción de 2017 no coincide con el INE; revisar calidad_datos.json antes de entrenar.')

    excluded = {normalize(name): reason for reason, names in EXCLUSION_GROUPS for name in names}
    rows = []
    exclusions = []
    for key, m in meta.items():
        reason = excluded.get(key)
        if not reason and any(key not in profiles[y] or profiles[y][key]['ambiguous'] for y in profiles):
            reason = 'Identidad ausente o ambigua en un censo histórico'
        if reason:
            exclusions.append({**m, 'reason': reason})
            continue
        for year, lookup in profiles.items():
            p = lookup[key]
            if p['population'] <= 0:
                raise ValueError('Población inicial no positiva.')
            rows.append({**m, 'year': year, **{k: p[k] for k in ('population', 'young', 'old')}})
    audit['exclusions'] = exclusions
    audit['included_communes'] = len(meta) - len(exclusions)
    audit['geography_limit'] = 'Exclusiones de cambios conocidos y unión por identidad documentada. Falta certificar todos los límites con cartografías históricas; prueba preliminar.'
    dump(OUT / 'calidad_datos.json', audit)
    frame = pd.DataFrame(rows)
    frame.to_csv(OUT / 'perfiles_historicos.csv', index=False)
    return frame, audit


def features(frame):
    return pd.DataFrame({'log_poblacion': np.log1p(frame['population']),
                         'proporcion_menores_15': frame['young'] / frame['population'],
                         'proporcion_65_mas': frame['old'] / frame['population']}, index=frame.index)


def annual_growth(initial, final, years):
    return np.power(np.asarray(final, dtype=float) / np.asarray(initial, dtype=float), 1 / years) - 1


def interval(frame, begin, end):
    initial = frame.loc[frame.year == begin].set_index('code').sort_index()
    final = frame.loc[frame.year == end].set_index('code').sort_index()
    assert initial.index.equals(final.index)
    rates = annual_growth(initial.population, final.population, end - begin)
    y = (rates >= .01).astype(int)
    return initial, features(initial), y, rates


def metrics(y, prediction):
    return {'n': len(y), 'f1_macro': float(f1_score(y, prediction, average='macro', labels=[0, 1], zero_division=0)),
            'balanced_accuracy': float(balanced_accuracy_score(y, prediction)),
            'accuracy': float(accuracy_score(y, prediction)),
            'confusion': confusion_matrix(y, prediction, labels=[0, 1]).tolist(),
            'classes': classification_report(y, prediction, labels=[0, 1], target_names=LABELS, zero_division=0, output_dict=True),
            'class_counts': [int(np.sum(y == c)) for c in (0, 1)]}


def make_models(protocol):
    constructors = {'DecisionTreeClassifier': DecisionTreeClassifier, 'RandomForestClassifier': RandomForestClassifier}
    return {a['id']: constructors[a['algorithm']](**a['params']) for a in protocol['alternatives']}


def read_2024(meta, included_codes):
    # Invocar solo después de guardar seleccion_cerrada.json.
    workbook = load_workbook(RAW / 'poblacion_2024.xlsx', read_only=True, data_only=True)
    rows = []
    values = {}
    for row in workbook['4'].iter_rows(min_row=6, values_only=True):
        code = row[4]
        if code not in included_codes:
            continue
        if str(row[6]).startswith('Total'):
            continue
        age = int(re.match(r'\d+', row[6]).group())
        p = values.setdefault(code, {'population': 0, 'young': 0, 'old': 0})
        p['population'] += row[7]
        if age < 15:
            p['young'] += row[7]
        if age >= 65:
            p['old'] += row[7]
    by_code = {v['code']: v for v in meta.values()}
    for row in workbook['2'].iter_rows(min_row=6, values_only=True):
        if row[4] in included_codes:
            assert row[6] == values[row[4]]['population'], row[4]
            rows.append({**by_code[row[4]], 'year': 2024, **values[row[4]]})
    workbook.close()
    assert len(rows) == len(included_codes)
    return pd.DataFrame(rows)


def plot_results(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family': 'DejaVu Sans', 'font.size': 10})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.3), layout='constrained')
    names = list(summary['validation'])
    axes[0].barh(names, [summary['validation'][k]['f1_macro'] for k in names], color=['#1d4ed8', '#0f766e', '#94a3b8', '#94a3b8'])
    axes[0].set(xlim=(0, 1), xlabel='F1 macro', title='Selección con 2002–2017')
    for i, k in enumerate(names):
        axes[0].text(summary['validation'][k]['f1_macro'] + .02, i, f"{summary['validation'][k]['f1_macro']:.3f}", va='center')
    matrix = np.array(summary['test']['modelo']['confusion'])
    axes[1].imshow(matrix, cmap='Blues')
    for i in range(2):
        for j in range(2):
            axes[1].text(j, i, str(matrix[i, j]), ha='center', va='center', color='white' if matrix[i, j] > matrix.max() * .7 else '#111827', fontsize=18)
    axes[1].set(xticks=[0, 1], yticks=[0, 1], xticklabels=['< 1%', '≥ 1%'], yticklabels=['< 1%', '≥ 1%'], xlabel='Predicción', ylabel='Resultado observado', title='Prueba final 2017–2024')
    fig.savefig(OUT / 'evaluacion.png', dpi=160)
    plt.close(fig)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    protocol = json.loads(PROTOCOL.read_text())
    assert protocol['features'] == FEATURES and protocol['target']['threshold'] == .01
    meta = territories()
    historical, audit = historical_profiles(meta)
    initial_train, x_train, y_train, _ = interval(historical, 1992, 2002)
    initial_val, x_val, y_val, _ = interval(historical, 2002, 2017)
    models = make_models(protocol)
    validation = {}
    training = {}
    for name, estimator in models.items():
        estimator.fit(x_train, y_train)
        training[name] = metrics(y_train, estimator.predict(x_train))
        validation[name] = metrics(y_val, estimator.predict(x_val))
    majority = int(np.bincount(y_train).argmax())
    validation['mayoria'] = metrics(y_val, np.full(len(y_val), majority))
    validation['persistencia'] = metrics(y_val, y_train)
    winner = max(models, key=lambda name: (validation[name]['f1_macro'], validation[name]['balanced_accuracy'], name == 'arbol'))
    decision = {'selected': winner, 'protocol_sha256': sha256(PROTOCOL.read_bytes()).hexdigest(),
                'validation': validation, 'params': models[winner].get_params(),
                'frozen_at': datetime.now(timezone.utc).isoformat(), 'test_used_for_selection': False}
    dump(OUT / 'seleccion_cerrada.json', decision)
    chosen = models[winner]
    chosen.fit(pd.concat([x_train, x_val]), np.concatenate([y_train, y_val]))

    # Lectura de las cifras finales aislada de la preparación y selección.
    final = read_2024(meta, set(initial_train.index))
    all_profiles = pd.concat([historical, final], ignore_index=True)
    initial_test, x_test, y_test, test_rates = interval(all_profiles, 2017, 2024)
    prediction = chosen.predict(x_test)
    scores = chosen.predict_proba(x_test)[:, 1]
    final_majority = int(np.bincount(np.concatenate([y_train, y_val])).argmax())
    test = {'modelo': metrics(y_test, prediction),
            'mayoria': metrics(y_test, np.full(len(y_test), final_majority)),
            'persistencia': metrics(y_test, y_val)}
    summary = {'status': 'preliminary_predictive', 'study': 'crecimiento_censal', 'selected': winner,
               'labels': LABELS, 'threshold': .01, 'features': FEATURES,
               'n_communes': len(x_train), 'n_training_before_test': len(x_train) + len(x_val),
               'train': training[winner],
               'validation': validation, 'test': test,
               'selection_fit_n': len(x_train), 'final_fit_n': len(x_train) + len(x_val),
               'limitations': protocol['limitations'] + [audit['geography_limit']],
               'source': 'INE: Censos 1992, 2002, 2017 y 2024. Tabulados por residencia habitual.',
               'test_superiority': {name: test['modelo']['f1_macro'] > test[name]['f1_macro'] for name in ('mayoria', 'persistencia')}}
    # Guardar resultados para inspección y aplicación. El score no se presenta
    # como porcentaje de certeza ni se calibra con la prueba.
    forecasts = final.set_index('code').sort_index()
    forecast_class = chosen.predict(features(forecasts))
    forecast_score = chosen.predict_proba(features(forecasts))[:, 1]
    records = []
    for i, code in enumerate(initial_test.index):
        row = initial_test.loc[code]
        latest = forecasts.loc[code]
        records.append({'code': int(code), 'name': row['name'], 'region': row['region'], 'region_code': int(row['region_code']),
                        'test': {'population': int(row.population), 'young_share': float(row.young / row.population), 'old_share': float(row.old / row.population),
                                 'predicted_class': int(prediction[i]), 'score': float(scores[i]), 'actual_class': int(y_test[i]), 'actual_rate': float(test_rates[i]),
                                 'actual_population': int(latest.population), 'correct': bool(prediction[i] == y_test[i])},
                        'forecast': {'population': int(latest.population), 'young_share': float(latest.young / latest.population), 'old_share': float(latest.old / latest.population),
                                     'predicted_class': int(forecast_class[i]), 'score': float(forecast_score[i]), 'verified': False}})
    dump(OUT / 'modelo.json', {'status': summary['status'], 'study': summary['study'], 'summary': summary, 'protocol': protocol, 'records': records, 'quality': audit})
    dump(OUT / 'resumen.json', summary)
    all_profiles.to_csv(OUT / 'perfiles_censales.csv', index=False)
    pd.DataFrame([{'code': r['code'], 'name': r['name'], **r['test']} for r in records]).to_csv(OUT / 'predicciones_prueba.csv', index=False)
    pd.DataFrame([{'model': name, **{k: v[k] for k in ('n', 'f1_macro', 'balanced_accuracy', 'accuracy')}} for name, v in validation.items()]).to_csv(OUT / 'comparacion_validacion.csv', index=False)
    import joblib
    joblib.dump(chosen, OUT / 'clasificador.joblib')
    # El árbol de comparación se conserva como apoyo didáctico. No explicar un
    # bosque con el árbol de otro modelo como si fueran el mismo clasificador.
    explanatory_tree = DecisionTreeClassifier(**protocol['alternatives'][0]['params']).fit(pd.concat([x_train, x_val]), np.concatenate([y_train, y_val]))
    (OUT / 'arbol_comparacion.txt').write_text(export_text(explanatory_tree, feature_names=FEATURES), encoding='utf-8')
    plot_results(summary)
    print(json.dumps({'communes': len(x_train), 'selected': winner,
                      'validation_f1': {k: v['f1_macro'] for k, v in validation.items()},
                      'test_f1': {k: v['f1_macro'] for k, v in test.items()},
                      'independent_check': audit['independent_2017_check']}, ensure_ascii=False, indent=2))
    return summary


if __name__ == '__main__':
    run()
