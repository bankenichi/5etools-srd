from __future__ import annotations
import argparse, collections, difflib, hashlib, json, re
from pathlib import Path
import fitz

parser=argparse.ArgumentParser(description='Independently compare all 339 spell bodies and printed header facts with the official PDF.')
parser.add_argument('--pdf',type=Path,required=True)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
ROOT=args.out.resolve();ROOT.mkdir(parents=True,exist_ok=True)
PDF=args.pdf.resolve()
STAGED=args.data.resolve()/'data/spells/spells-xphb.json'
assert hashlib.sha256(PDF.read_bytes()).hexdigest()=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87','Official PDF hash changed'
SPELLS = json.loads(STAGED.read_text(encoding='utf8'))['spell']
NAMES = {s['name'].replace('’', "'"): s['name'] for s in SPELLS}
REF_TAGS = {'spell','item','creature','race','feat','action','condition','status','skill','sense','variantrule','hazard','class','background'}
TAGS = collections.Counter()

def decode(text):
    def replace(m):
        tag, value = m.group(1), m.group(2)
        TAGS[tag] += 1
        parts = value.split('|')
        if tag in REF_TAGS: return parts[2] if len(parts)>2 and parts[2] else parts[0]
        if tag in {'i','b','filter','book'}: return parts[0]
        if tag in {'dice','damage'}: return parts[1] if len(parts)>1 and parts[1] else parts[0]
        if tag in {'scaledice','scaledamage'}: return parts[3] if len(parts)>3 and parts[3] else parts[2]
        if tag == 'dc': return 'DC ' + parts[0]
        if tag == 'chance': return parts[1] if len(parts)>1 and parts[1] else parts[0] + ' percent'
        raise ValueError((tag,value))
    while re.search(r'\{@(\w+) ([^{}]*)}',text):
        text = re.sub(r'\{@(\w+) ([^{}]*)}',replace,text)
    if '{@' in text: raise ValueError(text)
    return text

def flatten(value):
    if isinstance(value,str): return decode(value)
    if isinstance(value,list): return '\n'.join(flatten(v) for v in value)
    if isinstance(value,dict):
        if value.get('type')=='list':
            return '\n'.join(('' if value.get('style','').startswith('list-hang') else '• ') + flatten(v) for v in value['items'])
        if value.get('type')=='table':
            return '\n'.join([decode(value.get('caption','')), ' '.join(map(flatten,value.get('colLabels',[])))] + [' '.join(map(flatten,row)) for row in value['rows']])
        out=[]
        if value.get('name'): out.append(decode(value['name']) + ('' if re.search(r'[.!?:]$',value['name']) else '.'))
        for key in ['entry','entries','items']:
            if key in value: out.append(flatten(value[key]))
        return '\n'.join(out)
    raise ValueError(value)

def canonical(text):
    text = re.sub(r'\s+',' ',text.translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':''}))).strip()
    text = re.sub(r'\s*…', '...',text)
    text = re.sub(r'—\s+', '—',text)
    return text

doc=fitz.open(PDF)
lines=[]
for page in range(106,175):
    cols=[[],[]]
    for bi,block in enumerate(doc[page].get_text('dict')['blocks']):
        for li,line in enumerate(block.get('lines',[])):
            spans=line['spans']
            if all(s['color']==0x808285 for s in spans): continue
            text=''.join(s['text'] for s in spans)
            if not text.strip(): continue
            col=0 if line['bbox'][0]<300 else 1
            cols[col].append({'page':page+1,'column':col+1,'text':text,'red':any(s['color']==0x8c2220 for s in spans),'fonts':list(dict.fromkeys(s['font'] for s in spans)),'bbox':line['bbox']})
    lines.extend(cols[0]);lines.extend(cols[1])

sources={}
current=None;in_stat=False
for i,line in enumerate(lines):
    if line['red']:
        name=line['text'].strip().replace('’',"'")
        nxt=lines[i+1]['text'].strip() if i+1<len(lines) else ''
        if name in NAMES and ('Level ' in nxt or 'Cantrip' in nxt):
            current=NAMES[name];in_stat=False
            assert current not in sources,current
            sources[current]={'name':current,'lines':[],'embedded_statblocks':[]}
        elif current:
            in_stat=True
            sources[current]['embedded_statblocks'].append({'heading':line['text'],'page':line['page']})
            continue
        else: continue
    if current and not in_stat: sources[current]['lines'].append(line)

assert len(sources)==339,(len(sources),set(NAMES.values())-sources.keys())

def join_pdf(parts,draft):
    raw='\n'.join(parts)
    choices=[]
    # End-of-line hyphens have no semantic status by themselves. Record every
    # decision; choose joined spelling only when present in staged visible text.
    def dehyphen(m):
        left,right=m.group(1),m.group(2)
        together=left+right;hyphen=left+'-'+right
        use_join=together.lower() in draft.lower() and hyphen.lower() not in draft.lower()
        choices.append({'printed':left+'-\n'+right,'joined':together if use_join else hyphen,'removed_layout_hyphen':use_join})
        return together if use_join else hyphen
    raw=re.sub(r'([\w]+)-\n([\w]+)',dehyphen,raw)
    return canonical(raw),choices

SCHOOLS={'A':'Abjuration','C':'Conjuration','D':'Divination','E':'Enchantment','V':'Evocation','I':'Illusion','N':'Necromancy','T':'Transmutation'}
def render_metadata(spell):
    school=SCHOOLS[spell['school']]
    level=f"Level {spell['level']} {school}" if spell['level'] else school+' Cantrip'
    times=[]
    for time in spell['time']:
        unit=time['unit'];number=time['number']
        text={'action':'Action','bonus':'Bonus Action','reaction':'Reaction'}.get(unit,f"{number} {unit}"+('s' if number!=1 else ''))
        if time.get('condition'):text+=', '+decode(time['condition'])
        if time.get('note'):text+=' ('+time['note']+')'
        times.append(text)
    time=' or '.join(times)
    if spell.get('meta',{}).get('ritual'):time+=' or Ritual'
    rng=spell['range'];dist=rng.get('distance',{'type':'special'})
    if rng['type']=='special':rng='Special'
    elif rng['type']!='point':rng='Self'
    elif dist['type']=='feet':rng=f"{dist['amount']} feet"
    elif dist['type']=='miles':rng=f"{dist['amount']} mile"+('s' if dist['amount']!=1 else '')
    else:rng=dist['type'].title()
    comp=spell['components'];components=', '.join(k.upper() for k in ['v','s','m'] if comp.get(k))
    if comp.get('m'):
        material=comp['m'].get('text') if isinstance(comp['m'],dict) else comp['m']
        components+=' ('+decode(material)+')'
    durations=[]
    for duration in spell['duration']:
        typ=duration['type']
        if typ=='instant':text='Instantaneous'
        elif typ=='special':text='Special'
        elif typ=='permanent':text='Until dispelled'+(' or triggered' if 'trigger' in duration['ends'] else '')
        elif typ=='timed':
            number=duration['duration']['amount'];unit=duration['duration']['type']
            text=f'{number} {unit}'+('s' if number!=1 else '')
            if duration.get('concentration'):text='Concentration, up to '+text
            elif duration['duration'].get('upTo'):text='Up to '+text
        else:raise ValueError(duration)
        durations.append(text)
    return {'level_school':level,'casting_time':time,'range':rng,'components':components,'duration':' or '.join(durations)}

def parse_metadata(raw):
    pattern=r'Casting Time:|Range:|Components?:|Duration:'
    parts=re.split('('+pattern+')',raw)
    level=parts[0].strip();classes=re.search(r'\((.*?)\)',level)
    fields={'level_school':re.sub(r'\s*\(.*?\)','',level).strip(),'classes':classes.group(1).split(', ') if classes else None}
    keys={'Casting Time:':'casting_time','Range:':'range','Components:':'components','Component:':'components','Duration:':'duration'}
    for i in range(1,len(parts),2):fields[keys[parts[i]]]=parts[i+1].strip()
    assert len(fields)==6,fields
    return fields

results=[]
for spell in SPELLS:
    src=sources[spell['name']]
    draft=flatten(spell['entries'])+'\n'+flatten(spell.get('entriesHigherLevel',[]))
    meta=[];body=[];phase='level'
    for line in src['lines'][1:]:
        fonts=line['fonts'];text=line['text']
        if phase=='level' and any(f.startswith('Cambria-Italic') for f in fonts): meta.append(text);continue
        if phase=='level': phase='fields'
        if phase=='fields' and (all(f.startswith('GillSans') for f in fonts) or re.match(r'^(Casting Time|Range|Components?|Duration):',text)): meta.append(text);continue
        phase='body';body.append(text)
    table_layout=[]
    if spell['name']=='Prismatic Spray':
        positions=[i for i in range(len(body)-1) if body[i:i+2]==['1d8','Ray']]
        assert len(positions)==2,positions
        del body[positions[1]:positions[1]+2]
        table_layout.append('Removed the repeated continuation header 1d8 / Ray on p155; all ray rows retained.')
    if spell['name']=='Reincarnate':
        start=body.index('1d10');end=next(i for i in range(start,len(body)) if body[i].startswith('\t The reincarnated'))
        expected=['1d10','Species','1d10','Species','1','Roll again.','6','Goliath','2','Dragonborn','7','Halfling','3','Dwarf','8','Human','4','Elf','9','Orc','5','Gnome','10','Tiefling']
        assert body[start:end]==expected,body[start:end]
        pairs=[('1','Roll again.'),('2','Dragonborn'),('3','Dwarf'),('4','Elf'),('5','Gnome'),('6','Goliath'),('7','Halfling'),('8','Human'),('9','Orc'),('10','Tiefling')]
        body[start:end]=['1d10','Species']+[f'{n} {value}' for n,value in pairs]
        table_layout.append('Reassembled the two side-by-side p158 table panels into numeric row order 1-10; repeated panel header removed; exact source cells checked.')
    official,choices=join_pdf(body,draft)
    staged=canonical(draft)
    diffs=[]
    a,b=official.split(),staged.split()
    for op,i,j,k,l in difflib.SequenceMatcher(None,a,b,autojunk=False).get_opcodes():
        if op=='equal': continue
        diffs.append({'operation':op,'official':' '.join(a[i:j]),'staged':' '.join(b[k:l]),'official_context':' '.join(a[max(0,i-7):min(len(a),j+7)]),'staged_context':' '.join(b[max(0,k-7):min(len(b),l+7)])})
    exact_spans=[]
    for match in difflib.SequenceMatcher(None,official,staged,autojunk=False).get_matching_blocks():
        if not match.size:continue
        exact_spans.append({'official_start':match.a,'staged_start':match.b,'length':match.size,'text':official[match.a:match.a+match.size]})
    rendered_meta=render_metadata(spell)
    source_meta,meta_choices=join_pdf(meta,' '.join(rendered_meta.values()))
    parsed_meta=parse_metadata(source_meta)
    meta_diffs=[{'field':k,'official':parsed_meta[k],'staged':canonical(v)} for k,v in rendered_meta.items() if parsed_meta[k]!=canonical(v)]
    material=spell['components'].get('m')
    material_text=material.get('text','') if isinstance(material,dict) else ''
    numeric_material_notes=[]
    if len(re.findall(r'[\d,]+\+? GP',material_text))>1:
        numeric_material_notes.append('Material text specifies multiple prices; single cost field is a lossy scalar and not a complete component-price representation.')
    if isinstance(material,dict) and material.get('consume') and any(word in material_text for word in [' and a ',' and four ']):
        numeric_material_notes.append('Material consume=true applies to a combined material record; source consumes only the explicitly qualified ingredient. Confirm downstream interpretation.')
    typographic='\n'.join(body)
    for choice in choices:typographic=typographic.replace(choice['printed'],choice['joined'])
    typographic=re.sub(r'\s+',' ',typographic).strip()
    typographic=re.sub(r'—\s+','—',typographic)
    draft_typographic=re.sub(r'\s+',' ',draft).strip()
    draft_typographic=re.sub(r'—\s+', '—',draft_typographic)
    results.append({'name':spell['name'],'official_heading':src['lines'][0]['text'],'pages':sorted(set(x['page'] for x in src['lines'])),'review_coverage':'all spell prose and printed metadata compared; embedded stat blocks excluded for separate bestiary review','body_status':'exact_after_documented_layout_typography_normalization' if official==staged else 'confirmed_content_mismatch','body_comparison_verified':True,'official_metadata_raw':'\n'.join(meta),'official_metadata':parsed_meta,'staged_metadata_rendered':rendered_meta,'official_body_typographic':typographic,'staged_body_typographic':draft_typographic,'literal_typography_body_equal':typographic==draft_typographic,'official_body':official,'staged_body':staged,'exact_matched_spans':exact_spans,'differences':diffs,'table_layout_decisions':table_layout,'layout_hyphen_decisions':choices,'metadata_hyphen_decisions':meta_choices,'embedded_statblocks':src['embedded_statblocks'],'metadata_status':'exact_semantically_rendered_fields' if not meta_diffs else 'confirmed_difference','metadata_comparison_verified':True,'metadata_differences':meta_diffs,'classes_status':'official classes present; no classes field in staged spell record','numeric_material_representation_notes':numeric_material_notes,'staged_metadata':{k:spell[k] for k in ['level','school','time','range','components','duration','meta','classes'] if k in spell}})

for result,spell in zip(results,SPELLS):
    result['classes_status']='EXACT' if [c['name'] for c in spell.get('class',[])]==result['official_metadata']['classes'] else 'DIFFERENT'
(ROOT/'sources.json').write_text(json.dumps(sources,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'review.json').write_text(json.dumps({'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'staged_sha256':hashlib.sha256(STAGED.read_bytes()).hexdigest(),'normalizations':['Whitespace collapsed; paragraph/line wrapping ignored','Curly apostrophes and quotation marks compared with straight equivalents; unnormalized typography retained separately','En dash and Unicode minus compared with ASCII hyphen','Whitespace after an em dash arising from line wrap removed','Printed ellipsis with space compared with ASCII three-dot ellipsis','End-of-line hyphen decisions individually recorded; joined spelling only when staged text establishes it','Prismatic Spray repeated continuation table header removed; Reincarnate side-by-side table panels assembled in numeric row order; exact cells asserted in script'],'tag_counts':TAGS,'summary':{'records':len(results),'bodies_compared':len(results),'metadata_compared':len(results),'body_equal_normalized':sum(not r['differences'] for r in results),'body_different':sum(bool(r['differences']) for r in results),'metadata_equal_rendered':sum(not r['metadata_differences'] for r in results),'metadata_different':sum(bool(r['metadata_differences']) for r in results),'body_equal_preserving_typography':sum(r['literal_typography_body_equal'] for r in results),'classes_different':sum(r['classes_status']!='EXACT' for r in results),'unverified_spell_body_comparisons':0,'excluded_embedded_statblock_records':sorted({r['name'] for r in results if r['embedded_statblocks']})},'records':results},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print('Records',len(results),'body exact',sum(r['body_status'].startswith('exact_') for r in results),'remaining',sum(bool(r['differences']) for r in results))
for r in results:
    if r['differences']:
        print('\n',r['name'],r['pages'])
        for d in r['differences']: print(' SOURCE',d['official'],'\n STAGED',d['staged'])
print('\nMETADATA DIFFERENCES')
for r in results:
    if r['metadata_differences']:print(r['name'],r['metadata_differences'])
failed=[r['name'] for r in results if r['differences'] or not r['literal_typography_body_equal'] or r['metadata_differences'] or r['classes_status']!='EXACT']
if failed:
    print('EXACT SOURCE GATE FAILED:', ', '.join(failed))
    raise SystemExit(1)
