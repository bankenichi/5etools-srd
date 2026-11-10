"""Verify source-bound category indexes and absent-rarity compatibility values.

Schema codes/abbreviations are authored identifiers, not additional printed
game rules. none indexes the absence of an assigned magic-item rarity in the
ordinary equipment/poison/trinket scope; it does not assert nonmagical behavior.
Generic Variant identifies a schema wrapper, not its underlying physical type.
Derived horn/focus indexes retain the printed Wondrous Item classification and
do not assert mundane weight, price, proficiency grants or extra powers.
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
from locate_source_citations import Source as CitationSource,canon
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from source_identity import SOURCE_ID
from verify_equipment_categories import source_categories
from verify_item_grants import source_inventory as grant_inventory
from verify_item_abilities import exact
from verify_magic_item_headers import source_header
from verify_weapon_overrides import body_text
from item_proof_inputs import require_inputs

ROOT=Path(__file__).resolve().parents[1]
TYPE_NAMES={'A':'Ammunition','AIR':'Vehicle (Air)','AT':"Artisan's Tools",'FD':'Food and Drink','G':'Adventuring Gear',
 'GS':'Gaming Set','GV':'Generic Variant','HA':'Heavy Armor','INS':'Instrument','LA':'Light Armor','M':'Melee Weapon',
 'MA':'Medium Armor','MNT':'Mount','P':'Potion','R':'Ranged Weapon','RD':'Rod','RG':'Ring','S':'Shield','SC':'Scroll',
 'SCF':'Spellcasting Focus','SHP':'Vehicle (Water)','T':'Tool','TAH':'Tack and Harness','VEH':'Vehicle (Land)','WD':'Wand'}
PROPERTY_NAMES={'2H':'Two-Handed','A':'Ammunition','F':'Finesse','H':'Heavy','L':'Light','LD':'Loading','R':'Reach','T':'Thrown','V':'Versatile'}
GEAR_ALIASES={'Bottle, Glass':'Glass Bottle','Case, Crossbow Bolt':'Crossbow Bolt Case','Case, Map or Scroll':'Map or Scroll Case',
 'Clothes, Fine':'Fine Clothes',"Clothes, Traveler's":"Traveler's Clothes",'Lantern, Bullseye':'Bullseye Lantern',
 'Lantern, Hooded':'Hooded Lantern','Poison, Basic':'Basic Poison','Pot, Iron':'Iron Pot','Ram, Portable':'Portable Ram',
 'Spikes, Iron':'Iron Spikes'}


def identity(file,kind,name):return (file,kind,name)
def position(line):return line['page'],line['column'],line['origins'][0][1]


def physical_grid(source,caption,label,headers,count):
    source.table_row(caption,label);table=source.table_cache[caption]
    if table['headers']!=headers or len(table['rows'])!=count:raise ValueError(('Source grid inventory changed',caption,table['headers'],len(table['rows'])))
    return table


def inline_variants(a,glyphs,heading,count):
    src=a.SOURCES[heading];lines=src['lines']
    first=next(i for i,line in enumerate(lines) if line['text'].startswith('Variants:'))
    rendered=[]
    for line in lines[first:]:
        matches=[l for l in glyphs.page(line['page'])['lines'] if (l['block'],l['line'])==(line['block'],line['line'])]
        if len(matches)!=1:raise ValueError('Changed physical variant-list line')
        rendered.append({'page':line['page'],**glyphs.text(matches[0]['chars'])})
    raw='\n'.join(line['text'] for line in rendered);joins=[]
    if 'dul-\ncimer' in raw:
        # Reviewed on physical p94: this one word wraps across columns.
        raw=raw.replace('dul-\ncimer','dulcimer');joins.append({'printed':'dul-\ncimer','joined':'dulcimer','basis':'Reviewed physical source column-wrap hyphen.'})
    text=canon(raw).removeprefix('Variants: ')
    entries=[{'name':name.strip(),'printed_attributes':attrs} for name,attrs in re.findall(r'([^(),]+?) \(([^()]+)\)',text)]
    if len(entries)!=count or len({e['name'] for e in entries})!=count:raise ValueError(('Source variant-list inventory changed',heading,entries))
    return {'source_heading':heading,'entries':entries,'source_lines':rendered,'layout_joins':joins,'source_text':text}


def source_inventory(a,models):
    source=CitationSource(a.doc);glyphs=GlyphSource(a.doc);ordinary={};tables={};headers={}
    def add(name,kind,code,evidence,file=None):
        file=file or ('items-base.json' if kind=='baseitem' else 'items.json');key=identity(file,kind,name)
        if key in ordinary:raise ValueError(('Duplicate ordinary category identity',key))
        ordinary[key]={'type':code+'|'+SOURCE_ID,'rarity':'none','source_evidence':evidence}
    def rows(table):return [[cell['text'] for cell in row['cells']] for row in table['rows']]
    # All actual magic headers, independently identified by printed typography.
    for heading,src in a.SOURCES.items():
        if src['red12'] and 209<=src['heading_lines'][0]['page']<=254:
            header=source_header(src,glyphs)
            if header:headers[heading]=header
    if len(headers)!=258:raise ValueError('Magic source heading inventory changed')
    categories=source_categories(a.doc)
    for name,info in categories.items():add(name,'baseitem',info['facts']['type'],info)
    grants=grant_inventory(a,models)
    for name,info in grants['focus'].items():
        base=info['code']=='arcane' or name=='Wooden Staff'
        add(name,'baseitem' if base else 'item','SCF',info)
    for name,info in grants['groups'].items():add(name,'itemGroup','SCF',info)
    tables.update(grants['focus_tables'])
    ammunition=physical_grid(source,'Ammunition','Arrows',['Type','Amount','Storage','Weight','Cost'],5)
    ammo_aliases={'Arrows':('Arrow','Arrows (20)'),'Bolts':('Bolt','Bolts (20)'),
                  'Bullets, Firearm':('Firearm Bullet','Firearm Bullets (10)'),
                  'Bullets, Sling':('Sling Bullet','Sling Bullets (20)'),'Needles':('Needle','Needles (50)')}
    if {row[0] for row in rows(ammunition)}!=set(ammo_aliases):raise ValueError('Ammunition source identities changed')
    for row in rows(ammunition):
        names=ammo_aliases[row[0]]
        if not names[1].endswith('('+row[1]+')'):raise ValueError('Ammunition bundle alias no longer matches printed amount')
        for name in names:add(name,'baseitem','A',{'table':'Ammunition','source_cells':row,'alias_scope':'Single piece or complete printed bundle; this check asserts category only.'})
    tables['Ammunition']=ammunition
    gear=physical_grid(source,'Adventuring Gear','Acid',['Item','Weight','Cost'],82)
    excluded={'Ammunition','Arcane Focus','Druidic Focus','Holy Symbol','Potion of Healing','Spell Scroll (Cantrip)','Spell Scroll (Level 1)'}
    if not excluded<={canon(row[0]) for row in rows(gear)}:raise ValueError('Gear group/magic rows changed')
    for row in rows(gear):
        printed=canon(row[0])
        if printed in excluded:continue
        name=GEAR_ALIASES.get(printed,printed)
        add(name,'item','G',{'table':'Adventuring Gear','source_cells':row,'printed_name':printed})
        if printed=='Spikes, Iron':add('Iron Spike','item','G',{'table':'Adventuring Gear','source_cells':row,'alias_scope':'Individual member of the printed Iron Spikes bundle; category only.'})
    tables['Adventuring Gear']=gear
    # Named tool units are assigned by independent printed section boundaries.
    starts={name:position(a.SOURCES[name]['heading_lines'][0]) for name in ("Artisan's Tools",'Other Tools','Adventuring Gear')}
    tool_counts=Counter()
    for heading,src in a.SOURCES.items():
        match=re.fullmatch(r'(.+) \([\d,]+ GP\)',heading)
        if not match:continue
        pos=position(src['heading_lines'][0])
        code='AT' if starts["Artisan's Tools"]<pos<starts['Other Tools'] else ('T' if starts['Other Tools']<pos<starts['Adventuring Gear'] else None)
        if code:
            add(match[1],'baseitem' if code=='AT' else 'item',code,{'printed_heading':heading,'source_heading_lines':src['heading_lines'],'section_boundaries':starts})
            tool_counts[code]+=1
    if tool_counts!={'AT':17,'T':6}:raise ValueError(('Tool section inventory changed',tool_counts))
    add("Artisan's Tools",'itemGroup','AT',{'source_heading_lines':a.SOURCES["Artisan's Tools"]['heading_lines']})
    lists={}
    for heading,group,code,count in [('Gaming Set (Varies)','Gaming Set','GS',4),('Musical Instrument (Varies)','Musical Instrument','INS',10)]:
        variants=inline_variants(a,glyphs,heading,count);lists[heading]=variants
        add(group,'itemGroup',code,{'source_heading_lines':a.SOURCES[heading]['heading_lines'],'variant_list':heading})
        for entry in variants['entries']:
            name=entry['name'];name={'Dice':'Dice Set','dragonchess':'Dragonchess Set','playing cards':'Playing Cards','three-dragon ante':'Three-Dragon Ante Set',
                                    'drum':'Drum','dulcimer':'Dulcimer','flute':'Flute','horn':'Horn','lute':'Lute','lyre':'Lyre','pan flute':'Pan Flute','shawm':'Shawm','viol':'Viol'}.get(name,name)
            add(name,'baseitem' if code=='INS' else 'item',code,{'variant_list':heading,'source_entry':entry})
    mounts=physical_grid(source,'Mounts and Other Animals','Camel',['Item','Carrying Capacity','Cost'],8)
    for row in rows(mounts):add({'Horse, Draft':'Draft Horse','Horse, Riding':'Riding Horse'}.get(row[0],row[0]),'item','MNT',{'table':'Mounts and Other Animals','source_cells':row})
    tables['Mounts and Other Animals']=mounts
    tack=physical_grid(source,'Tack, Harness, and Drawn Vehicles','Carriage',['Item','Weight','Cost'],11)
    for row in rows(tack):
        if len(row)==1:continue
        printed=row[0];name={'Feed per day':'Feed (per day)','Stabling per day':'Stabling (per day)',
                            'Exotic':'Exotic Saddle','Military':'Military Saddle','Riding':'Riding Saddle'}.get(printed,printed)
        code='VEH' if printed in {'Carriage','Cart','Chariot','Sled','Wagon'} else 'TAH'
        add(name,'item',code,{'table':'Tack, Harness, and Drawn Vehicles','source_cells':row})
    tables['Tack, Harness, and Drawn Vehicles']=tack
    vehicles=physical_grid(source,'Airborne and Waterborne Vehicles','Airship',
                           ['Ship','Speed','Crew','Passengers','Cargo (Tons)','AC','HP','Damage Threshold','Cost'],7)
    for row in rows(vehicles):add(row[0],'item','AIR' if row[0]=='Airship' else 'SHP',{'table':'Airborne and Waterborne Vehicles','source_cells':row})
    tables['Airborne and Waterborne Vehicles']=vehicles
    food=physical_grid(source,'Food, Drink, and Lodging','Ale (mug)',['Item','Cost'],20)
    current=None;food_count=0
    for row in rows(food):
        if len(row)==1:current=row[0];continue
        if row[0] in {'Ale (mug)','Bread (loaf)','Cheese (wedge)'}:name=row[0]
        elif current=='Wine (bottle)':name=row[0]+' Wine (bottle)'
        else:continue
        add(name,'item','FD',{'table':'Food, Drink, and Lodging','source_cells':row,'printed_parent_row':current});food_count+=1
    if food_count!=5:raise ValueError('Food/wine item inventory changed')
    tables['Food, Drink, and Lodging']=food
    poison_count=0
    for heading,src in a.SOURCES.items():
        match=re.fullmatch(r'(.+) \([\d,]+ GP\)',heading)
        if match and {l['page'] for l in src['heading_lines']}<={197,198}:
            add(match[1],'item','G',{'source_heading_lines':src['heading_lines'],'source_scope':'Sample Poisons; no magic-item rarity assigned.'});poison_count+=1
    if poison_count!=14:raise ValueError('Poison source inventory changed')
    if {l['page'] for l in a.SOURCES['Trinkets']['heading_lines']+a.SOURCES['Trinkets']['lines']}!={26,27}:raise ValueError('Trinket source scope changed')
    add('Trinket','item','G',{'source_heading_lines':a.SOURCES['Trinkets']['heading_lines'],'source_scope':'Printed Trinkets unit; no magic-item rarity assigned.'})
    if len(ordinary)!=236 or Counter(k[1] for k in ordinary)!={'item':136,'itemGroup':6,'baseitem':94}:
        raise ValueError(('Ordinary source inventory changed',len(ordinary),Counter(k[1] for k in ordinary)))
    for key in ordinary:
        if a.source_name({'name':key[2]},key[1]) in headers:raise ValueError(('Magic source unit assigned absent rarity',key))
    return {'ordinary':ordinary,'source_tables':tables,'source_lists':lists,'magic_headers':headers,'grants':grants}


def source_facts(a,inventory):
    expected={key:{'facts':{'type':info['type'],'rarity':info['rarity']},'source_evidence':info['source_evidence'],
                   'classification':'Source-bound schema category and absence of assigned magic-item rarity.'} for key,info in inventory['ordinary'].items()}
    glyphs=GlyphSource(a.doc)
    for row in a.RESULT:
        file,kind,name,heading=row['file'],row['kind'],row['name'],row['source_name'];key=identity(file,kind,name)
        record=a.DATA[file][kind][row['index']]
        if kind=='magicvariant' or (kind=='itemGroup' and name in {'Armor of Resistance','Armor of Vulnerability'}):
            header=inventory['magic_headers'].get(heading)
            if not header or not header['text'].startswith(('Armor (','Weapon (')):raise ValueError(('Unbound generic schema source',key))
            expected[key]={'facts':{'type':'GV|'+SOURCE_ID},'source_evidence':header,'classification':'Authored generic-variant collection wrapper; not the physical item type or an extra game rule.'}
        elif name=='Hat of Many Spells' and kind=='item':
            text,evidence=body_text(a.SOURCES[heading],glyphs)
            if 'use it as a Spellcasting Focus for your Wizard spells' not in text:raise ValueError('Missing focus usage source')
            expected[key]={'facts':{'type':'SCF|'+SOURCE_ID},'source_evidence':{'source_text':text,**evidence},'classification':'Derived usage index; printed Wondrous Item classification remains separate.'}
        elif kind=='item' and (name=='Horn of Blasting' or name.startswith('Horn of Valhalla, ')):
            text,evidence=body_text(a.SOURCES[heading],glyphs)
            if not re.search(r'\bblow (?:the|this) horn\b',text) or inventory['ordinary'][('items-base.json','baseitem','Horn')]['type']!='INS|'+SOURCE_ID:
                raise ValueError('Missing source horn object/ordinary instrument relation')
            expected[key]={'facts':{'type':'INS|'+SOURCE_ID,'baseItem':'horn|'+SOURCE_ID},
                           'source_evidence':{'source_text':text,'ordinary_horn':inventory['ordinary'][('items-base.json','baseitem','Horn')],**evidence},
                           'classification':'Authored physical horn relation/usage index; not a claim of the mundane horn price, weight, proficiency or magical powers.'}
        if kind=='itemType':
            matches=[code for code,meaning in TYPE_NAMES.items() if meaning==name]
            if len(matches)!=1:raise ValueError(('Unreviewed type helper meaning',name))
            expected[key]={'facts':{'abbreviation':matches[0]},'source_evidence':{'helper_meaning':name},'classification':'Authored typed-helper identifier, not a printed SRD abbreviation.'}
        elif kind=='itemProperty':
            # Identity chooses the declared compatibility meaning. A candidate
            # body must not choose its own expected abbreviation, e.g. replace
            # Two-Handed with a second Heavy helper while retaining nine rows.
            meaning=PROPERTY_NAMES.get(name)
            if not meaning or record.get('entries',[{}])[0].get('name')!=meaning or meaning not in a.SOURCES:
                raise ValueError('Unbound property helper meaning')
            expected[key]={'facts':{'abbreviation':name},'source_evidence':{'property_meaning':meaning,'printed_heading_lines':a.SOURCES[meaning]['heading_lines']},'classification':'Authored property-helper identifier, not a printed SRD abbreviation.'}
    counts=Counter(field for info in expected.values() for field in info['facts'])
    if counts!={'type':295,'rarity':236,'baseItem':5,'abbreviation':34} or len(expected)!=329:
        raise ValueError(('Category/schema source inventory changed',len(expected),counts))
    property_ids={key[2] for key in expected if key[1]=='itemProperty'}
    if property_ids!=set(PROPERTY_NAMES):raise ValueError('Incomplete property helper meanings')
    # PDF extraction uses tuples for coordinates. Persisted evidence uses JSON
    # arrays; normalize only the evidence at its boundary so fresh and stored
    # source scopes compare with exactly the same strict JSON types.
    for info in expected.values():info['source_evidence']=json.loads(json.dumps(info['source_evidence'],ensure_ascii=False))
    return expected


def audit(a,expected):
    records=[];errors=[];seen=set()
    for row in a.RESULT:
        key=identity(row['file'],row['kind'],row['name']);record=a.DATA[row['file']][row['kind']][row['index']]
        effective={**record,**record.get('inherits',{})}
        if key not in expected:
            if effective.get('rarity')=='none':errors.append({'name':row['name'],'error':'Unbound absent-rarity index outside the complete ordinary source inventory'})
            continue
        if key in seen:errors.append({'name':row['name'],'error':'Duplicate category/schema projection'});continue
        seen.add(key);info=expected[key];verified={};differences=[]
        for field,wanted in info['facts'].items():
            actual=effective.get(field)
            if exact(actual,wanted):verified[field]={'value':actual,'source_expected':wanted}
            else:differences.append({'field':field,'value':actual,'source_expected':wanted})
        if 'type' in info['facts']:
            code=info['facts']['type'].split('|')[0]
            helpers=[h for h in a.DATA['items-base.json']['itemType'] if h.get('abbreviation')==code and h.get('source')==SOURCE_ID]
            if len(helpers)!=1 or helpers[0]['name']!=TYPE_NAMES[code]:differences.append({'field':'type','error':'Missing, duplicated or wrongly named type helper UID'})
        result={'file':key[0],'kind':key[1],'name':key[2],'verified_metadata':verified,'differences':differences,
                'source_evidence':info['source_evidence'],'classification':info['classification'],'passed':not differences}
        records.append(result)
        if differences:errors.append({'name':row['name'],'differences':differences})
    if seen!=set(expected):errors.append({'error':'Missing category/schema projections','missing':sorted(set(expected)-seen)})
    return {'records':records,'errors':errors,'passed':not errors}


def require_proof(proof,a,expected):
    """Import only a complete proof consistent with fresh source expectations.

    The caller obtains expected from source_inventory/source_facts again, not
    from a proof's claimed identities, counts, values or source evidence.
    """
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-schema-category')
    model_path=ROOT/'source/item-families.json'
    if proof.get('models_sha256')!=hashlib.sha256(model_path.read_bytes()).hexdigest():
        raise ValueError('Stale category/schema family model')
    if proof.get('errors')!=[]:raise ValueError('Category/schema proof has errors')
    # Re-run the scope exclusions as well as the expected facts. In particular,
    # rarity:none on a magic item outside the ordinary inventory must fail even
    # if someone updates all hashes on an otherwise valid old proof.
    current=audit(a,expected)
    if not current['passed']:raise ValueError('Current category/schema data differs from source expectations')
    records=proof.get('records')
    if not isinstance(records,list):raise ValueError('Missing category/schema proof records')
    indexed={}
    for row in records:
        key=(row.get('file'),row.get('kind'),row.get('name'))
        if key not in expected or key in indexed:raise ValueError('Category/schema proof identity coverage differs')
        indexed[key]=row
    if set(indexed)!=set(expected):raise ValueError('Category/schema proof identity coverage differs')
    actual={}
    for row in a.RESULT:
        key=(row['file'],row['kind'],row['name'])
        if key not in expected:continue
        if key in actual:raise ValueError('Duplicate current item identity')
        record=a.DATA[row['file']][row['kind']][row['index']]
        actual[key]={**record,**record.get('inherits',{})}
    for key,wanted in expected.items():
        row=indexed[key];facts=row.get('verified_metadata')
        if row.get('passed') is not True or row.get('differences')!=[]:
            raise ValueError('Unverified category/schema proof row')
        if not isinstance(facts,dict) or set(facts)!=set(wanted['facts']):
            raise ValueError('Category/schema proof per-record field coverage differs')
        if not exact(row.get('source_evidence'),wanted['source_evidence']) or row.get('classification')!=wanted['classification']:
            raise ValueError('Category/schema proof source scope differs')
        for field,value in wanted['facts'].items():
            fact=facts[field]
            if (not isinstance(fact,dict) or set(fact)!={'value','source_expected'} or key not in actual
                or field not in actual[key] or not exact(actual[key][field],value)
                or not exact(fact['value'],value) or not exact(fact['source_expected'],value)):
                raise ValueError('Inconsistent category/schema proof fact')
    return indexed


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
    inventory=source_inventory(a,models);expected=source_facts(a,inventory);result=audit(a,expected)
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  source_tables=inventory['source_tables'],source_lists=inventory['source_lists'],input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
