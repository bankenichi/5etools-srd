"""Verify fixed magic-item subtypes and normal Quarterstaff use of staffs.

Printed magic-item headers choose fixed base equipment; printed staff/focus
rules choose Quarterstaff defaults. Fresh source table rows supply category,
damage, Versatile and mastery facts. This does not certify extra bonuses,
special forms, conditional effects, generic-variant predicates or other fields.
The general staff rule explicitly says NONMAGICAL; this audit grants no magic
weapon or unconditional special-property claim.
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
from source_identity import SOURCE_ID
from verify_equipment_categories import source_categories,TYPE_NAMES
from verify_magic_item_headers import source_header

ROOT=Path(__file__).resolve().parents[1]
STAFF_RULE='Unless its description notes otherwise, a staff can be used as a nonmagical Quarterstaff and an Arcane Focus.'


def source_facts(a):
    categories=source_categories(a.doc);source=CitationSource(a.doc);glyphs=GlyphSource(a.doc)
    headers={}
    for name,src in a.SOURCES.items():
        if not src['red12'] or not 209<=src['heading_lines'][0]['page']<=254:continue
        header=source_header(src,glyphs)
        if header:headers[name]=header
    if len(headers)!=258:raise ValueError('Printed magic-item heading inventory changed')
    fixed={}
    for name,header in headers.items():
        match=re.match(r'^(Armor|Weapon) \(([^)]+)\),',header['text'])
        if match and match[2] in categories:
            base=categories[match[2]]
            if ('Weapons' if match[1]=='Weapon' else 'Armor')!=base['table']:
                raise ValueError(('Magic header/base category disagreement',name))
            fixed[name]={'base_name':match[2],'header':header,'base':base}
    if len(fixed)!=21:raise ValueError(('Fixed source subtype inventory changed',len(fixed)))
    staff_headers={name:header for name,header in headers.items() if header['text'].startswith('Staff,')}
    if len(staff_headers)!=12:raise ValueError(('Printed Staff inventory changed',len(staff_headers)))
    lines=source.pages[205]
    starts=[i for i,line in enumerate(lines) if line['text']=='Unless its description notes otherwise, a staff can']
    if len(starts)!=1:raise ValueError('Missing or ambiguous staff-default source clause')
    rule_lines=lines[starts[0]:starts[0]+3]
    if ' '.join(l['text'] for l in rule_lines)!=STAFF_RULE:raise ValueError('Staff-default source clause changed')
    quarterstaff=categories['Quarterstaff'];cells=quarterstaff['source_cells']
    damage=re.fullmatch(r'(\d+d\d+) (Bludgeoning)',cells[1])
    versatile=re.fullmatch(r'Versatile \((\d+d\d+)\)',cells[2])
    if not damage or not versatile or cells[3]!='Topple':raise ValueError('Unreviewed Quarterstaff source stats')
    defaults={'type':quarterstaff['facts']['type'],'weaponCategory':quarterstaff['facts']['weaponCategory'],
              'dmg1':damage[1],'dmgType':'B','dmg2':versatile[1],'property':['V'],'mastery':['Topple']}
    focuses={}
    for name,caption,label in [('Staff','Arcane Focuses','Staff (also a Quarterstaff)'),
                               ('Wooden Staff','Druidic Focuses','Wooden staff (also a Quarterstaff)')]:
        result=source.table_row(caption,label)
        if result['status']!='LOCATED':raise ValueError(('Missing Quarterstaff focus row',name))
        focuses[name]=result
    return {'fixed':fixed,'staff_headers':staff_headers,'staff_rule':STAFF_RULE,'staff_rule_lines':rule_lines,
            'quarterstaff':quarterstaff,'defaults':defaults,'focuses':focuses}


def uid_resolves(data,kind,packed,identifier,meaning=None,allow_implicit_source=False):
    if not isinstance(packed,str):return False
    parts=packed.split('|')
    if len(parts) not in (1,2) or parts[0]!=identifier:return False
    if len(parts)==1 and not allow_implicit_source:return False
    # The existing 5etools renderer installs a default-source compatibility
    # alias for a non-PHB property (render.js _addProperty). An implicit UID
    # is safe here only when that abbreviation has one unambiguous helper.
    if len(parts)==1 and sum(r.get('abbreviation')==identifier for r in data['items-base.json'][kind])!=1:return False
    source=parts[1] if len(parts)==2 else SOURCE_ID
    if source!=SOURCE_ID:return False
    key='abbreviation' if kind in {'itemType','itemProperty'} else 'name'
    found=[r for r in data['items-base.json'][kind] if r.get(key)==identifier and r['source']==source]
    if len(found)!=1:return False
    if meaning is None:return True
    if kind=='itemProperty':
        names=[e['name'] for e in found[0].get('entries',[]) if isinstance(e,dict) and 'name' in e]
        return names==[meaning] and found[0].get('name',meaning)==meaning
    return found[0].get('name')==meaning


def check_record(data,record,expected):
    facts={};differences=[]
    for key,wanted in expected.items():
        actual=record.get(key);equal=actual==wanted
        if key=='type':
            equal=uid_resolves(data,'itemType',actual,wanted,TYPE_NAMES[wanted])
        elif key=='baseItem':
            # Structural baseItem UIDs use case-insensitive item names.
            parts=actual.split('|') if isinstance(actual,str) else []
            matches=[r for r in data['items-base.json']['baseitem'] if r['name']==wanted and r['source']==SOURCE_ID]
            equal=len(parts)==2 and parts[0].casefold()==wanted.casefold() and parts[1]==SOURCE_ID and len(matches)==1
        elif key in {'property','mastery'}:
            kind='itemProperty' if key=='property' else 'itemMastery'
            equal=isinstance(actual,list) and len(actual)==len(wanted)
            if equal:
                equal=all(uid_resolves(data,kind,packed,code,'Versatile' if key=='property' and code=='V' else None,
                                      allow_implicit_source=key=='property') for packed,code in zip(actual,wanted,strict=True))
        if equal:facts[key]={'value':actual,'source_expected':wanted,'matches':True}
        else:differences.append({'field':key,'value':actual,'source_expected':wanted})
    return facts,differences


def audit(a,source):
    records=[];errors=[];covered=set();staff_covered=set();focus_covered=set();seen=set();counts=Counter()
    for review in a.RESULT:
        file,kind,name,heading=review['file'],review['kind'],review['name'],review['source_name']
        if kind not in {'item','itemGroup','baseitem'}:continue
        record=a.DATA[file][kind][review['index']];expected=None;evidence=None;scope=None
        if kind in {'item','itemGroup'} and heading in source['fixed']:
            binding=source['fixed'][heading];base=binding['base']
            expected={'baseItem':binding['base_name'],'type':base['facts']['type']}
            if 'weaponCategory' in base['facts']:expected['weaponCategory']=base['facts']['weaponCategory']
            evidence={'source_header':binding['header']['text'],'header_pages':binding['header']['pages'],
                      'base_table':base['table'],'base_category':base['source_category'],'base_cells':base['source_cells'],
                      'base_page':base['source_page']}
            scope='fixed_concrete_base_binding';covered.add(heading)
        elif kind=='item' and heading in source['staff_headers']:
            expected=source['defaults']
            evidence={'source_header':source['staff_headers'][heading]['text'],
                      'header_pages':source['staff_headers'][heading]['pages'],'staff_default_clause':source['staff_rule'],
                      'staff_default_page':205,'base_cells':source['quarterstaff']['source_cells'],'base_page':91,
                      'scope':'Normal Quarterstaff weapon use only. Special forms and printed magic/bonus overrides are not certified.'}
            scope='staff_normal_quarterstaff_use'
            staff_covered.add(heading)
        elif kind=='baseitem' and name in source['focuses']:
            expected={k:v for k,v in source['defaults'].items() if k!='type'}
            evidence={'focus_row':source['focuses'][name],'base_cells':source['quarterstaff']['source_cells'],'base_page':91}
            scope='focus_also_quarterstaff'
            focus_covered.add(name)
        if expected is None:continue
        identity=(file,kind,name)
        if identity in seen:
            errors.append({'file':file,'kind':kind,'name':name,'error':'Duplicate binding projection identity'});continue
        seen.add(identity)
        if record['name']!=name:
            errors.append({'file':file,'kind':kind,'name':name,'error':'Projection identity differs from indexed record'});continue
        facts,differences=check_record(a.DATA,record,expected)
        result={'file':file,'kind':kind,'name':name,'source_heading':heading,'scope':scope,'source_evidence':evidence,
                'verified_metadata':facts,'differences':differences,'passed':not differences}
        records.append(result);counts[scope]+=1
        if differences:errors.append({'file':file,'kind':kind,'name':name,'differences':differences})
    # The bonus Shield family uses generic predicates, not concrete baseItem
    # fields. Its three variants are deliberately outside this component.
    wanted=set(source['fixed'])-{'Shield, +1, +2, or +3'}
    if covered!=wanted:errors.append({'error':'Missing fixed concrete source subtypes','headings':sorted(wanted-covered),'extra':sorted(covered-wanted)})
    if staff_covered!=set(source['staff_headers']):errors.append({'error':'Missing printed Staff entries','headings':sorted(set(source['staff_headers'])-staff_covered)})
    if focus_covered!=set(source['focuses']):errors.append({'error':'Missing printed Quarterstaff focus rows','names':sorted(set(source['focuses'])-focus_covered)})
    if dict(counts)!={'fixed_concrete_base_binding':30,'staff_normal_quarterstaff_use':12,'focus_also_quarterstaff':2}:
        errors.append({'error':'Missing or duplicate binding projections','counts':dict(counts)})
    return {'records':records,'counts':dict(counts),'source_coverage':{'fixed_headings':sorted(covered),'staff_headings':sorted(staff_covered),'focus_names':sorted(focus_covered)},'errors':errors,'passed':not errors}


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
    print(json.dumps({'records':len(result['records']),'counts':result['counts'],'verified_fields':dict(Counter(k for r in result['records'] for k in r['verified_metadata'])),
                      'errors':result['errors'],'passed':result['passed']},ensure_ascii=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
