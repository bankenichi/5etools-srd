"""Extract all printed base-class spell lists without spell-record lookups.

The PDF's captions, painted cells and continuation headers supply all seventy
tables and their literal names, schools and C/R/M flags. Spell header class
labels are separate source statements and never override these tables.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

import fitz

sys.path.insert(0,str(Path(__file__).resolve().parent))
from locate_rule_tables import locate
from rule_table_grid import Source,PDF_SHA256,is_footer
from verify_rule_tables import canonical_model

CLASSES=('Bard','Cleric','Druid','Paladin','Ranger','Sorcerer','Warlock','Wizard')
SOURCE_ID='SRD521'


def levels(name):return range(1,6) if name in ('Paladin','Ranger') else range(10)


def table_inventory():
    return [{'name':caption,'caption':caption,'source':SOURCE_ID,'class':name,'spell_level':level}
      for name in CLASSES for level in levels(name)
      for caption in [f'Level {level} {name} Spells' if level else f'Cantrips (Level 0 {name} Spells)']]


def extract(pdf):
    source=Source(pdf);inventory=table_inventory();locators,errors=locate(pdf,inventory)
    if errors:raise ValueError(errors)
    assert len(locators)==70
    records=[];evidence=[]
    for name in CLASSES:
        matches=[line for number in range(1,len(pdf)+1) for line in source.page(number)['lines']
          if line['text'].strip()==name+' Spell List' and line['fonts']==['GillSans-SemiBold'] and line['sizes']==[14.0]]
        if len(matches)!=1:raise ValueError(('Missing or ambiguous class spell-list section',name))
        heading=matches[0];member_locators=[l for l in locators if l['name'] in {t['name'] for t in inventory if t['class']==name}]
        first=member_locators[0]['heading_lines'][0]
        def position(line):return (line['page'],int(line['origin'][0]>=300),line['origin'][1])
        # Cleric starts its first table in the next physical column; Warlock
        # starts on the next page. Source reading order is column, then page.
        lines=[l for number in range(heading['page'],first['page']+1) for l in source.page(number)['lines']
          if position(heading)<position(l)<position(first) and not is_footer(l)]
        if not lines or any(not all(f.startswith('Cambria') for f in l['fonts']) for l in lines):
            raise ValueError(('Unexpected class spell-list introduction typography',name))
        if len({position(l)[:2] for l in lines})!=1:raise ValueError(('Intro paragraph crosses an unreviewed physical frame',name))
        intro=source.text([c for l in lines for c in l['chars']])
        if not intro['text'].startswith('This section presents the '+name+' spell list.'):
            raise ValueError(('Missing introductory source paragraph',name))
        tables=[];models=[]
        for locator in member_locators:
            extracted=source.table(locator);model=canonical_model(extracted,locator)
            if model['headers']!=['Spell','School','Special'] or model['spanning_headers'] or model['footnotes']:
                raise ValueError(('Unreviewed class spell-list structure',locator['name']))
            if any(r['colspans']!=[1,1,1] for r in model['rows']):raise ValueError(('Unexpected spell-list colspan',locator['name']))
            if any(j['basis'].startswith('UNRESOLVED') for row in extracted['rows'] for cell in row['cells'] for j in cell['layout_joins']):
                raise ValueError(('Unresolved physical spelling join',locator['name']))
            table={'type':'table','caption':model['caption'],'source':SOURCE_ID,'page':locator['official_page'],
              'colLabels':model['headers'],'rows':[row['cells'] for row in model['rows']]}
            tables.append(table);models.append(model)
        if any(j['basis'].startswith('UNRESOLVED') for j in intro['layout_joins']):raise ValueError(('Unresolved introductory spelling join',name))
        # A table's intro is an existing 5etools entry-schema field. Keep the
        # section's printed legend once, before its first level table.
        tables[0]['intro']=[intro['text']]
        records.append({'type':'tableGroup','name':heading['text'].strip(),'source':SOURCE_ID,'page':heading['page'],'srd52':True,'tables':tables})
        evidence.append({'class':name,'section_heading':{k:v for k,v in heading.items() if k!='chars'},'intro':intro,'source_tables':models})
    assert len(records)==8 and sum(len(t['rows']) for g in records for t in g['tables'])==875
    return records,evidence


def verify(candidate,official):
    errors=[]
    if len(candidate)!=8:errors.append('Expected all eight class spell-list groups')
    names=Counter(g.get('name') for g in candidate)
    expected=Counter(g['name'] for g in official)
    if names!=expected:errors.append('Missing, duplicate or unprinted class spell-list group')
    for actual,wanted in zip(candidate,official):
        if actual!=wanted:errors.append('Literal source content, table inventory or metadata differs: '+str(actual.get('name')))
    return errors


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--data',type=Path);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    with fitz.open(args.pdf) as pdf:groups,evidence=extract(pdf)
    report={'official_pdf_sha256':pdf_hash,'scope':__doc__,'table_groups':groups,'evidence':evidence,
      'summary':{'groups':len(groups),'tables':sum(len(g['tables']) for g in groups),'rows':sum(len(t['rows']) for g in groups for t in g['tables']),
        'class_rows':{name:sum(len(t['rows']) for g in groups if g['name']==name+' Spell List' for t in g['tables']) for name in CLASSES}}}
    if args.data:
        file=args.data/'data/generated/gendata-tables.json';payload=json.loads(file.read_text(encoding='utf8'))
        errors=verify(payload.get('tableGroup',[]),groups)
        report.update(input_sha256=hashlib.sha256(file.read_bytes()).hexdigest(),errors=errors,passed=not errors)
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'summary':report['summary'],**{k:report[k] for k in ('errors','passed') if k in report}},ensure_ascii=False))
    if args.data and errors:raise SystemExit(1)


if __name__=='__main__':main()
