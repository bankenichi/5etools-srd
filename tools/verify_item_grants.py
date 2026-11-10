"""Verify retained language, proficiency, focus and scroll-level query fields.

These are indexes of available source effects, with full conditions retained.
The legacy proficiency flag on Elven Chain indexes training with that armor,
not training with an entire armor category. Source focus tables and literal
class clauses select categories/classes; candidate values never select them.
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
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from verify_item_abilities import exact
from verify_item_families import prove_models,required_paragraph_indexes
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
FIELDS={'grantsLanguage','grantsProficiency','focus','scfType','spellScrollLevel'}
LANGUAGE={'Belt of Dwarvenkind','Demon Armor'}|{'Ring of Elemental Command ('+plane+')' for plane in ('Air','Earth','Fire','Water')}
PROFICIENCY={'Bracers of Archery','Mysterious Deck','Elven Chain'}
CLASS_NAMES={'Barbarian','Bard','Cleric','Druid','Fighter','Monk','Paladin','Ranger','Rogue','Sorcerer','Warlock','Wizard'}


def source_inventory(a,models):
    _,errors=prove_models(a,models)
    if errors:raise ValueError(('Family models differ from physical source',errors))
    glyphs=GlyphSource(a.doc);source=CitationSource(a.doc);focus={};groups={};tables={}
    for group,heading,caption,first,code,count in [
        ('Arcane Focus','Arcane Focus (Varies)','Arcane Focuses','Crystal','arcane',5),
        ('Druidic Focus','Druidic Focus (Varies)','Druidic Focuses','Sprig of Mistletoe','druid',3),
        ('Holy Symbol','Holy Symbol (Varies)','Holy Symbols','Amulet (worn or held)','holy',3)]:
        result=source.table_row(caption,first);table=source.table_cache[caption]
        wanted_headers=['Symbol' if code=='holy' else 'Focus','Weight','Cost']
        if result['status']!='LOCATED' or table['headers']!=wanted_headers or len(table['rows'])!=count:
            raise ValueError(('Focus source table inventory changed',caption))
        text,evidence=body_text(a.SOURCES[heading],glyphs)
        classes=re.findall(r'\b('+'|'.join(sorted(CLASS_NAMES))+r')\b',re.search(r'A (.+?) can use (?:such an item|such an object|a Holy Symbol) as a Spellcasting Focus\.',text)[1])
        if not classes or len(classes)!=len(set(classes)):raise ValueError('Unbound focus class source clause')
        groups[group]={'code':code,'classes':classes,'heading':heading,'source_text':text,'source_evidence':evidence}
        for row in table['rows']:
            printed=row['cells'][0]['text'];name=re.sub(r' \([^)]*\)$','',printed)
            name={'Sprig of mistletoe':'Sprig of Mistletoe','Wooden staff':'Wooden Staff','Yew wand':'Yew Wand'}.get(name,name)
            if name in focus:raise ValueError('Duplicate focus source identity')
            focus[name]={'group':group,'source_cells':[c['text'] for c in row['cells']],**groups[group]}
        tables[caption]=table
    scroll=models['Spell Scroll']['tables']
    if len(scroll)!=1 or len(scroll[0]['rows'])!=10 or scroll[0]['colLabels'][0]!='Spell Level':raise ValueError('Spell Scroll level source grid changed')
    levels={}
    for row in scroll[0]['rows']:
        label=row[0]
        if label!='Cantrip' and not re.fullmatch(r'[1-9]',label):raise ValueError('Unreviewed printed scroll level')
        levels['Spell Scroll ('+('Cantrip' if label=='Cantrip' else 'Level '+label)+')']={'level':0 if label=='Cantrip' else int(label),'source_cells':row}
    # The schema's zero is a source-defined Cantrip level, not an assumed
    # number inferred from the candidate's existing spellScrollLevel.
    witnesses=[]
    for number,page in enumerate(a.doc,1):
        match=re.search(r'[Aa] cantrip is a level 0 spell',page.get_text())
        if match:witnesses.append({'page':number,'source_clause':match[0]})
    if not witnesses:raise ValueError('Missing printed definition of Cantrip level zero')
    identities=set()
    for name in LANGUAGE|PROFICIENCY|{'Hat of Many Spells'}|set(levels):
        variant=name in {'Demon Armor','Elven Chain'}
        identities.add(('magicvariants.json' if variant else 'items.json','magicvariant' if variant else 'item',name))
    identities.update(('items.json','itemGroup',name) for name in groups)
    identities.update(('items-base.json' if info['code']=='arcane' or name=='Wooden Staff' else 'items.json',
                       'baseitem' if info['code']=='arcane' or name=='Wooden Staff' else 'item',name) for name,info in focus.items())
    if len(identities)!=34 or len(levels)!=10:raise ValueError(('Grant projection inventory changed',len(identities)))
    return {'required_identities':identities,'focus':focus,'groups':groups,'focus_tables':tables,'scroll_levels':levels,'cantrip_zero_source':witnesses}


def facts(a,models,inventory,glyphs,record,kind,heading):
    name=record['name'];expected={}
    if name in inventory['focus'] or name in inventory['groups']:
        info=(inventory['groups'] if kind=='itemGroup' else inventory['focus'])[name]
        expected['scfType']=info['code']
        if kind=='itemGroup':expected['focus']=info['classes']
        return expected,info
    if heading in models:
        model=models[heading];indexes=required_paragraph_indexes(record,kind,model)
        text=' '.join(model['paragraphs'][i]['text'] for i in indexes)
        evidence={'pages':model['pages'],'paragraph_indexes':indexes,'source_text':text}
    else:
        text,evidence=body_text(a.SOURCES[heading],glyphs);evidence['source_text']=text
    if name in LANGUAGE:
        languages=re.findall(r'\b[Yy]ou know (Auran|Terran|Ignan|Aquan|Abyssal|Dwarvish)\b',text)
        if len(languages)!=1:raise ValueError('No unique literal language grant in this source scope')
        expected['grantsLanguage']=True;evidence['indexed_language']=languages[0]
    if name in PROFICIENCY:
        if name=='Elven Chain':
            clause='You are considered trained with this armor even if you lack training with Medium or Heavy armor.'
            evidence['legacy_schema_interpretation']='Training with this particular armor is indexed by grantsProficiency; no grant for an entire armor category.'
        elif name=='Bracers of Archery':clause='you have proficiency with the Longbow and Shortbow'
        else:clause='Throne. You gain proficiency and Expertise in your choice of History, Insight, Intimidation, or Persuasion.'
        if clause not in text:raise ValueError('Missing identity-scoped proficiency/training effect')
        expected['grantsProficiency']=True;evidence['indexed_effect']=clause
    if name=='Hat of Many Spells':
        matches=re.findall(r'use it as a Spellcasting Focus for your (\w+) spells',text)
        if len(matches)!=1 or matches[0] not in CLASS_NAMES:raise ValueError('Missing hat focus/class source clause')
        expected['focus']=matches
    if name in inventory['scroll_levels']:
        info=inventory['scroll_levels'][name];expected['spellScrollLevel']=info['level']
        evidence['source_table_row']=info['source_cells'];evidence['cantrip_zero_source']=inventory['cantrip_zero_source']
    return expected,evidence


def compare(record,expected):
    effective={**record,**record.get('inherits',{})};verified={};differences=[]
    for field in sorted(FIELDS):
        if field not in expected:
            if field in effective:differences.append({'field':field,'value':effective[field],'source_expected':'No existing index of this kind in this source scope.'})
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
        if identity in seen:errors.append({'name':name,'error':'Duplicate grant projection'});continue
        seen.add(identity)
        if identity not in inventory['required_identities'] or record['name']!=name:
            errors.append({'name':name,'error':'Unexpected grant identity/kind'});continue
        try:
            expected,evidence=facts(a,models,inventory,glyphs,record,kind,heading)
            result=compare(record,expected);result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'name':name,'differences':result['differences']})
        except (ValueError,KeyError,IndexError,TypeError) as exc:errors.append({'name':name,'error':str(exc)})
    if len(records)!=34 or seen!=inventory['required_identities']:
        errors.append({'error':'Missing or extra grant projections','missing':sorted(inventory['required_identities']-seen)})
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
                  focus_tables=inventory['focus_tables'],cantrip_zero_source=inventory['cantrip_zero_source'],
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
