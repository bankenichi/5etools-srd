"""Six approved data-only portrait overrides, with an exact source-audit inverse.

The apps already consume this entry flag. No rendering or splitting code is
changed. Whole-record and paragraph guards prevent source edits from being
hidden as layout metadata; unreviewed flags or wrapper shapes are rejected.
"""
import copy
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MODEL=ROOT/'source/layout-overrides.json'
FLAGS={'_force_portrait','_force_landscape'}


def record_digest(record):
    return hashlib.sha256(json.dumps(record,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode('utf8')).hexdigest()


def load_model(path=None):
    raw=Path(path or MODEL).read_bytes();model=json.loads(raw)
    if model['orientation']!='portrait' or len(model['records'])!=6:raise ValueError('Unexpected approved layout scope')
    keys=[(r['file'],r['kind'],r['name']) for r in model['records']]
    if len(set(keys))!=6:raise ValueError('Duplicate approved layout identity')
    return model,hashlib.sha256(raw).hexdigest()


def _parent(record,path):
    node=record
    for part in path[:-1]:node=node[part]
    return node,path[-1]


def _has_flag(value):
    if isinstance(value,dict):return bool(FLAGS & value.keys()) or any(_has_flag(v) for v in value.values())
    if isinstance(value,list):return any(_has_flag(v) for v in value)
    return False


def apply_layouts(data,pdf_sha256,upstream_commit,path=None):
    model,digest=load_model(path)
    if model['official_pdf_sha256']!=pdf_sha256 or model['upstream_commit']!=upstream_commit:
        raise ValueError('Layout source authority changed')
    if _has_flag(data):raise ValueError('Unexpected layout marker in source projection')
    result=copy.deepcopy(data);receipts=[]
    for spec in model['records']:
        matches=[r for r in result[spec['file']][spec['kind']] if r.get('name')==spec['name']]
        if len(matches)!=1:raise ValueError(('Missing/duplicate approved layout record',spec['name']))
        record=matches[0]
        if record_digest(record)!=spec['source_record_sha256']:raise ValueError(('Layout source record changed',spec['name']))
        parent,key=_parent(record,spec['paragraph_path']);text=parent[key]
        if not isinstance(text,str) or hashlib.sha256(text.encode('utf8')).hexdigest()!=spec['paragraph_sha256']:
            raise ValueError(('Layout source paragraph changed',spec['name']))
        parent[key]={'type':'item','entry':text,'_force_portrait':True}
        if record_digest(record)!=spec['layout_record_sha256']:raise ValueError(('Layout postimage differs',spec['name']))
        receipts.append({k:spec[k] for k in ('file','kind','name','paragraph_path','source_record_sha256','layout_record_sha256')})
    return result,{'reason':'User-approved existing portrait flags for six overflowing SRD layouts; source text/numbers/tables preserved and engine unchanged.',
                   'model_sha256':digest,'records':receipts,'approved_overrides':len(receipts),'expected_card_delta':model['expected_card_delta']}


def source_projection(data,path=None,require_all=False,require_applied=False):
    """Remove only exact frozen wrappers; never normalize modified source content."""
    model,digest=load_model(path);specs={(r['file'],r['kind'],r['name']):r for r in model['records']}
    result=copy.deepcopy(data);seen=set();removed=[]
    for file,payload in result.items():
        for kind,records in payload.items():
            if not isinstance(records,list):continue
            for record in records:
                if not isinstance(record,dict):continue
                identity=(file,kind,record.get('name'));spec=specs.get(identity)
                if spec is None:continue
                if identity in seen:raise ValueError(('Duplicate layout projection',identity))
                seen.add(identity);actual=record_digest(record)
                if not _has_flag(record):
                    if require_applied:raise ValueError(('Missing approved portrait override',identity))
                    continue
                if actual!=spec['layout_record_sha256']:raise ValueError(('Unknown layout/source postimage',identity))
                parent,key=_parent(record,spec['paragraph_path']);wrapper=parent[key]
                if not isinstance(wrapper,dict) or set(wrapper)!={'type','entry','_force_portrait'} or wrapper['type']!='item' or wrapper['_force_portrait'] is not True or not isinstance(wrapper['entry'],str):
                    raise ValueError(('Unapproved portrait wrapper',identity))
                if hashlib.sha256(wrapper['entry'].encode('utf8')).hexdigest()!=spec['paragraph_sha256']:
                    raise ValueError(('Layout paragraph content differs',identity))
                parent[key]=wrapper['entry']
                if record_digest(record)!=spec['source_record_sha256']:raise ValueError(('Normalized source record differs',identity))
                removed.append({'file':file,'kind':kind,'name':spec['name'],'source_record_sha256':spec['source_record_sha256']})
    if require_all and seen!=set(specs):raise ValueError('Approved layout record inventory differs')
    if _has_flag(result):raise ValueError('Unreviewed layout marker outside approved wrappers')
    return result,{'model_sha256':digest,'annotations_removed':removed,'scope':'Exact inverse of six frozen, user-approved portrait wrappers only; all rule content preserved.'}
