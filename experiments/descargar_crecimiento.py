"""Descarga tabulados agregados del INE para la prueba predictiva censal.

Los HTML se conservan intactos. REDATAM requiere ejecutar la consulta y
descargar inmediatamente su iframe temporal. No se descargan personas.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from html import unescape
import json
from pathlib import Path
import re
import time
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/raw/ine/crecimiento'
REDATAM = 'https://redatam-ine.ine.cl/redbin/RpWebStats.exe/'
XLSX = {
    'poblacion_2024.xlsx': 'https://censo2024.ine.gob.cl/wp-content/uploads/2025/03/D1_Poblacion-censada-por-sexo-y-edad-en-grupos-quinquenales.xlsx',
    'residentes_2017.xlsx': 'https://censo2024.ine.gob.cl/wp-content/uploads/2025/04/Poblacion-censada-y-residentes-habituales-Censo-2017.xlsx',
}


def request(url, params=None):
    body = None if params is None else urlencode(params).encode()
    for attempt in range(3):
        try:
            with urlopen(Request(url, data=body, headers={'User-Agent': 'EstudioAcademicoCensal/1.0'}), timeout=55) as response:
                return response.read()
        except OSError:
            if attempt == 2:
                raise
            time.sleep(1)


def query_spec(year, local=False):
    action = 'AreaList' if local else 'CrossTab'
    params = {
        'MAIN': 'WebServerMain.inl', 'BASE': f'CENSO_{year}', 'LANG': 'esp',
        'CODIGO': 'XXUSUARIOXX', 'ITEM': 'AREAPOB' if local else 'CRUCPOB',
        'MODE': 'RUN', 'SELECTION': 'ALL', 'INLINESELECTION': '',
        'FORMAT': 'HTML', 'PERCENT': 'OFF', 'UNIVERSE': '', 'FILTER': '',
        'TEXT_FILTER': 'PERSONA.P10 = 1 OR PERSONA.P10 = 2' if local else '',
        'Submit': 'Ejecutar',
    }
    if local:
        params.update(VARIABLE='PERSONA.EDQUINQ', OUTPUT='COMUNA', TOTCOL='on')
    else:
        params.update(ROW='PERSONA.P10COMUNA' if year == 2017 else 'PERSONA.VIVEHAB',
                      COLUMN='PERSONA.EDQUINQ', CONTROL='', AREABREAK='')
    return REDATAM + action + '?', params


def query(year, local=False):
    url, params = query_spec(year, local)
    wrapper = request(url, params).decode('utf-8-sig')
    match = re.search(r'<iframe src="([^"]+)"', wrapper)
    if match is None:
        raise ValueError('REDATAM no devolvió una tabla; no se sustituye por datos sintéticos.')
    return request(unescape(match.group(1))), {'url': url, 'params': params}


def main():
    DEST.mkdir(parents=True, exist_ok=True)
    manifest = {'retrieved_at': datetime.now(timezone.utc).isoformat(),
                'publisher': 'Instituto Nacional de Estadísticas de Chile',
                'license': 'CC BY-SA 4.0', 'files': []}
    tasks = [(f'edad_residencia_{year}.html', year, False) for year in (1992, 2002, 2017)]
    tasks.append(('edad_local_2017.html', 2017, True))
    for name, year, local in tasks:
        path = DEST / name
        # Los archivos existentes son caché de las mismas consultas. La descripción
        # se reconstruye sin volver a pedir trabajos costosos al servicio oficial.
        url, params = query_spec(year, local)
        if not path.exists():
            data, source = query(year, local)
            path.write_bytes(data)
        else:
            data = path.read_bytes()
            source = {'url': url, 'params': params}
        manifest['files'].append({'file': name, **source, 'bytes': len(data), 'sha256': sha256(data).hexdigest()})
        print(f'{name}: {len(data):,} bytes', flush=True)
    for name, url in XLSX.items():
        path = DEST / name
        if not path.exists():
            path.write_bytes(request(url))
        data = path.read_bytes()
        manifest['files'].append({'file': name, 'url': url, 'bytes': len(data), 'sha256': sha256(data).hexdigest()})
    (DEST / 'fuentes.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
