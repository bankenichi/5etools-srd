"""Verify literal family projections against a fresh official-PDF extraction.

Checks exact source glyphs/paragraph inventory, table row/column associations,
per-variant section choices and collective coverage. Does not certify remaining
item metadata or actual card/PDF layout.
"""
import argparse
import collections
import contextlib
import hashlib
import io
import json
from pathlib import Path
import re
import sys


def literal(lines,text):
    raw='\n'.join(line['text'].strip() for line in lines)
    raw=re.sub(r'(?<=\w)-\n(?=\w)','\ue000',raw)
    raw=' '.join(raw.split())
    return re.fullmatch(re.escape(raw).replace('\ue000','-?'),text) is not None


def row_witnesses(lines,table,siblings):
    caption=table.get('caption')
    if caption:
        start=next(i for i,l in enumerate(lines) if ' '.join(l['text'].split())==caption)+1
        end=next((i for i in range(start,len(lines)) if ' '.join(lines[i]['text'].split()) in siblings-{caption}),len(lines))
        lines=lines[start:end]
    keys=[row[0] for row in table['rows']]
    def anchor(line,key):
        text=' '.join(line['text'].split())
        return text==key or (len(text)>8 and key.startswith(text+' '))
    anchors=[l for l in lines if any(anchor(l,key) for key in keys)]
    proof=[]
    for row in table['rows']:
        found=[]
        for first in anchors:
            if not anchor(first,row[0]):continue
            x,y=first['origins'][0];page=first['page']
            right=min([l['origins'][0][0]-1 for l in anchors if l['page']==page and l['origins'][0][0]>x+15 and abs(l['origins'][0][1]-y)<.7]+[300 if x<300 else 555])
            roots=sorted([l for l in lines if l['page']==page and x-25<=l['origins'][0][0]<right and abs(l['origins'][0][1]-y)<.7],key=lambda l:l['origins'][0][0])
            if len(roots)!=len(row):continue
            next_y=min([l['origins'][0][1] for l in anchors if l['page']==page and x-25<=l['origins'][0][0]<roots[1]['origins'][0][0]-2 and l['origins'][0][1]>y+.7]+[10000])
            region=[l for l in lines if l['page']==page and x-25<=l['origins'][0][0]<right and y-.7<=l['origins'][0][1]<next_y-.7]
            cells=[]
            for i,root in enumerate(roots):
                left=root['origins'][0][0]-(25 if i==0 else 1);limit=roots[i+1]['origins'][0][0]-1 if i+1<len(roots) else right
                cell=sorted([l for l in region if left<=l['origins'][0][0]<limit],key=lambda l:(l['origins'][0][1],l['origins'][0][0]))
                cells.append(' '.join(' '.join(l['text'] for l in cell).split()))
            if cells==row:found.append({'page':page,'baseline':y,'cells':cells})
        if len(found)!=1:raise ValueError(('No unique exact printed row',caption,row,found))
        proof.append(found[0])
    header_text=' '.join(' '.join(l['text'] for l in lines).split())
    for header in table['colLabels']:
        if header not in header_text:raise ValueError(('Unprinted column header',header))
    return proof


def parts(value):
    if isinstance(value,str):return [value],[]
    if isinstance(value,list):
        prose=[];tables=[]
        for child in value:
            p,t=parts(child);prose+=p;tables+=t
        return prose,tables
    if isinstance(value,dict):
        if value.get('type')=='table':return [],[value]
        p,t=parts(value.get('entries',[]))
        if value.get('name'):p=[value['name']+'. '+p[0]]+p[1:]
        return p,t
    raise ValueError(value)


def complete_table_inventory(lines,tables):
    """Cover every printed table glyph, not just the requested row subset.

    Row witnesses separately establish the actual cell associations. Repeated
    physical headers are identified by source typography, not row content.
    These reviewed tables have no physical word-wrap hyphens in their cells;
    any future such change fails this check and requires source review.
    """
    headers=[l for l in lines if all(f=='GillSans-SemiBold' for f in l['fonts'])]
    body=[l for l in lines if l not in headers]
    source_headers={' '.join(l['text'].split()) for l in headers}
    model_headers={s for t in tables for s in t['colLabels']+([t['caption']] if t.get('caption') else [])}
    assert source_headers==model_headers,('Printed header/caption inventory differs',sorted(source_headers-model_headers),sorted(model_headers-source_headers))
    chars=lambda strings:collections.Counter(c for s in strings for c in s if not c.isspace())
    actual=chars(l['text'] for l in body)
    expected=chars(s for t in tables for row in t['rows'] for s in row)
    assert actual==expected,('Incomplete or duplicate table cell glyph inventory',dict(actual-expected),dict(expected-actual))
    return {'body_source_char_count':sum(actual.values()),'body_model_char_count':sum(expected.values()),
      'printed_header_labels':sorted(source_headers),'physical_header_lines':len(headers),
      'body_glyph_inventory_exact':True,'row_associations_verified_separately':True}


def prove_models(a,models):
    """Re-extract and prove all saved family models against the actual PDF."""
    family_proof={};errors=[]
    for name,model in models.items():
        try:
            src=a.SOURCES[name];(_, _),(_, _),body=a.split_source(src,'')
            fresh_prose=[l for l in body if not all(f.startswith('GillSans') for f in l['fonts'])]
            fresh_tables=[l for l in body if all(f.startswith('GillSans') for f in l['fonts'])]
            signature=lambda l:(l['page'],l['column'],l['block'],l['line'],l['text'])
            assert [signature(l) for p in model['paragraphs'] for l in p['source_lines']]==[signature(l) for l in fresh_prose],('Paragraph/source inventory differs',name)
            for p in model['paragraphs']:
                assert literal(p['source_lines'],p['text']),('Changed source paragraph',name,p['text'])
                assert all(not c['basis'].startswith('UNRESOLVED') for c in p.get('layout_hyphen_decisions',[])),('Unreviewed layout hyphen',name)
            header=[]
            for line in src['lines']:
                if not all(f.startswith('Cambria-Italic') for f in line['fonts']):break
                header.append(line)
            assert [signature(l) for l in header]==[signature(l) for l in model['header_source_lines']]
            assert literal(header,model['printed_header']),('Changed printed header',name)
            table_proof=[row_witnesses(fresh_tables,t,{x.get('caption') for x in model['tables'] if x.get('caption')}) for t in model['tables']]
            inventory=complete_table_inventory(fresh_tables,model['tables'])
            family_proof[name]={'paragraphs_verified':len(model['paragraphs']),'printed_header':model['printed_header'],
              'table_rows_verified':sum(len(t) for t in table_proof),'row_witnesses':table_proof,'table_inventory':inventory,
              'paragraph_coverage':set(),'row_coverage':set(),'records':[]}
        except (AssertionError,ValueError,KeyError,StopIteration) as error:errors.append({'family':name,'error':str(error)})
    return family_proof,errors


def required_paragraph_indexes(record,kind,model):
    name=model['source_heading']
    if kind=='itemEntry' and name=='Ioun Stone':return list(range(4))
    if kind not in {'itemGroup','itemEntry'} and name in {'Figurine of Wondrous Power','Ioun Stone','Feather Token'}:
        starts=[i for i,p in enumerate(model['paragraphs']) if re.match(r'^.+? \((?:Uncommon|Rare|Very Rare|Legendary)\)\.',p['text'])]
        subtype=record['name'].split(', ',1)[1]
        start=next(i for i in starts if model['paragraphs'][i]['text'].startswith(subtype+' ('))
        end=next((i for i in starts if i>start),len(model['paragraphs']))
        return list(range(starts[0]))+list(range(start,end))
    if kind not in {'itemGroup','itemEntry'} and name=='Ring of Elemental Command':
        plane=re.search(r'\((Air|Earth|Fire|Water)\)$',record['name'])[1]
        chosen=next(i for i,p in enumerate(model['paragraphs']) if p['text'].startswith(plane+'. '))
        return list(range(5))+[chosen,9]
    return list(range(len(model['paragraphs'])))


def main():
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from projection_provenance import check_family,family_tables
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--models',type=Path,default=Path(__file__).resolve().parents[1]/'source/item-families.json');parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    model_raw=args.models.read_bytes();document=json.loads(model_raw);models=document['families']
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    assert pdf_hash==document['official_pdf_sha256']=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
    # Re-extract the original PDF now. No source span, row, or header is accepted
    # just because it appears in the candidate's private provenance fields.
    sys.path.insert(0,str(Path(__file__).resolve().parent/'item_audit'))
    previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    family_proof,errors=prove_models(a,models)
    records=[];inputs={};all_entities={};structural=[]
    for filename in ['items.json','items-base.json','magicvariants.json']:
        payload=json.loads((args.data/'data'/filename).read_text(encoding='utf8'))
        for kind,items in payload.items():
            if not isinstance(items,list):continue
            for r in items:
                if not isinstance(r,dict) or not r.get('name'):continue
                source=r.get('source',r.get('inherits',{}).get('source',''))
                all_entities[(r['name'].casefold(),source.casefold())]=(kind,r)
    for filename in ['items.json','items-base.json','magicvariants.json']:
        file=args.data/'data'/filename;inputs[filename]=hashlib.sha256(file.read_bytes()).hexdigest();payload=json.loads(file.read_text(encoding='utf8'))
        for kind,items in payload.items():
            if not isinstance(items,list):continue
            for record in items:
                if not isinstance(record,dict):continue
                if '_srd521' not in record:
                    if kind=='itemGroup' and not record.get('entries') and a.source_name(record,kind) in models:structural.append((filename,record,a.source_name(record,kind)))
                    continue
                identity={'file':filename,'kind':kind,'name':record.get('name')};source=record['_srd521'];name=source['heading']
                try:
                    model=models[name];proof=family_proof[name]
                    assert a.source_name(record,kind)==a.canonical(name),('Wrong source family',identity)
                    assert source['printed_header']==model['printed_header']
                    indexes=source['paragraph_indexes'];assert indexes==sorted(set(indexes))
                    expected=required_paragraph_indexes(record,kind,model)
                    assert indexes==expected,('Missing or wrong variant paragraphs',identity,indexes,expected)
                    effective={**record,**record.get('inherits',{})};entries=effective.get('entriesTemplate',[]) if kind=='itemEntry' else effective.get('entries',[])
                    actual_prose,actual_tables=parts(entries)
                    assert actual_prose==[model['paragraphs'][i]['text'] for i in indexes],('Changed literal prose',identity)
                    assert actual_tables==family_tables(record,kind,model),('Wrong identity-selected source table projection',identity)
                    provenance=check_family(a,record,kind,model)
                    rows=[]
                    for table in actual_tables:
                        matches=[(i,t) for i,t in enumerate(model['tables']) if t.get('caption')==table.get('caption') and t['colLabels']==table['colLabels']]
                        assert len(matches)==1,('Wrong/missing source table header',identity)
                        i,t=matches[0]
                        for row in table['rows']:
                            assert row in t['rows'],('Changed source row',identity,row)
                            rows.append((i,t['rows'].index(row)))
                    assert len(actual_tables)==len(model['tables']) or (name=='Bag of Tricks' and len(actual_tables)==1) or (kind=='itemEntry' and name=='Ioun Stone' and not actual_tables)
                    if kind=='item' and name=='Bag of Tricks':assert actual_tables[0]['caption']==record['name'].split(', ')[1]+' Bag of Tricks'
                    if kind=='item' and len(actual_tables)==1 and len(actual_tables[0]['rows'])==1:
                        row=actual_tables[0]['rows'][0];identifier=record['name']
                        if name=='Dragon Scale Mail':assert row[0]==identifier.split()[0]
                        if name=='Elemental Gem':assert row[0].casefold()==identifier.split(', ')[1].casefold()
                        if name=='Carpet of Flying':assert row[1]==identifier.split(', ')[1]
                        if name=='Horn of Valhalla':assert row[1]==identifier.split(', ')[1]
                        if name=='Manual of Golems':assert row[1]==identifier.removeprefix('Manual of ').removesuffix(' Golems')+' Golem'
                        if name=='Ring of Elemental Command':assert row[0]==re.search(r'\((\w+)\)$',identifier)[1]
                        if name=='Feather Token':assert row[1].casefold()==identifier.split(', ')[1].casefold()
                    proof['paragraph_coverage'].update(indexes);proof['row_coverage'].update(rows);proof['records'].append(identity)
                    records.append({**identity,'literal_projection_verified':True,'source_pages':model['pages'],
                                    'verified_metadata':{'_srd521':provenance},
                                    'metadata_status':'Source-projection provenance verified; other metadata remains outside this body/row gate.'})
                except (AssertionError,ValueError,KeyError,StopIteration,TypeError) as error:errors.append({**identity,'error':str(error)})
    for filename,record,name in structural:
        identity={'file':filename,'kind':'itemGroup','name':record['name']}
        try:
            members=set()
            for uid in record['items']:
                key=uid.split('|');target=all_entities[(key[0].casefold(),key[1].casefold())][1]
                assert target.get('_srd521',{}).get('heading')==name,('Wrong or unverified family member',uid)
                members.add(target['name'])
            expected={r['name'] for _,r in all_entities.values() if r.get('_srd521',{}).get('heading')==name and r.get('name')!=record['name'] and 'entriesTemplate' not in r and 'items' not in r}
            assert members==expected,('Missing family membership',name,members,expected)
            records.append({**identity,'literal_projection_verified':False,'structural_delegation_verified':True,'source_family':name,'members':sorted(members),'metadata_status':'UNVERIFIED outside group membership/source coverage'})
        except (AssertionError,KeyError) as error:errors.append({**identity,'error':str(error)})
    for name,proof in family_proof.items():
        model=models[name]
        if proof['paragraph_coverage']!=set(range(len(model['paragraphs']))):errors.append({'family':name,'error':'Family paragraphs omitted across all members'})
        expected={(i,j) for i,t in enumerate(model['tables']) for j in range(len(t['rows']))}
        if proof['row_coverage']!=expected:errors.append({'family':name,'error':'Family rows omitted across all members'})
        proof['paragraph_coverage']=sorted(proof['paragraph_coverage']);proof['row_coverage']=sorted(proof['row_coverage'])
    result={'pdf_sha256':pdf_hash,'models_sha256':hashlib.sha256(model_raw).hexdigest(),'input_sha256':inputs,'scope':__doc__,'families':family_proof,'records':records,'errors':errors,'passed':not errors}
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'families':len(family_proof),'literal_projection_records':sum(r['literal_projection_verified'] for r in records),'structural_family_groups':sum(r.get('structural_delegation_verified',False) for r in records),'paragraphs':sum(f['paragraphs_verified'] for f in family_proof.values()),'table_rows':sum(f['table_rows_verified'] for f in family_proof.values()),'errors':errors,'passed':not errors},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
