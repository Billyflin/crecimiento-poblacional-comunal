"""Inicia el explorador local en segundo plano: python3 app/iniciar.py."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'


def available(url):
    try:
        with urlopen(url + '/api/model', timeout=1) as response:
            model = json.load(response)
        return model.get('status') == 'predictive_v2_exploratory' and model.get('study') == 'crecimiento_v2'
    except (URLError, TimeoutError, ValueError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('El puerto debe estar entre 1 y 65535.')
    url = f'http://127.0.0.1:{args.port}'
    if available(url):
        print(f'La aplicación ya está disponible: {url}/')
        return
    RUNTIME.mkdir(exist_ok=True)
    log_path = RUNTIME / f'servidor-{args.port}.log'
    with log_path.open('ab') as log:
        process = subprocess.Popen(
            [sys.executable, '-u', str(ROOT / 'app/server.py'), '--port', str(args.port)],
            cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True,
        )
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(f'No se pudo iniciar el servidor. Revisar: {log_path}')
        if available(url):
            (RUNTIME / f'servidor-{args.port}.pid').write_text(str(process.pid) + '\n')
            print(f'Aplicación disponible: {url}/\nServidor en segundo plano (PID {process.pid}).')
            return
        time.sleep(.1)
    raise SystemExit(f'El servidor no respondió a tiempo. Revisar: {log_path}')


if __name__ == '__main__':
    main()
