"""Verify remaining item links, bundles and small source/schema metadata.

Group/deck lists index source members/outcomes; their existing authoring order
and case are not additional game rules. Deck of Illusions'33 outcome references
do not assert the physical deck has33 cards: its literal source text specifies
34 cards including two mirrored cards. Schema templates/affixes are authored
labels bound to source identities, not extra source rules or grouping changes.
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
from item_proof_inputs import require_inputs
from locate_source_citations import Source as CitationSource,canon
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from source_identity import SOURCE_ID
from verify_item_abilities import exact
from verify_item_predicates import generic_identities
from verify_item_schema_categories import source_inventory as category_inventory,PROPERTY_NAMES
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'group','detail1','packContents','curse','weightNote','items','template','namePrefix','nameSuffix','cards','set'}
PREFIX={'Adamantine Armor':'Adamantine ','Berserker Axe':'Berserker ','Dancing Sword':'Dancing ','Defender':'Defender ',
 'Demon Armor':'Demon ','Dragon Slayer':'Dragon Slayer ','Dwarven Plate':'Dwarven ','Elven Chain':'Elven ',
 'Energy Bow':'Energy ','Flame Tongue':'Flame Tongue ','Frost Brand':'Frost Brand ','Giant Slayer':'Giant Slayer ',
 'Holy Avenger':'Holy Avenger ','Luck Blade':'Luck ','Mithral Armor':'Mithral ','Nine Lives Stealer':'Nine Lives Stealer ',
 'Oathbow':'Oath ','Vicious Weapon':'Vicious ','Vorpal Sword':'Vorpal '}
SUFFIX={'Ammunition of Slaying':' of Slaying','Hammer of Thunderbolts':' of Thunderbolts',
 'Plate Armor of Etherealness':' of Etherealness','Sword of Life Stealing':' of Life Stealing',
 'Sword of Sharpness':' of Sharpness','Sword of Wounding':' of Wounding','Weapon of Warning':' of Warning'}
TEMPLATES={code:'{{prop_name}}' for code in PROPERTY_NAMES}
TEMPLATES.update(A='{{prop_name}} (Range {{item.range}}\u00a0ft.; {{item.ammoType}})',
                 T='{{prop_name}} ({{item.range}}\u00a0ft.)',V='{{prop_name}} ({{item.dmg2}})')


def uid(name):return name+'|'+SOURCE_ID
def cells(table):return [[c['text'] for c in r['cells']] for r in table['rows']]
def key(row):return row['file'],row['kind'],row['index']


def group_members(inventory,models):
    groups={}
    for group in inventory['grants']['groups']:
        groups[group]=[name for name,info in inventory['grants']['focus'].items() if info['group']==group]
    groups["Artisan's Tools"]=[k[2] for k,info in inventory['ordinary'].items() if k[1]=='baseitem' and info['type']=='AT|'+SOURCE_ID]
    gaming_aliases={'Dice':'Dice Set','dragonchess':'Dragonchess Set','playing cards':'Playing Cards','three-dragon ante':'Three-Dragon Ante Set'}
    groups['Gaming Set']=[gaming_aliases[r['name']] for r in inventory['source_lists']['Gaming Set (Varies)']['entries']]
    groups['Musical Instrument']=[{'pan flute':'Pan Flute'}.get(r['name'],r['name'].title()) for r in inventory['source_lists']['Musical Instrument (Varies)']['entries']]
    for family in ('Armor of Resistance','Potion of Resistance','Ring of Resistance'):
        noun=family.split(' of ')[0];groups[family]=[noun+' of '+row[1]+' Resistance' for row in models[family]['tables'][0]['rows']]
    groups['Armor of Vulnerability']=['Armor of Vulnerability ('+t+')' for t in ('Bludgeoning','Piercing','Slashing')]
    groups['Bag of Tricks']=['Bag of Tricks, '+table['caption'].removesuffix(' Bag of Tricks') for table in models['Bag of Tricks']['tables']]
    for family in ('Belt of Giant Strength','Potion of Giant Strength'):
        names=[]
        for row in models[family]['tables'][0]['rows']:
            match=re.fullmatch(re.escape(family)+r' \(([^)]+)\)',row[0])
            if not match:raise ValueError('Unbound giant source subtype')
            names.extend(family.replace('Giant',part.title()+' Giant') for part in match[1].split(' or '))
        groups[family]=names
    groups['Carpet of Flying']=['Carpet of Flying, '+row[1] for row in models['Carpet of Flying']['tables'][0]['rows']]
    groups['Dragon Scale Mail']=[row[0]+' Dragon Scale Mail' for row in models['Dragon Scale Mail']['tables'][0]['rows']]
    groups['Elemental Gem']=['Elemental Gem, '+row[0].title() for row in models['Elemental Gem']['tables'][0]['rows']]
    for family in ('Figurine of Wondrous Power','Ioun Stone'):
        labels=[]
        for paragraph in models[family]['paragraphs']:
            match=re.match(r'^(.*?) \((?:Uncommon|Rare|Very Rare|Legendary)\)\.',paragraph['text'])
            if match:labels.append(family+', '+match[1])
        groups[family]=labels
    groups['Horn of Valhalla']=['Horn of Valhalla, '+row[1] for row in models['Horn of Valhalla']['tables'][0]['rows']]
    groups['Manual of Golems']=['Manual of '+row[1].removesuffix(' Golem')+' Golems' for row in models['Manual of Golems']['tables'][0]['rows']]
    groups['Potions of Healing']=[]
    for row in models['Potions of Healing']['tables'][0]['rows']:
        match=re.fullmatch(r'Potion of Healing(?: \(([^)]+)\))?',row[0])
        if not match:raise ValueError('Unbound healing source subtype')
        groups['Potions of Healing'].append('Potion of '+(match[1].title()+' ' if match[1] else '')+'Healing')
    groups['Feather Token']=['Feather Token, '+row[1] for row in models['Feather Token']['tables'][0]['rows']]
    groups['Ring of Elemental Command']=['Ring of Elemental Command ('+row[0]+')' for row in models['Ring of Elemental Command']['tables'][0]['rows']]
    groups['Spell Scroll']=['Spell Scroll ('+('Cantrip' if row[0]=='Cantrip' else 'Level '+row[0])+')' for row in models['Spell Scroll']['tables'][0]['rows']]
    groups['Wand of the War Mage']=['+'+str(n)+' Wand of the War Mage' for n in (1,2,3)]
    if len(groups)!=25 or any(not names or len(names)!=len(set(names)) for names in groups.values()):raise ValueError('Incomplete source group/member inventory')
    return groups


def pack_contents(text,names):
    match=re.search(r'contains the following items: (.+)\.$',canon(text))
    if not match:raise ValueError('Unbound printed pack list')
    result=[]
    aliases={'Candles':'Candle','Ink Pens':'Ink Pen','Map or Scroll Cases':'Map or Scroll Case','Costumes':'Costume','Torches':'Torch',
             # Physical p96 wraps Cos-/tumes. The source item heading is
             # Costume; this is a reviewed source-label alias, not data prose.
             'Cos-tumes':'Costume'}
    for part in re.split(r', (?:and )?',match[1]):
        amount=re.fullmatch(r'(\d+) (.+)',part);quantity=int(amount[1]) if amount else 1;label=amount[2] if amount else part
        label=re.sub(r'^(?:flasks|days|sheets) of ','',label);label=aliases.get(label,label)
        if quantity<1 or label.casefold() not in names:raise ValueError(('Unresolved source pack member',part))
        target=uid(names[label.casefold()].lower())
        result.append({'item':target,'quantity':quantity} if quantity!=1 else target)
    return result


def retained_targets(a):
    """Resolve against actual retained identities, never assumed source IDs."""
    items={};decks=set();cards=set()
    for row in a.RESULT:
        record=a.DATA[row['file']][row['kind']][row['index']]
        # Generic variants store their canonical source inside inherits. Other
        # records store it on the root. If both exist they must agree.
        actual_source=record.get('source',record.get('inherits',{}).get('source'))
        if actual_source!=SOURCE_ID or record.get('inherits',{}).get('source',actual_source)!=SOURCE_ID:
            raise ValueError('Retained item/link target has an invalid source: '+row['name'])
        if row['kind'] in {'item','baseitem','magicvariant','itemGroup'}:
            packed=uid(row['name'].casefold())
            if packed in items:raise ValueError('Ambiguous retained item UID')
            items[packed]=row
        elif row['kind']=='deck':
            if row['name'].casefold() in decks:raise ValueError('Ambiguous retained deck UID')
            decks.add(row['name'].casefold())
        elif row['kind']=='card':
            parent=record.get('set')
            if not isinstance(parent,str):raise ValueError('Invalid retained card parent')
            packed=(row['name'].casefold(),parent.casefold(),actual_source)
            if packed in cards:raise ValueError('Ambiguous retained card UID')
            cards.add(packed)
    return items,decks,cards


def check_links(a,expected):
    items,decks,cards=retained_targets(a)
    def resolve_item(packed,kinds):
        parts=packed.split('|') if isinstance(packed,str) else []
        target=items.get(uid(parts[0].casefold())) if len(parts)==2 and parts[1]==SOURCE_ID else None
        if target is None or target['kind'] not in kinds:raise ValueError('Unresolved retained item/link target: '+str(packed))
    for info in expected.values():
        for field,fact in info['facts'].items():
            values=fact['value']
            if field=='items':
                for packed in values:resolve_item(packed,{'item','baseitem','magicvariant'})
            elif field=='group':
                for parent in values:resolve_item(uid(parent),{'itemGroup'})
            elif field=='packContents':
                for member in values:resolve_item(member['item'] if isinstance(member,dict) else member,{'item','baseitem'})
            elif field=='set':
                if values.casefold() not in decks:raise ValueError('Unresolved retained deck parent')
            elif field=='cards':
                for member in values:
                    packed=member['uid'] if isinstance(member,dict) else member;parts=packed.split('|')
                    if len(parts)!=3 or (parts[0].casefold(),parts[1].casefold(),parts[2]) not in cards:
                        raise ValueError('Unresolved retained card target: '+packed)
    return items


def source_expectations(a,models):
    inventory=category_inventory(a,models);glyphs=GlyphSource(a.doc);source=CitationSource(a.doc)
    groups=group_members(inventory,models);generic=generic_identities(a,inventory,models,glyphs);expected={}
    wand=inventory['magic_headers']['Wand of the War Mage, +1, +2, or +3']['text']
    if re.findall(r'\(\+([123])\)',wand)!=['1','2','3']:raise ValueError('Wand source bonus/member inventory changed')
    def add(row,field,value,evidence,comparison='strict'):
        info=expected.setdefault(key(row),{'file':row['file'],'kind':row['kind'],'index':row['index'],'name':row['name'],'facts':{},'source_evidence':{}})
        if field in info['facts']:raise ValueError('Duplicate final metadata field expectation')
        info['facts'][field]={'value':value,'comparison':comparison};info['source_evidence'][field]=evidence
    all_items,_,_=retained_targets(a)
    for group,members in groups.items():
        parent=all_items.get(uid(group.casefold()))
        if not parent or parent['kind']!='itemGroup':raise ValueError(('Missing source group',group))
        for member in members:
            if uid(member.casefold()) not in all_items:raise ValueError(('Missing source-backed group member',group,member))
        evidence={'source_group':group,'source_members':members,'classification':'Source-backed membership; existing UID case and authoring order are preserved, not new game rules.'}
        add(parent,'items',[uid(n) for n in members],evidence,'item_members')
    for name,info in inventory['grants']['focus'].items():
        add(all_items[uid(name.casefold())],'group',[info['group']],info)
    # Two structured detail fields are selected by source identity/table rows.
    for row in models['Dragon Scale Mail']['tables'][0]['rows']:
        add(all_items[uid((row[0]+' Dragon Scale Mail').casefold())],'detail1',row[0].lower(),{'source_table':'Dragon Scale Mail','source_cells':row})
    for row in models['Ring of Resistance']['tables'][0]['rows']:
        add(all_items[uid(('Ring of '+row[1]+' Resistance').casefold())],'detail1',row[2].lower(),{'source_table':'Ring of Resistance','source_cells':row})
    # Literal source lists determine every bundle member and quantity.
    ordinary={k[2].casefold():k[2] for k in inventory['ordinary'] if k[1] in {'item','baseitem'}}
    packs=[(heading,src) for heading,src in a.SOURCES.items() if re.fullmatch(r".+ Pack \([\d,]+ GP\)",heading)]
    if len(packs)!=7:raise ValueError('Printed equipment pack inventory changed')
    for heading,src in packs:
        name=heading.split(' (')[0];text,evidence=body_text(src,glyphs)
        add(all_items[uid(name.casefold())],'packContents',pack_contents(text,ordinary),{'source_heading':heading,'source_text':text,**evidence})
    ammo_aliases={'Arrows':('Arrows (20)','Arrow'),'Bolts':('Bolts (20)','Bolt'),
                  'Bullets, Firearm':('Firearm Bullets (10)','Firearm Bullet'),'Bullets, Sling':('Sling Bullets (20)','Sling Bullet'),'Needles':('Needles (50)','Needle')}
    for row in cells(inventory['source_tables']['Ammunition']):
        bundle,piece=ammo_aliases[row[0]]
        add(all_items[uid(bundle.casefold())],'packContents',[{'item':uid(piece.lower()),'quantity':int(row[1])}],{'source_table':'Ammunition','source_cells':row})
    text,evidence=body_text(a.SOURCES['Spikes, Iron (1 GP)'],glyphs)
    if 'Iron Spikes come in bundles of ten.' not in text:raise ValueError('Missing printed iron-spike bundle quantity')
    add(all_items[uid('iron spikes')],'packContents',[{'item':uid('iron spike'),'quantity':10}],{'source_text':text,**evidence})
    water=next(row for row in cells(inventory['source_tables']['Adventuring Gear']) if row[0]=='Waterskin')
    if water[1]!='5 lb. (full)':raise ValueError('Waterskin source weight qualifier changed')
    add(all_items[uid('waterskin')],'weightNote','(full)',{'source_table':'Adventuring Gear','source_cells':water})
    # Naming/property templates are authored compatibility labels only.
    for name,heading in generic.items():
        parent=all_items[uid(name.casefold())]
        if name.startswith(('+1 ','+2 ','+3 ')):field,value='namePrefix',name[:3]
        elif heading in PREFIX:field,value='namePrefix',PREFIX[heading]
        elif heading in SUFFIX:field,value='nameSuffix',SUFFIX[heading]
        elif heading=='Armor of Resistance':field,value='nameSuffix',name.removeprefix('Armor')
        elif heading=='Armor of Vulnerability':field,value='nameSuffix',name.removeprefix('Armor')
        else:raise ValueError(('Unreviewed authored generic label template',name))
        add(parent,field,value,{'source_header':inventory['magic_headers'][heading],
                               'classification':'Authored label affix bound to a printed generic identity; not an additional game rule or rendering change.'})
    properties=[r for r in a.RESULT if r['kind']=='itemProperty']
    if len(properties)!=9 or {r['name'] for r in properties}!=set(TEMPLATES):raise ValueError('Incomplete property-template inventory')
    for row in properties:
        add(row,'template',TEMPLATES[row['name']],{'property_meaning':PROPERTY_NAMES[row['name']],
            'classification':'Authored display template using only the source-verified property name/range/damage/ammunition slots.'})
    cursed={}
    for heading in inventory['magic_headers']:
        text,evidence=body_text(a.SOURCES[heading],glyphs)
        labels=[line for line in a.SOURCES[heading]['lines'] if canon(line['text']).startswith('Curse.')]
        if labels:cursed[heading]={'source_text':text,'printed_curse_label_lines':labels,**evidence}
    if set(cursed)!={'Armor of Vulnerability','Berserker Axe','Demon Armor','Shield of Missile Attraction'}:raise ValueError(('Explicit cursed-item source scope changed',sorted(cursed)))
    for row in a.RESULT:
        if row['kind'] in {'item','itemGroup','magicvariant'} and row['source_name'] in cursed:
            add(row,'curse',True,cursed[row['source_name']])
    # Decks use independent physical grids and the literal replacement rule.
    decks={}
    for caption,anchor,count,columns in [('Deck of Illusions','Adult Red Dragon',33,['1d100','Illusion*']),
                                         ('Mysterious Deck','Balance',22,['1d100 (13-Card Deck)','1d100 (22-Card Deck)','Card'])]:
        source.table_row(caption,anchor);table=source.table_cache[caption]
        if len(table['rows'])!=count or table['headers']!=columns:raise ValueError('Printed deck table inventory changed')
        decks[caption]={'table':table,'names':[row[-1] for row in cells(table)]}
    mystery_text,mystery_evidence=body_text(a.SOURCES['Mysterious Deck'],glyphs)
    if 'Unless the card is the Fool or Jester, the card reappears in the deck' not in mystery_text:raise ValueError('Missing source card replacement exception')
    seen=set()
    for row in a.RESULT:
        if row['kind']!='card':continue
        record=a.DATA[row['file']]['card'][row['index']];entries=record.get('entries')
        illusion=isinstance(entries,list) and len(entries)==1 and isinstance(entries[0],dict) and entries[0].get('type')=='table' and entries[0].get('caption')=='Deck of Illusions'
        parent='Deck of Illusions' if illusion else 'Mysterious Deck';pair=(parent,row['name'])
        if row['name'] not in decks[parent]['names'] or pair in seen:raise ValueError(('Unbound, duplicate or wrongly projected deck card',pair))
        if illusion:
            physical=[r for r in cells(decks[parent]['table']) if r[-1]==row['name']]
            if len(physical)!=1 or entries[0].get('colLabels')!=decks[parent]['table']['headers'] or entries[0].get('rows')!=physical:
                raise ValueError('Illusion-card parent is not bound to its own physical source row')
        seen.add(pair);add(row,'set',parent,{'source_deck':parent,'source_card_name':row['name'],'source_table':decks[parent]['table']})
    wanted={(parent,name) for parent,info in decks.items() for name in info['names']}
    if seen!=wanted:raise ValueError('Incomplete independent deck/card identity coverage')
    deck_rows=[row for row in a.RESULT if row['kind']=='deck']
    if len(deck_rows)!=2 or {r['name'] for r in deck_rows}!=set(decks):raise ValueError('Deck parent inventory changed')
    for row in deck_rows:
        parent=row['name'];values=[]
        for name in decks[parent]['names']:
            packed=name+'|'+parent+'|'+SOURCE_ID
            values.append({'uid':packed,'replacement':True} if parent=='Mysterious Deck' and name not in {'Fool','Jester'} else packed)
        add(row,'cards',values,{'source_deck':parent,'source_table':decks[parent]['table'],
            'source_replacement_rule':mystery_evidence if parent=='Mysterious Deck' else None,
            'classification':'Source outcome links; authoring order preserved. Illusions has33 outcomes, while its literal prose describes34 physical cards.'},'card_members')
    counts=Counter(field for info in expected.values() for field in info['facts'])
    if counts!={'items':25,'group':11,'detail1':20,'packContents':13,'weightNote':1,'namePrefix':31,'nameSuffix':20,'template':9,'curse':7,'set':55,'cards':2}:
        raise ValueError(('Incomplete remaining metadata field inventory',counts))
    check_links(a,expected)
    for info in expected.values():info['source_evidence']=json.loads(json.dumps(info['source_evidence'],ensure_ascii=False))
    return expected


def members(value,field):
    if not isinstance(value,list):return None
    result=[]
    for member in value:
        replacement=False
        if isinstance(member,dict):
            if field!='cards' or set(member)!={'uid','replacement'} or member['replacement'] is not True:return None
            packed=member['uid'];replacement=True
        else:packed=member
        if not isinstance(packed,str):return None
        parts=packed.split('|');length=3 if field=='cards' else 2
        if len(parts)!=length or parts[-1]!=SOURCE_ID or any(not part for part in parts):return None
        result.append(('|'.join([p.casefold() for p in parts[:-1]]+[SOURCE_ID]),replacement))
    if len(result)!=len(set(result)) or len({r[0] for r in result})!=len(result):return None
    return sorted(result)


def audit(a,expected):
    records=[];errors=[];seen=set()
    try:check_links(a,expected)
    except ValueError as error:return {'records':[],'errors':[{'error':str(error)}],'passed':False}
    for row in a.RESULT:
        record=a.DATA[row['file']][row['kind']][row['index']];effective={**record,**record.get('inherits',{})};present=FIELDS & effective.keys();identity=key(row)
        if not present and identity not in expected:continue
        if identity not in expected or identity in seen:
            errors.append({'identity':identity,'error':'Unbound or duplicate remaining-metadata record'});continue
        seen.add(identity);info=expected[identity];differences=[];verified={}
        if present!=set(info['facts']):differences.append({'error':'Missing or unexpected remaining metadata fields','actual':sorted(present),'expected':sorted(info['facts'])})
        for field,fact in info['facts'].items():
            wanted=fact['value'];actual=effective.get(field)
            if fact['comparison']=='strict':equal=field in effective and exact(actual,wanted)
            else:equal=members(actual,field) is not None and members(actual,field)==members(wanted,field)
            if equal:verified[field]={'value':actual,'source_expected':wanted,'comparison':fact['comparison']}
            else:differences.append({'field':field,'value':actual,'source_expected':wanted,'comparison':fact['comparison']})
        result={k:info[k] for k in ('file','kind','index','name')}
        result.update(verified_metadata=verified,source_evidence=info['source_evidence'],differences=differences,passed=not differences)
        records.append(result)
        if differences:errors.append({'identity':identity,'differences':differences})
    if seen!=set(expected):errors.append({'error':'Incomplete remaining metadata identity coverage','missing':sorted(set(expected)-seen)})
    return {'records':records,'errors':errors,'passed':not errors}


def require_proof(proof,a,expected):
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-links')
    model_path=ROOT/'source/item-families.json'
    if proof.get('models_sha256')!=hashlib.sha256(model_path.read_bytes()).hexdigest():raise ValueError('Stale item-link family model')
    current=audit(a,expected)
    if not current['passed']:raise ValueError('Current item links differ from independent source expectations')
    if proof.get('errors')!=[] or not isinstance(proof.get('records'),list):raise ValueError('Invalid item-link proof')
    wanted={(r['file'],r['kind'],r['index']):r for r in current['records']};indexed={}
    for row in proof['records']:
        identity=(row.get('file'),row.get('kind'),row.get('index'))
        if identity in indexed or identity not in wanted or not exact(row,wanted[identity]):raise ValueError('Item-link proof identity, field or source scope differs')
        indexed[identity]=row
    if indexed.keys()!=wanted.keys():raise ValueError('Incomplete item-link proof identity coverage')
    return indexed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('pdf','data','out'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=PDF_SHA256:raise ValueError('Official source PDF changed')
    model_path=ROOT/'source/item-families.json';models=json.loads(model_path.read_text(encoding='utf8'))['families']
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    result=audit(a,source_expectations(a,models))
    result.update(pdf_sha256=PDF_SHA256,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
