"""Verify declared consumable facts and enhanced-ammo prices against the PDF.

Upstream CNS flags select the audit inventory only. A printed category rule or
reviewed finite-use source clause proves each boolean. The specific ammunition
equivalence and physical rarity-table rows prove its three prices. This does not
certify other item prices, omissions, typography, or consumer presentation.
"""
import argparse
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys


def normalize(value):
    value=re.sub(r'(?<=\w)-\n(?=\w)','',value)
    return ' '.join(value.translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':''})).split())


def rarity_rows(pdf,expected):
    lines=[]
    for block in pdf[205].get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            x,y=line['spans'][0]['origin'];text=''.join(s['text'] for s in line['spans']).strip()
            if 63<=x<291 and 118<y<162:lines.append({'x':x,'y':y,'text':text})
    proof={}
    for rarity,value in expected.items():
        anchors=[l for l in lines if l['text'].casefold()==rarity]
        assert len(anchors)==1,('Missing/ambiguous printed rarity',rarity)
        anchor=anchors[0];right=180 if anchor['x']<180 else 300
        row=sorted([l for l in lines if anchor['x']-.5<=l['x']<right and abs(l['y']-anchor['y'])<.3],key=lambda l:l['x'])
        value_text=value if isinstance(value,str) else f'{value:,} GP'
        assert [l['text'] for l in row]==[anchor['text'],value_text],('Changed printed rarity/value row',rarity,row)
        proof[rarity]={'page':206,'baseline':anchor['y'],'cells':[l['text'] for l in row]}
    assert len(lines)==12,'Unaccounted rarity-table cells'
    return proof


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--models',type=Path,default=Path(__file__).resolve().parents[1]/'source/item-consumables.json')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    raw=args.models.read_bytes();document=json.loads(raw);pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    assert pdf_hash==document['official_pdf_sha256']=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
    sys.path.insert(0,str(Path(__file__).resolve().parent/'item_audit'))
    previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    errors=[];records=[];inputs={};entities={};flagged=set();all_facts=set()
    with a.fitz.open(args.pdf) as pdf:
        prices=rarity_rows(pdf,document['rarity_values_gp'])
        category_rules={page:normalize(pdf[page-1].get_text()) for page in [204,205,206]}
    for filename in ['items.json','magicvariants.json']:
        file=args.data/'data'/filename;inputs[filename]=hashlib.sha256(file.read_bytes()).hexdigest()
        for kind,items in json.loads(file.read_text(encoding='utf8')).items():
            if not isinstance(items,list):continue
            for record in items:
                if not isinstance(record,dict) or not record.get('name'):continue
                key=(filename,kind,record['name']);assert key not in entities,('Ambiguous entity identity',key)
                entities[key]=record;effective={**record,**record.get('inherits',{})}
                if 'CNS' in effective.get('miscTags',[]) and effective.get('rarity') not in ['none',None]:flagged.add(key)
                if 'consumable' in effective:all_facts.add(key)
    expected={(m['file'],m['kind'],m['name']) for m in document['records']}
    # Final data omits redundant upstream query indexes. If a pre-pruning
    # candidate still carries CNS tags, also check that frozen seed inventory.
    # Printed rules, not those tags, continue to prove every actual boolean.
    if flagged and expected!=flagged:errors.append({'error':'Declared source classification does not cover exactly the retained upstream flagged inventory','missing':sorted(flagged-expected),'extra':sorted(expected-flagged)})
    if all_facts!=expected:errors.append({'error':'Missing or undeclared consumable field','missing':sorted(expected-all_facts),'extra':sorted(all_facts-expected)})
    for model in document['records']:
        identity={key:model[key] for key in ['file','kind','name']}
        try:
            record=entities[(model['file'],model['kind'],model['name'])];evidence=model['evidence'];heading=evidence['source_heading']
            assert a.source_name(record,model['kind'])==heading,('Wrong source association',identity,heading)
            src=a.SOURCES[heading];meta,_,_=a.split_source(src,'');meta=meta[0]
            text=normalize('\n'.join(l['text'] for l in src['lines']))
            if evidence['method']=='printed_category':
                category=evidence['printed_category'];assert category in ['Potion','Scroll']
                assert meta.startswith(category+',') or meta.startswith(category+' '),('Printed category differs',identity,meta)
                assert evidence['general_rule_page']==(204 if category=='Potion' else 205)
                quote='Potions are consumable items.' if category=='Potion' else 'Scrolls are consumable items.'
                assert evidence['general_rule_quote']==quote and quote in category_rules[evidence['general_rule_page']]
            else:
                assert evidence['method']=='finite_source_use'
                for quote in evidence['normalized_source_quotes']:assert normalize(quote) in text,('Missing source use clause',identity,quote)
                if evidence.get('required_quote_occurrences'):
                    assert text.count(normalize(evidence['normalized_source_quotes'][0]))==evidence['required_quote_occurrences']
            target=record['inherits'] if model['target']=='inherits' else record
            assert model['target']==('inherits' if model['kind']=='magicvariant' else 'record')
            assert model['facts']['consumable'] is True and target.get('consumable') is True,('Wrong consumable fact',identity)
            facts={'consumable':True}
            if 'value' in model['facts']:
                price=evidence['price_derivation'];rarity=target['rarity'];bonus=re.fullmatch(r'\+([123]) Ammunition',record['name'])
                assert bonus and heading=='Ammunition, +1, +2, or +3'
                source_rarity={'1':'uncommon','2':'rare','3':'very rare'}[bonus[1]]
                assert rarity==price['rarity']==source_rarity
                assert re.search(r'(?i)'+re.escape(rarity)+r' \(\+'+bonus[1]+r'\)',meta)
                assert price['ammunition_quote']=='Ten pieces of this ammunition are equivalent in value to a potion of the same rarity.'
                assert price['ammunition_quote'] in text
                assert price['consumable_price_quote']=='Halve the value for a consumable item other than a Spell Scroll.'
                assert price['consumable_price_quote'] in category_rules[206]
                assert price['potion_value_fraction']==[1,2] and price['pieces_equivalent_to_one_potion']==10
                gp=document['rarity_values_gp'][rarity];assert price['rarity_value_gp']==gp
                cp=gp*100//2//10
                assert target.get('value')==model['facts']['value']==cp,('Wrong specific ammunition value',identity,cp)
                facts['value']=cp
            records.append({**identity,'facts':facts,'source_heading':heading,'source_pages':evidence['source_pages'],'metadata_facts_verified':True})
        except (AssertionError,ValueError,KeyError,TypeError) as error:errors.append({**identity,'error':str(error)})
    result={'pdf_sha256':pdf_hash,'models_sha256':hashlib.sha256(raw).hexdigest(),'input_sha256':inputs,
      'scope':__doc__,'rarity_rows':prices,'records':records,'errors':errors,'passed':not errors}
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'consumable_facts':len(records),'specific_ammunition_values':sum('value' in r['facts'] for r in records),'errors':errors,'passed':not errors},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
