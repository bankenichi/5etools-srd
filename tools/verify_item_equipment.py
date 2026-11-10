"""Re-extract official PDF evidence for the declared equipment projections.

Verifies literal source paragraphs and selected table rows, source headings,
explicit projections and their exact candidate bodies. This is not a certificate
for unreviewed item metadata, all SRD omissions, or rendered/PDF layout.
"""
import argparse
import bisect
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
from verify_item_families import literal,row_witnesses


def expected_entries(model,document):
    entries=[]
    for section in model['sections']:
        unit=document['units'][section['unit']]
        texts=[p['text'] for p in unit['paragraphs']]
        if 'sentences' in section:
            assert len(texts)==1
            sentences=texts[0].split('. ')
            texts=[' '.join(sentences[i]+('' if sentences[i].endswith('.') else '.') for i in section['sentences'])]
        if section.get('remove_prefix'):
            assert texts[0].startswith(section['remove_prefix'])
            texts[0]=texts[0].removeprefix(section['remove_prefix'])
        if section.get('heading'):
            heading=' '.join(l['text'].strip() for l in unit['heading_source_lines'])
            entries.append({'type':'entries','name':heading,'entries':texts})
        else:entries.extend(texts)
    for key,indexes in model.get('table_rows',{}).items():
        table=dict(document['tables'][key]['table'])
        assert indexes==sorted(set(indexes)) and indexes
        table['rows']=[table['rows'][i] for i in indexes];entries.append(table)
    if model.get('cell_projection'):
        cell=document['cell_projections'][model['cell_projection']];entries.append(cell['row'][cell['cell']])
    return entries


def main():
    from projection_provenance import check_equipment
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--models',type=Path,default=Path(__file__).resolve().parents[1]/'source/item-equipment.json')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    model_raw=args.models.read_bytes();document=json.loads(model_raw)
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    assert pdf_hash==document['official_pdf_sha256']=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
    sys.path.insert(0,str(Path(__file__).resolve().parent/'item_audit'))
    previous=sys.argv
    try:
        sys.argv=['review_items.py','--pdf',str(args.pdf),'--data',str(args.data),'--out',str(args.out/'pdf-extraction')]
        with contextlib.redirect_stdout(io.StringIO()):import review_items as a
    finally:sys.argv=previous
    signature=lambda l:(l['page'],l['column'],l['block'],l['line'],l['text'])
    errors=[];units={};tables={};cells={};records=[];inputs={}
    for name,unit in document['units'].items():
        try:
            fresh=a.SOURCES[name]
            assert [signature(l) for l in unit['heading_source_lines']]==[signature(l) for l in fresh['heading_lines']]
            (_, _),(_, _),body=a.split_source(fresh,'')
            lines=[l for l in body if not all(f.startswith('GillSans') for f in l['fonts'])]
            groups=[]
            for line in lines:
                if not groups or line['text'].startswith('\t'):groups.append([])
                groups[-1].append(line)
            indexes=unit['paragraph_indexes'];assert indexes==sorted(set(indexes))
            assert len(indexes)==len(unit['paragraphs'])
            for index,paragraph in zip(indexes,unit['paragraphs']):
                assert [signature(l) for l in paragraph['source_lines']]==[signature(l) for l in groups[index]],('Source paragraph inventory differs',name,index)
                assert literal(paragraph['source_lines'],paragraph['text']),('Changed source glyphs',name,index)
                assert all(not d['basis'].startswith('UNRESOLVED') for d in paragraph.get('layout_hyphen_decisions',[]))
            assert indexes==list(range(len(groups))) or (name=='Mysterious Deck' and indexes==[20]),('Unreviewed source selection',name,indexes)
            units[name]={'paragraphs_verified':len(indexes),'source_pages':sorted({l['page'] for p in unit['paragraphs'] for l in p['source_lines']})}
        except (AssertionError,ValueError,KeyError,IndexError) as error:errors.append({'source':name,'error':str(error)})
    for key,model in document['tables'].items():
        try:
            lines=[l for l in a.SOURCES[model['source']]['lines'] if all(f.startswith('GillSans') for f in l['fonts'])]
            tables[key]=row_witnesses(lines,model['table'],{model['table'].get('caption')})
        except (AssertionError,ValueError,KeyError,StopIteration) as error:errors.append({'table':key,'error':str(error)})
    for key,model in document['cell_projections'].items():
        try:
            x0,y0,x1,y1=model['bounds'];breaks=model['column_breaks']
            lines=[l for l in a.LINES if l['page']==model['page'] and x0<=l['origins'][0][0]<=x1 and y0<=l['origins'][0][1]<=y1 and all(f.startswith('GillSans') for f in l['fonts']) and not l['red']]
            columns=[[] for _ in range(len(breaks)+1)]
            for line in sorted(lines,key=lambda l:(l['origins'][0][1],l['origins'][0][0])):
                columns[bisect.bisect_right(breaks,line['origins'][0][0])].append(line['text'])
            row=[' '.join(' '.join(c).split()) for c in columns]
            assert row==model['row'],('Wrong printed row',key,row)
            cells[key]={'page':model['page'],'row':row,'projected_cell':model['cell']}
        except (AssertionError,ValueError,KeyError,IndexError) as error:errors.append({'cell_projection':key,'error':str(error)})
    for model in document['records']:
        identity={key:model[key] for key in ['file','kind','name']}
        try:
            file=args.data/'data'/model['file'];inputs[model['file']]=hashlib.sha256(file.read_bytes()).hexdigest()
            payload=json.loads(file.read_text(encoding='utf8'))
            matches=[r for r in payload[model['kind']] if r['name']==model['name']]
            assert len(matches)==1,('Missing or ambiguous candidate identity',identity)
            candidate=matches[0];assert candidate['entries']==expected_entries(model,document),('Changed projected entries',identity)
            assert candidate['_srd521Equipment']['official_pdf_sha256']==pdf_hash
            digest=hashlib.sha256(json.dumps(model,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            assert candidate['_srd521Equipment']['projection_sha256']==digest
            provenance=check_equipment(candidate,model)
            assert all(s['unit'] in units for s in model['sections'])
            assert all(key in tables for key in model.get('table_rows',{}))
            assert not model.get('cell_projection') or model['cell_projection'] in cells
            records.append({**identity,'literal_projection_verified':True,'verified_metadata':{'_srd521Equipment':provenance},
                            'metadata_status':'Source-projection provenance verified; other metadata remains outside this body/row gate.'})
        except (AssertionError,ValueError,KeyError,IndexError) as error:errors.append({**identity,'error':str(error)})
    expected={(m['file'],m['kind'],m['name']) for m in document['records']}
    for filename in inputs:
        for kind,items in json.loads((args.data/'data'/filename).read_text(encoding='utf8')).items():
            if not isinstance(items,list):continue
            for r in items:
                if isinstance(r,dict) and '_srd521Equipment' in r and (filename,kind,r['name']) not in expected:
                    errors.append({'file':filename,'kind':kind,'name':r['name'],'error':'Undeclared equipment projection'})
    result={'pdf_sha256':pdf_hash,'models_sha256':hashlib.sha256(model_raw).hexdigest(),'input_sha256':inputs,
      'scope':__doc__,'units':units,'tables':tables,'cell_projections':cells,'records':records,'errors':errors,'passed':not errors}
    (args.out/'verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'units':len(units),'paragraphs':sum(u['paragraphs_verified'] for u in units.values()),'table_rows':sum(len(t) for t in tables.values())+len(cells),'literal_projection_records':len(records),'errors':errors,'passed':not errors},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
