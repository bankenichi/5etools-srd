"""Capture full installed-database counts and exact card/split signatures.

Includes official and playtest inputs using the workbench's existing all-source
request shape. Reads installed data only. A later capture can compare every
card's markup, order, titles, page shell, and input fingerprints with this one.
"""
import argparse
import contextlib
import hashlib
import json
from pathlib import Path
import sys
import shutil
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parent))
from check_typed_reference_boundary import Cards


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compare_baseline(before,after):
    """Require exact output, including boundaries, against the same platform."""
    for key in ('platform','input_sha256','catalog_sha256'):
        if before[key]!=after[key]:raise ValueError('Full-database baseline precondition differs: '+key)
    checked=('counts','sheets','cards','shell_sha256','html_sha256')
    for key in checked:
        if before[key]!=after[key]:raise ValueError('Full-database rendering regression: '+key)
    return {'passed':True,'exact_equal_fields':list(checked),
            'protected_code_unchanged':before['protected_sha256']==after['protected_sha256']}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('source','data','out'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--catalog',type=Path,required=True,help='Frozen actual workbench catalog, including only currently available origins')
    parser.add_argument('--platform',choices=('desktop','android'),required=True)
    parser.add_argument('--baseline',type=Path,help='Earlier capture from the same platform and exact input; require identical counts, ordered card markup, splits, shell, and whole HTML')
    args=parser.parse_args();source=args.source.resolve();data=args.data.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    if args.baseline and args.baseline.resolve()==(out/'baseline.json').resolve():
        raise ValueError('Use a separate output directory; never overwrite the regression baseline')
    inputs={p.relative_to(data).as_posix():sha(p) for p in data.rglob('*.json')}
    protected={p.name:sha(p) for p in [source/'card_engine.py',*source.glob('parser_*.py')]}
    catalog=json.loads(args.catalog.read_text(encoding='utf8'))
    def remap(value):
        if isinstance(value,list):return [remap(v) for v in value]
        for prefix in ('generators/data/','generators/rpg_data/'):
            if value.startswith(prefix):
                path=data/value[len(prefix):]
                if not path.is_file():raise FileNotFoundError(path)
                return str(path)
        raise ValueError('Unknown full-database input: '+value)
    requests=[]
    for name,entry in catalog.items():
        requests.append({'name':name,'file':remap(entry['file']),'filters':{}})
        if entry.get('playtestFile'):requests.append({'name':name,'file':remap(entry['playtestFile']),'filters':{}})
    sys.path.insert(0,str(source));import card_controller as controller
    native_initialization=None
    if args.platform=='android':
        # Native startup calls this after setting its files directory. Host
        # tests must supply the same reference data, rather than silently
        # testing an uninitialized cache in the desktop working directory.
        with tempfile.TemporaryDirectory(prefix='.native-context-',dir=out) as folder:
            native=Path(folder).resolve()
            if not native.is_relative_to(out):raise ValueError('Native test context escaped its output root')
            target=native/'generators/rpg_data/data/deities.json';target.parent.mkdir(parents=True)
            shutil.copyfile(data/'data/deities.json',target)
            controller.load_master_stats(str(native))
        native_initialization={'existing_startup_function':'load_master_stats','source':'data/deities.json','sha256':sha(data/'data/deities.json')}
    generate=controller.generate_deck if args.platform=='android' else controller.generate_html_isolated
    html=out/'full-database.html'
    with (out/'generation.log').open('w',encoding='utf8') as log,contextlib.redirect_stdout(log):
        result=generate({'datasets':requests},str(html))
    document=html.read_text(encoding='utf8');parsed=Cards(document)
    if len(parsed.cards)!=result['card_count'] or not parsed.cards:raise ValueError('Missing full-database card markup')
    import re
    cards=[{'title':re.search(r'<h1 class="title"[^>]*>\s*<span>(.*?)</span>',markup,re.S)[1],
            'sha256':hashlib.sha256(markup.encode('utf8')).hexdigest()} for _,_,markup in parsed.cards]
    if inputs!={p.relative_to(data).as_posix():sha(p) for p in data.rglob('*.json')}:raise ValueError('Installed full database changed during capture')
    if protected!={p.name:sha(p) for p in [source/'card_engine.py',*source.glob('parser_*.py')]}:raise ValueError('Protected generator changed during capture')
    report={'scope':__doc__,'platform':args.platform,'data_root':str(data),'input_sha256':inputs,'protected_sha256':protected,
            'catalog_sha256':sha(args.catalog),'requests':requests,'counts':{k:result[k] for k in ('card_count','item_count')},
            'native_initialization':native_initialization,
            'sheets':document.count('<div class="page">'),'html_sha256':sha(html),
            'shell_sha256':hashlib.sha256(parsed.shell().encode('utf8')).hexdigest(),'cards':cards,'installed_data_unchanged':True}
    if args.baseline:
        baseline=json.loads(args.baseline.read_text(encoding='utf8'))
        report['regression']=compare_baseline(baseline,report)
        report['regression'].update(baseline=str(args.baseline.resolve()),baseline_sha256=sha(args.baseline))
    (out/'baseline.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'platform':args.platform,'full_input_json_files':len(inputs),'requests':len(requests),'counts':report['counts'],'sheets':report['sheets'],'installed_data_unchanged':True}))


if __name__=='__main__':main()
