"""Verify the six remaining weapon-property/range/damage override fields.

Fresh physical magic-item clauses supply overrides; the printed weapon table
supplies inherited Versatile. Quarterstaff-form and active-blade conditions
remain explicit. Charge-limited throwing and optional per-hit damage choices
are recorded separately and are not promoted to universal metadata facts.
No source data or app rendering code is changed by this audit.
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
from rule_table_grid import Source as GlyphSource,PDF_SHA256,REVIEWED_JOINS
from verify_equipment_categories import source_categories
from verify_item_base_bindings import uid_resolves
from verify_magic_item_headers import source_header

ROOT=Path(__file__).resolve().parents[1]
PROPERTY_NAMES={'F':'Finesse','T':'Thrown','V':'Versatile'}
SOURCE_HEADINGS={'Dwarven Thrower','Energy Bow','Hammer of Thunderbolts','Javelin of Lightning','Quarterstaff of the Acrobat','Sun Blade'}
TARGET_FIELDS={'Dwarven Thrower':{'property','range'},'Quarterstaff of the Acrobat':{'property','range'},'Sun Blade':{'property','dmgType'}}


def body_text(src,glyphs):
    lines=[];phase='header'
    for line in src['lines']:
        if phase=='header' and all(f.startswith('Cambria-Italic') for f in line['fonts']):continue
        phase='body'
        if all(f.startswith('GillSans') for f in line['fonts']):continue
        matches=[l for l in glyphs.page(line['page'])['lines'] if l['block']==line['block'] and l['line']==line['line']]
        if len(matches)!=1:raise ValueError(('Physical source line changed',src['name']))
        lines.append({'page':line['page'],'text':glyphs.text(matches[0]['chars'])['text'],
                      'source_char_ids':[c['id'] for c in matches[0]['chars']]})
    raw='\n'.join(l['text'] for l in lines);joins=[]
    def hyphen(match):
        joined=match[1]+match[2];compound=match[1]+'-'+match[2]
        choices=[word for word in (joined,compound) if word.casefold() in glyphs.words]
        if match[0] in REVIEWED_JOINS:chosen=REVIEWED_JOINS[match[0]];basis='Reviewed physical source split.'
        elif len(choices)==1:chosen=choices[0];basis='Unbroken spelling elsewhere in official PDF.'
        else:chosen=compound;basis='Unresolved source line split retained; not a certified whole-body transcription.'
        joins.append({'printed':match[0],'chosen':chosen,'basis':basis});return chosen
    text=re.sub(r'(\w+)-\n(\w+)',hyphen,raw).replace('/\n','/')
    return ' '.join(text.split()),{'source_lines':lines,'layout_joins':joins,'pages':sorted({l['page'] for l in lines})}


def source_facts(a):
    glyphs=GlyphSource(a.doc);categories=source_categories(a.doc);headers={};found={}
    for name,src in a.SOURCES.items():
        if not src['red12'] or not 209<=src['heading_lines'][0]['page']<=254:continue
        header=source_header(src,glyphs)
        if not header:continue
        headers[name]=header
        text,evidence=body_text(src,glyphs)
        if re.search(r'(?:Thrown|Finesse) property|normal range of|instead of (?:Slashing|Piercing|Bludgeoning) damage',text):
            found[name]={'text':text,'source_evidence':evidence,'header':header}
    if len(headers)!=258 or set(found)!=SOURCE_HEADINGS:
        raise ValueError(('Printed override inventory changed',len(headers),sorted(found)))
    targets={};conditional={}
    for name,source in found.items():
        text=source['text']
        if name=='Energy Bow':
            clause=re.search(r'An arrow produced by this weapon deals (\w+) damage instead of (\w+) damage on a hit, and it disappears after it hits or misses its target\.',text)
            if not clause:raise ValueError('Missing produced-arrow damage restriction')
            conditional[name]={**source,'condition_clause':clause[0],'scope':'Produced energy arrows only; no universal bow/ammunition damage metadata certified.'};continue
        if name=='Hammer of Thunderbolts':
            clause=re.search(r'You can expend (\d+) charge and make a ranged attack with the weapon, hurling it as if it had the Thrown property with a normal range of (\d+) feet and a long range of (\d+) feet\.',text)
            if not clause:raise ValueError('Missing charge-limited throwing clause')
            conditional[name]={**source,'condition_clause':clause[0],'scope':'Per-attack charge expenditure; no universal property/range metadata certified.'};continue
        if name=='Javelin of Lightning':
            clause=re.search(r'Each time you make an attack roll with this magic weapon and hit, you can have it deal (\w+) damage instead of (\w+) damage\.',text)
            if not clause:raise ValueError('Missing optional per-hit damage choice')
            conditional[name]={**source,'condition_clause':clause[0],'scope':'Optional per-hit replacement; no universal damage-type override certified.'};continue
        base_match=re.match(r'^Weapon \(([^)]+)\),',source['header']['text'])
        if not base_match or base_match[1] not in categories:raise ValueError(('Missing printed fixed base',name))
        base=categories[base_match[1]]
        if not re.fullmatch(r'Versatile \(\d+d\d+\)',base['source_cells'][2]):raise ValueError(('Unreviewed base properties',name,base['source_cells']))
        expected={'property':['V']};clauses={};scope='Normal weapon use.'
        thrown=re.search(r'(?:It|This weapon) has the Thrown property with a normal range of (\d+) feet and a long range of (\d+) feet\.',text)
        if thrown:
            expected['property']=['T','V'];expected['range']=thrown[1]+'/'+thrown[2]
            clauses['property']=clauses['range']=thrown[0]
            if name=='Quarterstaff of the Acrobat':
                condition='Ranged Weapon (Quarterstaff Form Only).'
                if condition+' '+thrown[0] not in text:raise ValueError('Lost Quarterstaff-form restriction')
                scope=condition;clauses['property']=clauses['range']=condition+' '+thrown[0]
        if name=='Sun Blade':
            condition='While the blade exists, this magic weapon functions as a Longsword with the Finesse property.'
            clause=re.search(r'which deals (\w+) damage instead of (\w+) damage\.',text)
            if condition not in text or not clause or clause.groups()!=('Radiant','Slashing'):
                raise ValueError('Active-blade replacement clause changed')
            if not base['source_cells'][1].endswith(' Slashing'):raise ValueError('Source base damage no longer matches replacement')
            expected={'property':['F','V'],'dmgType':'R'}
            clauses={'property':condition,'dmgType':condition+' '+clause[0]}
            scope='While the blade exists; inherited Longsword properties and printed Radiant replacement.'
        if set(expected)!=TARGET_FIELDS[name]:raise ValueError(('Unreviewed override field inventory',name,expected))
        targets[name]={**source,'base_name':base_match[1],'base_source':base,'expected':expected,'clauses':clauses,'scope':scope}
    if set(targets)!=set(TARGET_FIELDS):raise ValueError('Incomplete source override targets')
    return {'source_header_count':len(headers),'override_headings':sorted(found),'targets':targets,'conditional_only':conditional}


def compare(data,record,source):
    verified={};differences=[]
    for field,expected in source['expected'].items():
        actual=record.get(field);equal=actual==expected
        if field=='property':
            equal=isinstance(actual,list) and len(actual)==len(expected)
            if equal:
                codes=[v.split('|')[0] if isinstance(v,str) else None for v in actual]
                equal=Counter(codes)==Counter(expected) and all(uid_resolves(data,'itemProperty',v,code,PROPERTY_NAMES[code],allow_implicit_source=True) for v,code in zip(actual,codes,strict=True))
        if equal:
            verified[field]={'value':actual,'source_expected':expected,'source_clause':source['clauses'][field],
                             'scope':source['scope'],'base_property_cells':source['base_source']['source_cells']}
        else:differences.append({'field':field,'value':actual,'source_expected':expected,'scope':source['scope']})
    return {'verified_metadata':verified,'differences':differences,'passed':not differences}


def audit(a,source):
    records=[];errors=[];seen=set()
    for review in a.RESULT:
        name=review['name']
        if name not in source['targets'] or review['kind']!='item':continue
        identity=(review['file'],review['kind'],name)
        if review['file']!='items.json':errors.append({'name':name,'error':'Unexpected override projection location'});continue
        if identity in seen:errors.append({'name':name,'error':'Duplicate override projection'});continue
        seen.add(identity)
        record=a.DATA[review['file']][review['kind']][review['index']]
        if record['name']!=name:errors.append({'name':name,'error':'Indexed identity mismatch'});continue
        result=compare(a.DATA,record,source['targets'][name])
        result.update(file=review['file'],kind=review['kind'],name=name,source_heading=name,
                      source_evidence={k:v for k,v in source['targets'][name].items() if k not in {'expected','clauses'}})
        records.append(result)
        if not result['passed']:errors.append({'name':name,'differences':result['differences']})
    if {name for _,_,name in seen}!=set(source['targets']) or len(records)!=3:
        errors.append({'error':'Missing or duplicate weapon override inventory'})
    return {'records':records,'errors':errors,'source_header_count':source['source_header_count'],
            'source_override_headings':source['override_headings'],'conditional_only':source['conditional_only'],'passed':not errors}


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
    source=source_facts(a);result=audit(a,source)
    result.update(pdf_sha256=pdf_hash,input_sha256={fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES},scope=__doc__)
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
