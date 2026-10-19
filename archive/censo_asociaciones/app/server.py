"""Servidor local del explorador: python app/server.py --port 8787."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parent / "static"
MODEL_PATH = ROOT / "results/censo_2024/modelo.json"


def load_model(path=MODEL_PATH):
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("status") != "exploratory":
        raise ValueError("El modelo debe declarar su alcance exploratorio.")
    codes = {d["code"] for d in model["items"]}
    groups = {d["code"]: d["group"] for d in model["items"]}
    allowed = {d["code"] for d in model["items"] if d["antecedent_allowed"]}
    for rule in model["rules"]:
        antecedent = rule["antecedent"]
        if (not 1 <= len(antecedent) <= 2 or not set(antecedent) <= allowed or
            len({groups[c] for c in antecedent}) != len(antecedent) or
            rule["consequent"] not in codes - allowed or not rule["eligible"]):
            raise ValueError("Regla inválida en el modelo publicado.")
    return model


def query_model(model, payload):
    """Consulta un antecedente exacto de 1–2 condiciones, nacional o regional."""
    if not isinstance(payload, dict) or not {"items"} <= set(payload) <= {"items", "region"}:
        raise ValueError("Envía items y, opcionalmente, region.")
    items = payload["items"]
    if not isinstance(items, list) or not all(isinstance(c, str) for c in items):
        raise ValueError("items debe ser una lista de códigos de condiciones.")
    lookup = {d["code"]:d for d in model["items"] if d["antecedent_allowed"]}
    if len(items) > 2 or len(set(items)) != len(items) or not set(items) <= set(lookup):
        raise ValueError("Elige hasta dos condiciones conocidas, sin repetir.")
    if len({lookup[c]["group"] for c in items}) != len(items):
        raise ValueError("No se pueden combinar categorías de una misma variable.")
    region = payload.get("region", 0)
    if type(region) is not int or region not in {0} | {r["code"] for r in model["regions"]}:
        raise ValueError("La región debe ser un código válido de 0 a 16; 0 corresponde a Chile.")
    known = set(items)
    matches = []
    for rule in model["rules"]:
        if set(rule["antecedent"]) != known:
            continue
        observed = rule["population"] if region == 0 else rule["by_region"][str(region)]
        if region and observed["antecedent_count"] < model["region_min_antecedents"]:
            continue
        matches.append({"id":rule["id"], "antecedent":rule["antecedent"], "consequent":rule["consequent"],
                        "observed":observed, "discovery":rule["discovery"], "selection":rule["selection"],
                        "test":rule["test"], "national_lift":rule["population"]["lift"]})
    label = "Chile" if region == 0 else next(r["label"] for r in model["regions"] if r["code"] == region)
    return {"selected_items": items, "region":region, "territory":label, "rules": matches,
            "message": ("Elige una o dos condiciones para consultar las asociaciones." if not items
                        else "No hay reglas publicadas para esta combinación y territorio. Esto no demuestra ausencia de asociación." if not matches
                        else f"{len(matches)} asociaciones para estas condiciones · {label}."),
            "scope": model["scope"]}


def make_handler(model):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, content, mime):
            self.send_response(status)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(content)

        def send_json(self, status, value):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8")

        def do_GET(self):
            route = urlsplit(self.path).path
            if route == "/api/model":
                return self.send_json(200, model)
            assets = {"/": ("index.html", "text/html; charset=utf-8"),
                      "/styles.css": ("styles.css", "text/css; charset=utf-8"),
                      "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                      "/availability.mjs": ("availability.mjs", "text/javascript; charset=utf-8")}
            if route not in assets:
                return self.send_json(404, {"error": "Ruta no encontrada."})
            name, mime = assets[route]
            return self.send_bytes(200, (STATIC / name).read_bytes(), mime)

        def do_POST(self):
            if urlsplit(self.path).path != "/api/query":
                return self.send_json(404, {"error": "Ruta no encontrada."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    raise ValueError("El tamaño de la consulta no es válido.")
                if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/json":
                    raise ValueError("La consulta debe usar application/json.")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                result = query_model(model, payload)
            except (ValueError, UnicodeDecodeError) as error:
                return self.send_json(400, {"error": str(error)})
            return self.send_json(200, result)

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    model = load_model()
    with ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(model)) as server:
        print(f"Explorador local: http://127.0.0.1:{args.port}", flush=True)
        server.serve_forever()


if __name__ == "__main__":
    main()
