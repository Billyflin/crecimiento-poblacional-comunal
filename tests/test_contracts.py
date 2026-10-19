"""Contrastes científicos de v2 y consultas HTTP del modelo publicado."""
from collections import Counter
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys,threading,unittest
from urllib.error import HTTPError
from urllib.request import Request,urlopen

import joblib
import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'experiments'))
sys.path.insert(0,str(ROOT/'app'))
import crecimiento_censal as v1
import crecimiento_v2 as v2
from server import load_model,make_handler

class ScientificContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=load_model()
        cls.summary=cls.model['summary']
        cls.profiles=pd.read_csv(v2.OUT/'perfiles_censales.csv')
        cls.core=cls.summary['core_codes']
        cls.all_codes=sorted(cls.core+[9101,9112])
        cls.decision=json.loads((v2.OUT/'seleccion_cerrada.json').read_text())

    def test_features_match_manual_growth_and_age_changes(self):
        rows=pd.DataFrame([
            dict(code=1,year=1992,population=100,young=30,old=10),
            dict(code=1,year=2002,population=121,young=24.2,old=24.2)])
        _,x,_=v2.inputs(rows,1992,2002,[1])
        self.assertAlmostEqual(x.iloc[0].crecimiento_previo,1.21**.1-1)
        self.assertAlmostEqual(x.iloc[0].proporcion_menores_15,.2)
        self.assertAlmostEqual(x.iloc[0].cambio_menores_15_anual,-.01)
        self.assertAlmostEqual(x.iloc[0].cambio_65_mas_anual,.01)

    def test_future_outcome_does_not_change_earlier_inputs(self):
        _,original,_=v2.inputs(self.profiles,2002,2017,self.all_codes)
        changed=self.profiles.copy()
        changed.loc[changed.year==2024,['population','young','old']]*=2
        _,repeated,_=v2.inputs(changed,2002,2017,self.all_codes)
        pd.testing.assert_frame_equal(original,repeated)

    def test_validation_folds_reserve_each_commune_once(self):
        reserved=[]
        for fold in self.decision['folds']:
            train,valid=set(fold['train']),set(fold['validation'])
            self.assertFalse(train&valid)
            self.assertEqual(train|valid,set(self.core))
            reserved.extend(fold['validation'])
        self.assertEqual(Counter(reserved),Counter({code:1 for code in self.core}))
        self.assertFalse({9101,9112}&set(reserved))

    def test_choice_matches_registered_cv_criterion(self):
        protocol=self.model['protocol']
        self.assertEqual(self.decision['protocol_sha256'],sha256(v2.PROTOCOL.read_bytes()).hexdigest())
        candidates=protocol['alternatives']
        order={c['id']:i for i,c in enumerate(candidates)}
        values=self.decision['validation']
        winner=max(candidates,key=lambda c:(values[c['id']]['selection_f1_mean'],
            values[c['id']]['balanced_accuracy_mean'],-len(c['features']),-c['complexity'],-order[c['id']]))
        self.assertEqual(self.decision['selected'],winner['id'])
        self.assertFalse(self.decision['selection_used_2024_labels'])
        self.assertTrue(self.decision['2024_seen_in_v1'])
        self.assertTrue(self.summary['reused_2024'])

    def test_saved_historical_and_future_fits_reproduce_from_timed_data(self):
        _,x,y_old=v2.inputs(self.profiles,1992,2002,self.core)
        y,_,_=v2.labels(self.profiles,2002,2017,self.core)
        _,later,_=v2.inputs(self.profiles,2002,2017,self.all_codes)
        chosen=self.decision['candidate']
        historical=v2.make_model(chosen).fit(x,y)
        saved=joblib.load(v2.OUT/'clasificador_historico.joblib')
        np.testing.assert_allclose(historical.predict_proba(later),saved.predict_proba(later))
        y_later,_,_=v2.labels(self.profiles,2017,2024,self.all_codes)
        future=v2.make_model(chosen).fit(pd.concat([x,later]),np.concatenate([y,y_later]))
        saved_future=joblib.load(v2.OUT/'clasificador_futuro.joblib')
        _,latest,_=v2.inputs(self.profiles,2017,2024,self.all_codes)
        np.testing.assert_allclose(future.predict_proba(latest),saved_future.predict_proba(latest))
        self.assertEqual(len(x),314)
        self.assertEqual(len(x)+len(later),630)

    def test_exported_outputs_match_their_respective_classifiers(self):
        records=sorted(self.model['records'],key=lambda r:r['code'])
        for previous,start,file,field in [
            (2002,2017,'clasificador_historico.joblib','test'),
            (2017,2024,'clasificador_futuro.joblib','forecast')]:
            with self.subTest(mode=field):
                _,x,_=v2.inputs(self.profiles,previous,start,self.all_codes)
                model=joblib.load(v2.OUT/file)
                np.testing.assert_array_equal(model.predict(x),[r[field]['predicted_class'] for r in records])
                np.testing.assert_allclose(model.predict_proba(x)[:,1],[r[field]['score'] for r in records])

    def test_logistic_scaler_uses_only_training_partition(self):
        _,x,_=v2.inputs(self.profiles,1992,2002,self.core)
        y,_,_=v2.labels(self.profiles,2002,2017,self.core)
        fold=self.decision['folds'][0]
        train=np.flatnonzero(x.index.isin(fold['train']))
        candidate=next(c for c in self.model['protocol']['alternatives'] if c['algorithm']=='LogisticRegression')
        model=v2.make_model(candidate).fit(x.iloc[train],y[train])
        np.testing.assert_allclose(model.named_steps['scale'].mean_,x.iloc[train][candidate['features']].mean())
        self.assertEqual(model.named_steps['scale'].n_samples_seen_,len(train))

    def test_recovered_communes_are_individual_and_1992_padre_is_not_used(self):
        records={r['code']:r for r in self.model['records']}
        self.assertEqual(records[9101]['name'],'Temuco')
        self.assertEqual(records[9112]['name'],'Padre Las Casas')
        self.assertNotEqual(records[9101]['test']['population'],records[9112]['test']['population'])
        for code in (9101,9112):
            self.assertTrue(records[code]['recovered'])
            self.assertFalse(records[code]['core_comparison'])
            self.assertEqual(records[code]['test']['previous_year'],2002)
            self.assertEqual(records[code]['forecast']['previous_year'],2017)
        self.assertTrue(self.profiles.loc[(self.profiles.code==9112)&(self.profiles.year==1992)].empty)
        self.assertEqual(len(records),316)
        self.assertEqual(len(self.model['quality']['exclusions']),30)

    def test_resident_reconstruction_2017_matches_independent_ine_publication(self):
        reconstructed=Counter()
        for r in v1.redatam(2017)+v1.redatam(2017,True):
            reconstructed[r['key']]+=r['population']
        codes={r['code'] for r in v1.territories().values()}
        workbook=load_workbook(v1.RAW/'residentes_2017.xlsx',read_only=True,data_only=True)
        checked=0
        for row in workbook['2'].iter_rows(min_row=6,values_only=True):
            if row[4] in codes:
                self.assertEqual(reconstructed[v1.normalize(row[5])],row[7])
                checked+=1
        workbook.close()
        self.assertEqual(checked,346)

    def test_metrics_and_detection_tradeoff_match_hand_counts(self):
        matrix=[[0,0],[0,0]]
        baseline=[[0,0],[0,0]]
        for record in self.model['records']:
            if not record['core_comparison']:continue
            r=record['test']
            rate=(r['actual_population']/r['population'])**(1/7)-1
            self.assertAlmostEqual(rate,r['actual_rate'])
            self.assertEqual(int(rate>=.01),r['actual_class'])
            matrix[r['actual_class']][r['predicted_class']]+=1
            baseline[r['actual_class']][r['baseline_class']]+=1
        self.assertEqual(matrix,self.summary['test']['modelo']['confusion'])
        self.assertEqual(baseline,self.summary['test']['persistencia']['confusion'])
        self.assertEqual(matrix[0][0]+matrix[1][1],205)
        self.assertEqual(matrix[1][1],130)
        self.assertEqual(matrix[0][1],89)
        self.assertEqual(baseline[1][1],73)
        f1=[2*matrix[c][c]/(2*matrix[c][c]+matrix[c][1-c]+matrix[1-c][c]) for c in (0,1)]
        self.assertAlmostEqual(self.summary['test']['modelo']['f1_macro'],sum(f1)/2)
        self.assertLess(self.summary['test']['modelo']['f1_macro'],self.summary['test']['persistencia']['f1_macro'])

    def test_raw_source_and_territorial_evidence_hashes_match(self):
        for name in ['fuentes.json','fuentes_territoriales_v2.json']:
            for row in json.loads((v1.RAW/name).read_text())['files']:
                with self.subTest(source=row['file']):
                    data=(v1.RAW/row['file']).read_bytes()
                    self.assertEqual(len(data),row['bytes'])
                    self.assertEqual(sha256(data).hexdigest(),row['sha256'])
        self.assertNotIn(2012,set(self.profiles.year))


class QueryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model=load_model()
        handler=make_handler(cls.model)
        handler.log_message=lambda *args:None
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True)
        cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join(timeout=2)

    def post(self,payload):
        request=Request(self.url+'/api/query',data=json.dumps(payload).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=5) as response:return json.load(response)

    def test_recovered_communes_work_in_both_modes_with_correct_cutoffs(self):
        for code in (9101,9112):
            for mode,cutoff in [('estudio',2017),('futuro',2024)]:
                with self.subTest(commune=code,mode=mode):
                    r=self.post({'commune':code,'mode':mode})
                    self.assertTrue(r['recovered'])
                    self.assertEqual(r['code'],code)
                    self.assertEqual(r['result']['training_through'],cutoff)
                    self.assertIn('previous_rate',r['result'])
                    if mode=='futuro':
                        self.assertNotIn('actual_class',r['result'])
                        self.assertFalse(r['result']['verified'])

    def test_invalid_and_still_excluded_communes_are_rejected(self):
        excluded=self.model['quality']['exclusions'][0]['code']
        for value in [
            {'commune':excluded,'mode':'estudio'},{'commune':True,'mode':'estudio'},
            {'commune':99999,'mode':'futuro'},{'commune':'9112','mode':'estudio'},
            {'commune':9112,'mode':[]},{'commune':9112,'mode':'bad'},
            {'commune':9112},{'commune':9112,'mode':'estudio','label':1},[]]:
            with self.subTest(value=value),self.assertRaises(HTTPError) as error:self.post(value)
            self.assertEqual(error.exception.code,400)

    def test_selector_lists_both_individual_communes_and_no_excluded_ids(self):
        with urlopen(self.url+'/api/model',timeout=5) as response:data=json.load(response)
        self.assertEqual(data['study'],'crecimiento_v2')
        self.assertEqual(len(data['communes']),316)
        codes={r['code'] for r in data['communes']}
        self.assertTrue({9101,9112}<=codes)
        self.assertFalse(codes&{r['code'] for r in data['excluded']})
        self.assertNotIn('records',data)

    def test_api_rejects_malformed_bodies_and_does_not_expose_artifacts(self):
        for body,mime in [(b'{','application/json'),(b'\xff','application/json'),(b'{}','text/plain'),(b' '*4097,'application/json')]:
            request=Request(self.url+'/api/query',data=body,headers={'Content-Type':mime},method='POST')
            with self.subTest(length=len(body)),self.assertRaises(HTTPError) as error:urlopen(request,timeout=5)
            self.assertEqual(error.exception.code,400)
        with urlopen(self.url+'/',timeout=5) as response:self.assertEqual(response.headers.get_content_type(),'text/html')
        for route in ['/../data/raw/ine/crecimiento/poblacion_2024.xlsx','/results/crecimiento_v2/clasificador_futuro.joblib']:
            with self.assertRaises(HTTPError) as error:urlopen(self.url+route,timeout=5)
            self.assertEqual(error.exception.code,404)

if __name__=='__main__':unittest.main()
