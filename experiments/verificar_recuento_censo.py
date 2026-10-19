"""Contraste de una regla publicada con un join independiente de los CSV crudos."""
import json
from pathlib import Path
import zipfile
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/ine'
OUT = ROOT / 'results/censo_2024'

def chunks(name, columns):
    with zipfile.ZipFile(RAW / f'{name}_censo2024.zip') as z:
        with z.open(f'{name}_censo2024.csv') as f:
            yield from pd.read_csv(f,sep=';',usecols=columns,chunksize=150_000)

def main():
    model = json.loads((OUT / 'modelo.json').read_text())
    rule = next(r for r in model['rules'] if set(r['antecedent']) == {'area:2','tipologia:1'} and r['consequent'] == 'internet:2')
    parts = []
    columns = ['id_vivienda','id_hogar','tipo_operativo','region','area','tipologia_hogar','p12_tenencia_viv','p15b_serv_compu','p15d_serv_internet_fija']
    for frame in chunks('hogares',columns):
        subset = frame[(frame.tipo_operativo == 2) & (frame.area == 2) & (frame.tipologia_hogar == 1) &
                       frame.p12_tenencia_viv.isin(range(1,10)) & frame.p15b_serv_compu.isin([1,2]) & frame.p15d_serv_internet_fija.isin([1,2])]
        parts.append(subset)
    households = pd.concat(parts,ignore_index=True)
    ids = set(households.id_vivienda)
    parts = []
    for frame in chunks('viviendas',['id_vivienda','p6_fuente_agua','indice_hacinamiento']):
        parts.append(frame.loc[frame.id_vivienda.isin(ids)])
    houses = pd.concat(parts,ignore_index=True)
    joined = households.merge(houses,on='id_vivienda',how='left',validate='many_to_one',indicator=True)
    assert (joined['_merge'] == 'both').all()
    joined = joined[joined.p6_fuente_agua.isin([1,2,3,4]) & joined.indice_hacinamiento.isin([1,2,3])]
    result = {'rule_id':rule['id'],'method':'Filtrado de CSV y merge pandas independiente, sin usar conteos de perfiles','by_region':{}}
    for r in range(17):
        part = joined if r == 0 else joined[joined.region == r]
        a,b = len(part),int((part.p15d_serv_internet_fija == 2).sum())
        expected = rule['population'] if r == 0 else rule['by_region'][str(r)]
        assert a == expected['antecedent_count'], (r,a,expected)
        assert b == expected['joint_count'], (r,b,expected)
        result['by_region'][str(r)] = {'antecedent_count':a,'joint_count':b}
    (OUT / 'verificacion_independiente.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(f"Verificado por unión independiente: {result['rule_id']}; {len(joined):,} antecedentes; Chile y 16 regiones.")

if __name__ == '__main__':
    main()
