"""Comprobaciones de métricas, selección de reglas y consultas del prototipo."""

import itertools
import json
from pathlib import Path
import sys
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from http.server import ThreadingHTTPServer

import pandas as pd

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "experiments"))
sys.path.insert(0, str(ROOT / "archive/veterinaria/app"))
from primera_prueba import apriori_counts, rule_metrics, resistance_status
from server import load_model, make_handler, query_model


class ScientificContracts(unittest.TestCase):
    def test_censored_values_are_not_equalities(self):
        self.assertIsNone(resistance_status("<=", 16, 16))
        self.assertIsNone(resistance_status(">", 8, 16))
        self.assertEqual(resistance_status("<", 16, 16), 0)
        self.assertEqual(resistance_status("=", 16, 16), 1)

    def test_metrics_match_hand_counted_transactions(self):
        m = pd.DataFrame({"A": [1, 1, 1, 1, 0, 0, 0, 0],
                          "B": [1, 1, 1, 0, 1, 0, 0, 0]}).astype(bool)
        r = rule_metrics(m, ["A"], "B")
        self.assertEqual(r["joint_count"], 3)
        self.assertEqual(r["antecedent_count"], 4)
        self.assertEqual(r["support"], 3 / 8)
        self.assertEqual(r["confidence"], 3 / 4)
        self.assertEqual(r["lift"], 1.5)

    def test_apriori_pruning_keeps_all_frequent_itemsets(self):
        m = pd.DataFrame({"A": [1, 1, 1, 1, 0, 0, 0, 0],
                          "B": [1, 1, 1, 0, 1, 0, 0, 0],
                          "C": [1, 1, 0, 0, 0, 0, 0, 1]}).astype(bool)
        observed, _ = apriori_counts(m, list(m), 0.25, 3)
        expected = {}
        for size in range(1, 4):
            for subset in itertools.combinations(list(m), size):
                ids = set(m.index)
                for item in subset:
                    ids &= set(m.index[m[item]])
                if len(ids) >= 2:
                    expected[subset] = len(ids)
        self.assertEqual(observed, expected)

    def test_published_model_obeys_family_and_selection_contracts(self):
        model = load_model()
        classes = {d["code"]: d["class"] for d in model["drugs"]}
        for rule in model["rules"]:
            families = [classes[c] for c in rule["antecedent"]]
            self.assertNotIn(classes[rule["consequent"]], families)
            self.assertEqual(len(families), len(set(families)))
            self.assertTrue(rule["passes_selection_2022"])
            self.assertTrue(rule["passes_lab_checks"])
        self.assertEqual(model["selected_configuration"], "conservadora")


class QueryContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = load_model()
        handler = make_handler(cls.model)
        handler.log_message = lambda *args: None
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def post(self, value):
        request = Request(self.url + "/api/query", data=json.dumps(value).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_known_antecedent_returns_actual_model_rules(self):
        result = self.post({"items": ["GEN"]})
        self.assertEqual({r["consequent"] for r in result["rules"]}, {"EFX", "MAR"})
        self.assertEqual({r["confirmation"]["antecedent_count"] for r in result["rules"]}, {37})

    def test_already_known_consequents_are_not_added(self):
        result = self.post({"items": ["GEN", "EFX"]})
        self.assertEqual([r["consequent"] for r in result["rules"]], ["MAR"])
        self.assertEqual(self.post({"items": ["GEN", "EFX", "MAR"]})["rules"], [])

    def test_empty_and_unmatched_selection_remain_explicit(self):
        self.assertEqual(self.post({"items": []})["rules"], [])
        result = self.post({"items": ["FOV"]})
        self.assertEqual(result["rules"], [])
        self.assertIn("no demuestra", result["message"])

    def test_invalid_queries_are_rejected(self):
        for payload in [{"items": ["UNKNOWN"]}, {"items": ["GEN", "GEN"]},
                        {"items": "GEN"}, {"items": [None]}, [], {"other": []}]:
            with self.subTest(payload=payload), self.assertRaises(HTTPError) as error:
                self.post(payload)
            self.assertEqual(error.exception.code, 400)

    def test_api_and_static_file_boundaries(self):
        with urlopen(self.url + "/api/model", timeout=5) as response:
            model = json.load(response)
            self.assertEqual(model["sample_count"], 3933)
        with urlopen(self.url + "/", timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(), "text/html")
        with self.assertRaises(HTTPError) as error:
            urlopen(self.url + "/../experiments/protocolo_estudio_v1.json", timeout=5)
        self.assertEqual(error.exception.code, 404)


if __name__ == "__main__":
    unittest.main()
