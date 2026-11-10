"""Fail on non-SRD selection, broken indexes, expansion refs or structural UIDs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from build_srd import DROP, TAG_KIND, selected, strings, uid
from source_identity import SOURCE_ID,SOURCE_FIELDS
from layout_overrides import source_projection


def validate(root):
    root=Path(root)
    manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'))
    errors=[];records=[];payloads={}
    if manifest.get('source_id')!=SOURCE_ID:errors.append('Missing canonical SRD source declaration')
    model=Path(__file__).resolve().parents[1]/'source/citations.json'
    if manifest.get('citation_model_sha256')!=hashlib.sha256(model.read_bytes()).hexdigest():errors.append('Stale or missing source citation model')
    citation_model=json.loads(model.read_text(encoding='utf8'))
    if manifest.get('provisional_probe'):errors.append('Provisional source probe cannot be released')
    actual={p.relative_to(root).as_posix() for p in (root/'data').rglob('*.json')}
    if actual!=set(manifest['sha256']):errors.append('Data file inventory differs from manifest')
    for path,digest in manifest['sha256'].items():
        raw=(root/path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:errors.append('Hash mismatch: '+path)
        payload=json.loads(raw);payloads[path]=payload
        for kind,items in payload.items():
            if isinstance(items,list):
                for record in items:
                    if isinstance(record,dict):records.append((path,kind,record))
    try:
        _,layout_receipt=source_projection(payloads,require_all=True,require_applied=True)
        if manifest.get('layout_model_sha256')!=layout_receipt['model_sha256']:errors.append('Stale or missing approved layout model')
    except (ValueError,KeyError,TypeError,IndexError) as error:errors.append('Invalid approved layout overrides: '+str(error))
    allowed_helpers={'itemType','itemProperty','itemEntry'}
    def citation_key(kind,name,record):
        return (kind,name,*(record.get(k) for k in ('className','subclassShortName','level','set')))
    expected_citations={citation_key(r['kind'],r['name'],r['identity']):r['page'] for r in citation_model['records']}
    seen_citations=set()
    for path,kind,record in records:
        if record.get('source',record.get('inherits',{}).get('source'))!=SOURCE_ID:
            errors.append(f'Non-SRD source identity: {path}: {record.get("name")}')
        key=citation_key(kind,record.get('name',record.get('abbreviation')),record)
        seen_citations.add(key)
        expected_page=expected_citations.get(key)
        if key not in expected_citations:errors.append('Unknown cited entity: '+repr(key))
        elif record.get('inherits',record).get('page')!=expected_page or ('page' in record and record['page']!=expected_page):
            errors.append('Citation page differs from reviewed source: '+repr(key))
        if not selected(record) and not (path=='data/items-base.json' and kind in allowed_helpers):
            errors.append(f'Unselected entity: {path}: {kind}: {record.get("name")}')
    if seen_citations!=set(expected_citations):errors.append('Cited entity inventory differs from source model')
    entity={}
    for path,kind,record in records:
        mapped='item' if kind in {'itemGroup','baseitem','magicvariant'} else kind
        name=record.get('abbreviation','') if kind in {'itemType','itemProperty'} else record.get('name','')
        source=record.get('source',record.get('inherits',{}).get('source',''))
        entity.setdefault((mapped,name.lower(),source.lower()),[]).append(record)
    features=set();cards=set()
    for _,kind,record in records:
        if kind in {'classFeature','subclassFeature'}:
            parts=[record['name'],record['className'],record['classSource']]
            if kind=='subclassFeature':parts += [record['subclassShortName'],record['subclassSource']]
            parts += [str(record['level']),record['source']]
            features.add((kind,'|'.join(parts).lower()))
        if kind=='card':cards.add((record['name'].lower(),record['set'].lower(),record['source'].lower()))
    def feature_exists(kind,packed):
        parts=packed.split('|');pos=6 if kind=='subclassFeature' else 4
        if len(parts)==pos:parts.append(parts[4] if kind=='subclassFeature' else parts[2])
        return (kind,'|'.join(parts).lower()) in features
    def exists(kind,packed):
        parts=uid(packed).split('|');source=parts[1].split('#')[0].lower() if len(parts)>1 else ''
        return any(k==kind and n==parts[0].lower() and (not source or s==source) for k,n,s in entity)
    def walk(value,where):
        if isinstance(value,list):
            for item in value:walk(item,where)
        elif isinstance(value,dict):
            for key,item in value.items():
                if key in SOURCE_FIELDS and item!=SOURCE_ID:errors.append(f'Non-SRD source identity: {where}: {key}: {item}')
                if key in DROP or key=='_copy':errors.append(f'Excluded field {key}: {where}')
                if key in {'classFeatures','subclassFeatures'}:
                    kind='subclassFeature' if key=='subclassFeatures' else 'classFeature'
                    for ref in item:
                        packed=ref if isinstance(ref,str) else ref.get(kind,'')
                        if not feature_exists(kind,packed):errors.append(f'Feature reference: {where}: {packed}')
                if key=='type' and isinstance(item,str) and item in {'refClassFeature','refSubclassFeature'}:
                    kind=item[3].lower()+item[4:]
                    packed=value.get(kind,'')
                    if not isinstance(packed,str) or not feature_exists(kind,packed):errors.append('Nested feature reference: '+where)
                if key=='type' and isinstance(item,str) and item in {'refFeat','refOptionalfeature'}:
                    kind={'refFeat':'feat','refOptionalfeature':'optionalfeature'}[item]
                    packed=value.get(kind,'')
                    if not isinstance(packed,str) or not packed or not exists(kind,packed):
                        errors.append(f'Nested entity reference: {where}: {item}: {packed}')
                walk(item,where)
        elif isinstance(value,str):
            for tag,packed in re.findall(r'\{[#@]([A-Za-z]+) ([^{}]*)\}',value):
                if tag in TAG_KIND and not exists(TAG_KIND[tag],packed):errors.append(f'Inline reference: {where}: {tag} {packed}')
    for path,kind,record in records:
        where=path+':'+record.get('name',record.get('abbreviation',''))
        walk(record,where)
        if kind=='itemGroup':
            for packed in record.get('items',[]):
                if not exists('item',packed):errors.append(f'Item group: {where}: {packed}')
        if kind=='deck':
            for packed in record['cards']:
                if tuple(uid(packed).lower().split('|')) not in cards:errors.append(f'Deck card: {where}: {packed}')
        if kind in {'item','baseitem','magicvariant','itemGroup'}:
            for item in (record,record.get('inherits',{})):
                if item.get('type') and not exists('itemType',item['type']):errors.append(f'Item type: {where}: {item["type"]}')
                for prop in item.get('property',[]):
                    if not exists('itemProperty',prop):errors.append(f'Item property: {where}: {prop}')
                if item.get('baseItem') and not exists('item',item['baseItem']):errors.append(f'Base item: {where}: {item["baseItem"]}')
                if 'containerCapacity' in item:
                    capacity=item['containerCapacity']
                    if not isinstance(capacity,dict) or not capacity:
                        errors.append(f'Container capacity shape: {where}')
                        continue
                    compartments=capacity.get('item',[])
                    if not isinstance(compartments,list):
                        errors.append(f'Container capacity item shape: {where}')
                        continue
                    for compartment in compartments:
                        if not isinstance(compartment,dict) or not compartment:
                            errors.append(f'Container capacity compartment shape: {where}')
                            continue
                        for packed,amount in compartment.items():
                            if not exists('item',packed):errors.append(f'Container item: {where}: {packed}')
                            if type(amount) is not int or amount<=0:errors.append(f'Container item quantity: {where}: {packed}')
    for category in ('class','spells','bestiary'):
        for filename in payloads[f'data/{category}/index.json'].values():
            if f'data/{category}/{filename}' not in payloads:errors.append('Stale index: '+filename)
    wanted_classes={Path(path).stem.removeprefix('class-'):Path(path).name for path in payloads if path.startswith('data/class/class-')}
    if wanted_classes!=payloads['data/class/index.json']:errors.append('Incomplete source index: class')
    for category,kind in (('spells','spell'),('bestiary','monster')):
        wanted={}
        for path,payload in payloads.items():
            if path.startswith(f'data/{category}/{category}-'):
                for record in payload.get(kind,[]):
                    source=record['source'];filename=Path(path).name
                    if source in wanted and wanted[source]!=filename:errors.append('Source index would omit a file: '+source)
                    wanted[source]=filename
        if wanted!=payloads[f'data/{category}/index.json']:errors.append('Incomplete source index: '+category)
    all_text='\n'.join(text for _,_,record in records for text in strings(record))
    for term in ('Dragonlance','Towers of High Sorcery',"A Bard's Repertoire",'A Question of Enmity','Slaad Tadpole','Bastion','Pet Specialization','Eldritch Knight','Arcane Trickster','City of Sigil','Lady of Pain'):
        if term in all_text:errors.append('Excluded content remains: '+term)
    report={'passed':not errors,'files':len(payloads),'records':len(records),'errors':sorted(set(errors))}
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('root',type=Path,nargs='?',default=Path(__file__).resolve().parents[1])
    report=validate(parser.parse_args().root);print(json.dumps(report,indent=2));raise SystemExit(0 if report['passed'] else 1)
