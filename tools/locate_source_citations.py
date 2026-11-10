"""Locate source citation pages independently in the pinned official PDF.

This is a citation-locator report, not a whole-record content certificate. It
never copies a candidate's old commercial page number or chooses a fuzzy match.
Unresolved names/aliases and ambiguous pages remain explicit pending records.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
import unicodedata

import fitz

sys.path.insert(0,str(Path(__file__).resolve().parent))
from rule_table_grid import PDF_SHA256
from build_srd import UPSTREAM
from rule_table_grid import Source as CellSource
from verify_rule_prose import decode

ITEM_KINDS={'item','baseitem','itemGroup','magicvariant','itemType','itemProperty','itemMastery','itemEntry','card','deck'}
CLASSES=('Barbarian','Bard','Cleric','Druid','Fighter','Monk','Paladin','Ranger','Rogue','Sorcerer','Warlock','Wizard')
ROW_TABLES={'Weapons':'Weapons','Armor':'Armor','gear':'Adventuring Gear','Ammunition':'Ammunition',
  'arcane_focus':'Arcane Focuses','druidic_focus':'Druidic Focuses','holy_symbol':'Holy Symbols',
  'mounts':'Mounts and Other Animals','vehicles_land':'Tack, Harness, and Drawn Vehicles',
  'Airborne and Waterborne Vehicles':'Airborne and Waterborne Vehicles','food':'Food, Drink, and Lodging','wine':'Food, Drink, and Lodging'}
HELPER_TABLES={'Ammunition':'Ammunition','Food and Drink':'Food, Drink, and Lodging','Adventuring Gear':'Adventuring Gear',
  'Heavy Armor':'Armor','Light Armor':'Armor','Medium Armor':'Armor','Melee Weapon':'Weapons','Mount':'Mounts and Other Animals',
  'Tack and Harness':'Tack, Harness, and Drawn Vehicles','Vehicle (Land)':'Tack, Harness, and Drawn Vehicles'}
MAGIC_CATEGORY_ROWS={'Potion':'Potions','Rod':'Rods','Ring':'Rings','Scroll':'Scrolls','Wand':'Wands'}


def canon(text):
    return ' '.join(unicodedata.normalize('NFKC',text).translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':''})).split())


def heading_key(text):
    text=canon(text).removesuffix('.')
    text=re.sub(r'^Level \d+:\s*','',text)
    text=re.sub(r'^(?:Barbarian|Bard|Cleric|Druid|Fighter|Monk|Paladin|Ranger|Rogue|Sorcerer|Warlock|Wizard) Subclass:\s*','',text)
    text=re.sub(r' \[[^\[\]]+\]$','',text)
    text=re.sub(r' \(Cost: [^)]+\)$','',text)
    return text.removesuffix('.').casefold()


def is_bold(span):return 'Bold' in span['font'] or 'Semibold' in span['font']


class Source:
    def __init__(self,pdf):
        self.pdf=pdf;self.pages={};self.headings=[]
        for number,page in enumerate(pdf,1):
            lines=[]
            for b,block in enumerate(page.get_text('dict')['blocks']):
                for n,line in enumerate(block.get('lines',[])):
                    spans=line['spans']
                    if not spans or not ''.join(s['text'] for s in spans).strip():continue
                    if all(s['color']==0x808285 for s in spans):continue
                    entry={'page':number,'block':b,'line':n,'text':''.join(s['text'] for s in spans).strip(),
                      'origin':list(spans[0]['origin']),'bbox':list(line['bbox']),'fonts':[s['font'] for s in spans],
                      'sizes':[s['size'] for s in spans],'colors':[s['color'] for s in spans],
                      'column':int(spans[0]['origin'][0]>=300),'spans':spans}
                    lines.append(entry)
                    visible_spans=[s for s in spans if s['text'].strip()]
                    if not visible_spans:continue
                    first=visible_spans[0]
                    if is_bold(first) and first['size']>=10.5:
                        self.headings.append({**{k:v for k,v in entry.items() if k!='spans'},'strength':'heading'})
                    elif first['font'].startswith('Cambria') and is_bold(first) and first['size']>=9.5:
                        prefix=[]
                        for s in visible_spans:
                            if not is_bold(s):break
                            prefix.append(s['text'])
                        text=''.join(prefix).strip()
                        if text:self.headings.append({**{k:v for k,v in entry.items() if k!='spans'},'text':text,'strength':'inline_bold_prefix'})
            self.pages[number]=lines
        # Wrapped printed headings remain a sequence of actual source lines.
        single=list(self.headings)
        for i,start in enumerate(single):
            if start['strength']!='heading':continue
            selected=[start]
            for following in single[i+1:i+3]:
                previous=selected[-1]
                if (following['strength']!='heading' or following['page']!=start['page'] or following['fonts']!=start['fonts']
                    or following['sizes']!=start['sizes'] or abs(following['origin'][0]-start['origin'][0])>.5
                    or not 0<following['origin'][1]-previous['origin'][1]<max(start['sizes'])*1.6):break
                selected.append(following)
                text=selected[0]['text']
                for line in selected[1:]:text+=('' if text.rstrip().endswith('/') else ' ')+line['text']
                self.headings.append({**start,'text':text,'source_lines':list(selected)})
        self.by_key={}
        for heading in self.headings:self.by_key.setdefault(heading_key(heading['text']),[]).append(heading)
        starts={}
        for name in CLASSES:
            matches=[h for h in self.by_key.get(name.casefold(),[]) if h['fonts']==['GillSans-SemiBold'] and h['sizes']==[18.0] and 28<=h['page']<83]
            if len(matches)!=1:raise ValueError(('Class source boundary ambiguous',name))
            starts[name]=self.position(matches[0])
        ordered=sorted(starts.items(),key=lambda t:t[1])
        self.class_bounds={name:(start,(ordered[i+1][1] if i+1<len(ordered) else (83,0,0))) for i,(name,start) in enumerate(ordered)}
        self.views={};self.cell_source=CellSource(pdf);self.table_cache={}

    @staticmethod
    def position(line):return line['page'],line['column'],line['origin'][1]

    def body_matches(self,page,text):
        if page not in self.views:
            lines=self.pages[page]
            native='\n'.join(l['text'] for l in lines)
            columns='\n'.join(l['text'] for col in (0,1) for l in lines if l['column']==col)
            self.views[page]=[canon(t) for raw in (native,columns) for t in (raw,re.sub(r'(?<=\w)-\n(?=\w)','',raw))]
        return any(canon(text) in view for view in self.views[page])

    def candidates(self,target,kind,record):
        candidates=list(self.by_key.get(heading_key(target),[]))
        parent=record.get('className')
        if kind=='class':parent=record['name']
        if kind=='optionalfeature':parent={'EI':'Warlock','MM':'Sorcerer'}.get(next(iter(record.get('featureType',[])),''))
        if parent in self.class_bounds:
            lo,hi=self.class_bounds[parent];candidates=[h for h in candidates if lo<=self.position(h)<hi]
        elif kind=='spell':candidates=[h for h in candidates if 107<=h['page']<=175 and h['fonts'][0].startswith('GillSans-SemiBold')]
        elif kind=='monster':candidates=[h for h in candidates if h['fonts'][0]=='GillSans-SemiBold' and abs(h['sizes'][0]-14.7732868)<.05]
        elif kind in ITEM_KINDS:candidates=[h for h in candidates if h['page'] in {26,27,197,198} or 89<=h['page']<=(106 if kind=='itemType' else 103) or 209<=h['page']<=254]
        elif kind in {'background','race'}:candidates=[h for h in candidates if 83<=h['page']<=86]
        elif kind=='feat':candidates=[h for h in candidates if 87<=h['page']<=88]
        elif kind=='table':candidates=[h for h in candidates if h['fonts'][0]=='GillSans-SemiBold' and abs(h['sizes'][0]-10.5)<.05]
        elif kind in {'action','condition','disease','status','sense','variantrule','trap','hazard'}:
            candidates=[h for h in candidates if h['page']<28 or 89<=h['page']<=106 or 175<=h['page']<=208]
        strong=[h for h in candidates if h['strength']=='heading']
        return strong or candidates

    def feature_level(self,heading,parent):
        if parent not in self.class_bounds:return None
        lo,hi=self.class_bounds[parent]
        levels=[h for h in self.headings if h['strength']=='heading' and re.match(r'^Level \d+:',h['text'])
          and lo<=self.position(h)<=self.position(heading)<hi]
        return max(levels,key=self.position) if levels else None

    def prose_citation(self,record,kind,target):
        paragraphs=list(prose(record.get('entries',record.get('entriesTemplate',[]))))
        allowed=self.candidates_for_prose(kind,record)
        for paragraph in sorted(paragraphs,key=len,reverse=True):
            if len(paragraph)<40:continue
            matches=[page for page in allowed if self.body_matches(page,paragraph)]
            if matches:
                return {'status':'LOCATED','target':target,'page':matches[0],'basis':'Full retained source paragraph found literally; citation does not assert an independently printed entity heading.',
                  'equivalent_source_pages':matches,'source_paragraph':paragraph}
        return None

    def candidates_for_prose(self,kind,record):
        parent=record.get('className')
        if parent in self.class_bounds:
            lo,hi=self.class_bounds[parent];return range(lo[0],min(hi[0]+1,365))
        if kind in {'action','condition','disease','status','sense','variantrule','trap','hazard'}:
            return [p for p in range(1,209) if p<28 or 89<=p<=106 or 175<=p<=208]
        if kind=='itemType':return range(89,107)
        return []

    def table_row(self,caption,label):
        if caption not in self.table_cache:
            found=self.candidates(caption,'table',{})
            if len({h['page'] for h in found})!=1:raise ValueError(('Ambiguous table citation',caption))
            heading=found[0]
            locator={'name':caption,'caption':caption,'official_page':heading['page'],'heading_lines':heading.get('source_lines',[heading])}
            self.table_cache[caption]=self.cell_source.table(locator)
        table=self.table_cache[caption];key=heading_key(label)
        rows=[row for row in table['rows'] if any(heading_key(cell['text'])==key for cell in row['cells'])]
        if len(rows)==1:
            row=rows[0]
            return {'status':'LOCATED','target':caption,'page':row['page'],'basis':'Printed row identifier in a freshly extracted source cell grid.',
              'printed_identifier':label,'source_cells':[cell['text'] for cell in row['cells']],'source_row_bounds':row['bounds']}
        footnotes=[n for n in table['footnotes'] if re.search(r'\b'+re.escape(canon(label))+r'\b',canon(n['text']),re.I)]
        if len(footnotes)==1:
            return {'status':'LOCATED','target':caption,'page':table['pages'][-1],'basis':'Literal named dialect in the printed language table footnote.',
              'printed_identifier':label,'source_footnote':footnotes[0]}
        return {'status':'PENDING','target':caption,'candidate_pages':table['pages'],'reason':'Missing or ambiguous source row identifier.'}


def prose(value,min_length=40):
    if isinstance(value,str):
        try:text=decode(value)
        except ValueError:return
        if len(text)>=min_length:yield text
    elif isinstance(value,list):
        for v in value:yield from prose(v,min_length)
    elif isinstance(value,dict):
        if value.get('type')=='table':return
        for key in ('entry','entries','items'):
            if key in value:yield from prose(value[key],min_length)


def locate(source,target,kind,record):
    candidates=source.candidates(target,kind,record)
    if kind in {'classFeature','subclassFeature'} and len({h['page'] for h in candidates})>1:
        selected=[]
        for heading in candidates:
            level=source.feature_level(heading,record.get('className'))
            if level and int(re.match(r'^Level (\d+):',level['text'])[1])==record.get('level'):
                selected.append({**heading,'containing_level_heading':level})
        if selected:candidates=selected
    pages=sorted({h['page'] for h in candidates});basis='Exact printed heading in its source category/class scope.'
    if len(pages)>1:
        paragraphs=list(prose(record.get('entries',record.get('entriesTemplate',[])),20))
        for paragraph in paragraphs:
            matches=[p for p in pages if source.body_matches(p,paragraph)]
            if matches:
                pages=matches[:1];basis='Exact printed heading and full retained paragraph on the same source page; first equivalent occurrence.';break
    if len(pages)!=1:return {'status':'PENDING','target':target,'candidate_pages':pages,'reason':'Missing or ambiguous exact source heading.'}
    witnesses=[h for h in candidates if h['page']==pages[0]]
    return {'status':'LOCATED','target':target,'page':pages[0],'basis':basis,'witnesses':witnesses}


def helper_scope(source,record):
    name=record['name']
    if record.get('entries') or record.get('entriesTemplate'):return None
    if name=='Generic Variant' and record.get('abbreviation')=='GV':
        return {'status':'SCHEMA_HELPER','target':name,'page':None,
          'basis':'Empty compatibility helper for the generic-variant schema. No independently printed SRD entity or rule text; remove its inherited commercial page.'}
    if name in MAGIC_CATEGORY_ROWS:
        result=source.table_row('Magic Item Categories',MAGIC_CATEGORY_ROWS[name])
    elif name in HELPER_TABLES:
        result=locate(source,HELPER_TABLES[name],'table',{})
    else:return None
    if result['status']=='LOCATED':
        result.update(status='LOCATED_SCOPE',schema_helper=name,
          basis='Compatibility category label; cite its actual printed category row or containing equipment table. This is not a claim of an independent entity heading.')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True);parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--item-review',type=Path,required=True);parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();assert pdf_hash==PDF_SHA256
    review=json.loads(args.item_review.read_text(encoding='utf8'));assert review['pdf_sha256']==pdf_hash
    for name,digest in review['files_sha256'].items():assert hashlib.sha256((args.data/'data'/name).read_bytes()).hexdigest()==digest
    aliases={(r['file'],r['kind'],r['index']):r['source_name'] for r in review['records']}
    item_records={(r['file'],r['kind'],r['index']):r for r in review['records']}
    results=[];inputs={}
    with fitz.open(args.pdf) as pdf:
        source=Source(pdf)
        for file in sorted((args.data/'data').rglob('*.json')):
            relative=file.relative_to(args.data).as_posix();raw=file.read_bytes();inputs[relative]=hashlib.sha256(raw).hexdigest()
            for kind,records in json.loads(raw).items():
                if not isinstance(records,list):continue
                for index,record in enumerate(records):
                    if not isinstance(record,dict):continue
                    name=record.get('name',record.get('abbreviation'));target=aliases.get((file.name,kind,index),name)
                    if kind=='card':target=record['set']
                    if kind=='classFeature' and name=='Subclass Feature' and not record.get('entries'):
                        target=record['className']+' Features'
                    result=locate(source,target,kind,record)
                    if kind=='skill':result=source.table_row('Skills',name)
                    elif kind=='language':
                        tables=[e for e in record.get('entries',[]) if isinstance(e,dict) and e.get('type')=='table']
                        if tables:result=source.table_row(tables[0]['caption'],name)
                    elif kind=='action' and name=='Don or Doff a Shield':
                        result=source.table_row('Armor',record['entries'][0])
                    if result['status']=='PENDING' and kind in ITEM_KINDS:
                        item_review=item_records.get((file.name,kind,index),{})
                        row_queries=[e for e in item_review.get('source_evidence',[]) if e.get('table') in ROW_TABLES and e.get('row')]
                        for query in row_queries:
                            row_result=source.table_row(ROW_TABLES[query['table']],query['row'][0])
                            if row_result['status']=='LOCATED':result=row_result;break
                    if result['status']=='PENDING':
                        alternative=source.prose_citation(record,kind,target)
                        if alternative:result=alternative
                    if result['status']=='PENDING' and kind=='itemType':
                        alternative=helper_scope(source,record)
                        if alternative:result=alternative
                    results.append({'file':relative,'kind':kind,'index':index,'name':name,
                      'identity':{k:record[k] for k in ('source','className','subclassShortName','level','set') if k in record},
                      'candidate_record_sha256':hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),**result})
    summary={'records':len(results),'located':sum(r['status']=='LOCATED' for r in results),
      'located_schema_scopes':sum(r['status']=='LOCATED_SCOPE' for r in results),'unprinted_empty_schema_helpers':sum(r['status']=='SCHEMA_HELPER' for r in results),
      'pending':sum(r['status']=='PENDING' for r in results),
      'pending_by_kind':dict(Counter(r['kind'] for r in results if r['status']=='PENDING'))}
    manifest=json.loads((args.data/'manifest.json').read_text(encoding='utf8'))
    report={'official_pdf_sha256':pdf_hash,'upstream_commit':UPSTREAM,'scope':__doc__,'input_sha256':inputs,'summary':summary,'records':results}
    args.out.parent.mkdir(parents=True,exist_ok=True);args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':main()
