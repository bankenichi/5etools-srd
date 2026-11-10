"""Reopen the official PDF and replay every reviewed source-citation recipe.

The builder's input guards remain enabled. An observer captures the uncited
projection while the normal cited build runs, then fresh heading/paragraph/cell
queries must reproduce the saved pages. This proves the reviewed citation map
and output bytes, not all aliases, rules/metadata, global completeness or PDF
layout; their independent content gates remain required.
"""
import argparse
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import sys

import fitz

sys.path.insert(0,str(Path(__file__).resolve().parent))
import build_srd
from locate_source_citations import Source,locate,helper_scope
from rule_table_grid import PDF_SHA256

ROOT=Path(__file__).resolve().parents[1]


def replay(source,recipe,record):
    status=recipe['status']
    if status in {'LOCATED_SCOPE','SCHEMA_HELPER'}:
        if recipe['kind']!='itemType':raise ValueError('Unreviewed schema helper kind')
        return helper_scope(source,record)
    if 'printed_identifier' in recipe:
        return source.table_row(recipe['target'],recipe['printed_identifier'])
    if 'source_paragraph' in recipe and 'witnesses' not in recipe:
        return source.prose_citation(record,recipe['kind'],recipe['target'])
    return locate(source,recipe['target'],recipe['kind'],record)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    path=ROOT/'source/citations.json';model=json.loads(path.read_text(encoding='utf8'))
    assert model['official_pdf_sha256']==pdf_hash and model['upstream_commit']==build_srd.UPSTREAM
    captured={};original=build_srd.apply_citations
    def observe(data,*values):
        captured.update(copy.deepcopy(data))
        return original(data,*values)
    try:
        build_srd.apply_citations=observe
        expected=build_srd.Builder(ROOT).output()
    finally:build_srd.apply_citations=original
    errors=[];verified=[]
    actual={p.relative_to(args.data).as_posix() for p in (args.data/'data').rglob('*.json')}|{'manifest.json'}
    if actual!=set(expected):errors.append({'error':'Cited dataset inventory differs from guarded rebuild'})
    for name,raw in expected.items():
        if not (args.data/name).is_file() or (args.data/name).read_bytes()!=raw:
            errors.append({'error':'Cited output differs from guarded rebuild','file':name})
    with fitz.open(args.pdf) as pdf:
        source=Source(pdf)
        for recipe in model['records']:
            record=captured[recipe['file']][recipe['kind']][recipe['index']]
            try:
                fresh=replay(source,recipe,record)
                if not fresh or fresh['status']!=recipe['status'] or fresh.get('page')!=recipe['page']:
                    errors.append({'file':recipe['file'],'kind':recipe['kind'],'name':recipe['name'],'error':'Saved citation differs from fresh source query','fresh':fresh})
                else:verified.append({'file':recipe['file'],'kind':recipe['kind'],'name':recipe['name'],'status':fresh['status'],'page':fresh.get('page')})
            except (ValueError,AssertionError,KeyError,IndexError,TypeError) as error:
                errors.append({'file':recipe['file'],'kind':recipe['kind'],'name':recipe['name'],'error':str(error)})
    summary={'recipes':len(model['records']),'fresh_queries_verified':len(verified),'statuses':dict(Counter(r['status'] for r in verified)),
      'guarded_output_files':len(expected),'errors':errors,'passed':not errors and len(verified)==len(model['records'])}
    result={'scope':__doc__,'official_pdf_sha256':pdf_hash,'upstream_commit':build_srd.UPSTREAM,
      'citation_model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'summary':summary,'records':verified,'passed':summary['passed']}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False));raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
