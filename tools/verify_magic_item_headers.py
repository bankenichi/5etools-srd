"""Verify magic-item categories, rarities and attunement against the SRD PDF.

This checks all printed magic-item entry headings and their retained concrete,
group and generic-variant projections. Variable rarities use freshly proven
family tables/paragraphs, never the candidate's rarity to select an answer.
Other mechanics, remaining type constraints, whole-record typography and card
layout remain separate gates.
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
from rule_table_grid import Source,PDF_SHA256
from verify_item_families import prove_models

ROOT=Path(__file__).resolve().parents[1]
RARITIES=r'Very Rare|Uncommon|Common|Rare|Legendary|Artifact'
TYPE_CODES={'Potion':'P','Ring':'RG','Rod':'RD','Scroll':'SC','Wand':'WD'}


def source_header(src,glyphs):
    lines=[]
    for line in src['lines']:
        if not all(f.startswith('Cambria-Italic') for f in line['fonts']):break
        lines.append(line)
    if not lines:return None
    chars=[]
    for line in lines:
        match=[l for l in glyphs.page(line['page'])['lines'] if l['block']==line['block'] and l['line']==line['line']]
        if len(match)!=1:raise ValueError(('Changed physical header locator',src['name']))
        chars.extend(match[0]['chars'])
    header=glyphs.text(chars)
    if any(j['basis'].startswith('UNRESOLVED') for j in header['layout_joins']):raise ValueError(('Unresolved printed header wrap',src['name']))
    if not re.match(r'^(Armor|Weapon|Wondrous Item|Potion|Ring|Rod|Scroll|Staff|Wand)(?=[ (,])',header['text']):return None
    return {**header,'heading':src['name'],'pages':sorted({l['page'] for l in lines}),'source_lines':lines}


def unique(values,context):
    values=list(values)
    if len(values)!=1:raise ValueError(('Ambiguous or absent source rarity',context,values))
    return values[0]


def expected_rarity(kind,name,heading,header,models):
    parameterized=re.findall(r'('+RARITIES+r') \(\+([123])\)',header)
    if parameterized:
        if kind=='itemGroup':return 'varies'
        bonus=re.match(r'^\+([123]) ',name)
        if not bonus:raise ValueError(('Missing concrete bonus identity',name))
        return unique((r.lower() for r,b in parameterized if b==bonus[1]),name)
    if heading=='Horn of Valhalla':
        if kind=='itemGroup':return 'varies'
        label=name.split(', ',1)[1]
        return unique((r.lower() for r,labels in re.findall(r'('+RARITIES+r') \(([^)]+)\)',header) if label in labels.split(' or ')),name)
    if 'Rarity Varies' not in header:
        return unique((m.lower() for m in re.findall(r'(?<!\w)('+RARITIES+r')(?= \(|$)',header)),name)
    if kind=='itemGroup':return 'varies'
    model=models[heading]
    if heading in ('Figurine of Wondrous Power','Ioun Stone','Feather Token'):
        label=name.split(', ',1)[1]
        values=[m[1].lower() for p in model['paragraphs'] if (m:=re.match(re.escape(label)+r' \(('+RARITIES+r')\)\.',p['text']))]
        return unique(values,name)
    table=unique(model['tables'],heading);column=table['colLabels'].index('Rarity')
    if heading in ('Belt of Giant Strength','Potion of Giant Strength'):
        label=unique(re.findall(r'of (\w+) Giant Strength$',name),name).casefold()
        rows=[r for r in table['rows'] if label in re.search(r'\(([^)]+)\)$',r[0])[1].split(' or ')]
    elif heading=='Potions of Healing':
        label={'Potion of Healing':'Potion of Healing','Potion of Greater Healing':'Potion of Healing (greater)',
          'Potion of Superior Healing':'Potion of Healing (superior)','Potion of Supreme Healing':'Potion of Healing (supreme)'}[name]
        rows=[r for r in table['rows'] if r[0]==label]
    elif heading=='Spell Scroll':
        label=unique(re.findall(r'^Spell Scroll \((Cantrip|Level [1-9])\)$',name),name).removeprefix('Level ')
        rows=[r for r in table['rows'] if r[0]==label]
    else:raise ValueError(('Unreviewed variable-rarity family',heading,name))
    return unique((r[column].lower() for r in rows),name)


def audit_record(a,record,kind,heading,header,models):
    effective={**record,**record.get('inherits',{})};name=record['name'];facts={};differences=[]
    def fact(key,expected,actual=None,provided=False,basis=None):
        if not provided:actual=effective.get(key)
        equal=actual==expected
        value={'value':effective.get(key),'expected':expected,'compared':actual,'matches':equal,'basis':basis or 'Printed magic-item category/header.'}
        if equal:facts[key]=value
        else:differences.append({'field':key,**value})
    category=re.match(r'^(Armor|Weapon|Wondrous Item|Potion|Ring|Rod|Scroll|Staff|Wand)',header['text'])[1]
    fact('rarity',expected_rarity(kind,name,heading,header['text'],models),basis='Literal single-tier header or source-specific bonus/subtype rarity association.')
    m=re.search(r'\(Requires Attunement(?: ([^()]*))?\)$',header['text'])
    wanted=(m[1] or True) if m else None
    actual=effective.get('reqAttune')
    if isinstance(actual,str):actual=a.decode(actual,effective)
    fact('reqAttune',wanted,actual,True,basis='Complete printed attunement qualifier, preserving capitalization.')
    if category=='Wondrous Item' or 'wondrous' in effective:fact('wondrous',True if category=='Wondrous Item' else None)
    if category=='Staff' or 'staff' in effective:fact('staff',True if category=='Staff' else None)
    if category in TYPE_CODES:
        # The abbreviation and source suffix are schema identifiers. Compare
        # the category meaning and require that its exact helper UID exists.
        value=effective.get('type','');code,_,source=value.partition('|')
        helpers=[r for r in a.DATA['items-base.json']['itemType'] if r['abbreviation']==code and r['source'].casefold()==source.casefold()]
        fact('type',TYPE_CODES[category],code,True,basis='Printed category mapped to an existing typed itemType helper UID.')
        if len(helpers)!=1 or helpers[0].get('name')!=category:
            differences.append({'field':'type','error':'Missing, ambiguous or incorrectly named category helper UID','value':value})
    return {'name':name,'kind':kind,'source_heading':heading,'source_category':category,'source_header':header['text'],
      'source_pages':header['pages'],'verified_metadata':facts,'differences':differences,'passed':not differences}


def audit(a,models):
    proof,errors=prove_models(a,models)
    if errors:raise ValueError(('Saved family model differs from fresh PDF',errors))
    glyphs=Source(a.doc);headers={}
    for name,src in a.SOURCES.items():
        if not src['red12'] or not 209<=src['heading_lines'][0]['page']<=254:continue
        header=source_header(src,glyphs)
        if header:headers[name]=header
    if len(headers)!=258:raise ValueError(('Official magic-item entry inventory changed',len(headers)))
    results=[];covered=set();errors=[]
    for review in a.RESULT:
        if review['kind'] not in ('item','itemGroup','magicvariant'):continue
        heading=review['source_name']
        if heading not in headers:continue
        record=a.DATA[review['file']][review['kind']][review['index']]
        try:
            result=audit_record(a,record,review['kind'],heading,headers[heading],models)
            result['file']=review['file'];results.append(result);covered.add(heading)
        except (AssertionError,ValueError,KeyError,TypeError,IndexError) as error:
            errors.append({'file':review['file'],'kind':review['kind'],'name':review['name'],'error':str(error)})
    missing=sorted(set(headers)-covered)
    if missing:errors.append({'error':'Missing printed magic-item entries','headings':missing})
    return {'source_magic_entries':len(headers),'covered_magic_entries':len(covered),'records':results,'errors':errors,
      'source_headers':headers,'family_table_inventory':{name:p['table_inventory'] for name,p in proof.items()},
      'passed':not errors and all(r['passed'] for r in results)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    model_path=ROOT/'source/item-families.json';models=json.loads(model_path.read_text(encoding='utf8'));assert models['official_pdf_sha256']==pdf_hash
    sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    result=audit(a,models['families'])
    counts=Counter(k for r in result['records'] for k in r['verified_metadata'])
    summary={'printed_magic_entries':result['source_magic_entries'],'covered_magic_entries':result['covered_magic_entries'],
      'projected_records':len(result['records']),'verified_fields':dict(counts),'records_with_differences':sum(not r['passed'] for r in result['records']),'errors':result['errors'],'passed':result['passed']}
    result.update(pdf_sha256=pdf_hash,models_sha256=hashlib.sha256(model_path.read_bytes()).hexdigest(),scope=__doc__,summary=summary,
      input_sha256={name:hashlib.sha256((a.STAGED/name).read_bytes()).hexdigest() for name in a.FILES})
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
