from __future__ import annotations
import bisect,collections,copy,contextlib,difflib,hashlib,io,json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.stdout.reconfigure(encoding='utf8')
with contextlib.redirect_stdout(io.StringIO()):
    import review_items as a
from item_proof_inputs import require_inputs
from projection_provenance import require_identity_coverage,require_imported_fact
ROOT=a.ROOT

def table_lines(page,x0,y0,x1,y1):
    return [l for l in a.LINES if l['page']==page and x0<=l['origins'][0][0]<=x1 and y0<=l['origins'][0][1]<=y1 and all(f.startswith('GillSans') for f in l['fonts']) and not l['red']]

def rows(page,bounds,breaks):
    lines=table_lines(page,*bounds);starts=[]
    for l in lines:
        x,y=l['origins'][0]
        if bisect.bisect_right(breaks,x)==0:
            # Category headers have no other cells on their baseline.
            if any(abs(q['origins'][0][1]-y)<.3 and bisect.bisect_right(breaks,q['origins'][0][0])>0 for q in lines):starts.append(l)
    starts.sort(key=lambda l:l['origins'][0][1]);out=[]
    for i,l in enumerate(starts):
        y=l['origins'][0][1];end=starts[i+1]['origins'][0][1]-.3 if i+1<len(starts) else bounds[3]+.3
        cells=[[] for _ in range(len(breaks)+1)]
        for q in lines:
            x,yy=q['origins'][0]
            col=bisect.bisect_right(breaks,x)
            if y-.3<=yy<end and (col!=0 or q is l):cells[col].append(q['text'])
        rendered=[a.join_pdf(c)[0] for c in cells]
        out.append({'page':page,'baseline':y,'cells':rendered,'raw_cells':cells})
    return out

TABLES={
 'weapons':rows(91,(49,70,554,742),[130,210,425,475,515]),
 'armor':rows(92,(63,370,541,608),[185,310,375,450,495]),
 'gear':rows(95,(63,70,290,694),[200,250])+rows(95,(313,60,544,687),[450,500]),
 'ammunition':rows(96,(63,75,290,145),[130,175,220,260]),
 'arcane_focus':rows(96,(63,315,290,385),[200,255]),
 'druidic_focus':rows(97,(63,620,290,660),[220,260]),
 'holy_symbol':rows(97,(313,517,542,557),[470,510]),
 'mounts':rows(100,(313,190,542,310),[400,490]),
 'vehicles_land':rows(100,(313,355,542,520),[450,495]),
 'vehicles_large':rows(101,(63,70,542,180),[130,170,210,270,335,365,400,490]),
 'food':rows(101,(313,612,425,660),[390]),
 'wine':rows(102,(179,70,291,107),[250]),
}
(ROOT/'printed-gear-table-rows.json').write_text(json.dumps(TABLES,ensure_ascii=False,indent=2)+'\n',encoding='utf8')

def number(text):
    text=text.replace(',','').replace('½','.5').replace('¼','.25')
    if text in ['—','']:return None
    if text.startswith('1/2'):return .5
    if text.startswith('1/4'):return .25
    return float(re.search(r'[-\d.]+',text)[0])
def cost(text):
    m=re.fullmatch(r'([\d,.]+) (CP|SP|GP|PP)',text)
    return float(m[1].replace(',',''))*{'CP':1,'SP':10,'GP':100,'PP':1000}[m[2]] if m else None
def weight(text):return number(text) if text!='Varies' else None

by_name={r['name']:r for fn,d in a.DATA.items() for kind,rs in d.items() if isinstance(rs,list) for r in rs if 'name' in r and kind in ['item','baseitem']}
reviews=copy.deepcopy(a.RESULT)
lookup={(r['file'],r['kind'],r['index']):r for r in reviews}
for r in reviews:r.update(verified_metadata={},metadata_differences=[],source_evidence=[])
def entry_for(name):
    for fn,d in a.DATA.items():
        for kind in ['item','baseitem']:
            for i,q in enumerate(d.get(kind,[])):
                if q.get('name')==name:return lookup[(fn,kind,i)],q
    raise KeyError(name)
def verify(r,q,key,expected,evidence):
    if key not in q:
        if expected is not None:r['metadata_differences'].append({'field':key,'official_expected':expected,'staged':None,'source':evidence})
        return
    actual=q[key]
    equal=actual==expected
    if key=='strength':equal=str(actual)==str(expected)
    if key=='reqAttune' and isinstance(actual,str) and isinstance(expected,str):
        rendered=a.decode(actual,q)
        equal=a.canonical(rendered).casefold()==a.canonical(expected).casefold()
        if equal and rendered!=expected:r.setdefault('metadata_typography_differences',[]).append({'field':key,'printed':expected,'staged_rendered':rendered})
    if equal:
        r['verified_metadata'][key]={'value':actual,'source':evidence};r['metadata_not_proved'].pop(key,None)
    else:r['metadata_differences'].append({'field':key,'official_expected':expected,'staged':actual,'source':evidence})

PROP={'A':'Ammunition','F':'Finesse','H':'Heavy','L':'Light','LD':'Loading','R':'Reach','T':'Thrown','2H':'Two-Handed','V':'Versatile'}
DAMAGE={'B':'Bludgeoning','P':'Piercing','S':'Slashing'}
def helper_uid(kind,field,name):
    matches=[q for q in a.DATA['items-base.json'][kind] if q.get(field)==name]
    assert len(matches)==1,('Missing or ambiguous source helper',kind,name)
    return name+'|'+matches[0]['source']
for row in TABLES['weapons']:
    c=row['cells'];name=c[0]
    if name not in by_name:continue
    r,q=entry_for(name);ev={'page':91,'table':'Weapons','row':c,'baseline':row['baseline']};r['source_evidence'].append(ev)
    dmg=re.fullmatch(r'(\S+) (Bludgeoning|Piercing|Slashing)',c[1]);verify(r,q,'dmg1',dmg[1],ev);verify(r,q,'dmgType',{v:k for k,v in DAMAGE.items()}[dmg[2]],ev)
    verify(r,q,'weight',weight(c[4]),ev);verify(r,q,'value',cost(c[5]),ev)
    verify(r,q,'mastery',[helper_uid('itemMastery','name',c[3])],ev)
    official_props=[]
    for code,label in PROP.items():
        if label in c[2]:official_props.append(helper_uid('itemProperty','abbreviation',code))
    actual_props=q.get('property',[])
    # Order is presentation metadata, not a rule difference.
    if {p.get('uid') if isinstance(p,dict) else p for p in actual_props}==set(official_props):
        r['verified_metadata']['property']={'value':actual_props,'source':ev};r['metadata_not_proved'].pop('property',None)
    else:r['metadata_differences'].append({'field':'property','official_expected':official_props,'staged':actual_props,'source':ev})
    if m:=re.search(r'Range (\d+/\d+)',c[2]):verify(r,q,'range',m[1],ev)
    if m:=re.search(r'Versatile \(([^)]+)\)',c[2]):verify(r,q,'dmg2',m[1],ev)
    if name=='Lance':r['limitations'].append('Two-Handed (unless mounted) source exception is represented by a generic property plus extra prose; prose must be source-literal to meet user goal.')
    r['body_status']='verified_printed_table_record_with_no_prose' if not q.get('entries') else 'confirmed_nonliteral_derived_prose'
    if name=='Lance':r['official_body']='Heavy, Reach, Two-Handed (unless mounted)';r['differences']=a.diffs(r['official_body'],r['staged_body'])
for row in TABLES['armor']:
    c=row['cells'];name=c[0]
    if name not in by_name:continue
    r,q=entry_for(name);ev={'page':92,'table':'Armor','row':c,'baseline':row['baseline']};r['source_evidence'].append(ev)
    verify(r,q,'ac',int(re.search(r'\d+',c[1])[0]),ev);verify(r,q,'weight',weight(c[4]),ev);verify(r,q,'value',cost(c[5]),ev)
    verify(r,q,'stealth',True if c[3]=='Disadvantage' else None,ev)
    verify(r,q,'strength',int(re.search(r'\d+',c[2])[0]) if c[2]!='—' else None,ev)
    r['body_status']='verified_printed_table_record_with_no_prose'

ALIASES={'Bottle, Glass':'Glass Bottle','Case, Crossbow Bolt':'Crossbow Bolt Case','Case, Map or Scroll':'Map or Scroll Case','Clothes, Fine':'Fine Clothes',"Clothes, Traveler's":"Traveler's Clothes",'Lantern, Bullseye':'Bullseye Lantern','Lantern, Hooded':'Hooded Lantern','Poison, Basic':'Basic Poison','Pot, Iron':'Iron Pot','Ram, Portable':'Portable Ram','Spikes, Iron':'Iron Spikes','Horse, Draft':'Draft Horse','Horse, Riding':'Riding Horse','Feed per day':'Feed (per day)','Stabling per day':'Stabling (per day)','Exotic':'Exotic Saddle','Military':'Military Saddle','Riding':'Riding Saddle','Common':'Common Wine (bottle)','Fine':'Fine Wine (bottle)'}
for table in ['gear','arcane_focus','druidic_focus','holy_symbol','mounts','vehicles_land','food','wine']:
    for row in TABLES[table]:
        c=row['cells'];name=ALIASES.get(c[0],c[0]);name=re.sub(r' \((?:also a Quarterstaff|worn or held|borne on fabric or a Shield|held)\)$','',name)
        if table=='druidic_focus':name={'Sprig of mistletoe':'Sprig of Mistletoe','Wooden staff':'Wooden Staff','Yew wand':'Yew Wand'}.get(name,name)
        if name not in by_name:continue
        r,q=entry_for(name);ev={'page':row['page'],'table':table,'row':c,'baseline':row['baseline']};r['source_evidence'].append(ev)
        verify(r,q,'value',cost(c[-1]),ev)
        if table not in ['food','wine','mounts']:
            if c[1]!='Varies':verify(r,q,'weight',weight(c[1]),ev)
        if table=='mounts':verify(r,q,'carryingCapacity',number(c[1]),ev)
        if not q.get('entries'):r['body_status']='verified_printed_table_record_with_no_prose'

for row in TABLES['vehicles_large']:
    c=row['cells'];name=c[0]
    if name not in by_name:continue
    r,q=entry_for(name);ev={'page':101,'table':'Airborne and Waterborne Vehicles','row':c,'baseline':row['baseline']};r['source_evidence'].append(ev)
    for key,idx in [('value',8),('crew',2),('capPassenger',3),('capCargo',4),('vehAc',5),('vehHp',6),('vehDmgThresh',7)]:
        expected=cost(c[idx]) if key=='value' else number(c[idx]);verify(r,q,key,expected,ev)
    # Different consumers may use mph or converted feet per round. Keep both raw fields for review.
    r['limitations'].append('Source speed is mph; speed/vehSpeed representation needs renderer/consumer-specific interpretation to prove exactness.')
    if not q.get('entries'):r['body_status']='verified_printed_table_record_with_no_prose'

for row in TABLES['ammunition']:
    c=row['cells'];names={'Arrows':('Arrow','Arrows (20)'),'Bolts':('Bolt','Bolts (20)'),'Bullets, Firearm':('Firearm Bullet','Firearm Bullets (10)'),'Bullets, Sling':('Sling Bullet','Sling Bullets (20)'),'Needles':('Needle','Needles (50)')}.get(c[0])
    if not names:continue
    for i,name in enumerate(names):
        r,q=entry_for(name);ev={'page':96,'table':'Ammunition','row':c,'baseline':row['baseline'],'derivation':'printed pack' if i else 'printed pack divided by amount'};r['source_evidence'].append(ev)
        amount=int(c[1]) if not i else 1
        verify(r,q,'weight',weight(c[3])/amount,ev);verify(r,q,'value',cost(c[4])/amount,ev)
        if q.get('entries'):
            r['body_status']='confirmed_nonliteral_derived_prose';r['official_body']='Ammunition is required by a weapon that has the Ammunition property. A weapon’s description specifies the type of ammunition used by the weapon. The Ammunition table lists the different types and the amount you get when you buy them. The table also lists the item that is typically used to store each type; storage must be bought separately.'
            r['differences']=a.diffs(a.canonical(r['official_body']),r['staged_body'])
        else:r['body_status']='verified_printed_table_record_with_no_prose'

# Tool descriptions print weight in the Ability line; remove that metadata from
# body comparison while recording exact price and weight checks separately.
for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']]
    src=a.SOURCES.get(r['source_name'])
    if not src:continue
    if r['kind'] in ['item','baseitem'] and r['name']!='Iron Spike' and re.search(r' \([\d,]+ (?:GP|SP|CP)\)$',r['source_name']):
        m=re.search(r' \(([\d,]+ (?:GP|SP|CP))\)$',r['source_name'])
        verify(r,q,'value',cost(m[1]),{'page':src['heading_lines'][0]['page'],'heading':r['source_name']})
    raw=r.get('official_body','')
    if r['kind'] in ['item','baseitem'] and 'Ability:' in raw and 'Weight:' in raw:
        wm=re.search(r'Weight: ([\d½¼/,]+ lb\.|—|Varies)',raw)
        if wm:
            if wm[1]!='Varies':verify(r,q,'weight',weight(wm[1]),{'pages':r['pages'],'printed':wm[0]})
            raw=raw[:wm.start()]+raw[wm.end():]
        r['official_body']=a.canonical(raw);r['differences']=a.diffs(r['official_body'],r['staged_body'])
        r['body_status']='exact_after_documented_layout_typography_normalization' if not r['differences'] else 'confirmed_content_mismatch'

    if r['kind']=='itemProperty':
        r['official_body']=r['source_name']+'. '+r['official_body'];r['differences']=a.diffs(r['official_body'],r['staged_body'])
        r['body_status']='exact_after_documented_layout_typography_normalization' if not r['differences'] else 'confirmed_content_mismatch'
    if r['kind'] in ['item','baseitem'] and r['source_name'] in ['Gaming Set (Varies)','Musical Instrument (Varies)']:
        source=r['official_body'].split(' Variants:')[0]
        if source==r['staged_body']:
            r.update(body_status='exact_source_excerpts_with_documented_family_projection',projection_note='Printed Ability and Utilize excerpt retained literally; Variants are represented by separate concrete records and their price/weight fields.',projected_official_body=source)
        original_body=a.join_pdf(src['lines'])[0]
        if r['source_name']=='Musical Instrument (Varies)':
            label={'Pan Flute':'pan flute'}.get(r['name'],r['name'].lower())
            pat=(r'(?i)\b'+re.escape(label)+r' \(([\d,]+ GP), ([\d,]+) lb\.\)')
            if vm:=re.search(pat,original_body):
                verify(r,q,'value',cost(vm[1]),{'page':94,'printed':vm[0]});verify(r,q,'weight',float(vm[2]),{'page':94,'printed':vm[0]})

for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']]
    if r['kind']=='itemType' and not q.get('entries'):
        r['body_status']='structural_type_no_own_prose';r['limitations'].append('Type taxonomy record contains no visible rules prose; its name/code is an application classification, not a printed standalone SRD item.')
    if r['kind']=='item' and r['name'] in ['Amulet','Emblem','Reliquary']:
        ev=next((ev for ev in r['source_evidence'] if ev.get('table')=='holy_symbol'),None)
        if ev:r.update(source_name='Holy Symbols / '+r['name'],pages=[97],official_body=' '.join(ev['row']),body_status='confirmed_nonliteral_derived_prose',differences=a.diffs(' '.join(ev['row']),r['staged_body']))
    if r['kind']=='item' and r['name'] in ['Exotic Saddle','Military Saddle','Riding Saddle']:
        src=a.SOURCES['Saddles'];raw=a.join_pdf(src['lines'])[0];common=raw[:raw.index(' A Military Saddle')]
        specific=''
        if r['name']=='Military Saddle':specific=raw[raw.index(' A Military Saddle'):raw.index(' An Exotic Saddle')]
        if r['name']=='Exotic Saddle':specific=raw[raw.index(' An Exotic Saddle'):]
        projected=common+specific;r.update(source_name='Saddles / '+r['name'],pages=[100],official_body=raw,projected_official_body=projected,differences=a.diffs(projected,r['staged_body']))
        r['body_status']='exact_source_excerpts_with_documented_family_projection' if projected==r['staged_body'] else 'confirmed_content_mismatch'
        r['projection_note']='Exact shared saddle sentence plus exact selected-type sentence; unrelated saddle types are omitted.'
    if r['kind']=='itemEntry':
        r['limitations'].append('Standalone parameter template is not itself a published source record. Concrete calls are decoded in every item/variant comparison; its raw placeholder syntax is retained for implementation review.')
        if r['name']!='Ioun Stone':r['body_status']='confirmed_nonliteral_parameterized_template'
    if r['kind']=='magicvariant' and q.get('entries'):
        eff={**q,**q.get('inherits',{})}
        rendered=a.canonical(a.flatten(q['entries'],eff))
        r['alternate_top_level_entries_review']={'staged_text':rendered,'status':'confirmed_non_source_editorial_note_or_variant_paraphrase','explanation':'Top-level entries are additional database content, distinct from inherited entries. Generic-variant name/source notes and item-value annotations are not literal SRD text.'}

# Single Iron Spike is a unit projection of the printed ten-spike bundle.
rr,qq=entry_for('Iron Spike')
verify(rr,qq,'weight',.5,{'page':95,'table':'Adventuring Gear','row':['Spikes, Iron','5 lb.','1 GP'],'derivation':'bundle of ten divided by ten; bundle size printed on p100'})
verify(rr,qq,'value',10,{'page':95,'table':'Adventuring Gear','row':['Spikes, Iron','5 lb.','1 GP'],'derivation':'bundle of ten divided by ten; bundle size printed on p100'})

# Each named Mysterious Deck effect is a literal subsection of the source.
deck_src=a.SOURCES['Mysterious Deck'];deck_text=a.join_pdf(deck_src['lines'])[0]
card_names=[q['name'] for q in a.DATA['decks.json']['card'] if q['set']=='Mysterious Deck']
positions={name:re.search(r'\b'+re.escape(name)+r'\. ',deck_text).start() for name in card_names}
positions_order=sorted(positions,key=positions.get)
for i,name in enumerate(positions_order):
    start=positions[name]+len(name)+2;end=positions[positions_order[i+1]] if i+1<len(positions_order) else len(deck_text)
    source=deck_text[start:end].strip()
    # Source native block stops at the following Avatar of Death heading.
    for j,q in enumerate(a.DATA['decks.json']['card']):
        if q['set']!='Mysterious Deck' or q['name']!=name:continue
        r=lookup[('decks.json','card',j)];r.update(source_name='Mysterious Deck / '+name,pages=[231,232],official_body=source,differences=a.diffs(source,r['staged_body']),exact_matched_spans=a.spans(source,r['staged_body']))
        r['body_status']='exact_after_documented_layout_typography_normalization' if source==r['staged_body'] else 'confirmed_content_mismatch'

illusion_lines=[l['text'].strip() for l in a.SOURCES['Deck of Illusions']['lines'] if all(f.startswith('GillSans') for f in l['fonts'])]
assert illusion_lines.pop(0)=='Deck of Illusions'
illusions=[];i=0
while i<len(illusion_lines) and not illusion_lines[i].startswith('*'):
    if illusion_lines[i:i+2]==['1d100','Illusion*']:i+=2;continue
    assert re.fullmatch(r'\d{2}–\d{2}',illusion_lines[i]),illusion_lines[i]
    illusions.append(illusion_lines[i:i+2]);i+=2
assert len(illusions)==33
illusion_footnote=' '.join(' '.join(illusion_lines[i:]).split())
for j,q in enumerate(a.DATA['decks.json']['card']):
    if q['set']!='Deck of Illusions':continue
    r=lookup[('decks.json','card',j)]
    staged_name=q['name'];printed_name='Veteran Warrior' if staged_name=='Warrior Veteran' else ('The card drawer' if staged_name=='The Card Drawer' else staged_name)
    matched=next((row for row in illusions if row[1].casefold()==printed_name.casefold()),None)
    if matched:
        source=matched[0]+' '+printed_name;r.update(source_name='Deck of Illusions / '+printed_name,pages=[217,218],official_body=source,differences=a.diffs(source,r['staged_body']),exact_matched_spans=a.spans(source,r['staged_body']),body_status='confirmed_nonliteral_derived_prose')
        r['source_evidence'].append({'pages':[217,218],'table':'Deck of Illusions','row':[matched[0],printed_name]})
        entries=q.get('entries',[])
        if len(entries)==1 and isinstance(entries[0],dict) and entries[0].get('type')=='table':
            table=entries[0]
            actual_rows=[[a.decode(cell,q) for cell in row] for row in table.get('rows',[])]
            if (q['name']==matched[1] and table.get('caption')=='Deck of Illusions'
                and table.get('colLabels')==['1d100','Illusion*'] and actual_rows==[matched]
                and table.get('footnotes')==[illusion_footnote]):
                r['body_status']='exact_printed_table_row_projection'
                r['projection_note']='Independent official PDF row, exact printed outcome name, caption, headers and footnote. Not copied from the staged deck table.'
                r['source_evidence'].append({'source':'official PDF only','printed_footnote':illusion_footnote})

def no_tables(value):
    if isinstance(value,list):return [no_tables(v) for v in value if not (isinstance(v,dict) and v.get('type')=='table')]
    if isinstance(value,dict):return {k:no_tables(v) for k,v in value.items()}
    return value
def tables_in(value):
    if isinstance(value,list):
        for v in value:yield from tables_in(v)
    elif isinstance(value,dict):
        if value.get('type')=='table':yield value
        else:
            for v in value.values():yield from tables_in(v)

def verify_table(table,record,src_lines,all_captions):
    caption=a.decode(table.get('caption',''),record)
    if not caption and record.get('name','').startswith('Bag of Tricks, '):
        caption=record['name'].split(', ')[1]+' Bag of Tricks'
        all_captions=all_captions|{'Gray Bag of Tricks','Rust Bag of Tricks','Tan Bag of Tricks'}
    lines=[l for l in src_lines if all(f.startswith('GillSans') for f in l['fonts'])]
    # Named sub-tables must remain associated with their printed caption.
    cap_positions=[i for i,l in enumerate(lines) if a.canonical(l['text'])==a.canonical(caption)] if caption else []
    caption_verified=False
    if len(cap_positions)==1:
        start=cap_positions[0]+1;end=next((i for i in range(start,len(lines)) if a.canonical(lines[i]['text']) in all_captions),len(lines));lines=lines[start:end];caption_verified=True
    rendered=[[a.canonical(a.flatten(v,record)) for v in row] for row in table['rows']]
    keys={row[0] for row in rendered}
    anchors=[l for l in lines if a.canonical(l['text']) in keys]
    checked=[];consumed=set();used_rows=set()
    signature=lambda l:(l['page'],l['column'],l['block'],l['line'])
    for row in rendered:
        candidates=[]
        for anchor in anchors:
            if a.canonical(anchor['text'])!=row[0]:continue
            x,y=anchor['origins'][0];page=anchor['page']
            max_x=540 if x>300 or record.get('name')=='Apparatus of the Crab' else 300
            # Two identical roll ranges can occupy different columns of one
            # row (Mysterious Deck's Void). Split a side-by-side panel only
            # when the baseline actually contains more cells than this table.
            baseline=[q for q in lines if q['page']==page and x-2<=q['origins'][0][0]<max_x and abs(q['origins'][0][1]-y)<.7]
            if len(baseline)>len(row):
                panel_starts=[q['origins'][0][0] for q in anchors if q['page']==page and q['origins'][0][0]>x+15 and abs(q['origins'][0][1]-y)<.7]
                if panel_starts:max_x=min(max_x,min(panel_starts)-.5)
            next_y=min([q['origins'][0][1] for q in anchors if q['page']==page and abs(q['origins'][0][0]-x)<12 and q['origins'][0][1]>y+.7]+[10000])
            # All table rows, including keys not retained by a derived record,
            # begin at the same x. They bound wrapped-cell extraction too.
            if re.fullmatch(r'[\d-]+',row[0]):
                next_y=min([q['origins'][0][1] for q in lines if q['page']==page and abs(q['origins'][0][0]-x)<12 and q['origins'][0][1]>y+.7 and re.fullmatch(r'[\d-]+',a.canonical(q['text']))]+[next_y])
            row_lines=[q for q in lines if q['page']==page and x-2<=q['origins'][0][0]<max_x and y-.7<=q['origins'][0][1]<next_y-.7]
            roots=sorted([q for q in row_lines if abs(q['origins'][0][1]-y)<.7],key=lambda q:q['origins'][0][0])
            if len(roots)!=len(row):continue
            boundaries=[(left['bbox'][2]+right['origins'][0][0])/2 for left,right in zip(roots,roots[1:])]
            cells=[]
            for i,root in enumerate(roots):
                # Centered wrapped cells can start slightly left of their
                # first line. Divide at the inter-column whitespace, not the
                # second root's x coordinate (Staff of Healing charge cost).
                start_x=boundaries[i-1] if i else x-2;end_x=boundaries[i] if i<len(boundaries) else max_x
                parts=[q for q in row_lines if start_x<=q['origins'][0][0]<end_x]
                parts.sort(key=lambda q:(q['origins'][0][1],q['origins'][0][0]));cells.append(a.join_pdf(parts,' '.join(row))[0])
            candidates.append({'page':page,'first_column_x':x,'baseline':y,'cells':cells,'exact':cells==row,
                               'source_line_ids':[signature(q) for q in row_lines]})
        exact=next((c for c in candidates if c['exact'] and (c['page'],c['first_column_x'],c['baseline']) not in used_rows),None)
        if exact:
            used_rows.add((exact['page'],exact['first_column_x'],exact['baseline']));consumed.update(exact['source_line_ids'])
        checked.append({'staged_row':row,'status':'exact_source_row_association' if exact else 'unverified_or_difference','source_row':exact,'candidate_rows':candidates if not exact else []})
    headers=[a.canonical(a.flatten(h,record)) for h in table.get('colLabels',[])]
    header_text=a.join_pdf(lines)[0]
    headers_verified=all(h in header_text for h in headers)
    footnotes=[a.canonical(a.flatten(f,record)) for f in table.get('footnotes',[])]
    def header_fragment(line):
        text=a.canonical(line['text'])
        return any(re.search(r'(?<!\w)'+re.escape(text)+r'(?!\w)',h) for h in headers+footnotes+[a.canonical(caption)] if h)
    uncovered=[{'id':signature(l),'text':l['text']} for l in lines if signature(l) not in consumed and not header_fragment(l)]
    all_rows=all(r['source_row'] for r in checked)
    complete=all_rows and headers_verified and not uncovered
    return {'caption':caption,'printed_caption_verified':caption_verified,'headers_verified':headers_verified,
            'row_status':'all_staged_rows_exactly_supported' if all_rows else 'unverified_or_difference',
            'complete_printed_table_coverage_status':'all_source_table_lines_accounted_for_after_documented_normalization' if complete else 'unverified_source_lines_or_headers_remain',
            'unaccounted_source_lines':uncovered,'complete_normalized_table_inventory_verified':complete,'rows':checked}

for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']];eff={**q,**q.get('inherits',{})}
    src=a.SOURCES.get(r['source_name'])
    if not src or (min(r.get('pages',[0]))<209 and r['name']!='Trinket') or r['kind'] not in ['item','itemGroup','magicvariant','deck']:continue
    (_, _),(_, _),body_lines=a.split_source(src,r.get('staged_body',''))
    prose_lines=[l for l in body_lines if not all(f.startswith('GillSans') for f in l['fonts'])]
    source_prose,choices=a.join_pdf(prose_lines,r.get('staged_body',''))
    staged_prose=a.canonical(a.flatten(no_tables(eff.get('entries',[])),eff))
    stage_tables=list(tables_in(eff.get('entries',[])))
    captions={a.canonical(a.decode(t.get('caption',''),eff)) for t in stage_tables if t.get('caption')}
    r.update(official_prose=source_prose,staged_prose=staged_prose,prose_layout_hyphen_decisions=choices,prose_differences=a.diffs(source_prose,staged_prose),prose_exact_matched_spans=a.spans(source_prose,staged_prose),prose_status='exact_after_documented_layout_typography_normalization' if source_prose==staged_prose else 'confirmed_literal_difference')
    r['table_reviews']=[verify_table(t,eff,body_lines,captions) for t in stage_tables]
    r['source_table_text']='\n'.join(l['text'] for l in body_lines if all(f.startswith('GillSans') for f in l['fonts']))
    if r['prose_status']=='confirmed_literal_difference':r['body_status']='confirmed_content_mismatch'
    elif not stage_tables and not r['source_table_text']:r['body_status']='exact_after_documented_layout_typography_normalization'
    elif stage_tables and all(t['complete_normalized_table_inventory_verified'] for t in r['table_reviews']):r['body_status']='exact_prose_and_complete_table_inventory_after_documented_normalization'
    elif stage_tables and all(t['row_status']=='all_staged_rows_exactly_supported' for t in r['table_reviews']):r['body_status']='exact_prose_retained_table_rows_supported_completeness_unverified'
    else:r['body_status']='exact_prose_table_content_unverified_or_difference'

# Explicit base-item mechanics retain the printed mundane row evidence.
lower_items={k.casefold():v for k,v in by_name.items()}
for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']];eff={**q,**q.get('inherits',{})}
    if eff.get('baseItem'):
        base=lower_items.get(eff['baseItem'].split('|')[0].casefold())
        if base:
            br,bq=entry_for(base['name'])
            for key in ['weight','ac','stealth','strength','dmg1','dmg2','dmgType','range','mastery','property']:
                if key in eff and key in br['verified_metadata']:
                    if eff[key]==bq.get(key):verify(r,eff,key,bq[key],{'base_item':base['name'],'base_source':br['verified_metadata'][key]['source']})
    if re.match(r'^\+[123] ',r['name']):
        bonus=r['name'][:2]
        for key in ['bonusAc','bonusWeapon','bonusSpellAttack']:
            if key in eff:verify(r,eff,key,bonus,{'pages':r.get('pages'),'source_heading':r['source_name'],'explanation':'printed bonus/rarity header association'})

# Printed magic-item metadata is checked for rarity and attunement in direct
# headers. Rarity-varies families remain table-specific, never passed by number
# presence alone. Other mechanics get explicit unverified field inventories.
for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']]
    eff={**q,**q.get('inherits',{})}
    meta=r.get('official_metadata','')
    if r['kind'] not in ['item','itemGroup','magicvariant'] or not meta:continue
    rarity=re.search(r', (Common|Uncommon|Rare|Very Rare|Legendary|Artifact)(?: |$)',meta)
    ev={'pages':r['pages'],'printed':meta}
    varying=bool(re.search(r'\([+][123]\)|Rare \(Silver or Brass\)',meta))
    if varying:
        expected=None
        if eff.get('rarity')=='varies':expected='varies'
        elif m:=re.match(r'^\+([123]) ',r['name']):
            rarities=dict((bonus,rar.lower()) for rar,bonus in re.findall(r'(Uncommon|Rare|Very Rare|Legendary) \(\+([123])\)',meta));expected=rarities.get(m[1])
        elif r['name'].startswith('Horn of Valhalla,'):
            expected={'Silver':'rare','Brass':'rare','Bronze':'very rare','Iron':'legendary'}[r['name'].split(', ')[1]]
        if expected:verify(r,eff,'rarity',expected,ev)
    elif rarity:verify(r,eff,'rarity',rarity[1].lower(),ev)
    if 'Requires Attunement' in meta:
        attune=re.search(r'Requires Attunement([^)]*)',meta)[1].strip()
        verify(r,eff,'reqAttune',attune[0].lower()+attune[1:] if attune else True,ev)
    elif 'reqAttune' in eff:verify(r,eff,'reqAttune',None,ev)
    for key in ['charges','recharge','rechargeAmount','bonusAc','bonusWeapon','bonusSpellAttack','bonusSavingThrow','resist','ability']:
        if key in eff and key not in r['verified_metadata']:
            r['limitations'].append('Mechanical field '+key+' is retained in metadata_not_proved; exact prose comparison does not independently verify its parser representation.')
    if r['metadata_differences']:r['metadata_status']='confirmed_difference'
    elif r['metadata_not_proved']:r['metadata_status']='partially_verified_remaining_fields_listed'
    else:r['metadata_status']='all_reviewed_fields_verified'

weight_policy=json.loads((Path(__file__).resolve().parents[2]/'source/item-weights.json').read_text(encoding='utf8'))
assert weight_policy['official_pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
weight_records={(p['file'],p['kind'],p['name']):p for p in weight_policy['records']}
gaming_labels={'Dice Set':'Dice','Dragonchess Set':'dragonchess','Playing Cards':'playing cards','Three-Dragon Ante Set':'three-dragon ante'}
for r in reviews:
    q=a.DATA[r['file']][r['kind']][r['index']]
    weight=weight_records.get((r['file'],r['kind'],r['name']))
    if weight:
        src=a.SOURCES[weight['source_heading']];raw=a.join_pdf(src['lines'])[0]
        ev={'source_heading':weight['source_heading'],'source_pages':weight['source_pages'],'policy_action':weight['action']}
        if weight['action']=='retain_printed_weight':
            assert weight['source_quote'] in raw,('Stale printed weight evidence',r['name'])
            ev.update(printed=weight['source_quote'],conversion=weight.get('conversion','Source pounds, without conversion.'))
            verify(r,q,'weight',weight['pounds'],ev)
        else:
            assert weight['action']=='remove_unprinted_fixed_weight'
            verify(r,q,'weight',None,ev)
            ev.update(reason=weight['reason'],weight_related_source_sentences=weight['source_weight_related_sentences'])
        r['source_evidence'].append(ev)
    if r['kind']=='item' and r['name'] in gaming_labels:
        raw=a.join_pdf(a.SOURCES['Gaming Set (Varies)']['lines'])[0]
        label=gaming_labels[r['name']]
        matches=re.findall(r'(?<!\w)'+re.escape(label)+r' \(([\d,]+ (?:CP|SP|GP))\)',raw,re.I)
        assert len(matches)==1,('Missing exact gaming-set variant cost',r['name'])
        verify(r,q,'value',cost(matches[0]),{'page':94,'source_heading':'Gaming Set (Varies)','printed_variant':label+' ('+matches[0]+')'})

for r in reviews:
    if r['kind']=='item' and r['name']=='Glass Bottle':
        # The PDF's ToUnicode mapping expands a single fraction glyph to
        # three characters: 1/2. The slash and denominator have zero advance.
        # The page-96 rendered source was also inspected: it reads 1½ pints.
        expected='A Glass Bottle holds up to 1½ pints.'
        with a.fitz.open(a.PDF) as pdf:
            raw=pdf[95].get_text('rawdict')
        witnesses=[]
        for block in raw['blocks']:
            for line in block.get('lines',[]):
                chars=[c for span in line['spans'] for c in span['chars']]
                text=''.join(c['c'] for c in chars)
                if text!='A Glass Bottle holds up to 11/2 pints.':continue
                start=text.index('11/2');fraction=chars[start+1:start+4]
                if (''.join(c['c'] for c in fraction)=='1/2'
                    and all(abs(c['bbox'][2]-c['bbox'][0])<.001 for c in fraction[1:])
                    and fraction[0]['bbox'][2]-fraction[0]['bbox'][0]>8):
                    witnesses.append({'page':96,'pdf_extracted_text':text,'fraction_glyph_characters':fraction,
                                      'printed_visual_reading':expected,'visual_review_clip':[305,40,555,755]})
        if len(witnesses)==1 and r['staged_body']==a.canonical(expected):
            r['body_status']='verified_printed_fraction_representation'
            r['source_evidence'].extend(witnesses)
            r['projection_note']='Lossless representation of the visually reviewed single half-fraction glyph, not a correction to the SRD or a change in bottle capacity.'
        else:r['body_status']='fraction_layout_not_literal_verified'
    if r['kind']=='itemGroup' and not a.DATA[r['file']][r['kind']][r['index']].get('entries') and r['body_status']=='needs_source_alignment_or_content_correction':
        r['body_status']='reference_group_no_own_prose';r['limitations'].append('Group delegates content to its member records; group rendering/inherited prose completeness is not verified here.')
    if r['kind']=='itemEntry' and r['name']=='Ioun Stone':
        source=r['official_body'].split(' The type of stone determines')[0]
        r.update(projected_official_body=source,body_status='exact_source_excerpts_with_documented_family_projection' if source==r['staged_body'] else 'needs_source_alignment_or_content_correction',projection_note='Exact generic four-paragraph source prefix; type effects reside in concrete stone records.')
    if r['kind']=='itemType' and r['name']=='Ranged Weapon':
        r['official_body']='Range. '+r['official_body'];r['differences']=a.diffs(r['official_body'],r['staged_body']);r['body_status']='exact_after_documented_layout_typography_normalization' if not r['differences'] else 'confirmed_content_mismatch'
    if r['kind']=='itemType' and r['name'] in ['Vehicle (Air)','Vehicle (Water)']:
        parts=[]
        for name in ['Speed','Crew','Passengers','Damage Threshold','Ship Repair']:
            src=a.SOURCES[name];parts.append(name+'. '+a.join_pdf(src['lines'])[0])
        source=' '.join(parts);r.update(official_body=source,differences=a.diffs(source,r['staged_body']),body_status='confirmed_content_mismatch')
    if r['kind']=='itemType' and r['name']=="Artisan's Tools":r['body_status']='confirmed_content_mismatch'

if a.args.family_proof:
    proof_raw=a.args.family_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,['items.json','items-base.json','magicvariants.json'],'family')
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family projection model'
    models=json.loads(model_path.read_text(encoding='utf8'))['families']
    literal_ids={(fn,kind,record['name']) for fn in ('items.json','items-base.json','magicvariants.json')
                 for kind,rows in a.DATA[fn].items() if isinstance(rows,list)
                 for record in rows if isinstance(record,dict) and '_srd521' in record}
    structural_ids={(fn,kind,record['name']) for fn in ('items.json','items-base.json','magicvariants.json')
                    for kind,rows in a.DATA[fn].items() if kind=='itemGroup'
                    for record in rows if '_srd521' not in record and not record.get('entries') and a.source_name(record,kind) in models}
    indexed=require_identity_coverage(proof,literal_ids,structural_ids)
    assert len(indexed)==len(proof['records'])==160,'Incomplete or duplicate family projections'
    certified={(r['file'],r['kind'],r['name']) for r in proof['records'] if r['literal_projection_verified']}
    structural={(r['file'],r['kind'],r['name']) for r in proof['records'] if r.get('structural_delegation_verified')}
    assert len(certified)==150 and len(structural)==10
    for r in reviews:
        identity=(r['file'],r['kind'],r['name'])
        if identity not in certified and identity not in structural:continue
        r['whole_family_comparison_before_projection_check']={'body_status':r['body_status'],'differences':r.get('differences',[]),'note':'A concrete projection is checked against its required exact source sections, not unrelated family members.'}
        r['body_status']='verified_literal_family_projection' if identity in certified else 'verified_structural_family_group'
        r['projection_proof_sha256']=hashlib.sha256(proof_raw).hexdigest()
        r['full_record_100_percent_verified']=False
        r['remaining_gate']='Metadata, source completeness outside this family model, and actual consumer/layout behavior remain separate.'
        if identity in certified:
            source=indexed[identity];assert set(source['verified_metadata'])=={'_srd521'}
            record=a.DATA[r['file']][r['kind']][r['index']]
            fact=require_imported_fact(record,'_srd521',source['verified_metadata']['_srd521'])
            verify(r,record,'_srd521',fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'classification':'authored source-projection provenance, not an additional printed game rule',
              'source_expected':fact['source_expected'],'interpretation':fact['interpretation']})

if a.args.equipment_proof:
    proof_raw=a.args.equipment_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,['items.json','items-base.json','decks.json'],'equipment')
    model_path=Path(__file__).resolve().parents[2]/'source/item-equipment.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale equipment projection model'
    models=json.loads(model_path.read_text(encoding='utf8'))['records']
    model_ids={(m['file'],m['kind'],m['name']) for m in models}
    actual_ids={(fn,kind,record['name']) for fn,payload in a.DATA.items()
                for kind,rows in payload.items() if isinstance(rows,list)
                for record in rows if isinstance(record,dict) and '_srd521Equipment' in record}
    assert len(models)==len(model_ids)==27 and model_ids==actual_ids,'Equipment source-projection identity mismatch'
    indexed=require_identity_coverage(proof,model_ids)
    assert len(indexed)==len(proof['records'])==27,'Incomplete or duplicate equipment projections'
    certified={(r['file'],r['kind'],r['name']) for r in proof['records'] if r['literal_projection_verified']}
    for r in reviews:
        if (r['file'],r['kind'],r['name']) not in certified:continue
        r['body_comparison_before_projection_check']={'body_status':r['body_status'],'differences':r.get('differences',[]),'note':'The independent proof checks literal sections and exact selected rows, including general equipment/helper rules.'}
        r['body_status']='verified_literal_equipment_projection'
        r['projection_proof_sha256']=hashlib.sha256(proof_raw).hexdigest()
        r['full_record_100_percent_verified']=False
        r['remaining_gate']='Unreviewed metadata, source completeness outside these declared projections, and actual consumer/layout behavior remain separate.'
        source=indexed[(r['file'],r['kind'],r['name'])]
        assert set(source['verified_metadata'])=={'_srd521Equipment'}
        record=a.DATA[r['file']][r['kind']][r['index']]
        fact=require_imported_fact(record,'_srd521Equipment',source['verified_metadata']['_srd521Equipment'])
        verify(r,record,'_srd521Equipment',fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
          'classification':'authored source-projection provenance, not an additional printed game rule',
          'source_expected':fact['source_expected'],'interpretation':fact['interpretation']})

if a.args.consumable_proof:
    proof_raw=a.args.consumable_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale consumable source proof: '+fn
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,value in certified['facts'].items():
            verify(r,effective,key,value,{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),'source_heading':certified['source_heading'],'pages':certified['source_pages']})

if a.args.header_proof:
    proof_raw=a.args.header_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale magic-header source proof: '+fn
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in header proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            assert key in {'rarity','reqAttune','type','wondrous','staff'} and fact['matches']
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'printed_header':certified['source_header'],
              'pages':certified['source_pages'],'interpretation':fact['basis'],'source_expected':fact['expected']})

if a.args.resource_proof:
    proof_raw=a.args.resource_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale item-resource source proof: '+fn
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in resource proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            assert key in {'charges','recharge','rechargeAmount'}
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_clauses':fact['source_clauses'],
              'source_scope':certified['source_evidence']})

if a.args.category_proof:
    proof_raw=a.args.category_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale equipment-category source proof: '+fn
    assert len(proof['records'])==51 and proof['source_weapon_rows']==38 and proof['source_armor_and_shield_rows']==13
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']]
        for key,fact in certified['verified_metadata'].items():
            assert key in {'type','weaponCategory','weapon','armor'} and fact['matches']
            verify(r,q,key,fact['expected'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_table':certified['table'],'source_category':certified['source_category'],
              'source_cells':certified['source_cells'],'page':certified['source_page']})

if a.args.binding_proof:
    proof_raw=a.args.binding_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale base-binding source proof: '+fn
    assert len(proof['records'])==44 and proof['counts']=={'fixed_concrete_base_binding':30,'staff_normal_quarterstaff_use':12,'focus_also_quarterstaff':2}
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==44,'Duplicate base-binding source proof records'
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']]
        for key,fact in certified['verified_metadata'].items():
            assert key in {'baseItem','type','weaponCategory','dmg1','dmg2','dmgType','property','mastery'} and fact['matches']
            verify(r,q,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'binding_scope':certified['scope'],
              'source_expected':fact['source_expected'],'source_evidence':certified['source_evidence']})

if a.args.bonus_proof:
    proof_raw=a.args.bonus_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale item-bonus source proof: '+fn
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in bonus proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records']),'Duplicate item-bonus source proof records'
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            assert key in {'bonusAc','bonusWeapon','bonusSpellAttack','bonusSavingThrow','bonusSpellSaveDc','bonusAbilityCheck','bonusProficiencyBonus','bonusWeaponDamage'}
            verify(r,effective,key,fact['source_expected'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_clauses':fact['source_clauses'],
              'source_scope':certified['source_evidence'],'conditional_context_preserved':True})

if a.args.defense_proof:
    proof_raw=a.args.defense_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale item-defense source proof: '+fn
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in defense proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records'])==56 and len(set(proof['damage_types']))==13
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences']
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            assert key in {'resist','immune','vulnerable'}
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
              'full_conditional_source_scope':certified['source_evidence']})

if a.args.weapon_override_proof:
    proof_raw=a.args.weapon_override_proof.read_bytes();proof=json.loads(proof_raw)
    assert proof['passed'] and proof['pdf_sha256']==hashlib.sha256(a.PDF.read_bytes()).hexdigest()
    for fn,digest in proof['input_sha256'].items():assert hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest()==digest,'Stale weapon-override source proof: '+fn
    from verify_weapon_overrides import SOURCE_HEADINGS,TARGET_FIELDS
    assert proof['source_header_count']==258 and set(proof['source_override_headings'])==SOURCE_HEADINGS
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records'])==3 and {p['name'] for p in proof['records']}==set(TARGET_FIELDS)
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences'] and set(certified['verified_metadata'])==TARGET_FIELDS[r['name']]
        q=a.DATA[r['file']][r['kind']][r['index']]
        for key,fact in certified['verified_metadata'].items():
            verify(r,q,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
              'source_clause':fact['source_clause'],'conditional_scope':fact['scope'],
              'base_source_cells':fact['base_property_cells'],'source_evidence':certified['source_evidence']})

if a.args.ability_proof:
    proof_raw=a.args.ability_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-ability')
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in ability proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records'])==30
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences'] and set(certified['verified_metadata'])=={'ability'}
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        fact=certified['verified_metadata']['ability']
        verify(r,effective,'ability',fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
          'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
          'full_conditional_source_scope':certified['source_evidence']})

if a.args.capacity_proof:
    proof_raw=a.args.capacity_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-capacity')
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records'])==19
    assert sum(p['verified_absence'] for p in proof['records'])==6
    assert sum(len(p['resolved_item_references']) for p in proof['records'])==11
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences'] and set(certified['verified_metadata'])<={'containerCapacity'}
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        if certified['verified_absence']:
            assert 'containerCapacity' not in effective and not certified['verified_metadata']
            r['unprinted_capacity_absence_proof_sha256']=hashlib.sha256(proof_raw).hexdigest()
        for key,fact in certified['verified_metadata'].items():
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
              'full_conditional_source_scope':certified['source_evidence'],'resolved_item_references':certified['resolved_item_references']})

if a.args.environment_proof:
    proof_raw=a.args.environment_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-environment')
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in environment proof'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    assert len(indexed)==len(proof['records'])==61
    expected_fields={'light':20,'modifySpeed':11,'poison':15,'poisonTypes':14,'speed':8,'vehSpeed':7}
    assert dict(collections.Counter(k for p in proof['records'] for k in p['verified_metadata']))==expected_fields
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences'] and set(certified['verified_metadata'])<=set(expected_fields)
        q=a.DATA[r['file']][r['kind']][r['index']];effective={**q,**q.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
              'full_conditional_source_scope':certified['source_evidence'],'query_index_scope':proof['scope']})

if a.args.grants_proof:
    proof_raw=a.args.grants_proof.read_bytes();proof=json.loads(proof_raw)
    require_inputs(proof,a.PDF,a.STAGED,a.FILES,'item-grants')
    model_path=Path(__file__).resolve().parents[2]/'source/item-families.json'
    assert proof['models_sha256']==hashlib.sha256(model_path.read_bytes()).hexdigest(),'Stale family model in grant proof'
    from verify_item_grants import FIELDS as grant_fields
    actual_ids={(fn,kind,record['name']) for fn,payload in a.DATA.items() for kind,rows in payload.items() if isinstance(rows,list)
                for record in rows if isinstance(record,dict) and grant_fields & {**record,**record.get('inherits',{})}.keys()}
    proof_ids={(p['file'],p['kind'],p['name']) for p in proof['records']}
    assert len(actual_ids)==len(proof_ids)==len(proof['records'])==34 and actual_ids==proof_ids,'Grant proof identity coverage differs'
    indexed={(p['file'],p['kind'],p['name']):p for p in proof['records']}
    expected_fields={'grantsLanguage':6,'grantsProficiency':3,'focus':4,'scfType':14,'spellScrollLevel':10}
    assert dict(collections.Counter(k for p in proof['records'] for k in p['verified_metadata']))==expected_fields
    for r in reviews:
        certified=indexed.get((r['file'],r['kind'],r['name']))
        if not certified:continue
        assert certified['passed'] and not certified['differences'] and set(certified['verified_metadata'])<=grant_fields
        record=a.DATA[r['file']][r['kind']][r['index']];effective={**record,**record.get('inherits',{})}
        assert set(certified['verified_metadata'])==grant_fields & effective.keys(),'Grant proof per-record field coverage differs'
        from verify_item_abilities import exact
        for key,fact in certified['verified_metadata'].items():
            assert exact(effective.get(key),fact['value']) and exact(fact['value'],fact['source_expected']),'Inconsistent grant proof fact'
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_heading':certified['source_heading'],'source_expected':fact['source_expected'],
              'full_conditional_source_scope':certified['source_evidence'],'query_index_scope':proof['scope']})

if a.args.schema_category_proof:
    proof_raw=a.args.schema_category_proof.read_bytes();proof=json.loads(proof_raw)
    from verify_item_schema_categories import source_inventory as category_inventory,source_facts as category_facts,require_proof as require_category_proof
    models=json.loads((Path(__file__).resolve().parents[2]/'source/item-families.json').read_text(encoding='utf8'))['families']
    expected=category_facts(a,category_inventory(a,models))
    indexed=require_category_proof(proof,a,expected)
    for r in reviews:
        identity=(r['file'],r['kind'],r['name']);certified=indexed.get(identity)
        if not certified:continue
        record=a.DATA[r['file']][r['kind']][r['index']];effective={**record,**record.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_expected':fact['source_expected'],'source_scope':expected[identity]['source_evidence'],
              'classification':expected[identity]['classification'],'query_index_scope':proof['scope']})

if a.args.predicate_proof:
    proof_raw=a.args.predicate_proof.read_bytes();proof=json.loads(proof_raw)
    from verify_item_predicates import source_expectations as predicate_expectations,require_proof as require_predicate_proof
    models=json.loads((Path(__file__).resolve().parents[2]/'source/item-families.json').read_text(encoding='utf8'))['families']
    expected=predicate_expectations(a,models);indexed=require_predicate_proof(proof,a,expected)
    for r in reviews:
        identity=(r['file'],r['kind'],r['name']);certified=indexed.get(identity)
        if not certified:continue
        record=a.DATA[r['file']][r['kind']][r['index']];effective={**record,**record.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_expected':fact['source_expected'],'source_scope':expected[identity]['source_evidence'],
              'classification':expected[identity]['classification'],'query_index_scope':proof['scope']})

if a.args.links_proof:
    proof_raw=a.args.links_proof.read_bytes();proof=json.loads(proof_raw)
    from verify_item_links import source_expectations as link_expectations,require_proof as require_link_proof
    models=json.loads((Path(__file__).resolve().parents[2]/'source/item-families.json').read_text(encoding='utf8'))['families']
    expected=link_expectations(a,models);indexed=require_link_proof(proof,a,expected)
    for r in reviews:
        identity=(r['file'],r['kind'],r['index']);certified=indexed.get(identity)
        if not certified:continue
        record=a.DATA[r['file']][r['kind']][r['index']];effective={**record,**record.get('inherits',{})}
        for key,fact in certified['verified_metadata'].items():
            verify(r,effective,key,fact['value'],{'independent_source_proof_sha256':hashlib.sha256(proof_raw).hexdigest(),
              'source_expected':fact['source_expected'],'comparison':fact['comparison'],
              'source_scope':expected[identity]['source_evidence'][key],'query_index_scope':proof['scope']})

for r in reviews:
    # These notes were created before independent component proofs imported.
    # Keep actual remaining limitations; remove a now-false automated note
    # only when that exact mechanical field has since been source-verified.
    r['limitations']=[note for note in r['limitations'] if not ((match:=re.match(r'^Mechanical field (\w+) is retained in metadata_not_proved;',note)) and match[1] in r['verified_metadata'])]
    r['metadata_status']='confirmed_difference' if r['metadata_differences'] else ('partially_verified_remaining_fields_listed' if r['metadata_not_proved'] else 'all_reviewed_fields_verified')

summary={'records':len(reviews),'body_statuses':dict(collections.Counter(x['body_status'] for x in reviews)),'metadata_fields_verified':sum(len(r['verified_metadata']) for r in reviews),'records_with_confirmed_metadata_differences':sum(bool(r['metadata_differences']) for r in reviews),'by_kind':{kind:dict(collections.Counter(x['body_status'] for x in reviews if x['kind']==kind)) for kind in sorted(set(x['kind'] for x in reviews))}}
out={'pdf_sha256':hashlib.sha256(a.PDF.read_bytes()).hexdigest(),'files_sha256':{fn:hashlib.sha256((a.STAGED/fn).read_bytes()).hexdigest() for fn in a.FILES},'layout_source_projection':a.LAYOUT_RECEIPT,'summary':summary,'scope':'Read-only source fidelity audit. Exact prose, printed rows, and mechanical metadata are distinct checks. Only the exact guarded inverse of approved portrait wrappers is used for source comparison; actual file/record hashes remain bound. No record is asserted 100 percent source-identical while metadata_not_proved is nonempty.','records':reviews}
(ROOT/'review.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(summary,indent=2))
print('\nMETADATA DIFFERENCES')
for r in reviews:
    if r['metadata_differences']:print(r['kind'],r['name'],json.dumps(r['metadata_differences'],ensure_ascii=False))
