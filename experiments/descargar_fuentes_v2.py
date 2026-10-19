"""Conserva evidencia territorial de v2; no descarga proyecciones ni cifras de 2012 para modelar."""
from datetime import datetime,timezone
from hashlib import sha256
import json
from pathlib import Path
from descargar_crecimiento import request

ROOT=Path(__file__).resolve().parents[1]
RAW=ROOT/'data/raw/ine/crecimiento'
SOURCES={
 'actualizacion_dpa_ine_2018.html':'https://www.ine.gob.cl/sala-de-prensa/prensa/general/noticia/2019/09/16/ine-actualiza-informaci%C3%B3n-de-censo-2017-a-la-nueva-divisi%C3%B3n-pol%C3%ADtica-administrativa-incorporando-la-nueva-regi%C3%B3n-de-%C3%B1uble',
 'diccionario_2002.html':'https://redatam-ine.ine.cl/redbin/RpWebStats.exe/Dictionary?BASE=CENSO_2002&ITEM=DICALL&lang=esp',
 'antecedentes_limites_mma_2015.pdf':'https://airechile.mma.gob.cl/download/DO-PDA-Temuco-y-Padre-Las-%20Casas.pdf'
}

def main():
    records=[]
    for filename,url in SOURCES.items():
        path=RAW/filename
        if not path.exists():path.write_bytes(request(url))
        data=path.read_bytes()
        records.append({'file':filename,'url':url,'bytes':len(data),'sha256':sha256(data).hexdigest(),
                        'scope':'Evidencia de procedencia o límites; no aporta etiquetas adicionales al modelo.'})
        print(filename,len(data),flush=True)
    (RAW/'fuentes_territoriales_v2.json').write_text(json.dumps({
        'retrieved_at':datetime.now(timezone.utc).isoformat(),'files':records,
        'legal_references':['https://www.bcn.cl/leychile/Navegar?idNorma=30758','https://www.bcn.cl/leychile/navegar?idNorma=1038291'],
        'census_manifest':'fuentes.json',
        'note':'Las cifras de 2012 del documento MMA no son datos de entrenamiento, respuestas o validación.'
    },ensure_ascii=False,indent=2)+'\n')

if __name__=='__main__':main()
