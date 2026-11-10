"""Verify retained lighting, poison-type and movement query metadata.

Fresh printed clauses, poison headers, vehicle grids and animal statblocks
supply the answers. Item identity selects a source scope, never candidate
values. Light dim distances are outer extents (bright plus additional dim),
not the additional annulus alone. These query indexes describe an available
effect; activation, form, wearing/holding, duration, upper/lower bounds and
other conditions remain in the complete source evidence and literal prose.
"""
import argparse
from collections import Counter
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from locate_source_citations import Source as CitationSource,canon,heading_key
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from verify_item_abilities import exact
from verify_item_families import prove_models,required_paragraph_indexes
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'light','poison','poisonTypes','modifySpeed','speed','vehSpeed'}
LIGHT={'Apparatus of the Crab','Bullseye Lantern','Candle','Candle of Invocation','Gem of Brightness',
       'Helm of Brilliance','Hooded Lantern','Lamp','Lantern of Revealing','Mace of Disruption',
       'Quarterstaff of the Acrobat','Ring of Shooting Stars','Robe of Scintillating Colors',
       'Rod of Alertness','Rod of Lordly Might','Sun Blade','Torch','Energy Bow','Flame Tongue','Frost Brand'}
MOVEMENT={'Boots of Speed','Boots of Striding and Springing','Cloak of Arachnida','Cloak of the Manta Ray',
          'Potion of Climbing','Potion of Flying','Ring of Elemental Command (Air)','Ring of Swimming',
          'Slippers of Spider Climbing','Winged Boots','Wings of Flying'}
VARIANTS={'Energy Bow','Flame Tongue','Frost Brand'}
MOUNT_NAMES={'Horse, Draft':'Draft Horse','Horse, Riding':'Riding Horse'}


def physical_header(src,glyphs):
    chars=[];lines=[]
    for line in src['lines']:
        if not all(f.startswith('Cambria-Italic') for f in line['fonts']):break
        matches=[l for l in glyphs.page(line['page'])['lines'] if (l['block'],l['line'])==(line['block'],line['line'])]
        if len(matches)!=1:raise ValueError('Poison physical header locator changed')
        chars+=matches[0]['chars'];lines.append(line)
    header=glyphs.text(chars)
    if any(j['basis'].startswith('UNRESOLVED') for j in header['layout_joins']):raise ValueError('Unresolved poison header wrap')
    return {**header,'source_lines':lines}


def grid(source,caption,label,headers,count):
    result=source.table_row(caption,label)
    if result['status']!='LOCATED':raise ValueError(('Missing physical source row',caption,label))
    table=source.table_cache[caption]
    if table['headers']!=headers or len(table['rows'])!=count:raise ValueError(('Physical source grid inventory changed',caption))
    rows=[[c['text'] for c in row['cells']] for row in table['rows']]
    if len({row[0] for row in rows})!=count:raise ValueError(('Duplicate source row identities',caption))
    return rows,table


def mount_speed(source,name):
    headings=[h for h in source.by_key.get(heading_key(name),[]) if h['page']>254 and
              h['fonts']==['GillSans-SemiBold'] and all(size>=14 for size in h['sizes']) and h['colors']==[0x8c2220]]
    if len(headings)!=1:raise ValueError(('Ambiguous animal statblock identity',name))
    heading=headings[0]
    following=[l for l in source.pages[heading['page']] if l['column']==heading['column'] and
               heading['origin'][1]<l['origin'][1]<heading['origin'][1]+100]
    lines=[l for l in following if re.fullmatch(r'Speed (\d+) ft\.',l['text'])]
    if len(lines)!=1 or not any(l['text'].startswith('HP ') for l in following) or not any(l['text'].startswith('AC ') for l in following):
        raise ValueError(('Animal speed statline boundary changed',name))
    return int(re.fullmatch(r'Speed (\d+) ft\.',lines[0]['text'])[1]),{'printed_statblock_heading':heading,'printed_speed_line':lines[0]}


def source_inventory(a,models):
    _,errors=prove_models(a,models)
    if errors:raise ValueError(('Family source model differs from fresh PDF',errors))
    source=CitationSource(a.doc);glyphs=GlyphSource(a.doc);poisons={}
    for heading,src in a.SOURCES.items():
        pages={line['page'] for line in src['heading_lines']}
        match=re.fullmatch(r'(.+) \([\d,]+ GP\)',heading)
        if not match or not pages<={197,198}:continue
        header=physical_header(src,glyphs);kind=re.fullmatch(r'(Contact|Ingested|Inhaled|Injury) Poison',header['text'])
        if not kind:raise ValueError(('Missing printed poison type',heading))
        name=canon(match[1])
        if name in poisons:raise ValueError('Duplicate poison source identity')
        poisons[name]={'type':kind[1].lower(),'source_heading':heading,'header':header}
    if len(poisons)!=14 or {p['type'] for p in poisons.values()}!={'contact','ingested','inhaled','injury'}:
        raise ValueError('Poison source inventory changed')
    mounts,mount_table=grid(source,'Mounts and Other Animals','Camel',['Item','Carrying Capacity','Cost'],8)
    animals={}
    for row in mounts:
        name=MOUNT_NAMES.get(row[0],row[0]);speed,evidence=mount_speed(source,name)
        animals[name]={'speed':speed,'equipment_row':row,**evidence}
    vehicles,vehicle_table=grid(source,'Airborne and Waterborne Vehicles','Airship',
                               ['Ship','Speed','Crew','Passengers','Cargo (Tons)','AC','HP','Damage Threshold','Cost'],7)
    vehicle_speeds={}
    for row in vehicles:
        match=re.fullmatch(r'(\d+)(½)? mph',row[1])
        if not match:raise ValueError(('Unreviewed vehicle speed/unit',row))
        value=int(match[1])+(0.5 if match[2] else 0)
        vehicle_speeds[row[0]]={'speed':value,'source_cells':row,'unit':'mph'}
    levers,lever_table=grid(source,'Apparatus of the Crab Levers','8',['Lever','Up','Down'],10)
    lever=next(row for row in levers if row[0]=='8')
    names=LIGHT|MOVEMENT|set(poisons)|set(animals)|set(vehicle_speeds)|{'Basic Poison'}
    identities={('magicvariants.json' if name in VARIANTS else 'items.json',
                 'magicvariant' if name in VARIANTS else 'item',name) for name in names}
    if len(names)!=61:raise ValueError(('Environment projection inventory changed',len(names)))
    return {'required_identities':identities,'poisons':poisons,'animals':animals,'vehicles':vehicle_speeds,
            'crab_light_lever':lever,'source_tables':{'mounts':mount_table,'vehicles':vehicle_table,'crab_levers':lever_table}}


def light_fact(text,name):
    pairs=re.findall(r'Bright Light in a (\d+)-foot (radius|Cone) and Dim Light for an additional (\d+) feet',text)
    if pairs:
        if len(pairs)!=1:raise ValueError(('Ambiguous printed bright/dim mode',name))
        bright,shape,additional=pairs[0]
        modes=[{'bright':int(bright),'dim':int(bright)+int(additional),**({'shape':'cone'} if shape=='Cone' else {})}]
        if name in {'Hooded Lantern','Lantern of Revealing'}:
            lowered=re.findall(r'reducing[^.]{0,70}Dim Light in a (\d+)-foot radius',text)
            if len(lowered)!=1:raise ValueError('Missing lowered-hood light mode')
            modes.append({'dim':int(lowered[0])})
        return modes
    dims=re.findall(r'Dim Light (?:in a (\d+)-foot radius|out to (\d+) feet)',text)
    if len(dims)!=1:raise ValueError(('Missing unique printed dim-light mode',name))
    return [{'dim':int(dims[0][0] or dims[0][1])}]


def movement_fact(text,name):
    if name=='Boots of Speed':
        if 'the boots double your Speed' not in text:raise ValueError('Missing source speed multiplier')
        return {'multiply':{'walk':2}}
    if name=='Boots of Striding and Springing':
        matches=re.findall(r'your Speed becomes (\d+) feet unless your Speed is higher',text)
        if len(matches)!=1:raise ValueError('Missing source speed floor and higher-speed exception')
        return {'static':{'walk':int(matches[0])}}
    equal=re.findall(r'a (Climb|Fly|Swim) Speed equal to your Speed',text)
    fixed=re.findall(r'a (Climb|Fly|Swim) Speed of (\d+) feet',text)
    if len(equal)+len(fixed)!=1:raise ValueError(('No unique source movement effect',name,equal,fixed))
    modes={'Climb':'climb','Fly':'fly','Swim':'swim'}
    if equal:return {'equal':{modes[equal[0]]:'walk'}}
    return {'static':{modes[fixed[0][0]]:int(fixed[0][1])}}


def facts(a,models,inventory,glyphs,record,kind,heading):
    name=record['name'];expected={};evidence={}
    if name in inventory['animals']:
        info=inventory['animals'][name];return {'speed':info['speed']},info
    if name in inventory['vehicles']:
        info=inventory['vehicles'][name];return {'vehSpeed':info['speed']},info
    if heading in models:
        model=models[heading];indexes=required_paragraph_indexes(record,kind,model)
        text=' '.join(model['paragraphs'][i]['text'] for i in indexes)
        evidence={'pages':model['pages'],'paragraph_indexes':indexes,'source_text':text}
    else:
        text,evidence=body_text(a.SOURCES[heading],glyphs);evidence['source_text']=text
    if name in LIGHT:
        if name=='Apparatus of the Crab':
            row=inventory['crab_light_lever'];evidence['source_lever_row']=row
            expected['light']=light_fact(row[1],name)
        else:expected['light']=light_fact(text,name)
        if name=='Helm of Brilliance':evidence['indexed_light_effect']='Fire Opal Flames; the separate conditional diamond Emanation remains in full source prose.'
        if name=='Energy Bow':evidence['indexed_light_effect']='Produced arrow until it disappears, not an unconditional aura around the bow.'
    if name in MOVEMENT:expected['modifySpeed']=movement_fact(text,name)
    if name in inventory['poisons']:
        info=inventory['poisons'][name]
        if info['source_heading']!=heading:raise ValueError('Poison source identity mismatch')
        expected.update(poison=True,poisonTypes=[info['type']]);evidence['printed_poison_header']=info['header']
    elif name=='Basic Poison':
        if heading!='Poison, Basic (100 GP)' or 'a vial of Basic Poison to coat one weapon or up to three pieces of ammunition' not in text:
            raise ValueError('Basic Poison source scope changed')
        expected['poison']=True
    return expected,evidence


def compare(record,expected):
    effective={**record,**record.get('inherits',{})};verified={};differences=[]
    for field in sorted(FIELDS):
        if field not in expected:
            if field in effective:differences.append({'field':field,'value':effective[field],'source_expected':'No retained source index of this kind in this reviewed identity.'})
            continue
        actual=effective.get(field);wanted=expected[field]
        if exact(actual,wanted):verified[field]={'value':actual,'source_expected':wanted}
        else:differences.append({'field':field,'value':actual,'source_expected':wanted})
    return {'verified_metadata':verified,'differences':differences,'passed':not differences}


def audit(a,models,inventory):
    glyphs=GlyphSource(a.doc);records=[];errors=[];seen=set()
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        record=a.DATA[file][kind][review['index']];effective={**record,**record.get('inherits',{})};identity=(file,kind,name)
        if identity not in inventory['required_identities'] and not FIELDS & effective.keys():continue
        if identity in seen:errors.append({'name':name,'error':'Duplicate environment projection'});continue
        seen.add(identity)
        if identity not in inventory['required_identities'] or record['name']!=name:
            errors.append({'name':name,'error':'Unexpected environment identity/kind'});continue
        try:
            expected,evidence=facts(a,models,inventory,glyphs,record,kind,heading)
            result=compare(record,expected);result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'name':name,'differences':result['differences']})
        except (ValueError,KeyError,IndexError,TypeError) as exc:errors.append({'name':name,'error':str(exc)})
    if len(records)!=61 or seen!=inventory['required_identities']:
        errors.append({'error':'Missing or extra environment projections','missing':sorted(inventory['required_identities']-seen)})
    return {'records':records,'errors':errors,'passed':not errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('pdf','data','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if pdf_hash!=PDF_SHA256:raise ValueError('Official PDF changed')
    model_path=ROOT/'source/item-families.json';models=json.loads(model_path.read_text(encoding='utf8'))['families']
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    inventory=source_inventory(a,models);result=audit(a,models,inventory)
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  source_tables=inventory['source_tables'],input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
