"""Check all printed ordinary weapon/armor category rows against retained data.

Source table geometry supplies the complete row inventory and enclosing category.
Schema codes must resolve to helpers with the matching meaning. This component
does not certify magic-item inheritance, other metadata, prose, or card layout.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import fitz

sys.path.insert(0,str(Path(__file__).resolve().parent))
from locate_source_citations import Source
from rule_table_grid import PDF_SHA256
from source_identity import SOURCE_ID

GROUPS={
    'Weapons':{
        'Simple Melee Weapons':{'type':'M','weaponCategory':'simple','weapon':True},
        'Simple Ranged Weapons':{'type':'R','weaponCategory':'simple','weapon':True},
        'Martial Melee Weapons':{'type':'M','weaponCategory':'martial','weapon':True},
        'Martial Ranged Weapons':{'type':'R','weaponCategory':'martial','weapon':True}},
    'Armor':{
        'Light Armor (1 Minute to Don or Doff)':{'type':'LA','armor':True},
        'Medium Armor (5 Minutes to Don and 1 Minute to Doff)':{'type':'MA','armor':True},
        'Heavy Armor (10 Minutes to Don and 5 Minutes to Doff)':{'type':'HA','armor':True},
        'Shield (Utilize Action to Don or Doff)':{'type':'S'}}}
TYPE_NAMES={'M':'Melee Weapon','R':'Ranged Weapon','LA':'Light Armor','MA':'Medium Armor','HA':'Heavy Armor','S':'Shield'}


def source_categories(pdf):
    source=Source(pdf);result={}
    for caption,label,count in [('Weapons','Quarterstaff',38),('Armor','Shield',13)]:
        source.table_row(caption,label)
        table=source.table_cache[caption]
        wanted_headers={'Weapons':['Name','Damage','Properties','Mastery','Weight','Cost'],
                        'Armor':['Armor','Armor Class (AC)','Strength','Stealth','Weight','Cost']}[caption]
        if table['headers']!=wanted_headers:raise ValueError(('Source columns changed',caption))
        seen=[];category=None;rows=0
        for row in table['rows']:
            cells=[c['text'] for c in row['cells']]
            if row['colspans']==[6]:
                category=cells[0]
                if category not in GROUPS[caption]:raise ValueError(('Unreviewed category',caption,category))
                seen.append(category);continue
            if row['colspans']!=[1]*6 or category is None:raise ValueError(('Unassigned source row',caption,cells))
            name=cells[0]
            if name in result:raise ValueError(('Duplicate printed equipment identity',name))
            result[name]={'facts':dict(GROUPS[caption][category]),'table':caption,'source_category':category,
                          'source_page':row['page'],'source_cells':cells,'source_row_bounds':row['bounds']}
            rows+=1
        if seen!=list(GROUPS[caption]) or rows!=count:raise ValueError(('Incomplete printed table',caption,seen,rows))
    return result


def audit_payload(payload,categories):
    records=[];errors=[];base=payload['baseitem'];helpers=payload['itemType']
    for name,source in categories.items():
        matches=[r for r in base if r['name']==name]
        if len(matches)!=1:
            errors.append({'name':name,'error':'Missing or duplicate printed base item'});continue
        item=matches[0];facts={};differences=[]
        for key,expected in source['facts'].items():
            if key=='type':expected+='|'+SOURCE_ID
            actual=item.get(key)
            equal=actual==expected and (not isinstance(expected,bool) or type(actual) is bool)
            if equal:facts[key]={'value':actual,'expected':expected,'matches':True}
            else:differences.append({'field':key,'value':actual,'expected':expected})
        code=source['facts']['type']
        typed=[h for h in helpers if h['abbreviation']==code and h['source']==SOURCE_ID]
        if len(typed)!=1 or typed[0]['name']!=TYPE_NAMES[code]:
            differences.append({'field':'type','error':'Missing, ambiguous or incorrectly named typed helper UID'})
        incompatible=('armor',) if source['table']=='Weapons' else ('weapon','weaponCategory')
        if code=='S':incompatible+=('armor',)
        for key in incompatible:
            if key not in item:continue
            if key in {'weapon','armor'} and item[key] is False:continue
            differences.append({'field':key,'value':item[key],
              'error':'Classification contradicts the printed equipment category'})
        record={'file':'items-base.json','kind':'baseitem','name':name,**source,
                'verified_metadata':facts,'differences':differences,'passed':not differences}
        records.append(record)
        if differences:errors.append({'name':name,'differences':differences})
    for item in base:
        if item['name'] not in categories and (item.get('weapon') or item.get('armor') or item.get('type','').split('|')[0] in TYPE_NAMES):
            errors.append({'name':item['name'],'error':'Unprinted base weapon/armor classification'})
    return {'records':records,'errors':errors,'passed':not errors and len(records)==len(categories)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('pdf','data','out'):parser.add_argument('--'+key,type=Path,required=True)
    args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest()
    if pdf_hash!=PDF_SHA256:raise ValueError('Official PDF changed')
    path=args.data/'data/items-base.json'
    with fitz.open(args.pdf) as pdf:categories=source_categories(pdf)
    result=audit_payload(json.loads(path.read_text(encoding='utf8')),categories)
    report={'scope':__doc__,'pdf_sha256':pdf_hash,'input_sha256':{'items-base.json':hashlib.sha256(path.read_bytes()).hexdigest()},
            'source_weapon_rows':38,'source_armor_and_shield_rows':13,**result}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'records':len(result['records']),'verified_fields':sum(len(r['verified_metadata']) for r in result['records']),
                      'errors':result['errors'],'passed':result['passed']}))
    raise SystemExit(0 if result['passed'] else 1)


if __name__=='__main__':main()
