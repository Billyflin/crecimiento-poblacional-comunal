"""Métricas sobre perfiles ponderados, partición por vivienda y API censal."""
import itertools
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT / 'experiments'))
sys.path.insert(0,str(ROOT / 'app'))
import censo_2024 as census
from server import load_model,make_handler,query_model

class ScientificContracts(unittest.TestCase):
    @staticmethod
    def toy():
        rows = np.zeros((8,7),dtype=int)
        rows[:4,0] = 1  # Rural
        rows[[0,1,2,4],6] = 1  # Sin internet fija
        codes = np.ravel_multi_index(rows.T,census.SIZES)
        return np.bincount(codes,minlength=census.PROFILE_COUNT)

    def test_metrics_match_eight_hand_counted_households(self):
        m = census.metrics(self.toy(),['area:2'],'internet:2')
        self.assertEqual(m['joint_count'],3)
        self.assertEqual(m['antecedent_count'],4)
        self.assertEqual(m['support'],3/8)
        self.assertEqual(m['confidence'],3/4)
        self.assertEqual(m['lift'],1.5)

    def test_apriori_matches_exhaustive_search_with_exclusive_categories(self):
        frequencies = self.toy()
        expected = {}
        codes = list(census.BY_CODE)
        # Independientemente reconstruir los ocho perfiles y comparar categorías.
        rows = np.repeat(census.COORDS,frequencies,axis=0)
        for size in range(1,4):
            for subset in itertools.combinations(sorted(codes),size):
                groups = [census.BY_CODE[c]['group'] for c in subset]
                if len(set(groups)) != size:
                    continue
                matches = np.ones(len(rows),dtype=bool)
                for code in subset:
                    item = census.BY_CODE[code]
                    column = next(j for j,g in enumerate(census.GROUPS) if g[0] == item['group'])
                    matches &= rows[:,column] == item['value']-1
                if matches.sum() >= 2:
                    expected[subset] = int(matches.sum())
        self.assertEqual(census.apriori(frequencies,.25),expected)

    def test_households_sharing_a_dwelling_stay_together(self):
        ids = np.repeat(np.arange(1,10_001),3)
        partitions = census.partition(ids).reshape(-1,3)
        self.assertTrue((partitions == partitions[:,[0]]).all())
        self.assertEqual(set(partitions.ravel()),{0,1,2})
        self.assertTrue(np.array_equal(census.partition(ids),census.partition(ids)))

    def test_empty_regional_denominator_has_no_invented_metrics(self):
        m = census.metrics(np.zeros(census.PROFILE_COUNT,dtype=int),['area:2'],'internet:2')
        self.assertIsNone(m['confidence'])
        self.assertIsNone(m['support'])
        self.assertIsNone(m['lift'])

    def test_published_aggregates_and_selection_match_saved_results(self):
        model = load_model()
        audit = json.loads((ROOT / 'results/censo_2024/calidad_datos.json').read_text())
        counts = np.load(ROOT / 'results/censo_2024/conteos_perfiles.npz')['counts']
        self.assertEqual(model['private_households'],6_596_527)
        self.assertEqual(model['sample_count'],audit['complete_households'])
        self.assertEqual(model['sample_count'],int(counts[:,0].sum()))
        self.assertTrue(np.array_equal(counts[:,0],counts[:,1:].sum(axis=1)))
        decision = json.loads((ROOT / 'results/censo_2024/seleccion_cerrada.json').read_text())
        self.assertEqual([r['id'] for r in model['rules']],decision['rule_ids'])
        self.assertEqual(model['selected_configuration'],decision['selected_configuration'])
        for rule in model['rules']:
            self.assertTrue(rule['eligible'])
            self.assertEqual(rule['population']['joint_count'],sum(m['joint_count'] for m in rule['by_region'].values()))
            self.assertEqual(rule['population']['antecedent_count'],sum(rule[s]['antecedent_count'] for s in ['discovery','selection','test']))

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

    def post(self,value):
        request=Request(self.url+'/api/query',data=json.dumps(value).encode(),headers={'Content-Type':'application/json'},method='POST')
        with urlopen(request,timeout=5) as response:
            return json.load(response)

    def test_national_query_returns_exact_counts(self):
        result=self.post({'items':['area:2','tipologia:1']})
        rule=next(r for r in result['rules'] if r['consequent']=='internet:2')
        self.assertEqual(rule['observed']['antecedent_count'],194_148)
        self.assertEqual(rule['observed']['joint_count'],172_325)
        self.assertTrue(all(set(r['antecedent'])=={'area:2','tipologia:1'} for r in result['rules']))

    def test_region_changes_both_numerator_and_denominator(self):
        result=self.post({'items':['area:2','tipologia:1'],'region':9})
        rule=next(r for r in result['rules'] if r['consequent']=='internet:2')
        original=next(r for r in self.model['rules'] if r['id']==rule['id'])
        self.assertEqual(rule['observed'],original['by_region']['9'])
        self.assertEqual(result['territory'],'La Araucanía')
        self.assertEqual(rule['observed']['n'],372_418)

    def test_small_regional_counts_are_omitted(self):
        # Una base reducida verifica que el filtro usa el antecedente regional.
        model=json.loads(json.dumps(self.model))
        rule=model['rules'][0]
        rule['by_region']['1']['antecedent_count']=99
        model['rules']=[rule]
        self.assertEqual(query_model(model,{'items':rule['antecedent'],'region':1})['rules'],[])

    def test_empty_selection_has_explicit_message(self):
        result=self.post({'items':[]})
        self.assertEqual(result['rules'],[])
        self.assertIn('Elige',result['message'])

    def test_contradictory_unknown_and_output_conditions_are_rejected(self):
        values=[{'items':['area:1','area:2']},{'items':['UNKNOWN']},{'items':['area:2','area:2']},
                {'items':['internet:2']},{'items':['area:2','agua:4','tipologia:1']},
                {'items':'area:2'},{'items':[None]},[],{'other':[]},
                {'items':[],'region':17},{'items':[],'region':True},{'items':[],'region':'9'}]
        for value in values:
            with self.subTest(value=value),self.assertRaises(HTTPError) as error:
                self.post(value)
            self.assertEqual(error.exception.code,400)

    def test_api_does_not_expose_source_files(self):
        with urlopen(self.url+'/api/model',timeout=5) as response:
            self.assertEqual(json.load(response)['sample_count'],6_581_257)
        with urlopen(self.url+'/',timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(),'text/html')
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url+'/../data/raw/ine/hogares_censo2024.zip',timeout=5)
        self.assertEqual(error.exception.code,404)

if __name__=='__main__':
    unittest.main()
