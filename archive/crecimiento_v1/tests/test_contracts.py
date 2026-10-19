"""Contrastes independientes de datos, modelo entrenado y consultas publicadas."""
from collections import Counter
from hashlib import sha256
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import joblib
import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'experiments'))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
import crecimiento_censal as study
from server import load_model, make_handler

OUT = ROOT / 'results/crecimiento_censal'


class ScientificContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_model()
        cls.profiles = pd.read_csv(OUT / 'perfiles_censales.csv')
        cls.classifier = joblib.load(OUT / 'clasificador.joblib')

    def test_annualization_and_labels_match_manual_examples(self):
        actual = study.annual_growth([100, 100, 100], [121, 100, 81], 2)
        np.testing.assert_allclose(actual, [.1, 0, -.1], atol=1e-12)
        np.testing.assert_array_equal(actual >= .01, [True, False, False])
        self.assertAlmostEqual(float(study.annual_growth(100, 100 * 1.02**15, 15)), .02)

    def test_communal_population_2017_matches_independent_official_table(self):
        reconstructed = Counter()
        for row in study.redatam(2017) + study.redatam(2017, local=True):
            reconstructed[row['key']] += row['population']
        wb = load_workbook(study.RAW / 'residentes_2017.xlsx', read_only=True, data_only=True)
        communal_codes = {r['code'] for r in study.territories().values()}
        count = 0
        for row in wb['2'].iter_rows(min_row=6, values_only=True):
            if isinstance(row[4], int) and row[4] in communal_codes:
                with self.subTest(commune=row[5]):
                    self.assertEqual(reconstructed[study.normalize(row[5])], row[7])
                count += 1
        wb.close()
        self.assertEqual(count, 346)

    def test_sources_match_saved_hashes(self):
        manifest = json.loads((study.RAW / 'fuentes.json').read_text())
        for record in manifest['files']:
            with self.subTest(file=record['file']):
                source = (study.RAW / record['file']).read_bytes()
                self.assertEqual(len(source), record['bytes'])
                self.assertEqual(sha256(source).hexdigest(), record['sha256'])
                if record['file'].endswith('.html'):
                    self.assertIn('params', record)

    def test_temporal_units_and_exclusions_are_consistent(self):
        records = self.model['records']
        included = {r['code'] for r in records}
        excluded = {r['code'] for r in self.model['quality']['exclusions']}
        self.assertEqual(len(included), 314)
        self.assertEqual(len(excluded), 32)
        self.assertFalse(included & excluded)
        self.assertIn('Temuco', [r['name'] for r in self.model['quality']['exclusions']])
        self.assertEqual(set(self.profiles.year), {1992, 2002, 2017, 2024})
        for year, rows in self.profiles.groupby('year'):
            self.assertEqual(set(rows.code), included)
            self.assertEqual(len(rows), 314)
            self.assertTrue((rows.population > 0).all())
            self.assertTrue((rows.young + rows.old <= rows.population).all())

    def test_selection_is_protocol_winner_without_final_test(self):
        protocol_file = ROOT / 'experiments/protocolo_crecimiento.json'
        protocol = json.loads(protocol_file.read_text())
        decision = json.loads((OUT / 'seleccion_cerrada.json').read_text())
        self.assertEqual(decision['protocol_sha256'], sha256(protocol_file.read_bytes()).hexdigest())
        self.assertFalse(decision['test_used_for_selection'])
        alternatives = [a['id'] for a in protocol['alternatives']]
        expected = max(alternatives, key=lambda k: (
            decision['validation'][k]['f1_macro'],
            decision['validation'][k]['balanced_accuracy'], k == 'arbol'))
        self.assertEqual(decision['selected'], expected)
        self.assertEqual(list(self.classifier.feature_names_in_), protocol['features'])
        self.assertEqual(protocol['split']['test'], [2017, 2024])

    def test_published_queries_are_outputs_of_saved_classifier(self):
        records = sorted(self.model['records'], key=lambda r: r['code'])
        for year, field in [(2017, 'test'), (2024, 'forecast')]:
            with self.subTest(year=year):
                initial = self.profiles.loc[self.profiles.year == year].set_index('code').sort_index()
                x = study.features(initial)
                np.testing.assert_array_equal(self.classifier.predict(x),
                                              [r[field]['predicted_class'] for r in records])
                np.testing.assert_allclose(self.classifier.predict_proba(x)[:, 1],
                                           [r[field]['score'] for r in records])
                self.assertEqual(x.shape, (314, 3))
        self.assertTrue(all(r['forecast']['verified'] is False for r in records))

    def test_saved_classifier_reproduces_fit_with_pretest_examples_only(self):
        historical = self.profiles.loc[self.profiles.year < 2024]
        _, x_train, y_train, _ = study.interval(historical, 1992, 2002)
        _, x_val, y_val, _ = study.interval(historical, 2002, 2017)
        protocol = self.model['protocol']
        reproduced = study.make_models(protocol)[self.model['summary']['selected']]
        reproduced.fit(pd.concat([x_train, x_val]), np.concatenate([y_train, y_val]))
        x_test = study.features(self.profiles.loc[self.profiles.year == 2017].set_index('code').sort_index())
        np.testing.assert_allclose(reproduced.predict_proba(x_test), self.classifier.predict_proba(x_test))
        self.assertEqual(len(x_train) + len(x_val), 628)

    def test_reported_errors_match_independent_record_counts(self):
        matrix = [[0, 0], [0, 0]]
        for record in self.model['records']:
            result = record['test']
            rate = (result['actual_population'] / result['population'])**(1 / 7) - 1
            self.assertAlmostEqual(rate, result['actual_rate'])
            actual = int(rate >= .01)
            self.assertEqual(actual, result['actual_class'])
            matrix[actual][result['predicted_class']] += 1
        metrics = self.model['summary']['test']['modelo']
        self.assertEqual(matrix, metrics['confusion'])
        self.assertEqual(matrix[0][0] + matrix[1][1], 169)
        self.assertAlmostEqual(metrics['accuracy'], 169 / 314)
        f1 = [2 * matrix[c][c] / (2 * matrix[c][c] + matrix[c][1-c] + matrix[1-c][c]) for c in (0, 1)]
        self.assertAlmostEqual(metrics['f1_macro'], sum(f1) / 2)
        self.assertGreater(self.model['summary']['test']['persistencia']['f1_macro'], metrics['f1_macro'])


class QueryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_model()
        handler = make_handler(cls.model)
        handler.log_message = lambda *args: None
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post(self, payload):
        request = Request(self.url + '/api/query', data=json.dumps(payload).encode(),
                          headers={'Content-Type': 'application/json'}, method='POST')
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_historical_and_future_modes_return_distinct_inputs(self):
        record = next(r for r in self.model['records'] if r['name'] == 'Valdivia')
        past = self.post({'commune': record['code'], 'mode': 'estudio'})
        future = self.post({'commune': record['code'], 'mode': 'futuro'})
        self.assertEqual(past['period'], [2017, 2024])
        self.assertEqual(past['result'], record['test'])
        self.assertEqual(future['period'], [2024, 2031])
        self.assertEqual(future['result'], record['forecast'])
        self.assertNotIn('actual_class', future['result'])
        self.assertFalse(future['result']['verified'])

    def test_invalid_and_excluded_selections_are_rejected(self):
        excluded = self.model['quality']['exclusions'][0]['code']
        values = [
            {'commune': excluded, 'mode': 'estudio'},
            {'commune': 99999, 'mode': 'futuro'}, {'commune': True, 'mode': 'estudio'},
            {'commune': '14101', 'mode': 'estudio'}, {'commune': 14101, 'mode': []},
            {'commune': 14101, 'mode': 'other'}, {'commune': 14101}, [],
            {'commune': 14101, 'mode': 'estudio', 'actual_class': 1},
        ]
        for value in values:
            with self.subTest(value=value), self.assertRaises(HTTPError) as error:
                self.post(value)
            self.assertEqual(error.exception.code, 400)

    def test_selector_contains_only_supported_communes(self):
        with urlopen(self.url + '/api/model', timeout=5) as response:
            data = json.load(response)
        self.assertEqual(data['study'], 'crecimiento_censal')
        self.assertEqual(len(data['communes']), 314)
        self.assertEqual({r['code'] for r in data['communes']},
                         {r['code'] for r in self.model['records']})
        self.assertNotIn('records', data)

    def test_malformed_and_oversized_queries_are_rejected(self):
        for body, mime in [(b'{', 'application/json'), (b'\xff', 'application/json'),
                           (b'{}', 'text/plain'), (b' ' * 4097, 'application/json')]:
            request = Request(self.url + '/api/query', data=body,
                              headers={'Content-Type': mime}, method='POST')
            with self.subTest(length=len(body), mime=mime), self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=5)
            self.assertEqual(error.exception.code, 400)

    def test_static_routes_do_not_expose_raw_data_or_artifact_files(self):
        with urlopen(self.url + '/', timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(), 'text/html')
        for route in ['/../data/raw/ine/crecimiento/poblacion_2024.xlsx',
                      '/results/crecimiento_censal/clasificador.joblib', '/unknown']:
            with self.subTest(route=route), self.assertRaises(HTTPError) as error:
                urlopen(self.url + route, timeout=5)
            self.assertEqual(error.exception.code, 404)


if __name__ == '__main__':
    unittest.main()
