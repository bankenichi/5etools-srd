"""Canonical SRD source identities; this does not establish page provenance.

Only declared source fields, packed reference source components and the source
parameter of filter tags are rewritten. Names and ordinary prose are preserved.
Apply this only after every retained record has a separately verified citation.
"""
import copy
import hashlib
import json
import re

SOURCE_ID='SRD521'
LEGACY_IDS=frozenset({'XPHB','XDMG','XMM','SRD52'})
SOURCE_FIELDS=frozenset({'source','classSource','subclassSource'})
PACKED=re.compile(r'(?<=\|)(?:XPHB|XDMG|XMM|SRD52)(?=[|#}]|$)',re.I)
SOURCE_FILTER=re.compile(r'(\|source=)([^|}]+)',re.I)


def remap(value,key=None):
    if isinstance(value,dict):return {k:remap(v,k) for k,v in value.items()}
    if isinstance(value,list):return [remap(v,key) for v in value]
    if not isinstance(value,str):return value
    if key in SOURCE_FIELDS and value.upper() in LEGACY_IDS:return SOURCE_ID
    if '|' not in value:return value
    value=PACKED.sub(SOURCE_ID,value)
    def source_parameter(match):
        tokens=match[2].split(';')
        tokens=[SOURCE_ID if token.upper() in LEGACY_IDS else token for token in tokens]
        return match[1]+';'.join(tokens)
    return SOURCE_FILTER.sub(source_parameter,value)


def consolidate_bestiary(data):
    """One canonical source index must cover all SRD statblocks.

    Preserve the original sorted file/record order. Silently assigning one
    source to several filenames would drop entries from the 5etools index.
    """
    result=copy.deepcopy(data);paths=sorted(p for p in result if p.startswith('data/bestiary/bestiary-') and p.endswith('.json'))
    monsters=[]
    for path in paths:
        payload=result.pop(path)
        if set(payload)!={'monster'}:raise ValueError('Unreviewed bestiary file structure: '+path)
        monsters.extend(payload['monster'])
    if any(r.get('source')!=SOURCE_ID for r in monsters):raise ValueError('Mixed source identities in canonical SRD bestiary')
    identities=[r['name'].casefold() for r in monsters]
    if len(set(identities))!=len(identities):raise ValueError('Monster identity collision after source remapping')
    result['data/bestiary/bestiary-srd521.json']={'monster':monsters}
    result['data/bestiary/index.json']={SOURCE_ID:'bestiary-srd521.json'}
    return result


def apply_citations(data,path,pdf_hash,upstream_commit):
    """Apply a complete, frozen-input citation map before source-ID remapping."""
    raw=path.read_bytes();model=json.loads(raw)
    if model['official_pdf_sha256']!=pdf_hash or model['upstream_commit']!=upstream_commit:
        raise ValueError('Citation authority changed')
    expected={(r['file'],r['kind'],r['index']):r for r in model['records']}
    if len(expected)!=len(model['records']):raise ValueError('Duplicate citation identities')
    actual={}
    for file,payload in data.items():
        for kind,records in payload.items():
            if not isinstance(records,list):continue
            for index,record in enumerate(records):
                if isinstance(record,dict):actual[(file,kind,index)]=record
    if set(actual)!=set(expected):raise ValueError('Citation record inventory changed')
    for key,record in actual.items():
        citation=expected[key]
        digest=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if digest!=citation['candidate_record_sha256']:raise ValueError('Citation input changed: '+repr(key))
        if citation['status'] not in {'LOCATED','LOCATED_SCOPE','SCHEMA_HELPER'}:raise ValueError('Unresolved citation: '+repr(key))
        if citation['status']=='SCHEMA_HELPER':
            if not (key[1]=='itemType' and record.get('name')=='Generic Variant' and record.get('abbreviation')=='GV'
                    and not record.get('entries') and not record.get('entriesTemplate') and citation['page'] is None):
                raise ValueError('Unreviewed unprinted helper: '+repr(key))
        elif type(citation.get('page')) is not int or not 1<=citation['page']<=364:
            raise ValueError('Invalid source page: '+repr(key))
    result=copy.deepcopy(data);changed=0;removed=0
    for key,citation in expected.items():
        file,kind,index=key;record=result[file][kind][index];page=citation['page']
        if page is None:
            if 'page' in record:record.pop('page');removed+=1
        else:
            if 'inherits' not in record or 'page' in record:
                changed+=record.get('page')!=page;record['page']=page
            if 'inherits' in record:
                changed+=record['inherits'].get('page')!=page;record['inherits']['page']=page
    result=consolidate_bestiary(remap(result))
    receipt={'reason':'Canonical SRD5.2.1 source identities and actual PDF citation pages; all packed references are remapped together. Empty generic-variant helper has no invented page.',
      'source_id':SOURCE_ID,'citation_model_sha256':hashlib.sha256(raw).hexdigest(),'citation_records':len(expected),
      'page_fields_corrected':changed,'unprinted_page_fields_removed':removed,'bestiary_statblocks':len(result['data/bestiary/bestiary-srd521.json']['monster'])}
    return result,receipt
