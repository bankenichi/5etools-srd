"""Locate exact source spans for retained non-character rules (not a release gate).

A matching prose leaf is not proof of metadata, table associations, completeness,
or renderer behavior. Every such remaining gate is explicit in the report.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

import fitz

KINDS={'action','condition','disease','status','sense','skill','hazard','trap','variantrule','table','tableGroup'}
REFS={'action','condition','status','sense','skill','hazard','trap','variantrule','spell','creature','item','race','feat','class','background','itemProperty','itemMastery','optfeature','table','deck'}


def decode(s):
    def sub(m):
        tag,body=m.group(1),m.group(2) or '';parts=body.split('|')
        if tag in REFS:return parts[2] if len(parts)>2 and parts[2] else parts[0]
        if tag in {'i','b','filter','book','area','5etools','note','link'}:return parts[0]
        if tag in {'dice','damage'}:return parts[1] if len(parts)>1 and parts[1] else parts[0]
        if tag=='dc':return 'DC '+parts[0]
        if tag=='hit':return ('' if parts[0].startswith(('-','+')) else '+')+parts[0]
        if tag=='chance':return parts[1] if len(parts)>1 and parts[1] else parts[0]+' percent'
        raise ValueError('Unsupported tag '+tag)
    while re.search(r'\{@(\w+)(?: ([^{}]*))?}',s):s=re.sub(r'\{@(\w+)(?: ([^{}]*))?}',sub,s)
    if re.search(r'\{[@#=]',s):raise ValueError('Unexpanded reference '+s)
    return s


def norm(s,join=False):
    s=unicodedata.normalize('NFKC',s).translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':'','\u200b':''}))
    if join:s=re.sub(r'(?<=[A-Za-z])-\s*\n\s*(?=[A-Za-z])','',s)
    s=re.sub(r'\s*—\s*','—',s)
    return ' '.join(s.split())


def leaves(v,path=()):
    if isinstance(v,str):yield path,v
    elif isinstance(v,list):
        for i,x in enumerate(v):yield from leaves(x,path+(str(i),))
    elif isinstance(v,dict):
        if v.get('type')=='table':return
        for k in ['name','caption','entry','entries','items','footnotes','intro','outro']:
            if k in v:yield from leaves(v[k],path+(k,))


def tables(v):
    if isinstance(v,list):return sum(tables(x) for x in v)
    if isinstance(v,dict):return int(v.get('type')=='table')+sum(tables(x) for x in v.values())
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args();pdf=args.pdf.read_bytes();pdf_hash=hashlib.sha256(pdf).hexdigest()
    assert pdf_hash=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87','Official PDF changed'
    doc=fitz.open(stream=pdf,filetype='pdf');views={mode:[] for mode in ['native','native-joined','columns','columns-joined','prose','prose-joined']}
    for page in doc:
        lines=[]
        for block in page.get_text('dict')['blocks']:
            for line in block.get('lines',[]):
                if all(span['color']==0x808285 for span in line['spans']):continue
                lines.append((int(line['bbox'][0]>=page.rect.width/2),''.join(span['text'] for span in line['spans']),all(span['font'].startswith('GillSans') for span in line['spans'])))
        for mode in ['native','columns','prose']:
            raw='\n'.join(text for _,text,_ in lines) if mode=='native' else '\n'.join(text for col in [0,1] for c,text,gill in lines if c==col and (mode!='prose' or not gill))
            views[mode].append(norm(raw));views[mode+'-joined'].append(norm(raw,True))
    records=[];input_hashes={}
    for file in sorted((args.data/'data').rglob('*.json')):
        payload=json.loads(file.read_text(encoding='utf8'))
        if not isinstance(payload,dict):continue
        if any(kind in KINDS for kind in payload):input_hashes[file.relative_to(args.data).as_posix()]=hashlib.sha256(file.read_bytes()).hexdigest()
        for kind,items in payload.items():
            if kind not in KINDS or not isinstance(items,list):continue
            for index,record in enumerate(items):
                result={'file':file.relative_to(args.data).as_posix(),'kind':kind,'index':index,'name':record.get('name'),'prose':[],'tables_unverified':tables(record),'metadata_status':'UNVERIFIED: literal prose locations do not certify metadata or derived mechanics','completeness_status':'UNVERIFIED: leaf locations do not certify omitted paragraphs, rows, headings or entities'}
                if kind in {'table','tableGroup'}:
                    result['status']='UNVERIFIED_TABLE_ASSOCIATIONS';records.append(result);continue
                for path,raw in leaves(record.get('entries',[]),('entries',)):
                    entry={'path':'/'+'/'.join(path),'raw':raw,'source_span':None}
                    try:
                        visible=decode(raw);query=norm(visible);entry['visible']=visible
                        if query:
                            for mode,pages in views.items():
                                for number,text in enumerate(pages):
                                    start=text.find(query)
                                    if start>=0:
                                        entry['source_span']={'page_start':number+1,'page_end':number+1,'extractor':mode,'normalized_start':start,'normalized_end':start+len(query),'exact_normalized_text':query};break
                                    if number+1<len(pages):
                                        combined=text+' '+pages[number+1];start=combined.find(query)
                                        if 0<=start<len(text) and start+len(query)>len(text):
                                            entry['source_span']={'page_start':number+1,'page_end':number+2,'extractor':mode,'normalized_start':start,'normalized_end':start+len(query),'exact_normalized_text':query};break
                                if entry['source_span']:break
                        entry['status']='EXACT_SOURCE_SPAN' if entry['source_span'] else 'UNVERIFIED'
                    except ValueError as error:entry.update(status='UNVERIFIED_TAG',error=str(error))
                    result['prose'].append(entry)
                result['status']='ALL_PROSE_LOCATED_OTHER_GATES_UNVERIFIED' if result['prose'] and all(x['source_span'] for x in result['prose']) else 'UNVERIFIED'
                records.append(result)
    summary={'records':len(records),'prose_leaves':sum(len(r['prose']) for r in records),'exact_leaves':sum(bool(p['source_span']) for r in records for p in r['prose']),'unverified_leaves':sum(not p['source_span'] for r in records for p in r['prose']),'full_records_certified':0}
    out={'pdf_sha256':pdf_hash,'input_sha256':input_hashes,'normalization':'NFKC, curly quotes/dashes to straight equivalents, whitespace collapse; separate preserved/joined physical line-end hyphen views. Gray footer spans excluded. Prose-only view excludes GillSans table lines across page continuations. Case, words and other punctuation retained. No fuzzy matches.','summary':summary,'records':records}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8');print(json.dumps(summary))


if __name__=='__main__':main()
