"""Versión 2: clasificación con historia previa y recuperación territorial documentada."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import clone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.tree import DecisionTreeClassifier

import crecimiento_censal as v1

ROOT = v1.ROOT
OUT = ROOT / 'results/crecimiento_v2'
PROTOCOL = ROOT / 'experiments/protocolo_crecimiento_v2.json'
FEATURES = ['log_poblacion','proporcion_menores_15','proporcion_65_mas',
            'crecimiento_previo','cambio_menores_15_anual','cambio_65_mas_anual']
RECOVERED = [9101, 9112]
SOURCE_UPDATE = 'https://www.ine.gob.cl/sala-de-prensa/prensa/general/noticia/2019/09/16/ine-actualiza-informaci%C3%B3n-de-censo-2017-a-la-nueva-divisi%C3%B3n-pol%C3%ADtica-administrativa-incorporando-la-nueva-regi%C3%B3n-de-%C3%B1uble'


def dump(name, value):
    v1.dump(OUT / name, value)


def prepare_history():
    """No modifica artefactos v1. Recupera solo las dos comunas solicitadas."""
    original = pd.read_csv(ROOT / 'results/crecimiento_censal/perfiles_historicos.csv')
    meta = v1.territories()
    by_code = {str(r['code']): k for k,r in meta.items()}
    mapped = {}
    for year in (1992,2002,2017):
        counts = defaultdict(lambda: dict(population=0,young=0,old=0))
        records = v1.redatam(year)
        if year == 2017:
            records += v1.redatam(2017,local=True)
        for r in records:
            key = by_code.get(r['key']) if year == 2002 else r['key']
            if key in ('temuco','padrelascasas'):
                for field in ('population','young','old'):
                    counts[key][field] += r[field]
        mapped[year] = counts
    extra = []
    for key in ('temuco','padrelascasas'):
        for year in (1992,2002,2017):
            # 1992 Padre Las Casas no se utiliza: no se certifica el traspaso de 2012.
            if key == 'padrelascasas' and year == 1992:
                continue
            p = mapped[year][key]
            assert p['population'] > 0 and p['young']+p['old'] <= p['population']
            extra.append({**meta[key],'year':year,**p})
    history = pd.concat([original,pd.DataFrame(extra)],ignore_index=True)
    old_audit = json.loads((ROOT / 'results/crecimiento_censal/calidad_datos.json').read_text())
    audit = {
        'included_communes':316,'core_comparison_communes':314,
        'independent_2017_check':old_audit['independent_2017_check'],
        'exclusions':[r for r in old_audit['exclusions'] if r['code'] not in RECOVERED],
        'recovered':[
            {'code':9101,'name':'Temuco','usable_years':[1992,2002,2017,2024],
             'note':'La tabla REDATAM de 1992 ya identifica Temuco y Padre Las Casas por separado. Se reserva Temuco fuera del ajuste histórico v2 para la aplicación adicional.'},
            {'code':9112,'name':'Padre Las Casas','usable_years':[2002,2017,2024],
             'note':'No se utiliza 1992 en su historia. Se usa el tabulado actual de 2002, publicado con DPA actualizada por el INE, y los censos posteriores al cambio de 2012.'}
        ],
        'geography_limit':'Recuperación preliminar: fuentes legales y publicación INE actualizada; falta auditoría cartográfica completa. No se sumaron habitantes de San Ramón manualmente.',
        'sources':[
            {'title':'Ley 19.391, creación de Padre Las Casas, 1995','url':'https://www.bcn.cl/leychile/Navegar?idNorma=30758'},
            {'title':'Ley 20.578, traspaso desde Freire, 2012','url':'https://www.bcn.cl/leychile/navegar?idNorma=1038291'},
            {'title':'INE, actualización de bases 2002 y 2017 a nueva DPA, comunicado 12-09-2018','url':SOURCE_UPDATE},
            {'title':'MMA, antecedentes territoriales Temuco y Padre Las Casas, 2015','url':'https://airechile.mma.gob.cl/download/DO-PDA-Temuco-y-Padre-Las-%20Casas.pdf','scope':'Solo evidencia de cambios de límites; ninguna cifra de 2012 se usa en entrenamiento o respuestas.'}
        ],
        'population_scope':old_audit['source_scope'],
    }
    for r in extra:
        if r['year']==2017:
            expected = 280295 if r['code']==9101 else 74911
            assert r['population']==expected
    return history,meta,audit


def inputs(frame, previous, start, codes):
    codes = sorted(codes)
    old = frame.loc[(frame.year==previous)&frame.code.isin(codes)].set_index('code').sort_index()
    initial = frame.loc[(frame.year==start)&frame.code.isin(codes)].set_index('code').sort_index()
    assert list(old.index)==codes and old.index.equals(initial.index)
    years = start-previous
    x = v1.features(initial)
    x['crecimiento_previo'] = v1.annual_growth(old.population,initial.population,years)
    x['cambio_menores_15_anual'] = (initial.young/initial.population-old.young/old.population)/years
    x['cambio_65_mas_anual'] = (initial.old/initial.population-old.old/old.population)/years
    assert list(x.columns)==FEATURES and np.isfinite(x.to_numpy()).all()
    return initial,x,old


def labels(frame,start,end,codes):
    begin = frame.loc[(frame.year==start)&frame.code.isin(codes)].set_index('code').sort_index()
    final = frame.loc[(frame.year==end)&frame.code.isin(codes)].set_index('code').sort_index()
    assert begin.index.equals(final.index)
    rates = v1.annual_growth(begin.population,final.population,end-start)
    return (rates>=.01).astype(int),rates,final


def make_model(candidate):
    constructors={'DecisionTreeClassifier':DecisionTreeClassifier,'RandomForestClassifier':RandomForestClassifier,'LogisticRegression':LogisticRegression}
    columns = ColumnTransformer([('inputs','passthrough',candidate['features'])],
                                remainder='drop',verbose_feature_names_out=False).set_output(transform='pandas')
    scale = StandardScaler().set_output(transform='pandas') if candidate['algorithm']=='LogisticRegression' else 'passthrough'
    return Pipeline([('columns',columns),('scale',scale),('classifier',constructors[candidate['algorithm']](**candidate['params']))])


def select_candidates(protocol,x,y):
    folds=list(StratifiedKFold(**{k:protocol['validation'][k] for k in ('n_splits','shuffle','random_state')}).split(x,y))
    values={}
    oof_table=pd.DataFrame({'code':x.index,'actual_class':y})
    for candidate in protocol['alternatives']:
        predictions=np.zeros(len(y),dtype=int)
        fold_values=[]
        for train,valid in folds:
            model=make_model(candidate).fit(x.iloc[train],y[train])
            predicted=model.predict(x.iloc[valid])
            predictions[valid]=predicted
            fold_values.append(v1.metrics(y[valid],predicted))
        values[candidate['id']]={**v1.metrics(y,predictions),
            'selection_f1_mean':float(np.mean([r['f1_macro'] for r in fold_values])),
            'selection_f1_std':float(np.std([r['f1_macro'] for r in fold_values],ddof=1)),
            'balanced_accuracy_mean':float(np.mean([r['balanced_accuracy'] for r in fold_values])),
            'fold_metrics':fold_values}
        oof_table[candidate['id']]=predictions
    majority_prediction=np.zeros(len(y),dtype=int)
    for train,valid in folds:
        majority_prediction[valid]=np.bincount(y[train]).argmax()
    values['mayoria']=v1.metrics(y,majority_prediction)
    values['persistencia']=v1.metrics(y,(x.crecimiento_previo.to_numpy()>=.01).astype(int))
    candidates=protocol['alternatives']
    order={c['id']:i for i,c in enumerate(candidates)}
    winner=max(candidates,key=lambda c:(values[c['id']]['selection_f1_mean'],
               values[c['id']]['balanced_accuracy_mean'],-len(c['features']),-c['complexity'],-order[c['id']]))
    oof_table.to_csv(OUT/'predicciones_validacion.csv',index=False)
    fold_codes=[{'train':x.index[tr].tolist(),'validation':x.index[va].tolist()} for tr,va in folds]
    return winner,values,fold_codes


def paired_region_interval(y,prediction,baseline,regions):
    """Intervalo exploratorio por remuestreo de regiones, no validación futura."""
    generator=np.random.default_rng(2025)
    regions=np.array(regions)
    blocks={r:np.flatnonzero(regions==r) for r in np.unique(regions)}
    names=list(blocks)
    differences=[]
    for _ in range(1000):
        selected=np.concatenate([blocks[names[i]] for i in generator.integers(0,len(names),size=len(names))])
        differences.append(v1.metrics(y[selected],prediction[selected])['f1_macro']-
                           v1.metrics(y[selected],baseline[selected])['f1_macro'])
    return {'method':'Bootstrap pareado por región, 1000 réplicas; intervalo exploratorio',
            'delta_f1_macro':v1.metrics(y,prediction)['f1_macro']-v1.metrics(y,baseline)['f1_macro'],
            'interval_95':np.quantile(differences,[.025,.975]).tolist(),
            'new_correct_baseline_wrong':int(np.sum((prediction==y)&(baseline!=y))),
            'new_wrong_baseline_correct':int(np.sum((prediction!=y)&(baseline==y)))}


def explain(estimator,features):
    classifier=estimator.named_steps['classifier']
    if hasattr(classifier,'coef_'):
        return {'kind':'Coeficientes sobre entradas estandarizadas; no son efectos causales.',
                'values':dict(zip(features,classifier.coef_[0].tolist()))}
    return {'kind':'Importancia interna de particiones; no es importancia causal.',
            'values':dict(zip(features,classifier.feature_importances_.tolist()))}


def record_result(initial,old,x,prediction,score,index,previous,actual=None):
    row=initial.iloc[index]
    result={'population':int(row.population),'young_share':float(row.young/row.population),
        'old_share':float(row.old/row.population),'previous_year':previous,
        'previous_population':int(old.iloc[index].population),
        'previous_rate':float(x.iloc[index].crecimiento_previo),
        'young_change_per_year':float(x.iloc[index].cambio_menores_15_anual),
        'old_change_per_year':float(x.iloc[index].cambio_65_mas_anual),
        'predicted_class':int(prediction[index]),'score':float(score[index]),
        'baseline_class':int(x.iloc[index].crecimiento_previo>=.01)}
    if actual is not None:
        y,rates,final=actual
        result.update(actual_population=int(final.iloc[index].population),
                      actual_rate=float(rates[index]),actual_class=int(y[index]),
                      correct=bool(prediction[index]==y[index]),training_through=2017)
    else:
        result.update(verified=False,training_through=2024)
    return result


def plot(summary):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(11,4.5),layout='constrained')
    data=summary['test']
    keys=['v1','modelo','persistencia']
    axes[0].barh(['Bosque v1','Modelo v2','Continuidad previa'],[data[k]['f1_macro'] for k in keys],color=['#94a3b8','#2563eb','#0f766e'])
    axes[0].set(xlim=(0,1),xlabel='F1 macro',title='Reevaluación exploratoria: mismas 314 comunas')
    for i,k in enumerate(keys):axes[0].text(data[k]['f1_macro']+.02,i,f"{data[k]['f1_macro']:.3f}",va='center')
    matrix=np.array(data['modelo']['confusion'])
    axes[1].imshow(matrix,cmap='Blues')
    for i in range(2):
        for j in range(2):
            axes[1].text(j,i,str(matrix[i,j]),ha='center',va='center',fontsize=18,
                         color='white' if matrix[i,j]>(matrix.min()+.7*(matrix.max()-matrix.min())) else '#111827')
    axes[1].set(xticks=[0,1],yticks=[0,1],xticklabels=['<1%','≥1%'],yticklabels=['<1%','≥1%'],
                xlabel='Predicción',ylabel='Clase observada',title='2017–2024 ya observado en v1')
    fig.savefig(OUT/'evaluacion.png',dpi=160)
    plt.close(fig)


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    protocol=json.loads(PROTOCOL.read_text())
    assert protocol['features']==FEATURES and protocol['evaluation']['previously_observed']
    history,meta,audit=prepare_history()
    core=sorted(pd.read_csv(ROOT/'results/crecimiento_censal/perfiles_historicos.csv').code.unique())
    all_codes=sorted(core+RECOVERED)
    _,x_train,_=inputs(history,1992,2002,core)
    y_train,_,_=labels(history,2002,2017,core)
    winner,validation,folds=select_candidates(protocol,x_train,y_train)
    decision={'selected':winner['id'],'candidate':winner,'validation':validation,'folds':folds,
        'protocol_sha256':sha256(PROTOCOL.read_bytes()).hexdigest(),
        'frozen_at':datetime.now(timezone.utc).isoformat(),
        'selection_used_2024_labels':False,'2024_seen_in_v1':True}
    dump('seleccion_cerrada.json',decision)
    historical_model=make_model(winner).fit(x_train,y_train)
    joblib.dump(historical_model,OUT/'clasificador_historico.joblib')

    # La lectura de cifras finales viene después de cerrar la selección v2.
    # Su interpretación sigue siendo exploratoria: 2024 se conoce desde v1.
    final=v1.read_2024(meta,set(all_codes))
    profiles=pd.concat([history,final],ignore_index=True)
    initial,x_test,previous=inputs(profiles,2002,2017,all_codes)
    y_test,rates,actual=labels(profiles,2017,2024,all_codes)
    predicted=historical_model.predict(x_test)
    score=historical_model.predict_proba(x_test)[:,1]
    baseline=(x_test.crecimiento_previo.to_numpy()>=.01).astype(int)
    core_mask=np.array([code in core for code in initial.index])
    old_records=json.loads((ROOT/'results/crecimiento_censal/modelo.json').read_text())['records']
    old_by_code={r['code']:r for r in old_records}
    old_prediction=np.array([old_by_code[code]['test']['predicted_class'] for code in initial.index[core_mask]])
    test={'modelo':v1.metrics(y_test[core_mask],predicted[core_mask]),
          'persistencia':v1.metrics(y_test[core_mask],baseline[core_mask]),
          'mayoria':v1.metrics(y_test[core_mask],np.full(sum(core_mask),np.bincount(y_train).argmax())),
          'v1':v1.metrics(y_test[core_mask],old_prediction)}
    interval=paired_region_interval(y_test[core_mask],predicted[core_mask],baseline[core_mask],initial.loc[core,'region_code'])
    future_model=make_model(winner).fit(pd.concat([x_train,x_test]),np.concatenate([y_train,y_test]))
    joblib.dump(future_model,OUT/'clasificador_futuro.joblib')
    future,future_x,future_previous=inputs(profiles,2017,2024,all_codes)
    future_class=future_model.predict(future_x)
    future_score=future_model.predict_proba(future_x)[:,1]
    records=[]
    for i,code in enumerate(initial.index):
        row=initial.iloc[i]
        records.append({'code':int(code),'name':row['name'],'region':row['region'],'region_code':int(row['region_code']),
            'recovered':bool(code in RECOVERED),'core_comparison':bool(core_mask[i]),
            'geography_note':next((r['note'] for r in audit['recovered'] if r['code']==code),'Serie incluida en v1; auditoría cartográfica completa pendiente.'),
            'test':record_result(initial,previous,x_test,predicted,score,i,2002,(y_test,rates,actual)),
            'forecast':record_result(future,future_previous,future_x,future_class,future_score,i,2017)})
    summary={'status':'predictive_v2_exploratory','study':'crecimiento_v2','selected':winner['id'],
        'selected_algorithm':winner['algorithm'],'selected_features':winner['features'],'labels':v1.LABELS,
        'n_communes':316,'comparison_n':314,'selection_fit_n':314,'historical_fit_n':314,'forecast_fit_n':630,
        'validation':validation,'test':test,'test_all':v1.metrics(y_test,predicted),
        'paired_vs_persistence':interval,'reused_2024':True,'forecast_verified':False,
        'historical_training_through':2017,'forecast_training_through':2024,
        'train':v1.metrics(y_train,historical_model.predict(x_train)),
        'explanation':explain(future_model,winner['features']),'limitations':protocol['limitations'],
        'core_codes':[int(x) for x in core],'recovered_codes':RECOVERED,
        'source':'INE: residentes habituales identificados, censos 1992, 2002, 2017 y 2024.'}
    dump('resumen.json',summary)
    dump('calidad_datos.json',audit)
    dump('modelo.json',{'status':summary['status'],'study':summary['study'],'summary':summary,
                       'protocol':protocol,'records':records,'quality':audit})
    profiles.to_csv(OUT/'perfiles_censales.csv',index=False)
    pd.DataFrame([{'code':r['code'],'name':r['name'],'core_comparison':r['core_comparison'],**r['test']} for r in records]).to_csv(OUT/'predicciones_historicas.csv',index=False)
    pd.DataFrame([{'model':c['id'],'algorithm':c['algorithm'],'features':len(c['features']),
       **{k:validation[c['id']][k] for k in ('selection_f1_mean','selection_f1_std','f1_macro','accuracy')}} for c in protocol['alternatives']]).to_csv(OUT/'comparacion_validacion.csv',index=False)
    plot(summary)
    print(json.dumps({'selected':winner['id'],'cv_f1_mean':validation[winner['id']]['selection_f1_mean'],
        'retrospective_f1':{k:v['f1_macro'] for k,v in test.items()},
        'hits':int(np.sum(predicted[core_mask]==y_test[core_mask])),
        'paired_interval':interval,'recovered':[r['name'] for r in records if r['recovered']]},ensure_ascii=False,indent=2))
    return summary


if __name__=='__main__':
    run()
