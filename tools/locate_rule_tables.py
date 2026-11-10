"""Locate every retained rule-table title in the official SRD PDF.

Exact, unique printed heading evidence establishes the primary source page. It
does not prove row/cell fidelity, continuation coverage, or other metadata and
must not be used as a complete table/release certificate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import unicodedata

import fitz


def normalize(text):
    return ' '.join(unicodedata.normalize('NFKC',text).translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':''})).split()).casefold()


def locate(pdf,tables):
    captions={normalize(t['caption']) for t in tables};exact={key:[] for key in captions};small={key:[] for key in captions}
    for number,page in enumerate(pdf,1):
        lines=[]
        for b,block in enumerate(page.get_text('dict')['blocks']):
            for n,line in enumerate(block.get('lines',[])):
                spans=line['spans'];text=''.join(s['text'] for s in spans).strip()
                heading=bool(spans) and all('Bold' in s['font'] or 'Semibold' in s['font'] for s in spans)
                if not heading:continue
                evidence={'page':number,'block':b,'line':n,'text':text,'bbox':line['bbox'],
                  'fonts':[s['font'] for s in spans],'sizes':[s['size'] for s in spans],
                  'colors':[s['color'] for s in spans],'origin':list(spans[0]['origin'])}
                key=normalize(text)
                if key in exact:exact[key].append([evidence])
                is_caption=all(s['font']=='GillSans-SemiBold' and abs(s['size']-10.5)<.05 for s in spans)
                if is_caption:lines.append(evidence)
        for i,start in enumerate(lines):
            selected=[]
            for following in lines[i:i+3]:
                if selected:
                    previous=selected[-1]
                    if abs(following['origin'][0]-start['origin'][0])>.3 or not 0<following['origin'][1]-previous['origin'][1]<18:break
                selected.append(following);key=normalize(' '.join(l['text'] for l in selected))
                if key in small:small[key].append(list(selected))
    records=[];errors=[]
    for table in tables:
        key=normalize(table['caption']);matches=small[key] or exact[key]
        if len(matches)!=1:
            errors.append({'name':table['name'],'caption':table['caption'],'error':'Missing or ambiguous exact printed heading','candidate_pages':[m[0]['page'] for m in matches]});continue
        lines=matches[0]
        records.append({'name':table['name'],'caption':table['caption'],'official_page':lines[0]['page'],
          'locator_kind':'exact_table_caption' if small[key] else 'exact_section_heading',
          'heading_lines':lines,'dataset_source_id':table['source'],'dataset_page':table.get('page'),
          'row_fidelity_status':'UNVERIFIED by this heading locator'})
    return records,errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    assert pdf_hash=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
    file=args.data/'data/generated/gendata-tables.json';tables=json.loads(file.read_text(encoding='utf8'))['table']
    with fitz.open(args.pdf) as pdf:records,errors=locate(pdf,tables)
    result={'pdf_sha256':pdf_hash,'input_sha256':hashlib.sha256(file.read_bytes()).hexdigest(),
      'scope':__doc__,'normalization':'NFKC; curly quotes and dash forms to straight equivalents; whitespace collapse; case folding. No word substitutions or fuzzy matching.',
      'records':records,'errors':errors,'all_primary_headings_located':not errors}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'retained_tables':len(tables),'unique_printed_headings':len(records),'errors':errors},ensure_ascii=False))
    if errors:raise SystemExit(1)


if __name__=='__main__':main()
