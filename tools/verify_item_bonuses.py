"""Verify retained bonus scalars from fresh, identity-scoped SRD clauses.

Conditional clauses remain attached to each fact: a number is not an
unconditional grant. Optional query fields are not invented when absent.
Configurable AC transfer is not representable by a fixed AC scalar; examples
must not be mistaken for a fixed grant. Other mechanics/layout remain separate.
"""
import argparse
from collections import Counter,defaultdict
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from rule_table_grid import PDF_SHA256,Source as GlyphSource
from verify_item_families import prove_models
from verify_item_resources import source_scope
from verify_magic_item_headers import source_header

ROOT=Path(__file__).resolve().parents[1]
TARGETS={
    'Armor Class, saving throws, and spell attack rolls':('bonusAc','bonusSavingThrow','bonusSpellAttack'),
    'Armor Class and saving throws':('bonusAc','bonusSavingThrow'),
    'ability checks and saving throws':('bonusAbilityCheck','bonusSavingThrow'),
    'attack rolls and damage rolls':('bonusWeapon',),
    'the attack and damage rolls of your Unarmed Strikes':('bonusWeapon',),
    'damage rolls made with such weapons':('bonusWeaponDamage',),
    'spell attack rolls':('bonusSpellAttack',),'saving throws':('bonusSavingThrow',),
    'Armor Class':('bonusAc',),'ability checks':('bonusAbilityCheck',)}
FIELDS={'bonusAc','bonusWeapon','bonusSpellAttack','bonusSavingThrow','bonusSpellSaveDc',
        'bonusAbilityCheck','bonusProficiencyBonus','bonusWeaponDamage'}
BONUS=re.compile(r'(\+\d+) bonus to (?:your )?('+'|'.join(re.escape(s) for s in TARGETS)+r')\b')


def extract_facts(text,header,name,kind):
    values=defaultdict(set);clauses=defaultdict(list);dynamic={}
    def add(field,value,clause):values[field].add(value);clauses[field].append(clause)
    for match in BONUS.finditer(text):
        # Keep the full sentence so restrictions such as ranged attacks,
        # wearing no armor, or the triggering attack remain visible evidence.
        start=text.rfind('. ',0,match.start())+2 if '. ' in text[:match.start()] else 0
        end=text.find('. ',match.end());sentence=text[start:] if end<0 else text[start:end+1]
        for field in TARGETS[match[2]]:add(field,match[1],sentence)
    for match in re.finditer(r'Your Proficiency Bonus increases by (\d+)\b',text):
        add('bonusProficiencyBonus','+'+match[1],text)
    for match in re.finditer(r'Your spell save DC and spell attack bonus each increase by (\d+)\b',text):
        for field in ('bonusSpellSaveDc','bonusSpellAttack'):add(field,'+'+match[1],text)
    for match in re.finditer(r'turning the coated weapon into a \+(\d+) Weapon or the coated ammunition into \+\1 Ammunition',text):
        add('bonusWeapon','+'+match[1],text)
    transfer=re.search(r"you can transfer some or all of the weapon['’]s bonus to your Armor Class",text)
    if transfer:
        # A chosen amount is not a universal +1, the +2 example, or a
        # universal +3. Preserve the source rule instead of a false scalar.
        dynamic['bonusAc']={'reason':'Configurable transfer of weapon bonus; no fixed scalar.',
                            'source_clause':transfer[0],'ignored_example_matches':clauses.pop('bonusAc',[])}
        values.pop('bonusAc',None)
    parameter_values=set(re.findall(r'\(\+([123])\)',header or ''))
    if parameter_values and kind!='itemGroup':
        identity=re.match(r'^\+([123])(?: |$)',name)
        if not identity or identity[1] not in parameter_values:raise ValueError(('Bonus identity has no printed header parameter',name))
        category=re.match(r'^(Armor|Weapon|Wand)\b',header)
        if not category:raise ValueError(('Unreviewed parameterized bonus category',name))
        field={'Armor':'bonusAc','Weapon':'bonusWeapon','Wand':'bonusSpellAttack'}[category[1]]
        required={'bonusAc':r'bonus to (?:your )?Armor Class','bonusWeapon':r'bonus to attack rolls and damage rolls',
                  'bonusSpellAttack':r'bonus to spell attack rolls'}[field]
        if not re.search(required,text):raise ValueError(('Header parameter lacks its printed bonus rule',name,field))
        add(field,'+'+identity[1],header)
    return dict(values),dict(clauses),dynamic


def compare(record,kind,text,header):
    effective={**record,**record.get('inherits',{})}
    values,clauses,dynamic=extract_facts(text,header,record['name'],kind)
    verified={};differences=[]
    for field in sorted(FIELDS & effective.keys()):
        actual=effective[field];expected=values.get(field,set())
        if field in dynamic:
            differences.append({'field':field,'value':actual,'expected':'No fixed scalar; retain the complete configurable source rule.','source':dynamic[field]})
        elif len(expected)==1 and isinstance(actual,str) and actual in expected:
            verified[field]={'value':actual,'source_expected':next(iter(expected)),'source_clauses':clauses[field]}
        else:differences.append({'field':field,'value':actual,'source_expected':sorted(expected),'source_clauses':clauses.get(field,[])})
    return {'verified_metadata':verified,'differences':differences,'dynamic_source_effects':dynamic,
            'optional_source_fields_not_encoded':{k:sorted(v) for k,v in values.items() if k not in effective},'passed':not differences}


def audit(a,models):
    _,model_errors=prove_models(a,models)
    if model_errors:raise ValueError(('Saved family model differs from fresh source',model_errors))
    glyphs=GlyphSource(a.doc);headers={};records=[];errors=[];seen=set()
    for name,src in a.SOURCES.items():
        if src['red12'] and 209<=src['heading_lines'][0]['page']<=254:
            header=source_header(src,glyphs)
            if header:headers[name]=header['text']
    if len(headers)!=258:raise ValueError('Printed magic-item entry inventory changed')
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        if kind not in {'item','itemGroup','magicvariant'} or heading not in headers:continue
        record=a.DATA[file][kind][review['index']];effective={**record,**record.get('inherits',{})}
        if not FIELDS & effective.keys():continue
        identity=(file,kind,name)
        if identity in seen:
            errors.append({'file':file,'kind':kind,'name':name,'error':'Duplicate bonus projection identity'});continue
        seen.add(identity)
        if record['name']!=name:
            errors.append({'file':file,'kind':kind,'name':name,'error':'Indexed source identity differs from record'});continue
        try:
            text,evidence=source_scope(a,record,kind,heading,models)
            result=compare(record,kind,text,headers[heading])
            result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'file':file,'kind':kind,'name':name,'differences':result['differences']})
        except (ValueError,AssertionError,KeyError,TypeError,IndexError) as error:
            errors.append({'file':file,'kind':kind,'name':name,'error':str(error)})
    return {'records':records,'errors':errors,'passed':not errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('pdf','data','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if pdf_hash!=PDF_SHA256:raise ValueError('Official PDF changed')
    model_path=ROOT/'source/item-families.json';models=json.loads(model_path.read_text(encoding='utf8'))
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    result=audit(a,models['families'])
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,
                  input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'verified_fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),
                      'errors':result['errors'],'passed':result['passed']},ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
