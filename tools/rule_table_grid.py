"""Recover source table cells from the official PDF's painted cell rectangles.

The source geometry, font styles and repeated headers determine rows, columns,
panels and continuations. Candidate JSON rows are never extraction inputs.
This extraction report is not a release certificate until its diagnostics,
footnotes and comparison to retained data are reviewed.
"""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import re

import fitz

PDF_SHA256='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87'
FILLS=[(.9032272696,.9066758156,.9101853967),(.9373769760,.9396658540,.9419088960)]
FRACTIONS={'1/2':'½','1/4':'¼','3/4':'¾','1/8':'⅛','3/8':'⅜','5/8':'⅝','7/8':'⅞','1/3':'⅓','2/3':'⅔'}
REVIEWED_JOINS={'indefi-\nnitely':'indefinitely','emo-\ntion':'emotion'}


def is_footer(line):
    text=line['text'].strip()
    return line['bbox'][1]>735 and (text==str(line['page']) or 'System Reference Document 5.2.1' in text)


def main_font(line):
    return all(font.startswith('GillSans') for font in line['fonts']) and any(abs(size-9.5)<.05 for size in line['sizes']) and max(line['sizes'])<9.55


def header_font(line):
    return all(font.startswith('GillSans') and 'SemiBold' in font for font in line['fonts']) and all(min(abs(size-9.25),abs(size-9.5))<.05 for size in line['sizes'])


def box_chars(chars,box):
    x0,y0,x1,y1=box
    return [c for c in chars if x0-.05<=c['origin'][0]<x1-.05 and y0-.05<=c['origin'][1]<y1-.05]


class Source:
    def __init__(self,pdf):
        self.pdf=pdf;self.cache={}
        self.words={w.casefold() for page in pdf for w in re.findall(r'[A-Za-z]+(?:-[A-Za-z]+)*',page.get_text())}

    def page(self,number):
        if number in self.cache:return self.cache[number]
        page=self.pdf[number-1];lines=[];chars=[]
        for b,block in enumerate(page.get_text('rawdict')['blocks']):
            for n,line in enumerate(block.get('lines',[])):
                row=[];fonts=[];sizes=[]
                for s,span in enumerate(line['spans']):
                    fonts.append(span['font']);sizes.append(span['size'])
                    for k,char in enumerate(span['chars']):
                        item={**char,'id':[number,b,n,s,k],'font':span['font'],'size':span['size']}
                        row.append(item);chars.append(item)
                lines.append({'page':number,'block':b,'line':n,'text':''.join(c['c'] for c in row),
                  'bbox':list(line['bbox']),'origin':list(row[0]['origin']),'fonts':fonts,'sizes':sizes,'chars':row})
        grids=[]
        for shape in page.get_drawings():
            fill=shape.get('fill');rect=shape['rect']
            if not fill or len(fill)!=3 or not any(all(abs(a-b)<.001 for a,b in zip(fill,color)) for color in FILLS):continue
            cells=[list(item[1]) for item in shape['items'] if item[0]=='re']
            if rect.width<90 or not cells:continue
            groups=collections.defaultdict(list)
            for cell in cells:groups[(round(cell[1],2),round(cell[3],2))].append(cell)
            rows=[{'bounds':[min(c[0] for c in cells),top,max(c[2] for c in cells),bottom],
                   'cells':sorted(cells,key=lambda c:c[0])} for (top,bottom),cells in sorted(groups.items())]
            detailed=max(rows,key=lambda row:len(row['cells']))
            grid=[detailed['cells'][0][0]]+[cell[2] for cell in detailed['cells']]
            grids.append({'page':number,'bounds':list(rect),'rows':rows,'grid_x':grid,'paint_seqno':shape['seqno']})
        result={'lines':lines,'chars':chars,'grids':grids};self.cache[number]=result;return result

    def text(self,chars):
        if not chars:return {'text':'','raw_lines':[],'layout_joins':[],'fraction_glyphs':[],'source_char_ids':[]}
        # Preserve native text lines so a raised footnote marker remains after
        # its word instead of becoming an earlier, separate text line.
        baselines=collections.defaultdict(list)
        for char in chars:baselines[tuple(char['id'][:3])].append(char)
        rendered=[];fractions=[]
        ordered=sorted(baselines.values(),key=lambda row:(round(max(c['origin'][1] for c in row),2),min(c['origin'][0] for c in row)))
        for row in ordered:
            row.sort(key=lambda c:(c['origin'][0],c['id']));text=[];i=0
            while i<len(row):
                found=False
                for encoded,glyph in FRACTIONS.items():
                    part=row[i:i+len(encoded)]
                    if (len(part)==len(encoded) and ''.join(c['c'] for c in part)==encoded
                        and all(abs(c['bbox'][2]-c['bbox'][0])<.001 for c in part[1:])):
                        text.append(glyph);fractions.append({'glyph':glyph,'pdf_mapping':encoded,'source_char_ids':[c['id'] for c in part]});i+=len(part);found=True;break
                if not found:text.append(row[i]['c']);i+=1
            rendered.append(''.join(text).strip())
        raw='\n'.join(rendered);joins=[]
        def hyphen(match):
            left,right=match[1],match[2];joined=left+right;compound=left+'-'+right
            choices=[w for w in [joined,compound] if w.casefold() in self.words]
            if match[0] in REVIEWED_JOINS:chosen=REVIEWED_JOINS[match[0]];basis='Reviewed physical source word split.'
            elif len(choices)==1:chosen=choices[0];basis='Spelling appears unbroken elsewhere in the official PDF.'
            else:chosen=compound;basis='UNRESOLVED layout hyphen: manual source review required.'
            joins.append({'printed':match[0],'chosen':chosen,'basis':basis});return chosen
        raw=re.sub(r'(\w+)-\n(\w+)',hyphen,raw)
        if '/\n' in raw:joins.append({'printed':'/\n','chosen':'/','basis':'Physical line wrap after a slash.'});raw=raw.replace('/\n','/')
        return {'text':' '.join(raw.split()),'raw_lines':rendered,'layout_joins':joins,'fraction_glyphs':fractions,'source_char_ids':[c['id'] for c in chars]}

    def panel(self,grid,floor):
        number=grid['page'];page=self.page(number);x0,_,x1,_=grid['bounds'];full=x1-x0>300
        physical=(30,565) if full else ((30,300) if x0<300 else (300,565))
        lines=sorted([line for line in page['lines'] if physical[0]<=line['origin'][0]<physical[1] and not is_footer(line)],key=lambda l:(l['origin'][1],l['origin'][0]))
        above=[line for line in lines if x0-.2<=line['origin'][0]<x1 and floor<line['origin'][1]<grid['bounds'][1]-.1]
        # Headers can mix regular and semibold styles. Wrapped header lines
        # use 12.5-point leading; the first body row is separated by the
        # independent 15.12-point row spacing. Use that first header cluster,
        # rather than mistaking regular header text for a body row.
        candidates=[l for l in above if all(f.startswith('GillSans') for f in l['fonts']) and any(min(abs(s-9.25),abs(s-9.5))<.05 for s in l['sizes']) and max(l['sizes'])<9.55]
        baseline_groups=[]
        for y in sorted({l['origin'][1] for l in candidates}):
            if not baseline_groups or y-baseline_groups[-1][-1]>.5:baseline_groups.append([])
            baseline_groups[-1].append(y)
        header_end=baseline_groups[0][-1] if baseline_groups else floor
        for group in baseline_groups[1:]:
            if group[0]-header_end>13.2:break
            header_end=group[-1]
        strong=[l for l in candidates if any(abs(s-9.25)<.05 for s in l['sizes']) and all('SemiBold' in f for f in l['fonts'])]
        if strong:header_end=max(l['origin'][1] for l in strong)
        headers=[l for l in candidates if l['origin'][1]<=header_end+.5]
        if not headers:raise ValueError(('No independent header above source grid',number,grid['bounds']))
        header_bottom=max(l['origin'][1] for l in headers)
        header_chars=[c for l in headers for c in l['chars']]
        columns=grid['grid_x']
        # Continuous header text crossing real cell boundaries is a spanner;
        # ordinary labels separated by a large text-position gap stay separate.
        spanners=[];spanner_ids=set()
        for line in headers:
            segments=[]
            for c in line['chars']:
                if c['c'].isspace() and c['bbox'][2]-c['bbox'][0]>5:
                    segments.append([]);continue
                if not segments or (segments[-1] and c['origin'][0]-segments[-1][-1]['bbox'][2]>5):segments.append([])
                segments[-1].append(c)
            for segment in segments:
                if not segment:continue
                touched=[i for i,(left,right) in enumerate(zip(columns,columns[1:])) if any(c['c'].strip() and left-.1<=c['origin'][0]<right-.1 for c in segment)]
                if len(touched)>1:
                    spanners.append({'columns':touched,**self.text(segment)})
                    spanner_ids.update(tuple(c['id']) for c in segment)
        leaf_chars=[c for c in header_chars if tuple(c['id']) not in spanner_ids]
        header_cells=[self.text([c for c in leaf_chars if left-.1<=c['origin'][0]<right-.1]) for left,right in zip(columns,columns[1:])]
        rows=[]
        leading=[c for line in above if main_font(line) and line['origin'][1]>header_bottom+.2 for c in line['chars'] if x0-.1<=c['origin'][0]<x1-.1]
        if any(c['c'].strip() for c in leading):rows.append({'bounds':[x0,header_bottom+.3,x1,grid['bounds'][1]],'derived_from':'unshaded leading row before first painted row','painted_cells':None})
        for i,painted in enumerate(grid['rows']):
            if i:
                previous=grid['rows'][i-1]['bounds']
                rows.append({'bounds':[x0,previous[3],x1,painted['bounds'][1]],'derived_from':'unshaded row between independently painted rows','painted_cells':None})
            rows.append({'bounds':painted['bounds'],'derived_from':'painted cell rectangles','painted_cells':painted['cells']})
        last=grid['rows'][-1]['bounds'][3];tail=[];stop=None
        for line in lines:
            if line['origin'][1]<=last+.2:continue
            if not main_font(line):stop=line;break
            tail.extend(c for c in line['chars'] if x0-.1<=c['origin'][0]<x1-.1)
        if any(c['c'].strip() for c in tail):
            end=stop['origin'][1]-.3 if stop else 739
            rows.append({'bounds':[x0,last,x1,end],'derived_from':'unshaded final row before next typographic boundary','painted_cells':None})
        used=[]
        by_id={tuple(c['id']):c for c in page['chars']}
        for row in rows:
            glyphs=box_chars(page['chars'],row['bounds'])
            glyphs=[c for c in glyphs if c['font'].startswith('GillSans') and c['size']<9.55]
            if not any(c['c'].strip() for c in glyphs):raise ValueError(('Empty source row between painted bounds',number,row['bounds']))
            all_italic=all('Italic' in c['font'] for c in glyphs if c['c'].strip())
            painted=row['painted_cells']
            colspan=(painted and len(painted)==1 and len(columns)>2) or (all_italic and len(columns)>2)
            if colspan:
                row['cells']=[self.text(glyphs)];row['colspans']=[len(columns)-1]
            else:
                row['cells']=[self.text([c for c in glyphs if left-.05<=c['origin'][0]<right-.05]) for left,right in zip(columns,columns[1:])]
                row['colspans']=[1]*(len(columns)-1)
            ids=[tuple(c['id']) for c in glyphs if c['c'].strip()]
            assigned=[tuple(i) for cell in row['cells'] for i in cell['source_char_ids'] if by_id[tuple(i)]['c'].strip()]
            if set(ids)!=set(assigned) or len(assigned)!=len(set(assigned)):
                raise ValueError(('Source cell glyph assignment is not bijective',number,row['bounds']))
            if set(ids).intersection(used):raise ValueError(('Source glyph assigned to multiple rows',number))
            used.extend(ids)
        # Some PDF tables paint an empty spacer as a physical third column.
        # Keep that geometry as evidence, but omit columns with no header or
        # source glyph in any logical row (Coin Values is the current example).
        active=[i for i,h in enumerate(header_cells) if h['text'] or any(row['colspans']==[1]*len(header_cells) and row['cells'][i]['text'] for row in rows)]
        if len(active)<len(header_cells):
            if any(row['colspans']!=[1]*len(header_cells) for row in rows):raise ValueError(('Empty spacer mixed with source colspan rows',number))
            for row in rows:row['cells']=[row['cells'][i] for i in active];row['colspans']=[1]*len(active)
            header_cells=[header_cells[i] for i in active]
        header_ids=[tuple(c['id']) for c in header_chars if c['c'].strip()]
        assigned_headers=[tuple(i) for cell in header_cells+spanners for i in cell['source_char_ids'] if by_id[tuple(i)]['c'].strip()]
        if set(header_ids)!=set(assigned_headers) or len(assigned_headers)!=len(set(assigned_headers)):
            raise ValueError(('Source header glyph assignment is not bijective',number))
        return {**grid,'columns':columns,'headers':header_cells,'spanning_headers':spanners,'active_physical_columns':active,'header_lines':[{k:v for k,v in l.items() if k!='chars'} for l in headers],
          'extracted_rows':rows,'stop':{k:v for k,v in stop.items() if k!='chars'} if stop else None,
          'body_source_char_count':len(used),'header_source_char_count':len(header_ids),'physical_column':list(physical),
          'glyph_assignment_bijective':True}

    def primary(self,locator):
        last=locator['heading_lines'][-1];number=last['page'];x=last['bbox'][0];bottom=last['bbox'][3]
        page=self.page(number)
        choices=[g for g in page['grids'] if abs(g['bounds'][0]-x)<12 and bottom<=g['bounds'][1]+1 and g['bounds'][1]-bottom<80]
        if not choices:raise ValueError(('No painted source table below caption',locator['caption']))
        first=min(choices,key=lambda g:g['bounds'][1]);physical=(30,565) if first['bounds'][2]-first['bounds'][0]>300 else ((30,300) if x<300 else (300,565))
        partners=[g for g in page['grids'] if g is not first and physical[0]<=g['bounds'][0]<physical[1]
          and g['bounds'][0]>first['bounds'][2] and abs(g['bounds'][1]-first['bounds'][1])<35]
        group=sorted([first]+partners,key=lambda g:g['bounds'][0])
        return [self.panel(g,bottom-.5) for g in group]

    def continuation(self,parts):
        last=parts[-1];page_number=last['page'];full=parts[0]['bounds'][2]-parts[0]['bounds'][0]>300
        group=[p for p in parts if p['page']==last['page'] and p['physical_column']==last['physical_column']]
        if any(p['stop'] is not None for p in group):return []
        if not full and last['physical_column'][1]<=300:physical=(300,565)
        else:page_number+=1;physical=(30,565) if full else (30,300)
        if page_number>len(self.pdf):return []
        page=self.page(page_number)
        lines=sorted([l for l in page['lines'] if physical[0]<=l['origin'][0]<physical[1] and not is_footer(l)],key=lambda l:(l['origin'][1],l['origin'][0]))
        if not lines or not header_font(lines[0]):return []
        shapes=[g for g in page['grids'] if physical[0]<=g['bounds'][0]<physical[1] and 35<g['bounds'][1]<100]
        if not shapes:return []
        start=min(shapes,key=lambda g:g['bounds'][1]);partners=[g for g in shapes if g is not start and g['bounds'][0]>start['bounds'][2] and abs(g['bounds'][1]-start['bounds'][1])<35]
        result=[self.panel(g,0) for g in sorted([start]+partners,key=lambda g:g['bounds'][0])]
        expected=[h['text'] for h in parts[0]['headers']]
        if any([h['text'] for h in panel['headers']]!=expected for panel in result):return []
        return result

    def footnotes(self,parts):
        last=parts[-1];group=[p for p in parts if p['page']==last['page'] and p['physical_column']==last['physical_column']]
        left=min(p['bounds'][0] for p in group);right=max(p['bounds'][2] for p in group)
        bottom=max(row['bounds'][3] for p in group for row in p['extracted_rows'])
        page=self.page(last['page']);selected=[]
        lines=sorted([l for l in page['lines'] if left-.2<=l['origin'][0]<right and l['origin'][1]>bottom and not is_footer(l)],key=lambda l:(l['origin'][1],l['origin'][0]))
        for line in lines:
            if not all(f.startswith('GillSans') for f in line['fonts']) or not 7.5<=max(line['sizes'])<=9:break
            selected.append(line)
        notes=[];current=[]
        for line in selected:
            if current and line['text'].lstrip().startswith(('*','†','‡')):
                notes.append(self.text([c for l in current for c in l['chars']]));current=[]
            current.append(line)
        if current:notes.append(self.text([c for l in current for c in l['chars']]))
        return notes

    def table(self,locator):
        parts=self.primary(locator)
        for _ in range(8):
            more=self.continuation(parts)
            if not more:break
            parts+=more
        else:raise ValueError(('Too many source continuation frames',locator['caption']))
        if locator['caption']=='Travel Pace':
            # Visually reviewed p12: the left-aligned parent heading applies
            # to Minute/Hour/Day. Its glyphs only reach two of those columns;
            # the third belongs to the same printed distance header group.
            span=parts[0]['spanning_headers']
            assert len(span)==1 and span[0]['text']=='Distance Traveled Per …' and span[0]['columns']==[1,2]
            span[0].update(columns_touched_by_glyphs=[1,2],columns=[1,2,3],
              reviewed_layout_note='PDF p12 visually reviewed: parent distance heading spans the Minute, Hour and Day columns.')
        headers=[h['text'] for h in parts[0]['headers']];rows=[]
        for panel in parts:
            current=[h['text'] for h in panel['headers']]
            if current!=headers:raise ValueError(('Panel header mismatch',locator['caption'],headers,current))
        # Repeated logical panels continue across physical column breaks.
        # CR/XP p256 must finish CR0..13 across both physical frames before
        # reading the second logical panel (CR14..30), not interleave them.
        period=next((n for n in range(1,len(headers)+1) if len(headers)%n==0 and headers==headers[:n]*(len(headers)//n)),len(headers))
        if period<len(headers):
            for start in range(0,len(headers),period):
                for panel in parts:
                    for row in panel['extracted_rows']:
                        if row['colspans']!=[1]*len(headers):raise ValueError(('Colspan across repeated source panels',locator['caption']))
                        cells=row['cells'][start:start+period]
                        if any(cell['text'] for cell in cells):rows.append({'cells':cells,'colspans':[1]*period,'page':panel['page'],'bounds':row['bounds']})
        else:
            for panel in parts:
                rows.extend({**row,'page':panel['page']} for row in panel['extracted_rows'])
        return {'name':locator['name'],'caption':locator['caption'],'headers':headers[:period],'rows':rows,'parts':parts,
          'footnotes':self.footnotes(parts),'pages':sorted({p['page'] for p in parts}),'status':'EXTRACTED_NOT_YET_CERTIFIED'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pdf',type=Path,required=True)
    parser.add_argument('--locators',type=Path,default=Path(__file__).resolve().parents[1]/'source/rule-table-locators.json')
    parser.add_argument('--out',type=Path,required=True);args=parser.parse_args()
    pdf_hash=hashlib.sha256(args.pdf.read_bytes()).hexdigest();locators=json.loads(args.locators.read_text(encoding='utf8'))
    assert pdf_hash==locators['pdf_sha256']==PDF_SHA256
    tables=[];errors=[]
    with fitz.open(args.pdf) as pdf:
        source=Source(pdf)
        for locator in locators['records']:
            try:tables.append(source.table(locator))
            except (AssertionError,ValueError,KeyError,IndexError) as error:errors.append({'name':locator['name'],'caption':locator['caption'],'error':str(error)})
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps({'pdf_sha256':pdf_hash,'scope':__doc__,'tables':tables,'errors':errors},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    print(json.dumps({'extracted_tables':len(tables),'rows':sum(len(t['rows']) for t in tables),'errors':errors},ensure_ascii=False))


if __name__=='__main__':main()
