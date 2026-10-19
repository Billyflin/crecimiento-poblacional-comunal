"""Tuning registrado, con CV anidada y reevaluación temporal exploratoria."""
from __future__ import annotations
from datetime import datetime, timezone
from hashlib import sha256
from itertools import product
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, FixedThresholdClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

import crecimiento_v2 as v2
import crecimiento_censal as v1

ROOT = v2.ROOT
OUT = ROOT / 'results/tuning_crecimiento'
PROTOCOL = ROOT / 'experiments/protocolo_tuning_crecimiento.json'


def dump(name, value):
    v1.dump(OUT / name, value)


def candidates(protocol):
    grid = protocol['candidate_grid']
    four = v2.FEATURES[:4]
    six = v2.FEATURES
    result = []
    def add(name, algorithm, features, **params):
        result.append({'id': name, 'algorithm': algorithm, 'features': features,
                       'params': {**params, 'random_state': protocol['seed']}})
    reference = dict(n_estimators=300, max_depth=5, min_samples_leaf=8,
                     class_weight='balanced_subsample', n_jobs=2)
    add('bosque_v2', 'RandomForestClassifier', four, **reference)
    rf = grid['forests']
    for depth, leaf, weight in product(rf['max_depth'], rf['min_samples_leaf'], rf['class_weight']):
        add(f'bosque_d{depth}_h{leaf}_'+('balanceado' if weight else 'sin_pesos'),
            'RandomForestClassifier', four, n_estimators=rf['n_estimators'],
            max_depth=depth, min_samples_leaf=leaf, class_weight=weight, n_jobs=2)
    add('bosque_seis', 'RandomForestClassifier', six, **reference)
    lr = grid['logistic']
    for regularization, weight in product(lr['C'], lr['class_weight']):
        add(f'logistica_c{regularization}_'+('balanceada' if weight else 'sin_pesos'),
            'LogisticRegression', four, C=regularization, class_weight=weight, max_iter=2000)
    gb = grid['gradient_boosting']
    for depth, rate in product(gb['max_depth'], gb['learning_rate']):
        add(f'boost_d{depth}_t{rate}', 'GradientBoostingClassifier', four,
            n_estimators=gb['n_estimators'], max_depth=depth, learning_rate=rate,
            min_samples_leaf=gb['min_samples_leaf'])
    add('boost_seis', 'GradientBoostingClassifier', six, n_estimators=150,
        max_depth=2, learning_rate=.05, min_samples_leaf=10)
    assert len(result) == protocol['candidate_count']
    assert len(result)*len(protocol['score_thresholds']) == protocol['configuration_threshold_combinations']
    return result


def make_model(candidate):
    constructors = {'RandomForestClassifier': RandomForestClassifier,
                    'LogisticRegression': LogisticRegression,
                    'GradientBoostingClassifier': GradientBoostingClassifier}
    columns = ColumnTransformer([('inputs', 'passthrough', candidate['features'])],
        remainder='drop', verbose_feature_names_out=False).set_output(transform='pandas')
    scale = StandardScaler().set_output(transform='pandas') if candidate['algorithm']=='LogisticRegression' else 'passthrough'
    return Pipeline([('columns', columns), ('scale', scale),
                     ('classifier', constructors[candidate['algorithm']](**candidate['params']))])


def threshold_predict(score, threshold):
    return (np.asarray(score) >= threshold).astype(int)


def short_metrics(y, predicted):
    y, predicted = np.asarray(y), np.asarray(predicted)
    matrix = np.bincount(2*y+predicted, minlength=4).reshape(2, 2)
    a, b, c, d = matrix.ravel()
    f1_0 = 2*a/(2*a+b+c) if 2*a+b+c else 0.
    f1_1 = 2*d/(2*d+b+c) if 2*d+b+c else 0.
    return {'f1_macro': float((f1_0+f1_1)/2), 'accuracy': float((a+d)/len(y)),
            'balanced_accuracy': float((a/(a+b)+d/(c+d))/2)}


def rank(row):
    return (row['selection_f1_mean'], row['accuracy_mean'], row['balanced_accuracy_mean'],
            -row['features'], -abs(row['threshold']-.5), -row['order'])


def search(protocol, x, y, split_spec, name):
    """No recibe etiquetas ni variables del período 2017–2024."""
    folds = list(StratifiedKFold(**split_spec).split(x, y))
    choices = candidates(protocol)
    rows, probabilities = [], {}
    for order, candidate in enumerate(choices):
        score = np.full(len(y), np.nan)
        for train, valid in folds:
            model = make_model(candidate).fit(x.iloc[train], y[train])
            assert list(model.classes_) == [0, 1]
            score[valid] = model.predict_proba(x.iloc[valid])[:, 1]
        assert np.isfinite(score).all()
        probabilities[candidate['id']] = score
        for threshold in protocol['score_thresholds']:
            predicted = threshold_predict(score, threshold)
            fold_metrics = [short_metrics(y[valid], predicted[valid]) for _, valid in folds]
            values = short_metrics(y, predicted)
            rows.append({'candidate': candidate['id'], 'algorithm': candidate['algorithm'],
                'features': len(candidate['features']), 'threshold': threshold, 'order': order,
                'selection_f1_mean': float(np.mean([r['f1_macro'] for r in fold_metrics])),
                'selection_f1_std': float(np.std([r['f1_macro'] for r in fold_metrics], ddof=1)),
                'accuracy_mean': float(np.mean([r['accuracy'] for r in fold_metrics])),
                'balanced_accuracy_mean': float(np.mean([r['balanced_accuracy'] for r in fold_metrics])),
                **values})
    table = pd.DataFrame(rows)
    table.to_csv(OUT/f'busqueda_{name}.csv', index=False)
    best = max(rows, key=rank)
    chosen = next(c for c in choices if c['id']==best['candidate'])
    codes = [{'train': x.index[train].tolist(), 'validation': x.index[valid].tolist()} for train, valid in folds]
    return chosen, best, probabilities, codes


def select(protocol):
    # Se filtra la época antes de preparar las entradas y respuestas del tuning.
    history = pd.read_csv(v2.OUT/'perfiles_censales.csv').query('year <= 2017').copy()
    previous_summary = json.loads((v2.OUT/'resumen.json').read_text())
    core = previous_summary['core_codes']
    _, x, _ = v2.inputs(history, 1992, 2002, core)
    y = np.asarray(v2.labels(history, 2002, 2017, core)[0])
    outer = list(StratifiedKFold(**protocol['outer_validation']).split(x, y))
    tuned = np.zeros(len(y), dtype=int)
    reference = np.zeros(len(y), dtype=int)
    scores = np.full(len(y), np.nan)
    all_folds = []
    for i, (train, valid) in enumerate(outer):
        candidate, best, _, inner = search(protocol, x.iloc[train], y[train],
                                           protocol['inner_validation'], f'externa_{i+1}')
        model = make_model(candidate).fit(x.iloc[train], y[train])
        scores[valid] = model.predict_proba(x.iloc[valid])[:, 1]
        tuned[valid] = threshold_predict(scores[valid], best['threshold'])
        ref = make_model(candidates(protocol)[0]).fit(x.iloc[train], y[train])
        reference[valid] = ref.predict(x.iloc[valid])
        all_folds.append({'train': x.index[train].tolist(), 'validation': x.index[valid].tolist(),
            'inner_folds': inner, 'chosen': candidate, 'threshold': best['threshold'],
            'inner_selection_f1': best['selection_f1_mean'],
            'external_metrics': v1.metrics(y[valid], tuned[valid])})
        dump('particiones_anidadas.json', all_folds)
        print(f'Validación externa {i+1}/5: {candidate["id"]}, corte {best["threshold"]:.2f}', flush=True)
    persistence = threshold_predict(x.crecimiento_previo.to_numpy(), .01)
    nested = {'tuneado': v1.metrics(y, tuned), 'v2_fijo': v1.metrics(y, reference),
              'persistencia': v1.metrics(y, persistence),
              'scope': 'Evaluación entre comunas de 2002–2017 dentro de este tuning; no prueba temporal futura.'}
    pd.DataFrame({'code': x.index, 'actual_class': y, 'tuned': tuned,
                  'v2_fixed': reference, 'persistence': persistence, 'score': scores}).to_csv(OUT/'predicciones_anidadas.csv', index=False)
    chosen, best, probabilities, folds = search(protocol, x, y,
        protocol['final_selection_validation'], 'final')
    reference_rows = pd.read_csv(OUT/'busqueda_final.csv').query("candidate == 'bosque_v2'")
    threshold_only = max(reference_rows.to_dict('records'), key=rank)
    pd.DataFrame({'code': x.index, 'actual_class': y, **probabilities}).to_csv(OUT/'scores_seleccion.csv', index=False)
    decision = {'closed_at': datetime.now(timezone.utc).isoformat(),
        'protocol_sha256': sha256(PROTOCOL.read_bytes()).hexdigest(),
        'search_sha256': sha256((OUT/'busqueda_final.csv').read_bytes()).hexdigest(),
        'candidate': chosen, 'threshold': best['threshold'], 'selection': best,
        'threshold_only_v2': threshold_only['threshold'], 'folds': folds,
        'nested_validation': nested, 'selection_used_2024_labels': False,
        '2024_already_observed_in_prior_versions': True, 'historical_fit_n': len(y),
        'historical_training_through': 2017, 'core_codes': core}
    dump('seleccion_cerrada.json', decision)
    historical = FixedThresholdClassifier(make_model(chosen), threshold=best['threshold'],
        response_method='predict_proba').fit(x, y)
    joblib.dump(historical, OUT/'clasificador_historico.joblib')
    print('Selección cerrada antes de reevaluar 2024:', chosen['id'], best['threshold'], flush=True)
    return decision, historical, x, y


def evaluate(protocol, decision, historical, x_train, y_train):
    # Solo aquí se leen las etiquetas del intervalo posterior.
    profiles = pd.read_csv(v2.OUT/'perfiles_censales.csv')
    core = decision['core_codes']
    all_codes = sorted(core + v2.RECOVERED)
    initial, x_test, old = v2.inputs(profiles, 2002, 2017, all_codes)
    y_test, rates, final = v2.labels(profiles, 2017, 2024, all_codes)
    y_test = np.asarray(y_test)
    score = historical.predict_proba(x_test)[:, 1]
    predicted = historical.predict(x_test)
    np.testing.assert_array_equal(predicted, threshold_predict(score, decision['threshold']))
    previous_model = json.loads((v2.OUT/'modelo.json').read_text())
    by_code = {r['code']: r for r in previous_model['records']}
    v2_prediction = np.array([by_code[c]['test']['predicted_class'] for c in all_codes])
    v2_score = np.array([by_code[c]['test']['score'] for c in all_codes])
    threshold_only = threshold_predict(v2_score, decision['threshold_only_v2'])
    baseline = threshold_predict(x_test.crecimiento_previo.to_numpy(), .01)
    mask = np.array([c in core for c in all_codes])
    comparisons = {name: v1.metrics(y_test[mask], values[mask]) for name, values in
        [('tuneado', predicted), ('v2', v2_prediction), ('solo_corte_v2', threshold_only), ('persistencia', baseline)]}
    interval = v2.paired_region_interval(y_test[mask], predicted[mask], baseline[mask], initial.loc[core,'region_code'])
    future = FixedThresholdClassifier(make_model(decision['candidate']), threshold=decision['threshold'],
        response_method='predict_proba').fit(pd.concat([x_train, x_test]), np.concatenate([y_train, y_test]))
    joblib.dump(future, OUT/'clasificador_futuro.joblib')
    latest, x_future, prior = v2.inputs(profiles, 2017, 2024, all_codes)
    forecast_class = future.predict(x_future)
    forecast_score = future.predict_proba(x_future)[:, 1]
    records = []
    for i, code in enumerate(all_codes):
        original = by_code[code]
        records.append({**{k: original[k] for k in ('code','name','region','region_code','recovered','core_comparison','geography_note')},
            'test': {**v2.record_result(initial, old, x_test, predicted, score, i, 2002,
                       (y_test, rates, final)), 'score_threshold': decision['threshold']},
            'forecast': {**v2.record_result(latest, prior, x_future, forecast_class, forecast_score, i, 2017),
                         'score_threshold': decision['threshold']}})
    improved = comparisons['tuneado']['accuracy'] > comparisons['v2']['accuracy'] and comparisons['tuneado']['f1_macro'] > comparisons['v2']['f1_macro']
    summary = {'status': 'predictive_tuning_exploratory', 'study': 'tuning_crecimiento',
        'selected': decision['candidate']['id'], 'selected_algorithm': decision['candidate']['algorithm'],
        'selected_parameters': decision['candidate']['params'],
        'selected_features': decision['candidate']['features'], 'score_threshold': decision['threshold'],
        'target_annual_growth': .01, 'labels': v1.LABELS, 'n_communes': 316, 'comparison_n': 314,
        'historical_fit_n': 314, 'forecast_fit_n': 630, 'historical_training_through': 2017,
        'forecast_training_through': 2024, 'forecast_verified': False, 'reused_2024': True,
        'validation': decision['nested_validation'], 'selection': decision['selection'],
        'threshold_only_v2': decision['threshold_only_v2'], 'test': comparisons,
        'test_all': v1.metrics(y_test, predicted), 'paired_vs_persistence': interval,
        'improved_vs_v2': improved, 'limitations': protocol['limitations'],
        'core_codes': core, 'recovered_codes': v2.RECOVERED}
    dump('resumen.json', summary)
    dump('modelo.json', {'status': summary['status'], 'study': summary['study'], 'summary': summary,
                        'protocol': protocol, 'records': records, 'quality': previous_model['quality']})
    pd.DataFrame([{'code': r['code'], 'name': r['name'], 'core_comparison': r['core_comparison'], **r['test']} for r in records]).to_csv(OUT/'predicciones_historicas.csv', index=False)
    plot(summary)
    print(json.dumps({'selected': summary['selected'], 'threshold': summary['score_threshold'],
        'nested_f1': {k:r['f1_macro'] for k,r in summary['validation'].items() if isinstance(r,dict)},
        'historical': {k:{'hits':round(r['accuracy']*314),'f1_macro':r['f1_macro'],'confusion':r['confusion']} for k,r in comparisons.items()},
        'improved_vs_v2': improved}, ensure_ascii=False, indent=2), flush=True)
    return summary


def plot(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.5), constrained_layout=True)
    rows = [('v2', 'Bosque v2'), ('tuneado', 'Tuning elegido'), ('persistencia', 'Tendencia previa')]
    counts = [round(summary['test'][k]['accuracy']*314) for k,_ in rows]
    bars = axes[0].bar([name for _,name in rows], counts, color=['#778596','#2458c7','#428a76'])
    axes[0].bar_label(bars, labels=[f'{c}/314' for c in counts], padding=5)
    axes[0].set_ylim(0, 314)
    axes[0].set_title('Reevaluación 2017–2024 · exploratoria')
    axes[0].set_ylabel('Comunas clasificadas correctamente')
    matrix = np.asarray(summary['test']['tuneado']['confusion'])
    axes[1].imshow(matrix, cmap='Blues')
    for (i,j), value in np.ndenumerate(matrix):
        axes[1].text(j,i,str(value),ha='center',va='center',fontsize=17,
                     color='white' if value > matrix.max()*.6 else '#182633')
    axes[1].set_xticks([0,1], ['Predice <1%', 'Predice ≥1%'])
    axes[1].set_yticks([0,1], ['Real <1%', 'Real ≥1%'])
    axes[1].set_title('Errores del tuning seleccionado')
    fig.savefig(OUT/'evaluacion.png', dpi=160)
    plt.close(fig)


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    original = {str(p.relative_to(ROOT)): sha256(p.read_bytes()).hexdigest() for p in v2.OUT.iterdir() if p.is_file()}
    protocol = json.loads(PROTOCOL.read_text())
    decision, historical, x, y = select(protocol)
    result = evaluate(protocol, decision, historical, x, y)
    for name, digest in original.items():
        assert sha256((ROOT/name).read_bytes()).hexdigest()==digest, f'Se modificó v2: {name}'
    dump('procedencia_v2.json', original)
    return result


if __name__=='__main__':
    run()
