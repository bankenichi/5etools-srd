"""Verify generic-item eligibility and authored equipment-family indexes.

Printed headers select eligible canonical base equipment. Equivalent existing
predicate encodings must agree on that source set after resolving only the
printed Staff/Wooden Staff "also a Quarterstaff" physical-identity aliases.
Family flags are authored compatibility indexes, not additional printed rules;
in particular they do not grant weapon properties, proficiencies or powers.
This audit changes no data, grouping, splitting, parser or renderer behavior.
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
from locate_source_citations import canon
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from source_identity import SOURCE_ID
from verify_equipment_categories import source_categories
from verify_item_abilities import exact
from verify_item_schema_categories import source_inventory as category_inventory
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
FAMILY_NAMES={
 'arrow':['Arrow','Arrows (20)'],'axe':['Battleaxe','Greataxe','Handaxe'],
 'bolt':['Bolt','Bolts (20)'],'club':['Club','Greatclub'],'dagger':['Dagger'],
 'bulletFirearm':['Firearm Bullet','Firearm Bullets (10)'],'polearm':['Glaive','Halberd'],
 'sword':['Greatsword','Longsword','Rapier','Scimitar','Shortsword'],
 'crossbow':['Hand Crossbow','Heavy Crossbow','Light Crossbow'],'spear':['Javelin','Spear'],
 'lance':['Lance'],'hammer':['Light Hammer','Maul','Warhammer'],'bow':['Longbow','Shortbow'],
 'mace':['Mace','Morningstar'],'firearm':['Musket','Pistol'],'needleBlowgun':['Needle','Needles (50)'],
 'rapier':['Rapier'],'bulletSling':['Sling Bullet','Sling Bullets (20)'],'staff':['Staff']}
FAMILY_FIELDS=set(FAMILY_NAMES)
VARIANT_FIELDS={'requires','excludes','ammo','strength','stealth'}
FIELDS=FAMILY_FIELDS|VARIANT_FIELDS|{'ammoType'}


def uid(code):return code+'|'+SOURCE_ID
def names_predicate(names):return [{'name':name,'source':SOURCE_ID} for name in names]


def source_rule(header,categories,ordinary):
    match=re.match(r'^(Armor|Weapon) \(([^)]+)\),',header['text'])
    if not match:raise ValueError('Unbound generic source header')
    category,condition=match.groups();excluded=None
    if condition.endswith(', Except Hide Armor'):
        condition=condition.removesuffix(', Except Hide Armor');excluded={'name':'Hide Armor'}
    if condition=='Any Light, Medium, or Heavy' and category=='Armor':
        alternatives=[[{'type':uid(code)} for code in ('LA','MA','HA')]]
        eligible={n for n,r in categories.items() if r['facts']['type'] in {'LA','MA','HA'}}
    elif condition=='Any Medium or Heavy' and category=='Armor':
        alternatives=[[{'type':uid(code)} for code in ('MA','HA')]]
        eligible={n for n,r in categories.items() if r['facts']['type'] in {'MA','HA'}}
    elif condition=='Shield' and category=='Armor':
        alternatives=[[{'type':uid('S')}]];eligible={'Shield'}
    elif condition=='Any Simple or Martial' and category=='Weapon':
        alternatives=[[{'weapon':True}],[{'weaponCategory':'simple'},{'weaponCategory':'martial'}]]
        eligible={n for n,r in categories.items() if r['facts'].get('weaponCategory') in {'simple','martial'}}
    elif condition=='Any Ammunition' and category=='Weapon':
        alternatives=[[{'type':uid('A')}]]
        eligible={key[2] for key,info in ordinary.items() if info['type']==uid('A')}
    elif condition=='Any Melee Weapon' and category=='Weapon':
        alternatives=[[{'type':uid('M')}]]
        eligible={n for n,r in categories.items() if r['facts']['type']=='M'}
    else:
        names=re.split(r', or | or |, ',condition)
        if len(names)!=len(set(names)) or not set(names)<=set(categories):raise ValueError(('Unreviewed named source restriction',condition))
        expected_category='Weapons' if category=='Weapon' else 'Armor'
        if any(categories[n]['table']!=expected_category for n in names):raise ValueError('Wrong named source equipment category')
        alternatives=[names_predicate(names)];eligible=set(names)
        if eligible==set(FAMILY_NAMES['sword']):alternatives.append([{'sword':True}])
    if excluded:
        if 'Hide Armor' not in eligible:raise ValueError('Inapplicable source armor exclusion')
        eligible.remove('Hide Armor')
    if not eligible:raise ValueError('Empty source equipment eligibility')
    return {'source_header':header,'allowed_requires':alternatives,'excludes':excluded,'eligible':sorted(eligible)}


def evaluate(record,base):
    requires=record.get('requires')
    if not isinstance(requires,list) or not requires:return set()
    def matches(item,rule):
        return isinstance(rule,dict) and bool(rule) and all(k in item and exact(item[k],v) for k,v in rule.items())
    excluded=record.get('excludes')
    if excluded is not None and (not isinstance(excluded,dict) or not excluded):return set()
    return {item['name'] for item in base if any(matches(item,r) for r in requires) and not (excluded and matches(item,excluded))}


def generic_identities(a,inventory,models,glyphs):
    """Enumerate projections from printed headers, not candidate row counts."""
    result={}
    for heading,header in inventory['magic_headers'].items():
        match=re.match(r'^(Armor|Weapon) \(([^)]+)\),',header['text'])
        if not match:continue
        condition=match[2]
        if not (condition.startswith('Any ') or ', ' in condition or ' or ' in condition or '(+1)' in header['text']):continue
        if heading in {'Ammunition, +1, +2, or +3','Armor, +1, +2, or +3','Shield, +1, +2, or +3','Weapon, +1, +2, or +3'}:
            bonuses=re.findall(r'\(\+([123])\)',header['text'])
            if bonuses!=['1','2','3']:raise ValueError('Printed generic bonus tiers changed')
            names=['+'+bonus+' '+heading.split(',')[0]+(' (*)' if heading.startswith('Shield,') else '') for bonus in bonuses]
        elif heading=='Armor of Resistance':
            tables=models[heading]['tables']
            if len(tables)!=1 or tables[0]['colLabels']!=['1d10','Damage Type']:raise ValueError('Armor resistance source table changed')
            names=['Armor of '+row[1]+' Resistance' for row in tables[0]['rows']]
        elif heading=='Armor of Vulnerability':
            text,_=body_text(a.SOURCES[heading],glyphs)
            clause=re.search(r'Resistance to one of the following damage types: ([^.]+)\.',text)
            if not clause:raise ValueError('Missing armor vulnerability damage choices')
            types=re.split(r', or | or |, ',clause[1])
            if types!=['Bludgeoning','Piercing','Slashing']:raise ValueError('Armor vulnerability source choices changed')
            names=['Armor of Vulnerability ('+kind+')' for kind in types]
        else:names=[heading+(' (*)' if heading=='Plate Armor of Etherealness' else '')]
        for name in names:
            if name in result:raise ValueError('Duplicate independent generic source projection')
            result[name]=heading
    if len(result)!=51:raise ValueError(('Incomplete independent generic source projection inventory',len(result),sorted(result)))
    return result


def source_expectations(a,models):
    inventory=category_inventory(a,models);categories=source_categories(a.doc);ordinary=inventory['ordinary'];expected={}
    aliases={}
    for name,info in inventory['grants']['focus'].items():
        if re.search(r' \(also a Quarterstaff\)$',info['source_cells'][0]):
            aliases[name]={'canonical':'Quarterstaff','source_cells':info['source_cells'],'source_group':info['group']}
    if {name:info['canonical'] for name,info in aliases.items()}!={'Staff':'Quarterstaff','Wooden Staff':'Quarterstaff'}:
        raise ValueError('Printed focus/weapon alias inventory changed')
    def add(key,facts,evidence,classification):
        if key in expected:raise ValueError('Duplicate predicate source identity')
        expected[key]={'facts':facts,'source_evidence':evidence,'classification':classification}
    for field,names in FAMILY_NAMES.items():
        for name in names:
            key=('items-base.json','baseitem',name)
            if key not in ordinary:raise ValueError(('Unbound authored equipment-family identity',field,name))
            info=expected.setdefault(key,{'facts':{},'source_evidence':{'source_identity':ordinary[key]['source_evidence'],'family_indexes':{}},
                                         'classification':'Authored compatibility-family index; not an additional printed weapon property or proficiency.'})
            info['facts'][field]=True;info['source_evidence']['family_indexes'][field]=names
    for name,info in categories.items():
        match=re.search(r'Ammunition \(Range \d+/\d+; (Arrow|Bolt|Bullet|Needle)\)',info['source_cells'][2])
        if not match:continue
        ammo=match[1]
        if ammo=='Bullet':ammo='Firearm Bullet' if name in FAMILY_NAMES['firearm'] else ('Sling Bullet' if name=='Sling' else None)
        if not ammo or ('items-base.json','baseitem',ammo) not in ordinary:raise ValueError('Unbound printed ammunition relation')
        key=('items-base.json','baseitem',name)
        result=expected.setdefault(key,{'facts':{},'source_evidence':{'source_identity':ordinary[key]['source_evidence'],'family_indexes':{}},
                                        'classification':'Authored compatibility-family index and source weapon ammunition relation.'})
        result['facts']['ammoType']=uid(ammo.lower());result['source_evidence']['ammunition_relation']={'source_cells':info['source_cells'],
            'printed_ammunition_label':match[1],'resolved_source_item':ammo,
            'interpretation':'The printed Bullet label resolves to the Firearm or Sling ammunition-table row by its source weapon; no damage or quantity is inferred.'}
    variants=[r for r in a.RESULT if r['kind']=='magicvariant'];glyphs=GlyphSource(a.doc)
    identities=generic_identities(a,inventory,models,glyphs)
    if len(variants)!=51 or len({r['name'] for r in variants})!=51 or {r['name']:r['source_name'] for r in variants}!=identities:
        raise ValueError('Generic source projection inventory changed')
    for row in variants:
        heading=row['source_name'];header=inventory['magic_headers'].get(heading)
        if not header:raise ValueError('Missing generic source header')
        rule=source_rule(header,categories,ordinary);rule['canonical_physical_aliases']=aliases
        facts={'requires':rule['allowed_requires']}
        if rule['excludes'] is not None:facts['excludes']=[rule['excludes']]
        if 'Any Ammunition' in header['text']:facts['ammo']=[True]
        if heading=='Mithral Armor':
            text,evidence=body_text(a.SOURCES[heading],glyphs)
            clause="If the armor normally imposes Disadvantage on Dexterity (Stealth) checks or has a Strength requirement, the mithral version of the armor doesn't."
            if clause not in canon(text):raise ValueError('Missing printed Mithral requirement/stealth exception')
            facts.update(strength=[None],stealth=[False]);rule['conditional_exception']={'source_text':text,**evidence}
        add((row['file'],row['kind'],row['name']),facts,rule,'Source-bound generic equipment eligibility; alternate encodings are existing equivalent schema predicates.')
    # All source geometry is compared as persisted JSON evidence; game/schema
    # values still use strict type-aware comparison.
    for info in expected.values():info['source_evidence']=json.loads(json.dumps(info['source_evidence'],ensure_ascii=False))
    return expected


def audit(a,expected):
    results=[];errors=[];seen=set();base=a.DATA['items-base.json']['baseitem']
    for row in a.RESULT:
        key=(row['file'],row['kind'],row['name']);record=a.DATA[row['file']][row['kind']][row['index']]
        effective={**record,**record.get('inherits',{})}
        fields=FIELDS if row['kind']=='magicvariant' else (FAMILY_FIELDS|{'ammoType'} if row['kind']=='baseitem' else set())
        present=fields & effective.keys()
        if not present and key not in expected:continue
        if key not in expected or key in seen:
            errors.append({'identity':key,'error':'Missing or duplicate independently source-bound predicate projection'});continue
        seen.add(key);info=expected[key];facts=info['facts'];verified={};differences=[]
        if present!=set(facts):differences.append({'error':'Unexpected or missing predicate fields','actual':sorted(present),'expected':sorted(facts)})
        for field,wanted in facts.items():
            allowed=wanted if row['kind']=='magicvariant' else [wanted]
            matches=[value for value in allowed if field in effective and exact(effective[field],value)]
            if len(matches)==1:verified[field]={'value':effective[field],'source_expected':matches[0]}
            else:differences.append({'field':field,'value':effective.get(field),'source_allowed_encodings':allowed})
        if row['kind']=='magicvariant':
            actual=evaluate(record,base);wanted=set(info['source_evidence']['eligible'])
            aliases=info['source_evidence']['canonical_physical_aliases']
            actual={aliases[name]['canonical'] if name in aliases else name for name in actual}
            if actual!=wanted:differences.append({'field':'requires/excludes','missing_eligible':sorted(wanted-actual),'unexpected_eligible':sorted(actual-wanted)})
        result={'file':key[0],'kind':key[1],'name':key[2],'verified_metadata':verified,'source_evidence':info['source_evidence'],
                'classification':info['classification'],'differences':differences,'passed':not differences}
        results.append(result)
        if differences:errors.append({'identity':key,'differences':differences})
    if seen!=set(expected):errors.append({'error':'Incomplete predicate identity coverage','missing':sorted(set(expected)-seen)})
    return {'records':results,'errors':errors,'passed':not errors}


def require_proof(proof,a,expected):
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-predicate')
    model_path=ROOT/'source/item-families.json'
    if proof.get('models_sha256')!=hashlib.sha256(model_path.read_bytes()).hexdigest():raise ValueError('Stale predicate family model')
    current=audit(a,expected)
    if not current['passed']:raise ValueError('Current predicate data differs from independent source expectations')
    if proof.get('errors')!=[] or not isinstance(proof.get('records'),list):raise ValueError('Invalid predicate proof')
    wanted={(r['file'],r['kind'],r['name']):r for r in current['records']};indexed={}
    for record in proof['records']:
        key=(record.get('file'),record.get('kind'),record.get('name'))
        if key in indexed or key not in wanted or not exact(record,wanted[key]):raise ValueError('Predicate proof identity, field or source scope differs')
        indexed[key]=record
    if indexed.keys()!=wanted.keys():raise ValueError('Incomplete predicate proof identity coverage')
    return indexed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('pdf','data','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    if hashlib.sha256(args.pdf.read_bytes()).hexdigest()!=PDF_SHA256:raise ValueError('Official source PDF changed')
    model_path=ROOT/'source/item-families.json';models=json.loads(model_path.read_text(encoding='utf8'))['families']
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    expected=source_expectations(a,models);result=audit(a,expected)
    result.update(pdf_sha256=PDF_SHA256,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
