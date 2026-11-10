"""Exercise both existing card generators against this data without installing it."""
import argparse
from collections import Counter
import contextlib
import hashlib
from html import unescape
import json
from pathlib import Path
import re
import subprocess
import sys


def run(source,data,out,platform):
    sys.path.insert(0,str(source))
    import card_controller as controller
    generate=controller.generate_deck if platform=='android' else controller.generate_html_isolated
    catalog=json.loads((source/'datasets.json').read_text(encoding='utf-8'))
    out.mkdir(parents=True,exist_ok=True);report={};requests=[]
    def remap(name):
        for prefix in ('generators/data/','generators/rpg_data/'):
            if name.startswith(prefix):
                target=data/name[len(prefix):]
                if not target.is_file():raise FileNotFoundError('Missing test input: '+str(target))
                return str(target)
        raise ValueError('Unknown catalog path: '+name)
    with (out/'generation.log').open('w',encoding='utf-8') as log,contextlib.redirect_stdout(log):
        for name,entry in catalog.items():
            files=entry['file'];files=[remap(f) for f in files] if isinstance(files,list) else remap(files)
            request={'name':name,'file':files,'filters':{}};requests.append(request)
            path=out/(name.replace(' / ','-').replace(' ','-').lower()+'.html')
            stats=generate({'datasets':[request]},str(path))
            titles=Counter()
            if stats.get('card_count'):
                text=path.read_text(encoding='utf-8')
                titles.update(' '.join(unescape(title).split()) for title in re.findall(r'<h1 class="title"[^>]*>\s*<span>(.*?)</span>',text,re.S))
                if sum(titles.values())!=stats['card_count']:raise AssertionError('Missing card markup: '+name)
            report[name]={'cards':stats.get('card_count',0),'items':stats.get('item_count',0),'titles':dict(sorted(titles.items()))}
        stats=generate({'datasets':requests},str(out/'all.html'))
        report['all']={'cards':stats.get('card_count',0),'items':stats.get('item_count',0)}
    if not report['all']['cards']:raise AssertionError('No cards generated; empty runs cannot prove parity')
    (out/'counts.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:{x:v[x] for x in ('cards','items')} for k,v in report.items()},indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--desktop',type=Path);parser.add_argument('--android-python',type=Path)
    parser.add_argument('--data',type=Path,default=Path(__file__).resolve().parents[1])
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--child',choices=['desktop','android']);parser.add_argument('--source',type=Path)
    args=parser.parse_args()
    if args.child:run(args.source.resolve(),args.data.resolve(),args.out.resolve(),args.child)
    else:
        before={}
        for platform,source in [('desktop',args.desktop),('android',args.android_python)]:
            if source is None:parser.error('Provide both generator source locations')
            for path in [source/'card_engine.py',*source.glob('parser_*.py')]:before[path]=hashlib.sha256(path.read_bytes()).hexdigest()
            subprocess.run([sys.executable,str(Path(__file__).resolve()),'--child',platform,'--source',str(source),'--data',str(args.data),'--out',str(args.out/platform)],check=True)
        for path,digest in before.items():
            if hashlib.sha256(path.read_bytes()).hexdigest()!=digest:raise AssertionError('Generator source changed: '+str(path))
        reports={name:json.loads((args.out/name/'counts.json').read_text(encoding='utf-8')) for name in ['desktop','android']}
        if reports['desktop']!=reports['android']:raise AssertionError('Generator results differ; inspect counts.json')
        (args.out/'verification.json').write_text(json.dumps({'matching':True,'protected_files':len(before),'all':reports['desktop']['all']},indent=2),encoding='utf-8')
