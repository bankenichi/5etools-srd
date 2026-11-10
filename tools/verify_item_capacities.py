"""Verify literal retained container capacities and their SRD-only references.

Volume query values use cubic feet. Rounded conversions of printed pints or
gallons are not exact source facts and must be absent. Unqualified ounces do
not establish a weight in pounds. Complete capacities, alternate loads and
compartment conditions stay in the unchanged printed prose. weightless indexes
contents exempt from ordinary added load; the source still gives the container
a fixed weight or upper bound, rather than zero weight.
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
from verify_item_abilities import exact
from verify_weapon_overrides import body_text

ROOT=Path(__file__).resolve().parents[1]
WEIGHT={'Backpack','Basket','Pouch','Sack'}
VOLUME={'Barrel','Bucket','Chest'}
LIQUID={'Flask','Glass Bottle','Iron Pot','Jug','Waterskin','Vial'}
ITEMS={'Crossbow Bolt Case','Map or Scroll Case','Quiver','Efficient Quiver'}
REQUIRED=WEIGHT|VOLUME|LIQUID|ITEMS|{'Bag of Holding','Handy Haversack'}
IDENTITIES={('items.json','item',name) for name in REQUIRED}


def uid(name):return name.lower()+'|srd521'


def facts(name,text):
    evidence={'source_text':text,'interpretation':__doc__}
    if name in WEIGHT:
        matches=re.findall(r'holds up to (\d+) pounds\b',text)
        if len(matches)!=1:raise ValueError('Missing unique printed container weight capacity')
        return {'weight':[int(matches[0])]},evidence
    if name in VOLUME:
        matches=re.findall(r'holds up to (half a|\d+) cubic (?:foot|feet)\b',text)
        # Barrel's alternate dry-goods capacity follows its liquid capacity.
        if name=='Barrel':matches=re.findall(r'or up to (\d+) cubic feet of dry goods\.',text)
        if len(matches)!=1:raise ValueError('Missing unique printed cubic-foot capacity')
        return {'volume':[0.5 if matches[0]=='half a' else int(matches[0])]},evidence
    if name in LIQUID:
        matches=re.findall(r'holds up to (\d+(?:½)?) (pints?|gallons?|ounces?)\.',text)
        if len(matches)!=1:raise ValueError('Missing printed liquid/unqualified-ounce capacity')
        evidence['unconverted_printed_quantity']={'amount':matches[0][0],'unit':matches[0][1]}
        evidence['absence_reason']='No approximate cubic-foot conversion or assumed pound conversion is encoded; retain the exact printed quantity in prose.'
        return None,evidence
    if name=='Bag of Holding':
        capacity=re.search(r'bag can hold up to (\d+) pounds, not exceeding a volume of (\d+) cubic feet\.',text)
        fixed=re.search(r'bag weighs (\d+) pounds, regardless of its contents\.',text)
        if not capacity or not fixed:raise ValueError('Bag load, volume or fixed-weight condition missing')
        evidence['fixed_container_weight_lb']=int(fixed[1]);evidence['additional_printed_volume_cuft']=int(capacity[2])
        return {'weight':[int(capacity[1])],'weightless':True},evidence
    if name=='Handy Haversack':
        side=re.search(r'Each side pouch can hold up to (\d+) pounds of material, not exceeding a volume of (\d+) cubic feet\.',text)
        central=re.search(r'central pouch can hold up to (\d+) pounds of material, not exceeding a volume of (\d+) cubic feet\.',text)
        fixed=re.search(r'haversack always weighs (\d+) pounds, regardless of its contents\.',text)
        if not side or not central or not fixed or 'a central pouch and two side pouches' not in text:
            raise ValueError('Haversack compartment inventory/conditions missing')
        evidence['fixed_container_weight_lb']=int(fixed[1]);evidence['additional_printed_volume_cuft']=[int(side[2]),int(side[2]),int(central[2])]
        evidence['compartment_order']=['side','side','central']
        return {'weight':[int(side[1]),int(side[1]),int(central[1])],'weightless':True},evidence
    if name=='Crossbow Bolt Case':
        match=re.search(r'Case holds up to (\d+) Bolts\.',text)
        if not match:raise ValueError('Missing Bolt capacity')
        return {'item':[{uid('Bolt'):int(match[1])}]},evidence
    if name=='Map or Scroll Case':
        match=re.search(r'holds up to (\d+) sheets of paper or (\d+) sheets of parchment\.',text)
        if not match:raise ValueError('Missing alternate paper/parchment capacities')
        evidence['alternatives_not_additive']=True
        return {'item':[{uid('Parchment'):int(match[2]),uid('Paper'):int(match[1])}]},evidence
    if name=='Quiver':
        match=re.search(r'Quiver holds up to (\d+) Arrows\.',text)
        if not match:raise ValueError('Missing Arrow capacity')
        return {'item':[{uid('Arrow'):int(match[1])}]},evidence
    if name=='Efficient Quiver':
        fixed=re.search(r'never weighing more than (\d+) pounds\.',text)
        small=re.search(r'shortest compartment can hold up to (\d+) Arrows, Bolts, or similar objects\.',text)
        middle=re.search(r'mid-size compartment holds up to (\d+) Javelins or similar objects\.',text)
        long=re.search(r'longest compartment holds up to (\d+) long objects, such as bows, Quarterstaffs, or Spears\.',text)
        if not all((fixed,small,middle,long)) or 'three compartments' not in text:raise ValueError('Missing quiver compartment inventory/conditions')
        evidence['compartment_order']=['shortest','mid-size','longest'];evidence['alternatives_not_additive']=True
        evidence['maximum_container_weight_lb']=int(fixed[1]);evidence['similar_objects_not_exhaustively_indexed']=True
        return {'item':[{uid(n):int(small[1]) for n in ('Bolt','Arrow')},
                        {uid('Javelin'):int(middle[1])},
                        {uid(n):int(long[1]) for n in ('Longbow','Shortbow','Quarterstaff','Spear')}],
                'weightless':True},evidence
    raise ValueError(('Unreviewed container identity',name))


def compare(record,expected,identities):
    actual=record.get('containerCapacity');differences=[]
    equal=('containerCapacity' not in record) if expected is None else exact(actual,expected)
    if not equal:differences.append({'field':'containerCapacity','value':actual,'source_expected':expected})
    refs=[]
    if isinstance(actual,dict):
        for compartment in actual.get('item',[]):
            for reference in compartment:
                if identities.get(reference,0)!=1:differences.append({'field':'containerCapacity.item','unresolved_or_duplicate_uid':reference})
                else:refs.append(reference)
    return {'verified_metadata':{'containerCapacity':{'value':actual,'source_expected':expected}} if equal and expected is not None else {},
            'verified_absence':expected is None and equal,'resolved_item_references':refs,'differences':differences,'passed':not differences}


def audit(a):
    identities=Counter(uid(r['name']) for file in ('items.json','items-base.json') for kind in ('item','baseitem')
                       for r in a.DATA[file].get(kind,[]) if r.get('source')=='SRD521')
    glyphs=GlyphSource(a.doc);records=[];errors=[];seen=set()
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        record=a.DATA[file][kind][review['index']];effective={**record,**record.get('inherits',{})}
        identity=(file,kind,name)
        if identity not in IDENTITIES and 'containerCapacity' not in effective:continue
        if identity in seen:errors.append({'name':name,'error':'Duplicate container projection'});continue
        seen.add(identity)
        if identity not in IDENTITIES or record['name']!=name:
            errors.append({'name':name,'error':'Unexpected container identity/kind'});continue
        try:
            text,evidence=body_text(a.SOURCES[heading],glyphs);expected,fact_evidence=facts(name,text)
            result=compare(effective,expected,identities);evidence.update(fact_evidence)
            result.update(file=file,kind=kind,name=name,source_heading=heading,source_evidence=evidence)
            records.append(result)
            if not result['passed']:errors.append({'name':name,'differences':result['differences']})
        except (ValueError,KeyError,IndexError,TypeError) as exc:errors.append({'name':name,'error':str(exc)})
    if len(records)!=19 or seen!=IDENTITIES:
        errors.append({'error':'Missing or extra container projections','missing':sorted(IDENTITIES-seen)})
    return {'records':records,'errors':errors,'passed':not errors}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('pdf','data','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if pdf_hash!=PDF_SHA256:raise ValueError('Official PDF changed')
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    result=audit(a);result.update(pdf_sha256=pdf_hash,scope=__doc__,
                                input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),
                      'verified_absences':sum(r['verified_absence'] for r in result['records']),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
