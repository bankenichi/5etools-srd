"""Verify retained rule-table content against fresh, independent PDF cell grids.

Requires literal captions, labels, string cells and footnotes, complete ordered
rows/colspans, lossless typed-roll mappings, and truthful SRD5.2.1 source/page
metadata. CSS column classes are presentation metadata, not source rules. This
does not certify other records, global SRD completeness, card layout or PDFs.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

import fitz

sys.path.insert(0,str(Path(__file__).resolve().parent))
from locate_rule_tables import locate
from rule_table_grid import Source,PDF_SHA256

SOURCE_ID='SRD521'
ALLOWED_FIELDS={'name','caption','source','page','srd52','colLabels','colLabelRows','colStyles','rows','footnotes'}


def inventory_errors(tables):
    # Only the reviewed caption inventory is taken from the saved source model.
    # All rows, headers and notes are re-extracted from the PDF below.
    model=json.loads((Path(__file__).resolve().parents[1]/'source/rule-tables.json').read_text(encoding='utf8'))
    assert model['official_pdf_sha256']==PDF_SHA256
    expected=Counter(t['caption'] for t in model['tables'])
    assert len(expected)==59 and all(n==1 for n in expected.values())
    actual=Counter(t.get('caption') for t in tables)
    errors=[]
    if actual!=expected:
        errors.append({'error':'Printed table inventory differs','missing':list((expected-actual).elements()),'extra':list((actual-expected).elements())})
    names=Counter(t.get('name') for t in tables)
    if any(n!=1 for n in names.values()):errors.append({'error':'Duplicate table identities'})
    return errors


def metadata_errors(table):
    errors=[]
    if table.get('srd52') is not True:errors.append('Invalid SRD selection marker')
    for i,row in enumerate(table.get('colLabelRows',[])):
        for j,cell in enumerate(row):
            if not isinstance(cell,dict):continue
            keys=set(cell)
            valid=keys in ({'type','width','entry'},{'type','width','entry','style'})
            valid=valid and cell.get('type')=='cellHeader' and type(cell.get('width')) is int
            valid=valid and ('style' not in cell or cell['style']=='th-skewer')
            if not valid:errors.append(f'Unsupported header metadata: {i}/{j}')
    for i,row in enumerate(table['rows']):
        if isinstance(row,dict) and (set(row)!={'type','style','row'} or row.get('type')!='row' or row.get('style')!='row-indent-first'):
            errors.append(f'Unsupported row metadata: {i}')
        for j,cell in enumerate(cells_of(row)):
            if not isinstance(cell,dict):continue
            if 'roll' in cell:
                roll=cell['roll'];keys=set(roll)
                valid=keys in ({'exact'},{'exact','pad'},{'min','max'},{'min','max','pad'})
                valid=valid and all(type(v) is int for k,v in roll.items() if k!='pad') and ('pad' not in roll or type(roll['pad']) is bool)
                valid=valid and set(cell)=={'type','roll'} and cell.get('type')=='cell'
            else:valid=set(cell)=={'type','width','entry'} and cell.get('type')=='cell' and type(cell.get('width')) is int
            if not valid:errors.append(f'Unsupported cell metadata: {i}/{j}')
    return errors


def normalized(text):
    return ' '.join(unicodedata.normalize('NFKC',text).translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u2044':'/'})).split())


def cell_text(cell):
    if isinstance(cell,str):return cell
    if isinstance(cell,(int,float)):return str(cell)
    if isinstance(cell,dict):
        if 'roll' in cell:
            roll=cell['roll'];pad=roll.get('pad',False)
            if 'min' in roll and 'max' in roll:return f"{roll['min']:02d}–{roll['max']:02d}" if pad else f"{roll['min']}–{roll['max']}"
            if 'exact' in roll:return f"{roll['exact']:02d}" if pad else str(roll['exact'])
        if 'entry' in cell:return str(cell['entry'])
    raise ValueError(('Unsupported table cell',cell))


def cells_of(row):return row['row'] if isinstance(row,dict) and row.get('type')=='row' else row


def width(cell):return cell.get('width',1) if isinstance(cell,dict) else 1


def replace_cell(cell,text):
    if isinstance(cell,str):return text
    if isinstance(cell,dict):
        result=copy.deepcopy(cell)
        if 'roll' in result:
            if normalized(cell_text(cell))!=normalized(text):raise ValueError(('Typed roll does not encode the printed source range',cell,text))
            return result
        if 'entry' in result:result['entry']=text;return result
    if isinstance(cell,(int,float)) and str(cell)==text:return cell
    raise ValueError(('Cannot losslessly update table cell',cell,text))


def canonical_model(source,locator):
    title=' '.join(l['text'].strip() for l in locator['heading_lines'])
    spanners=[{'columns':s['columns'],'text':s['text']} for s in source['parts'][0]['spanning_headers']]
    return {'caption':title,'official_pages':source['pages'],'headers':source['headers'],'spanning_headers':spanners,
      'rows':[{'cells':[c['text'] for c in row['cells']],'colspans':row['colspans']} for row in source['rows']],
      'footnotes':[n['text'] for n in source['footnotes']],
      'source_geometry':[{'page':p['page'],'paint_seqno':p['paint_seqno'],'bounds':[round(v,3) for v in p['bounds']],
         'grid_x':[round(v,3) for v in p['grid_x']],'body_source_char_count':p['body_source_char_count'],
         'header_source_char_count':p['header_source_char_count'],'glyph_assignment_bijective':p['glyph_assignment_bijective']} for p in source['parts']]}


def corrected_table(candidate,source,locator):
    """Literal data projection; only works when independent row structure agrees."""
    result=copy.deepcopy(candidate);model=canonical_model(source,locator)
    result.update(name=model['caption'],caption=model['caption'],source=SOURCE_ID,page=locator['official_page'])
    if 'colLabelRows' in result:
        rows=result['colLabelRows'];spanners=model['spanning_headers']
        if len(rows)!=2 or len(spanners)!=1:raise ValueError('Unreviewed multi-row header structure')
        span=spanners[0];start=span['columns'][0]
        if span['columns']!=list(range(start,start+len(span['columns']))):raise ValueError('Discontinuous printed spanning header')
        index=0;found=False
        for cell in rows[0]:
            if isinstance(cell,dict) and cell.get('type')=='cellHeader':
                if index!=start or width(cell)!=len(span['columns']):raise ValueError('Candidate header span differs from source')
                text=span['text']
                if re.fullmatch(r'—{2,} .+ —{2,}',text):
                    if cell.get('style')!='th-skewer':raise ValueError('Missing source header adornment mapping')
                    text=re.sub(r'^—+ | —+$','',text)
                elif cell.get('style')=='th-skewer':
                    # The p12 distance parent heading has no printed side bars.
                    del cell['style']
                cell['entry']=text;found=True
            elif cell_text(cell):raise ValueError('Unaccounted upper-row header text')
            index+=width(cell)
        if not found:raise ValueError('Missing spanning header cell')
        rows[1]=list(model['headers'])
    else:result['colLabels']=list(model['headers'])
    if len(candidate['rows'])!=len(source['rows']):raise ValueError(('Row inventory differs',len(candidate['rows']),len(source['rows'])))
    for i,(data_row,source_row) in enumerate(zip(result['rows'],source['rows'])):
        cells=cells_of(data_row)
        if not isinstance(cells,list) or [width(c) for c in cells]!=source_row['colspans']:
            raise ValueError(('Source row/colspan structure differs',i,[width(c) for c in cells],source_row['colspans']))
        cells[:]=[replace_cell(cell,witness['text']) for cell,witness in zip(cells,source_row['cells'])]
    if model['footnotes']:result['footnotes']=list(model['footnotes'])
    else:result.pop('footnotes',None)
    return result


def compare(candidate,source,locator):
    differences=[];normalized_rows=0;literal_rows=0;typed_cells=0
    for i,(data_row,source_row) in enumerate(zip(candidate['rows'],source['rows'])):
        cells=cells_of(data_row);wanted=[c['text'] for c in source_row['cells']]
        if not isinstance(cells,list):differences.append({'row':i,'error':'Unsupported row'});continue
        actual=[cell_text(cell) for cell in cells]
        shape=[width(c) for c in cells]==source_row['colspans']
        if shape and [normalized(s) for s in actual]==[normalized(s) for s in wanted]:normalized_rows+=1
        literal=shape and len(actual)==len(wanted)
        for j,(cell,text) in enumerate(zip(cells,wanted)):
            typed=isinstance(cell,dict) and 'roll' in cell
            if typed:typed_cells+=1
            equal=normalized(cell_text(cell))==normalized(text) if typed else cell_text(cell)==text
            literal=literal and equal
            if not equal:differences.append({'row':i,'column':j,'source':text,'candidate':cell_text(cell),'normalized_equal':normalized(cell_text(cell))==normalized(text)})
        if literal:literal_rows+=1
    target=corrected_table(candidate,source,locator)
    changes=[key for key in target.keys()|candidate.keys() if target.get(key)!=candidate.get(key)]
    all_cells=[cell for row in source['rows'] for cell in row['cells']]+source['footnotes']+[h for p in source['parts'] for h in p['headers']]+[h for p in source['parts'] for h in p['spanning_headers']]
    unresolved=[j for c in all_cells for j in c['layout_joins'] if j['basis'].startswith('UNRESOLVED')]
    unknown=sorted(set(candidate)-ALLOWED_FIELDS)
    metadata=metadata_errors(candidate)
    verified=not changes and not unresolved and not unknown and not metadata and literal_rows==len(source['rows']) and len(candidate['rows'])==len(source['rows'])
    return {'name':candidate['name'],'caption':candidate['caption'],'official_pages':source['pages'],'source_rows':len(source['rows']),
      'literal_rows_or_lossless_typed_mappings':literal_rows,'normalized_rows_diagnostic_only':normalized_rows,'typed_roll_cells':typed_cells,
      'fields_requiring_source_correction':sorted(changes),'cell_differences':differences,'unresolved_layout_joins':unresolved,
      'unknown_fields':unknown,'metadata_errors':metadata,'source_content_verified':verified,'source_model':canonical_model(source,locator)},target


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    file=args.data/'data/generated/gendata-tables.json';tables=json.loads(file.read_text(encoding='utf8'))['table']
    results=[];errors=inventory_errors(tables)
    with fitz.open(args.pdf) as pdf:
        locators,locator_errors=locate(pdf,tables);errors.extend(locator_errors);source=Source(pdf);by_name={t['name']:t for t in tables}
        for locator in locators:
            try:
                extracted=source.table(locator);result,_=compare(by_name[locator['name']],extracted,locator);results.append(result)
            except (AssertionError,ValueError,KeyError,IndexError,TypeError) as error:errors.append({'name':locator['name'],'error':str(error)})
    summary={'tables':len(tables),'source_tables_extracted':len(results),'source_rows':sum(r['source_rows'] for r in results),
      'literal_rows_or_lossless_typed_mappings':sum(r['literal_rows_or_lossless_typed_mappings'] for r in results),
      'normalized_rows_diagnostic_only':sum(r['normalized_rows_diagnostic_only'] for r in results),
      'tables_source_content_verified':sum(r['source_content_verified'] for r in results),'errors':errors}
    passed=not errors and len(results)==len(tables) and all(r['source_content_verified'] for r in results)
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'pdf_sha256':pdf_hash,'input_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
      'scope':__doc__,'summary':summary,'records':results,'errors':errors,'passed':passed},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({**summary,'passed':passed},ensure_ascii=False));raise SystemExit(0 if passed else 1)


if __name__=='__main__':main()
