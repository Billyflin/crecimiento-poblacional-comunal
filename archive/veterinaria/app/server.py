"""Servidor local del explorador: python app/server.py --port 8787."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[3]
STATIC = Path(__file__).resolve().parent / "static"
MODEL_PATH = ROOT / "results/estudio_v1/modelo.json"


def load_model(path=MODEL_PATH):
    model = json.loads(Path(path).read_text(encoding="utf-8"))
    if model.get("status") != "exploratory":
        raise ValueError("El modelo debe declarar su alcance exploratorio.")
    codes = {d["code"] for d in model["drugs"]}
    for rule in model["rules"]:
        if not set(rule["antecedent"]) <= codes or rule["consequent"] not in codes or not rule["eligible"]:
            raise ValueError("Regla inválida en el modelo publicado.")
    return model


def query_model(model, payload):
    """Consulta ítems R conocidos, sin interpretar los no seleccionados como S."""
    if not isinstance(payload, dict) or set(payload) != {"items"}:
        raise ValueError("Envía un objeto con el campo items.")
    items = payload["items"]
    if not isinstance(items, list) or not all(isinstance(c, str) for c in items):
        raise ValueError("items debe ser una lista de códigos de antibióticos.")
    codes = {d["code"] for d in model["drugs"]}
    if len(items) > len(codes) or len(set(items)) != len(items) or not set(items) <= codes:
        raise ValueError("La selección contiene códigos desconocidos o repetidos.")
    known = set(items)
    matches = [r for r in model["rules"] if set(r["antecedent"]) <= known and r["consequent"] not in known]
    return {"selected_items": items, "rules": matches,
            "message": ("Selecciona al menos un antibiótico con resultado R para explorar las reglas." if not items
                        else "No hay reglas seleccionadas que añadan un elemento a esta selección. Esto no demuestra ausencia de asociación." if not matches
                        else f"Reglas disponibles para la selección: {len(matches)}."),
            "scope": "Resultados históricos de la cohorte; no predicción para un paciente."}


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
                      "/app.js": ("app.js", "text/javascript; charset=utf-8")}
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
