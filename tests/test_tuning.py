"""Separación de selección/evaluación, cortes y reproducción del tuning."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import sys, unittest

import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import FixedThresholdClassifier

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
import tuning_crecimiento as tuning
import crecimiento_v2 as v2
import crecimiento_censal as v1
sys.path.insert(0,str(ROOT/'app'))
from server import load_model,query_model

class TuningContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.protocol=json.loads(tuning.PROTOCOL.read_text())
        cls.closed=json.loads((tuning.OUT/'seleccion_cerrada.json').read_text())
        cls.summary=json.loads((tuning.OUT/'resumen.json').read_text())
        cls.records=json.loads((tuning.OUT/'modelo.json').read_text())['records']
        cls.profiles=pd.read_csv(v2.OUT/'perfiles_censales.csv')
        cls.core=cls.closed['core_codes']
        cls.all_codes=sorted(cls.core+v2.RECOVERED)

    def test_nested_inner_folds_do_not_use_external_communes(self):
        folds=json.loads((tuning.OUT/'particiones_anidadas.json').read_text())
        reserved=[]
        self.assertEqual(len(folds),5)
        for fold in folds:
            train, valid=set(fold['train']),set(fold['validation'])
            self.assertFalse(train&valid)
            self.assertEqual(train|valid,set(self.core))
            inner_reserved=[]
            for inner in fold['inner_folds']:
                fit,selection=set(inner['train']),set(inner['validation'])
                self.assertFalse(fit&selection)
                self.assertFalse((fit|selection)&valid)
                self.assertEqual(fit|selection,train)
                inner_reserved.extend(inner['validation'])
            self.assertEqual(Counter(inner_reserved),Counter({c:1 for c in train}))
            reserved.extend(fold['validation'])
        self.assertEqual(Counter(reserved),Counter({c:1 for c in self.core}))
        self.assertFalse(set(reserved)&set(v2.RECOVERED))

    def test_choice_and_cut_match_registered_search(self):
        self.assertEqual(self.closed['protocol_sha256'],sha256(tuning.PROTOCOL.read_bytes()).hexdigest())
        table=pd.read_csv(tuning.OUT/'busqueda_final.csv')
        best=max(table.to_dict('records'),key=tuning.rank)
        self.assertEqual(len(table),171)
        self.assertEqual(best['candidate'],self.closed['candidate']['id'])
        self.assertEqual(best['threshold'],self.closed['threshold'])
        self.assertEqual(self.protocol['target_threshold_annual_growth'],.01)
        self.assertFalse(self.closed['selection_used_2024_labels'])
        self.assertTrue(self.closed['2024_already_observed_in_prior_versions'])
        self.assertEqual(self.closed['historical_training_through'],2017)
        self.assertTrue(self.summary['reused_2024'])
        self.assertEqual(self.closed['search_sha256'],sha256((tuning.OUT/'busqueda_final.csv').read_bytes()).hexdigest())

    def test_current_and_tuned_prediction_tie_behavior_is_explicit(self):
        np.testing.assert_array_equal(tuning.threshold_predict([.49,.5,.51],.5),[0,1,1])
        # Cortes sobre el score y sobre el crecimiento anual son magnitudes diferentes.
        self.assertNotEqual(self.closed['threshold'],.01)
        rows=sorted(self.records,key=lambda r:r['code'])
        for field,previous,start,file in [('test',2002,2017,'clasificador_historico.joblib'),('forecast',2017,2024,'clasificador_futuro.joblib')]:
            _,x,_=v2.inputs(self.profiles,previous,start,self.all_codes)
            model=joblib.load(tuning.OUT/file)
            scores=model.predict_proba(x)[:,1]
            predicted=model.predict(x)
            np.testing.assert_array_equal(predicted,tuning.threshold_predict(scores,self.closed['threshold']))
            np.testing.assert_array_equal(predicted,[r[field]['predicted_class'] for r in rows])
            np.testing.assert_allclose(scores,[r[field]['score'] for r in rows])
            for r in rows:
                self.assertEqual(r[field]['score_threshold'],self.closed['threshold'])
                self.assertEqual(r[field]['training_through'],2017 if field=='test' else 2024)
                if field=='forecast':
                    self.assertNotIn('actual_class',r[field])
                    self.assertFalse(r[field]['verified'])

    def test_saved_fits_reproduce_with_historical_and_future_responses(self):
        _,x,_=v2.inputs(self.profiles,1992,2002,self.core)
        y=np.asarray(v2.labels(self.profiles,2002,2017,self.core)[0])
        _,later,_=v2.inputs(self.profiles,2002,2017,self.all_codes)
        y_later=np.asarray(v2.labels(self.profiles,2017,2024,self.all_codes)[0])
        for fit_x,fit_y,file in [(x,y,'clasificador_historico.joblib'),
                                (pd.concat([x,later]),np.concatenate([y,y_later]),'clasificador_futuro.joblib')]:
            candidate=self.closed['candidate']
            refit=FixedThresholdClassifier(tuning.make_model(candidate),threshold=self.closed['threshold'],response_method='predict_proba').fit(fit_x,fit_y)
            saved=joblib.load(tuning.OUT/file)
            np.testing.assert_allclose(refit.predict_proba(later),saved.predict_proba(later))
            np.testing.assert_array_equal(refit.predict(later),saved.predict(later))
        self.assertEqual(len(x),314)
        self.assertEqual(len(x)+len(later),630)

    def test_metrics_match_independent_counts_and_original_v2_is_preserved(self):
        core_rows=[r['test'] for r in self.records if r['core_comparison']]
        matrix=np.zeros((2,2),dtype=int)
        for r in core_rows:
            rate=(r['actual_population']/r['population'])**(1/7)-1
            self.assertEqual(r['actual_class'],int(rate>=.01))
            matrix[r['actual_class'],r['predicted_class']]+=1
        self.assertEqual(matrix.tolist(),self.summary['test']['tuneado']['confusion'])
        self.assertAlmostEqual(np.trace(matrix)/314,self.summary['test']['tuneado']['accuracy'])
        for name,digest in json.loads((tuning.OUT/'procedencia_v2.json').read_text()).items():
            self.assertEqual(sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)
        nested=pd.read_csv(tuning.OUT/'predicciones_anidadas.csv')
        self.assertEqual(set(nested.code),set(self.core))
        metrics=v1.metrics(nested.actual_class.to_numpy(),nested.tuned.to_numpy())
        self.assertAlmostEqual(metrics['f1_macro'],self.summary['validation']['tuneado']['f1_macro'])

    def test_application_reports_tuning_and_keeps_v2_predictions(self):
        model=load_model()
        self.assertEqual(model['study'],'crecimiento_v2')
        self.assertFalse(model['tuning']['improved_vs_v2'])
        self.assertEqual(model['tuning']['selected_parameters'],self.closed['candidate']['params'])
        self.assertEqual(model['tuning']['comparison_n'],314)
        self.assertTrue(model['tuning']['reused_2024'])
        for record in model['records']:
            for mode,key in [('estudio','test'),('futuro','forecast')]:
                result=query_model(model,{'commune':record['code'],'mode':mode})
                self.assertEqual(result['model'],'bosque_tendencia')
                self.assertEqual(result['result'],record[key])

if __name__=='__main__':unittest.main()
