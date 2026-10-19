"""Descarga fuentes publicadas en el portal oficial del Censo 2024."""
import hashlib
import json
import shutil
import urllib.request
from urllib.error import HTTPError
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/raw/ine'
PORTAL = 'https://brave-grass-0c5df3c0f.3.azurestaticapps.net/datos.json'
WANTED = ['hogares_censo2024.zip', 'viviendas_censo2024.zip',
          'manual_uso_microdatos_censo2024.pdf', 'diccionario_variables_censo2024.xlsx']

def main():
    DEST.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(PORTAL, timeout=60) as response:
        catalog = json.load(response)
    (DEST / 'catalogo_descargas.json').write_text(json.dumps(catalog, ensure_ascii=False, indent=2))
    entries = [e for e in catalog['datos']['pais'] if e['url'].split('/')[-1] in WANTED]
    if len(entries) != len(WANTED):
        raise RuntimeError('El catálogo cambió; revisar las fuentes antes de descargar.')

    def download(entry):
        path = DEST / entry['url'].split('/')[-1]
        if not path.exists():
            temporary = path.with_suffix(path.suffix + '.part')
            try:
                with urllib.request.urlopen(entry['url'], timeout=120) as response, temporary.open('wb') as output:
                    shutil.copyfileobj(response, output, length=1024 * 1024)
            except HTTPError as error:
                if path.suffix == '.xlsx' and error.code == 404:
                    print('Diccionario XLSX no disponible (404); usar diccionario del manual PDF.', flush=True)
                    return {**entry, 'available': False, 'http_status': 404}
                raise
            temporary.replace(path)
        digest = hashlib.file_digest(path.open('rb'), 'sha256').hexdigest()
        print(f'Disponible: {path.name} ({path.stat().st_size:,} bytes)', flush=True)
        return {**entry, 'file': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size, 'sha256': digest}

    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(download, entries))
    manifest = {'retrieved_at': datetime.now(timezone.utc).isoformat(), 'catalog_url': PORTAL,
                'landing_url': 'https://censo2024.ine.gob.cl/resultados/',
                'license_url': 'https://www.ine.gob.cl/terminos-de-uso-y-licencia-de-datos-abiertos',
                'license': 'CC BY-SA 4.0', 'files': records}
    (DEST / 'fuentes.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
