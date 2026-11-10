"""Verify retained ability-score query fields against fresh SRD source scopes.

These fields index an available effect; they do not encode its complete rule.
Wearing, attunement, duration, prerequisites, score limits and optional card
effects remain in the source evidence and literal item prose. No renderer or
source data is changed by this audit.
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
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from verify_item_families import prove_models,required_paragraph_indexes
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
ABILITIES={'Strength':'str','Dexterity':'dex','Constitution':'con','Intelligence':'int','Wisdom':'wis','Charisma':'cha'}
SINGLES={'Amulet of Health','Gauntlets of Ogre Power','Headband of Intellect','Belt of Dwarvenkind',
         'Manual of Bodily Health','Manual of Gainful Exercise','Manual of Quickness of Action',
         'Tome of Clear Thought','Tome of Leadership and Influence','Tome of Understanding',
         'Mysterious Deck','Hammer of Thunderbolts'}
IOUN={'Agility','Fortitude','Insight','Intellect','Leadership','Strength'}


def source_inventory(a,models):
    _,errors=prove_models(a,models)
    if errors:raise ValueError(('Family model differs from fresh PDF',errors))
    names=set(SINGLES)|{'Ioun Stone, '+name for name in IOUN}
    giant_rows={}
    for heading,prefix in [('Belt of Giant Strength','Belt'),('Potion of Giant Strength','Potion')]:
        tables=models[heading]['tables']
        if len(tables)!=1 or tables[0]['colLabels']!=[prefix,'Str.','Rarity'] or len(tables[0]['rows'])!=5:
            raise ValueError(('Giant Strength source grid changed',heading))
        for row in tables[0]['rows']:
            match=re.fullmatch(re.escape(heading)+r' \(([^)]+)\)',row[0])
            if not match or not row[1].isdigit():raise ValueError(('Unbound giant source row',row))
            for giant in match[1].split(' or '):
                name=prefix+' of '+giant.title()+' Giant Strength'
                if name in giant_rows:raise ValueError(('Duplicate giant source identity',name))
                names.add(name);giant_rows[name]={'score':int(row[1]),'cells':row,'heading':heading}
    if len(names)!=30 or len(giant_rows)!=12:raise ValueError('Ability projection inventory changed')
    identities={('items.json','item',name) for name in names-{'Hammer of Thunderbolts'}}
    identities.add(('magicvariants.json','magicvariant','Hammer of Thunderbolts'))
    return {'required_names':names,'required_identities':identities,'giant_rows':giant_rows}


def facts(a,models,inventory,glyphs,record,kind,heading):
    name=record['name']
    if heading in models:
        model=models[heading];indexes=required_paragraph_indexes(record,kind,model)
        text=' '.join(model['paragraphs'][i]['text'] for i in indexes)
        evidence={'pages':model['pages'],'paragraph_indexes':indexes,'source_text':text}
    else:
        text,evidence=body_text(a.SOURCES[heading],glyphs);evidence['source_text']=text
    evidence['interpretation']='Query index of an available effect; complete conditions and limits remain in the source text.'
    if name in inventory['giant_rows']:
        row=inventory['giant_rows'][name]
        if row['heading']!=heading or 'has no effect on you if your Strength' not in text:raise ValueError('Giant score condition/identity differs')
        evidence['source_table_row']=row['cells'];return {'static':{'str':row['score']}},evidence
    if name=='Mysterious Deck':
        match=re.search(r'\bStar\. Increase one of your ability scores by (\d+), to a maximum of (\d+)\.',text)
        if not match:raise ValueError('Missing printed Star ability-score choice')
        evidence['indexed_effect']=match[0]
        return {'from':list(ABILITIES.values()),'count':1,'amount':int(match[1])},evidence
    if name=='Hammer of Thunderbolts':
        match=re.search(r'The Strength score bestowed by your Belt of Giant Strength or Gauntlets of Ogre Power increases by (\d+), to a maximum of (\d+)\.',text)
        condition='While you are attuned to the weapon and wearing either a Belt of Giant Strength or Gauntlets of Ogre Power to which you are also attuned'
        if not match or condition not in text:raise ValueError('Missing conditional bestowed-score increase')
        evidence['score_maximum']=int(match[2]);return {'str':int(match[1])},evidence
    static=re.findall(r'Your (Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) is (\d+) while you wear',text)
    increase=re.findall(r'[Yy]our (Strength|Dexterity|Constitution|Intelligence|Wisdom|Charisma) increases by (\d+), to a maximum of (\d+)',text)
    if len(static)+len(increase)!=1:raise ValueError(('No unique source ability-score effect',name,static,increase))
    if static:
        ability,value=static[0]
        if 'no effect on you if your '+ability+' is '+value+' or higher without' not in text:
            raise ValueError('Missing existing-higher-score exception')
        return {'static':{ABILITIES[ability]:int(value)}},evidence
    ability,value,maximum=increase[0];evidence['score_maximum']=int(maximum)
    return {ABILITIES[ability]:int(value)},evidence


def exact(value,expected):
    # JSON's true == 1 must never pass a numeric-source assertion.
    if type(value) is not type(expected):return False
    if isinstance(expected,dict):return value.keys()==expected.keys() and all(exact(value[k],v) for k,v in expected.items())
    if isinstance(expected,list):return len(value)==len(expected) and all(exact(a,b) for a,b in zip(value,expected))
    return value==expected


def compare(record,expected):
    effective={**record,**record.get('inherits',{})};actual=effective.get('ability')
    equal=exact(actual,expected)
    return {'verified_metadata':{'ability':{'value':actual,'source_expected':expected}} if equal else {},
            'differences':[] if equal else [{'field':'ability','value':actual,'source_expected':expected}],'passed':equal}


def audit(a,models,inventory):
    glyphs=GlyphSource(a.doc);seen=set();records=[];errors=[]
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        record=a.DATA[file][kind][review['index']];effective={**record,**record.get('inherits',{})}
        identity=(file,kind,name)
        if identity not in inventory['required_identities'] and 'ability' not in effective:continue
        if identity in seen:errors.append({'name':name,'error':'Duplicate ability projection'});continue
        seen.add(identity)
        if record['name']!=name or identity not in inventory['required_identities']:
            errors.append({'name':name,'error':'Unexpected ability identity/kind'});continue
        try:
            expected,evidence=facts(a,models,inventory,glyphs,record,kind,heading)
            result=compare(record,expected);result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'name':name,'differences':result['differences']})
        except (ValueError,KeyError,IndexError,TypeError) as exc:errors.append({'name':name,'error':str(exc)})
    if len(records)!=30 or seen!=inventory['required_identities']:
        errors.append({'error':'Missing or extra ability projections','missing':sorted(inventory['required_identities']-seen)})
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
    result=audit(a,models,source_inventory(a,models))
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
