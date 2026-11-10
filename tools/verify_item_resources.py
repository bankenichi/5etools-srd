"""Verify item charge pools and daily restoration from fresh printed clauses.

Daily ability-use limits do not imply that expended charges regenerate. In
particular, Luck Blade's daily Wish limit must not replenish its finite pool.
Robe of Stars uses six expendable stars, explicitly restored at dusk. Other
conditional recharge rules remain literal source prose; this audit does not
invent a generic timer for them or certify other item mechanics/layout.
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
from rule_table_grid import PDF_SHA256
from verify_item_families import prove_models,required_paragraph_indexes

ROOT=Path(__file__).resolve().parents[1]
EXPR=r'(?:\d+d\d+(?: \+ \d+)?|\d+)'
FIELDS=('charges','recharge','rechargeAmount')


def number_or_dice(value):return int(value) if value.isdecimal() else value


def source_scope(a,record,kind,heading,models):
    if heading not in models:
        source=a.SOURCES[heading];body=a.split_source(source,'')[2]
        lines=[l for l in body if not all(f.startswith('GillSans') for f in l['fonts'])]
        text,joins=a.join_pdf(lines,'')
        return text,{'heading':heading,'pages':sorted({l['page'] for l in lines}),'source_lines':lines,'layout_joins':joins}
    model=models[heading];indexes=required_paragraph_indexes(record,kind,model)
    # These groups delegate distinct subtype rules to their members. Only the
    # generic prefix defines a common group-level resource, not (for example)
    # an Ivory Goat's charge pool on every figurine in the family.
    if kind=='itemGroup' and heading in {'Figurine of Wondrous Power','Ioun Stone','Feather Token'}:
        end=next(i for i,p in enumerate(model['paragraphs']) if re.match(r'^.+? \((?:Uncommon|Rare|Very Rare|Legendary)\)\.',p['text']))
        indexes=list(range(end))
    return ' '.join(model['paragraphs'][i]['text'] for i in indexes),{'heading':heading,'pages':model['pages'],'source_paragraph_indexes':indexes,
      'scope_basis':'Identity-selected source paragraphs; no candidate paragraph indexes or numeric values select the source.'}


def extract_facts(text,heading):
    facts={};evidence={}
    capacities=list(re.finditer(r'\b(?:has|have|starts with) ('+EXPR+r') charges\b',text))
    values={number_or_dice(m[1]) for m in capacities}
    if len(values)>1:raise ValueError(('Multiple independently scoped charge pools require review',heading,values))
    if values:
        facts['charges']=values.pop();evidence['charges']=[m[0] for m in capacities]
    restored=list(re.finditer(r'\bregains? ('+EXPR+r'|all) expended charges? daily at (dawn|dusk)\b',text))
    if restored:
        times={m[2] for m in restored};amounts={m[1] for m in restored}
        if len(times)!=1 or len(amounts)!=1:raise ValueError(('Multiple restoration clauses require review',heading))
        facts['recharge']=times.pop();amount=amounts.pop()
        if amount=='all':
            if type(facts.get('charges')) is not int:raise ValueError(('Restoration of all charges lacks a fixed source capacity',heading))
            amount=facts['charges']
        else:amount=number_or_dice(amount)
        facts['rechargeAmount']=amount
        evidence['recharge']=evidence['rechargeAmount']=[m[0] for m in restored]
    if heading=='Bag of Tricks':
        clause="Once three fuzzy objects have been pulled from the bag, the bag can't be used again until the next dawn."
        normalized=text.replace('’',"'")
        if clause not in normalized:raise ValueError('Bag of Tricks use-restoration clause changed')
        facts['recharge']='dawn';evidence['recharge']=[clause]
    if heading=='Robe of Stars':
        capacity="Six stars, located on the robe's upper-front portion, are particularly large."
        restored='Daily at dusk, 1d6 removed stars reappear on the robe.'
        normalized=text.replace('’',"'")
        if capacity not in normalized or restored not in normalized:raise ValueError('Robe of Stars resource clauses changed')
        facts.update(charges=6,recharge='dusk',rechargeAmount='1d6')
        evidence.update(charges=[capacity],recharge=[restored],rechargeAmount=[restored])
    return facts,evidence


def compare(record,kind,heading,text):
    facts,evidence=extract_facts(text,heading);effective={**record,**record.get('inherits',{})}
    differences=[];verified={}
    for field in FIELDS:
        actual=effective.get(field);expected=facts.get(field)
        # Lack of a simple universal capacity/timer is not evidence that a
        # resource has no conditional rules. Those rules remain in source prose.
        if actual==expected:
            if field in effective:verified[field]={'value':actual,'source_clauses':evidence.get(field,[])}
        else:differences.append({'field':field,'actual':actual,'expected':expected,'source_clauses':evidence.get(field,[])})
    return {'name':record['name'],'kind':kind,'source_heading':heading,'verified_metadata':verified,
      'source_facts':facts,'differences':differences,'passed':not differences}


def audit(a,models):
    _,model_errors=prove_models(a,models)
    if model_errors:raise ValueError(('Saved source model differs from fresh PDF',model_errors))
    records=[];errors=[]
    for review in a.RESULT:
        if review['kind'] not in ('item','itemGroup','magicvariant'):continue
        record=a.DATA[review['file']][review['kind']][review['index']];heading=review['source_name']
        if heading not in a.SOURCES:continue
        try:
            text,source=source_scope(a,record,review['kind'],heading,models)
            result=compare(record,review['kind'],heading,text)
            if not result['source_facts'] and not any(k in {**record,**record.get('inherits',{})} for k in FIELDS):continue
            result.update(file=review['file'],source_evidence=source);records.append(result)
        except (AssertionError,ValueError,KeyError,TypeError,IndexError,StopIteration) as error:
            errors.append({'name':record['name'],'kind':review['kind'],'error':str(error)})
    return {'records':records,'errors':errors,'passed':not errors and all(r['passed'] for r in records)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    path=ROOT/'source/item-families.json';model=json.loads(path.read_text(encoding='utf8'));assert model['official_pdf_sha256']==pdf_hash
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    result=audit(a,model['families'])
    summary={'resource_records':len(result['records']),'verified_fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),
      'records_with_differences':sum(not r['passed'] for r in result['records']),'errors':result['errors'],'passed':result['passed']}
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),summary=summary,scope=__doc__,
      input_sha256={name:hashlib.sha256((a.STAGED/name).read_bytes()).hexdigest() for name in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
