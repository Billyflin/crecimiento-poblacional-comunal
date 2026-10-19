"""Aplicación local de la primera prueba predictiva censal."""
from __future__ import annotations
import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
STATIC = Path(__file__).resolve().parent / 'static'
MODEL_PATH = ROOT / 'results/crecimiento_v2/modelo.json'
TUNING_PATH = ROOT / 'results/tuning_crecimiento/resumen.json'

def load_model(path=MODEL_PATH):
    model = json.loads(Path(path).read_text(encoding='utf-8'))
    if model.get('status') != 'predictive_v2_exploratory' or model.get('study') != 'crecimiento_v2':
        raise ValueError('Se requiere el experimento predictivo ejecutado.')
    codes = [r['code'] for r in model['records']]
    if len(codes) != len(set(codes)) or len(codes) != model['summary']['n_communes']:
        raise ValueError('Identidades inconsistentes en el modelo.')
    if TUNING_PATH.exists():
        tuning = json.loads(TUNING_PATH.read_text(encoding='utf-8'))
        if tuning.get('study') != 'tuning_crecimiento' or tuning.get('comparison_n') != 314:
            raise ValueError('El informe de tuning no corresponde a esta comparación.')
        model['tuning'] = {k: tuning[k] for k in ('selected', 'selected_algorithm',
            'selected_parameters',
            'score_threshold', 'comparison_n', 'validation', 'test', 'threshold_only_v2',
            'improved_vs_v2', 'reused_2024')}
    return model

def query_model(model, payload):
    if not isinstance(payload, dict) or set(payload) != {'commune', 'mode'}:
        raise ValueError('Envía commune y mode.')
    if type(payload['commune']) is not int or not isinstance(payload['mode'], str) or payload['mode'] not in ('estudio', 'futuro'):
        raise ValueError('Elige una comuna y un modo válidos.')
    record = next((r for r in model['records'] if r['code'] == payload['commune']), None)
    if record is None:
        raise ValueError('La comuna no tiene una serie incluida en esta primera prueba.')
    key = 'test' if payload['mode'] == 'estudio' else 'forecast'
    return {'code': record['code'], 'name': record['name'], 'region': record['region'],
            'mode': payload['mode'], 'model': model['summary']['selected'],
            'algorithm': model['summary']['selected_algorithm'],
            'recovered': record['recovered'], 'geography_note': record['geography_note'],
            'period': [2017, 2024] if key == 'test' else [2024, 2031],
            'result': record[key]}

def make_handler(model):
    class Handler(BaseHTTPRequestHandler):
        def send_bytes(self, status, content, mime):
            self.send_response(status)
            self.send_header('Content-Type', mime)
            self.send_header('Content-Length', str(len(content)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(content)
        def send_json(self, status, value):
            self.send_bytes(status, json.dumps(value, ensure_ascii=False, allow_nan=False).encode(), 'application/json; charset=utf-8')
        def do_GET(self):
            route = urlsplit(self.path).path
            if route == '/api/model':
                return self.send_json(200, {'status': model['status'], 'study': model['study'],
                    'summary': model['summary'], 'protocol': model['protocol'],
                    'tuning': model.get('tuning'),
                    'communes': [{k: r[k] for k in ('code', 'name', 'region', 'region_code', 'recovered')} for r in model['records']],
                    'quality': model['quality'],
                    'excluded': model['quality']['exclusions']})
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/styles.css': ('styles.css', 'text/css; charset=utf-8'),
                      '/app.js': ('app.js', 'text/javascript; charset=utf-8')}
            if route not in assets:
                return self.send_json(404, {'error': 'Ruta no encontrada.'})
            name, mime = assets[route]
            self.send_bytes(200, (STATIC / name).read_bytes(), mime)
        def do_POST(self):
            if urlsplit(self.path).path != '/api/query':
                return self.send_json(404, {'error': 'Ruta no encontrada.'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 4096 or self.headers.get('Content-Type', '').split(';')[0] != 'application/json':
                    raise ValueError('Envía una consulta JSON de hasta 4096 bytes.')
                result = query_model(model, json.loads(self.rfile.read(length).decode()))
            except (ValueError, UnicodeDecodeError) as error:
                return self.send_json(400, {'error': str(error)})
            self.send_json(200, result)
    return Handler

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    with ThreadingHTTPServer(('127.0.0.1', args.port), make_handler(load_model())) as server:
        print('Aplicación predictiva: http://127.0.0.1:' + str(args.port) + '/', flush=True)
        server.serve_forever()

if __name__ == '__main__':
    main()
