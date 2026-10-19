"""Procesamiento completo por bloques y reglas de asociación del Censo 2024.

No requiere expandir millones de filas a una matriz one-hot. Cuenta exactamente
los perfiles categóricos de todos los hogares y aplica Apriori hasta tamaño 3.
"""
from __future__ import annotations
from collections import Counter
from itertools import combinations
import hashlib
import json
import math
from pathlib import Path
import time
import zipfile
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / 'data/raw/ine'
OUT = ROOT / 'results/censo_2024'
PROTOCOL = ROOT / 'experiments/protocolo_censo_2024.json'
GROUPS = [
    ('area', 'Área', 'area', ['Urbana', 'Rural']),
    ('tenencia', 'Tenencia', 'p12_tenencia_viv', ['Propia pagada', 'Propia pagándose', 'Arrendada con contrato', 'Arrendada sin contrato', 'Cedida por trabajo o servicio', 'Cedida por familiar u otro', 'Usufructo', 'Ocupada de hecho', 'En sucesión o litigio']),
    ('tipologia', 'Tipo de hogar', 'tipologia_hogar', ['Unipersonal', 'Nuclear monoparental', 'Nuclear pareja sin hijos', 'Nuclear pareja con hijos', 'Extenso', 'Compuesto', 'Sin núcleo']),
    ('agua', 'Fuente de agua', 'p6_fuente_agua', ['Red pública', 'Pozo o noria', 'Camión aljibe', 'Río, vertiente, estero, canal, lago o lluvia']),
    ('hacinamiento', 'Hacinamiento de la vivienda', 'indice_hacinamiento', ['Sin hacinamiento', 'Hacinamiento medio', 'Hacinamiento crítico']),
    ('computador', 'Computador', 'p15b_serv_compu', ['Con computador', 'Sin computador']),
    ('internet', 'Internet fija', 'p15d_serv_internet_fija', ['Con internet fija', 'Sin internet fija'])]
REGIONS = {1:'Tarapacá', 2:'Antofagasta', 3:'Atacama', 4:'Coquimbo', 5:'Valparaíso', 6:"O’Higgins", 7:'Maule', 8:'Biobío', 9:'La Araucanía', 10:'Los Lagos', 11:'Aysén', 12:'Magallanes', 13:'Metropolitana', 14:'Los Ríos', 15:'Arica y Parinacota', 16:'Ñuble'}
SIZES = tuple(len(g[3]) for g in GROUPS)
PROFILE_COUNT = math.prod(SIZES)
COORDS = np.array(np.unravel_index(np.arange(PROFILE_COUNT), SIZES)).T
ITEMS = [{'code': f'{group}:{i+1}', 'group': group, 'group_label': label, 'source_variable': source,
          'value': i+1, 'label': name, 'antecedent_allowed': j < 5}
         for j, (group, label, source, names) in enumerate(GROUPS) for i, name in enumerate(names)]
BY_CODE = {item['code']: item for item in ITEMS}
MASKS = {item['code']: COORDS[:, next(j for j,g in enumerate(GROUPS) if g[0] == item['group'])] == item['value']-1 for item in ITEMS}

def partition(vivienda):
    """SplitMix64: vivienda compartida siempre pertenece a la misma partición."""
    x = np.asarray(vivienda, dtype=np.uint64) + np.uint64(2024)
    with np.errstate(over='ignore'):
        x = (x ^ (x >> np.uint64(30))) * np.uint64(0xbf58476d1ce4e5b9)
        x = (x ^ (x >> np.uint64(27))) * np.uint64(0x94d049bb133111eb)
        x = x ^ (x >> np.uint64(31))
    bucket = x % np.uint64(100)
    return np.where(bucket < 70, 0, np.where(bucket < 85, 1, 2))

def read_chunks(name, columns):
    with zipfile.ZipFile(RAW / f'{name}_censo2024.zip') as archive:
        members = [x for x in archive.namelist() if x.endswith('.csv')]
        if len(members) != 1:
            raise ValueError('Se esperaba un único CSV en el ZIP oficial.')
        with archive.open(members[0]) as file:
            yield from pd.read_csv(file, sep=';', usecols=columns, dtype='float64', chunksize=150_000)

def prepare():
    # Un índice denso evita una unión de DataFrames de varios GB.
    maximum_id = 7_664_466
    fields = ['region', 'area', 'tipo_operativo', 'p6_fuente_agua', 'indice_hacinamiento']
    houses = np.full((maximum_id+1, len(fields)), -100, dtype=np.int16)
    present = np.zeros(maximum_id+1, dtype=bool)
    seen_hog = np.zeros(maximum_id+1, dtype=np.uint32)
    dwelling_rows = 0
    for frame in read_chunks('viviendas', ['id_vivienda']+fields):
        ids = frame['id_vivienda'].to_numpy(dtype=np.int64)
        if np.any(ids < 1) or np.any(ids > maximum_id) or len(np.unique(ids)) != len(ids) or present[ids].any():
            raise ValueError('Identificador de vivienda repetido o fuera del diccionario.')
        values = frame[fields].fillna(-100).to_numpy(dtype=np.int16)
        houses[ids] = values
        present[ids] = True
        dwelling_rows += len(frame)
    if dwelling_rows != maximum_id:
        raise ValueError('La versión de viviendas difiere del manual; revisar antes de continuar.')
    counts = np.zeros((3, 17, PROFILE_COUNT), dtype=np.int64)
    missing = Counter()
    audit = Counter()
    by_region = {r:Counter() for r in REGIONS}
    marginals = {source:Counter() for _,_,source,_ in GROUPS}
    household_fields = ['id_vivienda', 'id_hogar', 'tipo_operativo', 'region', 'area', 'p12_tenencia_viv', 'tipologia_hogar', 'p15b_serv_compu', 'p15d_serv_internet_fija']
    for frame in read_chunks('hogares', household_fields):
        audit['household_file_rows'] += len(frame)
        audit['excluded_other_operations'] += int((frame.tipo_operativo != 2).sum())
        frame = frame.loc[frame.tipo_operativo == 2]
        ids = frame.id_vivienda.to_numpy(dtype=np.int64)
        hids = frame.id_hogar.to_numpy(dtype=np.int64)
        if np.any(ids < 1) or np.any(ids > maximum_id) or np.any(hids < 1) or np.any(hids > 26) or not present[ids].all():
            raise ValueError('Clave de hogar o referencia a vivienda inválida.')
        keys = ids*32 + hids
        if len(np.unique(keys)) != len(keys):
            raise ValueError('Hogar duplicado dentro de un bloque.')
        bits = np.left_shift(np.uint32(1), hids.astype(np.uint32))
        if np.any(np.bitwise_and(seen_hog[ids], bits)):
            raise ValueError('Hogar duplicado entre bloques.')
        np.bitwise_or.at(seen_hog, ids, bits)
        house = houses[ids]
        region = frame.region.to_numpy(dtype=np.int16)
        area = frame.area.to_numpy(dtype=np.int16)
        if not np.array_equal(region, house[:,0]) or not np.array_equal(area, house[:,1]) or not np.all(house[:,2] == 2):
            raise ValueError('La unión altera región, área o tipo de operativo.')
        values = np.column_stack([area, frame.p12_tenencia_viv.fillna(-100), frame.tipologia_hogar.fillna(-100), house[:,3], house[:,4], frame.p15b_serv_compu.fillna(-100), frame.p15d_serv_internet_fija.fillna(-100)]).astype(np.int16)
        valid = np.ones(len(frame), dtype=bool)
        for j,(_,_,source,_) in enumerate(GROUPS):
            ok = (values[:,j] >= 1) & (values[:,j] <= SIZES[j])
            missing[source] += int((~ok).sum())
            valid &= ok
            unique, frequencies = np.unique(values[:,j], return_counts=True)
            marginals[source].update(dict(zip(unique.tolist(), frequencies.tolist())))
        audit['private_households'] += len(frame)
        audit['complete_households'] += int(valid.sum())
        for r in REGIONS:
            belongs = region == r
            by_region[r]['private_households'] += int(belongs.sum())
            by_region[r]['complete_households'] += int((belongs & valid).sum())
        codes = np.ravel_multi_index((values[valid]-1).T, SIZES)
        splits = partition(ids[valid])
        regions = region[valid]
        flat = (splits*17 + regions)*PROFILE_COUNT + codes
        counts += np.bincount(flat, minlength=3*17*PROFILE_COUNT).reshape(counts.shape)
        print(f"Hogares leídos: {audit['household_file_rows']:,}; completos: {audit['complete_households']:,}", flush=True)
    counts[:,0] = counts[:,1:].sum(axis=1)
    audit['dwelling_file_rows'] = dwelling_rows
    audit['excluded_incomplete'] = audit['private_households'] - audit['complete_households']
    audit['private_household_dwellings'] = int(np.count_nonzero(seen_hog))
    # Contar viviendas completas sin volver a almacenar identificadores individuales.
    audit['join_unmatched'] = 0
    audit['duplicate_households'] = 0
    audit['missing_by_variable'] = dict(missing)
    audit['by_region'] = {str(r):dict(c) for r,c in by_region.items()}
    audit['marginals_before_complete_case_exclusion'] = {k:dict(v) for k,v in marginals.items()}
    audit['split_counts'] = dict(zip(['discovery','selection','test'], counts[:,0].sum(axis=1).tolist()))
    np.savez_compressed(OUT / 'conteos_perfiles.npz', counts=counts, sizes=np.array(SIZES))
    (OUT / 'calidad_datos.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2))
    return counts, audit

def item_count(frequencies, codes):
    mask = np.ones(PROFILE_COUNT, dtype=bool)
    for code in codes:
        mask &= MASKS[code]
    return int(frequencies[mask].sum())

def metrics(frequencies, antecedent, consequent):
    n = int(frequencies.sum())
    a = item_count(frequencies, antecedent)
    b = item_count(frequencies, [consequent])
    ab = item_count(frequencies, list(antecedent)+[consequent])
    confidence = ab/a if a else None
    baseline = b/n if n else None
    return {'n':n, 'antecedent_count':a, 'consequent_count':b, 'joint_count':ab,
            'support':ab/n if n else None, 'confidence':confidence, 'baseline':baseline,
            'lift':confidence/baseline if a and b and n else None}

def apriori(frequencies, minimum, max_size=3):
    """Ítems frecuentes con poda Apriori y exclusión de categorías incompatibles."""
    threshold = math.ceil(int(frequencies.sum())*minimum)
    frequent = {(c,):item_count(frequencies,[c]) for c in BY_CODE}
    frequent = {c:n for c,n in frequent.items() if n >= threshold}
    previous = set(frequent)
    for size in range(2,max_size+1):
        candidates = set()
        for left,right in combinations(sorted(previous),2):
            union = tuple(sorted(set(left)|set(right)))
            if len(union) != size or len({BY_CODE[c]['group'] for c in union}) != size:
                continue
            if not all(tuple(subset) in previous for subset in combinations(union,size-1)):
                continue
            candidates.add(union)
        level = {c:item_count(frequencies,c) for c in candidates}
        level = {c:n for c,n in level.items() if n >= threshold}
        frequent.update(level)
        previous = set(level)
    return frequent

def passes_selection(rule, config, protocol):
    s,d = rule['selection'],rule['discovery']
    limits = protocol['selection']
    return (s['antecedent_count'] >= limits['min_antecedent_count'] and
            s['support'] >= limits['min_support'] and
            s['confidence'] >= config['min_confidence'] - limits['confidence_tolerance'] and
            s['lift'] >= limits['min_lift'] and
            abs(s['confidence'] - d['confidence']) <= limits['max_confidence_drift'])

def build(counts, audit):
    protocol = json.loads(PROTOCOL.read_text())
    configs, candidates, comparison = protocol['configurations'], [], []
    for config in configs:
        frequent = apriori(counts[0,0], config['min_support'])
        rules = []
        for pattern in sorted(frequent):
            for consequent in pattern:
                if BY_CODE[consequent]['group'] not in protocol['consequent_groups']:
                    continue
                antecedent = tuple(c for c in pattern if c != consequent)
                if not antecedent or any(BY_CODE[c]['group'] not in protocol['antecedent_groups'] for c in antecedent):
                    continue
                d = metrics(counts[0,0],antecedent,consequent)
                if d['confidence'] < config['min_confidence'] or d['lift'] < protocol['min_discovery_lift']:
                    continue
                if len(antecedent) == 2:
                    simpler = max(metrics(counts[0,0],[a],consequent)['confidence'] for a in antecedent)
                    if d['confidence'] - simpler < protocol['two_condition_min_confidence_gain']:
                        continue
                rule = {'id':' + '.join(antecedent)+' -> '+consequent, 'configuration':config['name'],
                        'antecedent':list(antecedent), 'consequent':consequent, 'discovery':d,
                        'selection':metrics(counts[1,0],antecedent,consequent)}
                rule['eligible'] = passes_selection(rule,config,protocol)
                rules.append(rule)
        eligible = [r for r in rules if r['eligible']]
        comparison.append({**config, 'candidate_rules':len(rules), 'eligible_rules':len(eligible),
                           'consequent_categories':len({r['consequent'] for r in eligible}),
                           'retention':len(eligible)/len(rules) if rules else 0,
                           'mean_antecedent_size':sum(len(r['antecedent']) for r in eligible)/len(eligible) if eligible else 100})
        candidates.extend(rules)
    best = max(comparison,key=lambda c:(c['consequent_categories'],c['retention'],-c['mean_antecedent_size'],c['min_support']))
    selected = [r for r in candidates if r['eligible'] and r['configuration'] == best['name']]
    selected.sort(key=lambda r:(-r['discovery']['lift'], -r['discovery']['support'],r['id']))
    # La elección y el orden quedan cerrados antes de acceder a la partición de prueba.
    decision = {'selected_configuration':best['name'], 'rule_ids':[r['id'] for r in selected],
                'protocol_sha256':hashlib.file_digest(PROTOCOL.open('rb'),'sha256').hexdigest()}
    (OUT / 'seleccion_cerrada.json').write_text(json.dumps(decision,ensure_ascii=False,indent=2))
    geographic = []
    for rule in selected:
        a,b = rule['antecedent'], rule['consequent']
        rule['test'] = metrics(counts[2,0],a,b)
        rule['population'] = metrics(counts[:,0].sum(axis=0),a,b)
        rule['by_region'] = {str(r):metrics(counts[:,r].sum(axis=0),a,b) for r in REGIONS}
        for r,m in rule['by_region'].items():
            geographic.append({'rule_id':rule['id'],'region':int(r),**m})
    example = next((r['antecedent'] for r in selected if len(r['antecedent']) == 1), selected[0]['antecedent'] if selected else [])
    source = json.loads((RAW / 'fuentes.json').read_text())
    model = {'status':'exploratory', 'title':protocol['title'], 'census_year':2024,
             'sample_count':audit['complete_households'], 'private_households':audit['private_households'],
             'excluded_incomplete':audit['excluded_incomplete'], 'split_counts':audit['split_counts'],
             'items':ITEMS, 'regions':[{'code':r,'label':REGIONS[r],**audit['by_region'][str(r)]} for r in REGIONS],
             'selected_configuration':best['name'], 'comparison':comparison, 'rules':selected,
             'example_items':example, 'region_min_antecedents':100,
             'source':source, 'protocol_sha256':decision['protocol_sha256'],
             'scope':'Asociaciones descriptivas de hogares con datos completos del Censo 2024; evaluación interna por vivienda.'}
    (OUT / 'modelo.json').write_text(json.dumps(model,ensure_ascii=False,indent=2,allow_nan=False))
    (OUT / 'reglas_candidatas.json').write_text(json.dumps(candidates,ensure_ascii=False,indent=2,allow_nan=False))
    pd.DataFrame(comparison).to_csv(OUT / 'comparacion.csv',index=False)
    pd.DataFrame(geographic).to_csv(OUT / 'reglas_por_region.csv',index=False)
    rows = [{'rule_id':r['id'], 'antecedent':' + '.join(r['antecedent']), 'consequent':r['consequent'],
             **{f'{stage}_{k}':v for stage in ['discovery','selection','test','population'] for k,v in r[stage].items()}} for r in selected]
    pd.DataFrame(rows).to_csv(OUT / 'reglas.csv',index=False)
    summary = {'quality':audit, 'comparison':comparison, 'selected_configuration':best['name'], 'selected_rules':len(selected),
               'test_min_lift':min((r['test']['lift'] for r in selected),default=None),
               'test_max_confidence_drift':max((abs(r['test']['confidence']-r['discovery']['confidence']) for r in selected),default=None)}
    (OUT / 'resumen.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    print(json.dumps({k:v for k,v in summary.items() if k != 'quality'},ensure_ascii=False,indent=2),flush=True)

def main():
    start = time.monotonic()
    OUT.mkdir(parents=True,exist_ok=True)
    manifest = json.loads((RAW / 'fuentes.json').read_text())
    for entry in manifest['files']:
        if entry.get('available',True) and hashlib.file_digest((ROOT / entry['file']).open('rb'),'sha256').hexdigest() != entry['sha256']:
            raise ValueError('El archivo fuente cambió respecto del manifiesto.')
    counts,audit = prepare()
    build(counts,audit)
    print(f'Tiempo total: {time.monotonic()-start:.1f} segundos',flush=True)

if __name__ == '__main__':
    main()
