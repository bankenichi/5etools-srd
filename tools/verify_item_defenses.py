"""Verify retained item Resistance, Immunity and Vulnerability arrays.

The official damage-type grid and freshly re-proven family rows supply values;
identity selects the subtype, never the candidate defense array. Full wearing,
holding, gemstone, duration and curse conditions remain bound as source text.
This component covers 56 existing defense-bearing projections, not every
optional query field that could be added or other item rules/layout.
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
from locate_source_citations import Source as CitationSource
from rule_table_grid import Source as GlyphSource,PDF_SHA256
from verify_item_families import prove_models,required_paragraph_indexes
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'resist','immune','vulnerable'}
SINGLES={'Belt of Dwarvenkind','Boots of the Winterlands','Brooch of Shielding','Cloak of Arachnida',
         'Helm of Brilliance','Potion of Invulnerability','Ring of Warmth','Staff of Fire','Staff of Frost',
         'Periapt of Proof against Poison'}
SELECTABLE={'Armor of Resistance':'Armor','Potion of Resistance':'Potion','Ring of Resistance':'Ring'}


def source_inventory(a,models):
    _,errors=prove_models(a,models)
    if errors:raise ValueError(('Family source model differs from fresh PDF',errors))
    source=CitationSource(a.doc);found=source.table_row('Damage Types','Acid')
    if found['status']!='LOCATED':raise ValueError('Damage-type source table missing')
    table=source.table_cache['Damage Types']
    if table['headers']!=['Type','Examples'] or len(table['rows'])!=13:raise ValueError('Damage-type source inventory changed')
    types=[row['cells'][0]['text'] for row in table['rows']]
    if len(set(types))!=13:raise ValueError('Duplicate physical damage types')
    selected={};names=set(SINGLES)
    for heading,prefix in SELECTABLE.items():
        model=models[heading];grid=model['tables'][0]
        if grid['colLabels'][:2]!=['1d10','Damage Type'] or len(grid['rows'])!=10:raise ValueError(('Damage-selection source grid changed',heading))
        choices=[row[1] for row in grid['rows']]
        if len(set(choices))!=10 or not set(choices)<=set(types):raise ValueError(('Invalid damage type grid',heading))
        selected[heading]=choices;names.update(prefix+' of '+kind+' Resistance' for kind in choices)
    dragons=models['Dragon Scale Mail']['tables'][0]
    if dragons['colLabels']!=['Dragon','Resistance'] or len(dragons['rows'])!=10:raise ValueError('Dragon-defense source rows changed')
    names.update(row[0]+' Dragon Scale Mail' for row in dragons['rows'])
    vulnerability=models['Armor of Vulnerability']['paragraphs'][0]['text']
    match=re.search(r'one of the following damage types: (.+?)\.',vulnerability)
    if not match:raise ValueError('Missing armor defense choice clause')
    physical=[p.strip() for p in re.split(r',|\bor\b',match[1]) if p.strip()]
    if len(physical)!=3 or not set(physical)<=set(types):raise ValueError('Armor vulnerability type inventory changed')
    names.update('Armor of Vulnerability ('+kind+')' for kind in physical)
    names.update('Ring of Elemental Command ('+plane+')' for plane in ('Air','Earth','Fire'))
    if len(names)!=56:raise ValueError(('Defense projection inventory changed',len(names)))
    return {'damage_types':types,'damage_source_table':table,'selectable':selected,
            'dragon_rows':dragons['rows'],'physical_armor_types':physical,'required_names':names}


def facts(a,models,inventory,glyphs,record,kind,heading):
    evidence={};name=record['name'];expected={}
    if heading in models:
        model=models[heading];indexes=required_paragraph_indexes(record,kind,model)
        text=' '.join(model['paragraphs'][i]['text'] for i in indexes)
        evidence={'pages':model['pages'],'paragraph_indexes':indexes,'source_text':text}
    else:
        text,evidence=body_text(a.SOURCES[heading],glyphs);evidence['source_text']=text
    if heading in SELECTABLE:
        prefix=SELECTABLE[heading];choices=inventory['selectable'][heading]
        matches=[choice for choice in choices if name==prefix+' of '+choice+' Resistance']
        if len(matches)!=1 or not re.search(r'Resistance to one (?:type of damage|damage type)',text):raise ValueError(('Unbound defense family identity',name))
        expected['resist']=[matches[0].lower()];evidence['source_damage_rows']=models[heading]['tables'][0]
    elif heading=='Dragon Scale Mail':
        matches=[row for row in inventory['dragon_rows'] if name==row[0]+' Dragon Scale Mail']
        if len(matches)!=1 or 'While wearing this armor' not in text or 'Resistance to one damage type' not in text:raise ValueError(('Unbound dragon defense',name))
        expected['resist']=[matches[0][1].lower()];evidence['source_damage_row']=matches[0]
    elif heading=='Armor of Vulnerability':
        choices=inventory['physical_armor_types'];selected=[choice for choice in choices if name=='Armor of Vulnerability ('+choice+')']
        clause='While cursed, you have Vulnerability to two of the three damage types associated with the armor (not the one to which it grants Resistance).'
        if len(selected)!=1 or clause not in text:raise ValueError(('Unbound curse defense',name))
        expected={'resist':[selected[0].lower()],'vulnerable':sorted(c.lower() for c in choices if c!=selected[0])}
    else:
        if name=='Ring of Warmth' and 'If you take Cold damage while wearing this ring, the ring reduces the damage you take by 2d8.' not in text:
            raise ValueError('Missing printed flat Cold-damage reduction; absence is not a Resistance proof')
        alternatives='|'.join(re.escape(t) for t in sorted(inventory['damage_types'],key=len,reverse=True))
        for match in re.finditer(r'\b(Resistance|Immunity|Vulnerability) to (?:the \w+ condition and )?(all|'+alternatives+r') damage\b',text):
            field={'Resistance':'resist','Immunity':'immune','Vulnerability':'vulnerable'}[match[1]]
            values=inventory['damage_types'] if match[2]=='all' else [match[2]]
            expected.setdefault(field,[]).extend(v.lower() for v in values)
        expected={key:sorted(set(value)) for key,value in expected.items()}
        if name in SINGLES-{'Ring of Warmth'} and not expected:raise ValueError(('Source defense clause did not parse',name))
        if name=='Ring of Elemental Command (Fire)' and expected!={'immune':['fire']}:raise ValueError('Fire-plane Immunity source scope changed')
    return expected,evidence


def compare(record,expected):
    effective={**record,**record.get('inherits',{})};verified={};differences=[]
    for field in sorted(FIELDS):
        if field not in expected:
            if field in effective:differences.append({'field':field,'value':effective[field],'source_expected':'No printed defense of this kind in this exact source scope.'})
            continue
        actual=effective.get(field);wanted=expected[field]
        equal=isinstance(actual,list) and all(isinstance(v,str) for v in actual) and Counter(actual)==Counter(wanted)
        if equal:verified[field]={'value':actual,'source_expected':wanted}
        else:differences.append({'field':field,'value':actual,'source_expected':wanted})
    return {'verified_metadata':verified,'differences':differences,'passed':not differences}


def audit(a,models,inventory):
    glyphs=GlyphSource(a.doc);seen=set();records=[];errors=[]
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        record=a.DATA[file][kind][review['index']];effective={**record,**record.get('inherits',{})}
        if name not in inventory['required_names'] and not FIELDS & effective.keys():continue
        identity=(file,kind,name)
        if identity in seen:errors.append({'name':name,'error':'Duplicate defense projection'});continue
        seen.add(identity)
        if record['name']!=name or kind not in {'item','magicvariant'}:
            errors.append({'name':name,'error':'Defense projection identity/kind mismatch'});continue
        try:
            expected,evidence=facts(a,models,inventory,glyphs,record,kind,heading)
            result=compare(record,expected);result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'name':name,'differences':result['differences']})
        except (ValueError,KeyError,IndexError,TypeError) as exc:errors.append({'name':name,'error':str(exc)})
    if {name for _,_,name in seen}!=inventory['required_names'] or len(records)!=56:
        errors.append({'error':'Missing or extra defense projections','missing':sorted(inventory['required_names']-{name for _,_,name in seen})})
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
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),
                  damage_types=inventory['damage_types'],damage_source_table=inventory['damage_source_table'],
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES},scope=__doc__)
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
