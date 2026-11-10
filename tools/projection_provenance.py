"""Strict schemas for authored SRD source-projection receipts, not game rules.

Call these only after the source model's complete physical PDF extraction has
been re-proven. Record identity selects the source family/table subset. Receipt
fields never select an answer or make a source-fidelity certificate themselves.
"""
import copy
import hashlib
import json
import re

from verify_item_abilities import exact
from verify_item_families import required_paragraph_indexes

PDF_SHA256='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
PROJECTION_NOTE='Literal source family paragraphs and printed table rows; existing concrete identity and family references preserved.'


def require_identity_coverage(proof,literal_ids,structural_ids=()):
    """Counts alone must never let a real record disappear behind a fake ID."""
    indexed={}
    for row in proof['records']:
        identity=tuple(row[key] for key in ('file','kind','name'))
        if not all(isinstance(part,str) and part for part in identity) or identity in indexed:
            raise ValueError('Invalid or duplicate source-projection proof identity')
        indexed[identity]=row
    literal={identity for identity,row in indexed.items() if row.get('literal_projection_verified') is True}
    structural={identity for identity,row in indexed.items() if row.get('structural_delegation_verified') is True}
    if (literal!=set(literal_ids) or structural!=set(structural_ids) or literal&structural
        or set(indexed)!=literal|structural):
        raise ValueError('Incomplete source-projection proof identity coverage')
    return indexed


def require_imported_fact(record,field,fact):
    if (set(fact)!={'value','source_expected','interpretation'} or not isinstance(fact['interpretation'],str)
        or not exact(record.get(field),fact['value']) or not exact(fact['value'],fact['source_expected'])):
        raise ValueError('Inconsistent source-projection proof fact: '+field)
    return fact


def family_tables(record,kind,model):
    """Derive the existing literal projection from source rows and identity."""
    heading=model['source_heading'];name=record['name'];tables=copy.deepcopy(model['tables'])
    if kind in {'itemGroup','itemEntry'}:return tables
    if heading=='Bag of Tricks':
        caption=name.split(', ',1)[1]+' Bag of Tricks'
        tables=[table for table in tables if table.get('caption')==caption]
        if len(tables)!=1:raise ValueError('Missing identity-selected Bag of Tricks table')
        return tables
    selected={'Belt of Giant Strength','Potion of Giant Strength','Dragon Scale Mail','Carpet of Flying',
              'Elemental Gem','Horn of Valhalla','Manual of Golems','Potions of Healing','Feather Token','Ring of Elemental Command'}
    if heading not in selected:return tables
    if len(tables)!=1:raise ValueError('Missing unique source-family selection table')
    table=tables[0]
    def matches(row):
        if heading in {'Belt of Giant Strength','Potion of Giant Strength'}:
            identity=re.fullmatch(r'(Belt|Potion) of (\w+) Giant Strength',name)
            printed=re.fullmatch(re.escape(heading)+r' \(([^)]+)\)',row[0])
            return bool(identity and printed and identity[2].lower() in printed[1].split(' or '))
        if heading=='Dragon Scale Mail':return row[0]==name.removesuffix(' Dragon Scale Mail')
        if heading=='Carpet of Flying':return row[1]==name.split(', ',1)[1]
        if heading=='Elemental Gem':return row[0].casefold()==name.split(', ',1)[1].casefold()
        if heading=='Horn of Valhalla':return row[1]==name.split(', ',1)[1]
        if heading=='Manual of Golems':return row[1]==name.removeprefix('Manual of ').removesuffix(' Golems')+' Golem'
        if heading=='Potions of Healing':
            identity={'Potion of Healing':'Potion of Healing','Potion of Greater Healing':'Potion of Healing (greater)',
                      'Potion of Superior Healing':'Potion of Healing (superior)','Potion of Supreme Healing':'Potion of Healing (supreme)'}
            return row[0]==identity.get(name)
        if heading=='Feather Token':return row[1].casefold()==name.split(', ',1)[1].casefold()
        if heading=='Ring of Elemental Command':
            identity=re.fullmatch(r'Ring of Elemental Command \((Air|Earth|Fire|Water)\)',name)
            return bool(identity and row[0]==identity[1])
        raise ValueError('Unreviewed source-family row selection')
    rows=[row for row in table['rows'] if matches(row)]
    if len(rows)!=1:raise ValueError(('Missing unique identity-selected family row',name))
    table['rows']=rows
    return tables


def expected_family(a,record,kind,model):
    heading=a.source_name(record,kind)
    if heading!=a.canonical(model['source_heading']):raise ValueError('Source-family identity mismatch')
    source=a.SOURCES[heading]
    pages=sorted({line['page'] for line in source['heading_lines']+source['lines']})
    if pages!=model['pages']:raise ValueError('Declared family pages differ from fresh physical source')
    result={'version':'5.2.1','official_pdf_sha256':PDF_SHA256,'heading':model['source_heading'],
            'printed_header':model['printed_header'],'pages':pages,
            'paragraph_indexes':required_paragraph_indexes(record,kind,model),'projection':PROJECTION_NOTE}
    tables=family_tables(record,kind,model)
    if tables:result['printed_tables']=tables
    return result


def check_family(a,record,kind,model):
    wanted=expected_family(a,record,kind,model);actual=record.get('_srd521')
    if not exact(actual,wanted):raise ValueError(('Source-family provenance differs',record['name']))
    return {'value':actual,'source_expected':wanted,'interpretation':__doc__}


def expected_equipment(model):
    return {'official_pdf_sha256':PDF_SHA256,'source_units':[section['unit'] for section in model['sections']],
            'projection_sha256':hashlib.sha256(json.dumps(model,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def check_equipment(record,model):
    wanted=expected_equipment(model);actual=record.get('_srd521Equipment')
    if not exact(actual,wanted):raise ValueError(('Equipment provenance differs',record['name']))
    return {'value':actual,'source_expected':wanted,'interpretation':__doc__}
