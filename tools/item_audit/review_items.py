from __future__ import annotations
import argparse,collections,copy,difflib,hashlib,json,re,sys
from pathlib import Path
import fitz
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from layout_overrides import source_projection

if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf8')
parser=argparse.ArgumentParser(description='Independently audit equipment and magic items against the pinned official SRD PDF.')
parser.add_argument('--pdf',type=Path,required=True)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
parser.add_argument('--family-proof',type=Path)
parser.add_argument('--equipment-proof',type=Path)
parser.add_argument('--consumable-proof',type=Path)
parser.add_argument('--header-proof',type=Path)
parser.add_argument('--resource-proof',type=Path)
parser.add_argument('--category-proof',type=Path)
parser.add_argument('--binding-proof',type=Path)
parser.add_argument('--bonus-proof',type=Path)
parser.add_argument('--weapon-override-proof',type=Path)
parser.add_argument('--defense-proof',type=Path)
parser.add_argument('--ability-proof',type=Path)
parser.add_argument('--capacity-proof',type=Path)
parser.add_argument('--environment-proof',type=Path)
parser.add_argument('--grants-proof',type=Path)
parser.add_argument('--schema-category-proof',type=Path)
parser.add_argument('--predicate-proof',type=Path)
parser.add_argument('--links-proof',type=Path)
args=parser.parse_args()
ROOT=args.out.resolve();ROOT.mkdir(parents=True,exist_ok=True)
STAGED=args.data.resolve()/'data'
PDF=args.pdf.resolve()
assert hashlib.sha256(PDF.read_bytes()).hexdigest()=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87','Official source PDF changed'
FILES=['items.json','items-base.json','magicvariants.json','decks.json']
RAW_DATA={fn:json.loads((STAGED/fn).read_text(encoding='utf8')) for fn in FILES}
_projected,LAYOUT_RECEIPT=source_projection({'data/'+fn:payload for fn,payload in RAW_DATA.items()})
DATA={fn:_projected['data/'+fn] for fn in FILES}
ALL_STAGED_TEXT='\n'.join(json.dumps(DATA[fn],ensure_ascii=False) for fn in FILES).lower()
HELPERS={r['name']:r for r in DATA['items-base.json']['itemEntry']}
REFS={'spell','item','creature','race','feat','action','condition','status','skill','sense','variantrule','hazard','class','background','itemProperty','itemMastery','table','deck','card'}
TAGS=collections.Counter()

def decode(text,record):
    def template(m):
        name=m[1].split('|')[0]
        return flatten(HELPERS[name]['entriesTemplate'],record)
    text=re.sub(r'\{#itemEntry ([^}]+)}',template,text)
    text=re.sub(r'\{=([^}]+)}',lambda m:str(record[m[1]]),text)
    def helper(m):
        value=m[1]
        if value.startswith('getFullImmRes item.'):
            vals=record[value.split('.')[-1]]
            return ', '.join(v.title() for v in vals)
        if value.startswith('item.'):
            return str(record[value.split('.')[-1]])
        raise ValueError(('helper',value))
    text=re.sub(r'\{\{([^}]+)}}',helper,text)
    def replace(m):
        tag,value=m[1],m[2];TAGS[tag]+=1;parts=value.split('|')
        if tag in REFS:return parts[2] if len(parts)>2 and parts[2] else parts[0]
        if tag in {'i','b','filter','book','note'}:return parts[0]
        if tag in {'dice','damage'}:return parts[1] if len(parts)>1 and parts[1] else parts[0]
        if tag=='dc':return 'DC '+parts[0]
        if tag=='hit':return ('+' if not parts[0].startswith('-') else '')+parts[0]
        if tag=='chance':return parts[1] if len(parts)>1 and parts[1] else parts[0]+' percent'
        raise ValueError((tag,value))
    while re.search(r'\{@(\w+) ([^{}]*)}',text):text=re.sub(r'\{@(\w+) ([^{}]*)}',replace,text)
    if '{@' in text or '{#' in text or '{=' in text or '{{' in text:raise ValueError(text)
    return text

def flatten(value,record):
    if isinstance(value,str):return decode(value,record)
    if isinstance(value,(int,float)):return str(value)
    if isinstance(value,list):return '\n'.join(flatten(v,record) for v in value)
    if isinstance(value,dict):
        typ=value.get('type')
        if typ=='list':return '\n'.join(('' if value.get('style','').startswith('list-hang') else '• ')+flatten(v,record) for v in value['items'])
        if typ=='table':return '\n'.join([decode(value.get('caption',''),record),' '.join(flatten(v,record) for v in value.get('colLabels',[]))]+[' '.join(flatten(v,record) for v in row) for row in value['rows']])
        if typ=='cell':
            if 'entry' in value:return flatten(value['entry'],record)
            roll=value.get('roll',{})
            if 'exact' in roll:return str(roll['exact'])
            if 'min' in roll:return f"{roll['min']:02d}-{roll['max']:02d}"
        out=[]
        if value.get('name'):out.append(decode(value['name'],record)+('' if re.search(r'[.!?:]$',value['name']) else '.'))
        for k in ['entry','entries','items']:
            if k in value:out.append(flatten(value[k],record))
        return '\n'.join(out)
    raise ValueError(value)

def canonical(text):
    text=text.translate(str.maketrans({'’':"'",'‘':"'",'“':'"','”':'"','–':'-','−':'-','\u00ad':''}))
    text=re.sub(r'\s+',' ',text).strip()
    text=re.sub(r'\s*…','...',text)
    return re.sub(r'—\s+','—',text)

def join_pdf(lines,draft=''):
    raw='\n'.join(x['text'] if isinstance(x,dict) else x for x in lines);choices=[]
    # A physical wrap after the slash in Enlarge/Reduce (or a fraction) does
    # not insert a printed space into the name. Keep this source-layout join
    # explicit, rather than correcting already-correct candidate text.
    if '/\n' in raw:
        choices.append({'printed':'/\n','joined':'/','removed_layout_hyphen':False,'kind':'physical_line_wrap_after_slash'})
        raw=raw.replace('/\n','/')
    def dehyphen(m):
        a,b=m[1],m[2];together=a+b;hyphen=a+'-'+b
        use_join=(together.lower() in draft.lower() or together.lower() in ALL_STAGED_TEXT) and hyphen.lower() not in draft.lower()
        choices.append({'printed':a+'-\n'+b,'joined':together if use_join else hyphen,'removed_layout_hyphen':use_join})
        return together if use_join else hyphen
    raw=re.sub(r'([\w]+)-\n([\w]+)',dehyphen,raw)
    return canonical(raw),choices

doc=fitz.open(PDF)
LINES=[]
for n in [26,27]+list(range(89,104))+[197,198]+list(range(209,254)):
    cols=[[],[]]
    for bi,b in enumerate(doc[n-1].get_text('dict')['blocks']):
        for li,l in enumerate(b.get('lines',[])):
            ss=l['spans']
            if all(s['color']==0x808285 for s in ss):continue
            tx=''.join(s['text'] for s in ss)
            if not tx.strip():continue
            col=0 if l['bbox'][0]<300 else 1
            cols[col].append({'page':n,'column':col+1,'block':bi,'line':li,'text':tx,'red':any(s['color']==0x8c2220 for s in ss),'red12':any(s['color']==0x8c2220 and abs(s['size']-12)<.1 for s in ss),'fonts':list(dict.fromkeys(s['font'] for s in ss)),'origins':[s['origin'] for s in ss],'bbox':l['bbox']})
    LINES.extend(cols[0]);LINES.extend(cols[1])

SOURCES={}
current=None
for line in LINES:
    if line['red']:
        if current and current['red12'] and line['red12'] and not current['lines'] and current['heading_lines'][-1]['page']==line['page'] and current['heading_lines'][-1]['column']==line['column']:
            current['heading_lines'].append(line)
            current['name']=canonical(' '.join(x['text'] for x in current['heading_lines']))
            continue
        if current:
            SOURCES[current['name']]=current
        current={'name':canonical(line['text']),'heading_lines':[line],'lines':[],'red12':line['red12']}
    elif current:current['lines'].append(line)
if current:SOURCES[current['name']]=current

# The audit deliberately skips the intervening character chapter. Its next
# selected page (89) must not extend the page-26/27 Trinkets unit into the
# unrelated Selling Equipment sidebar.
SOURCES['Trinkets']['lines']=[l for l in SOURCES['Trinkets']['lines'] if l['page'] in {26,27}]

# The p210 lever table spans both columns. Native reading order puts its
# rightmost Down column after Armor of Resistance. Reassign that spatial region.
apparatus_down=[l for l in SOURCES['Armor of Resistance']['lines'] if l['page']==210 and min(o[1] for o in l['origins'])>440]
SOURCES['Armor of Resistance']['lines']=[l for l in SOURCES['Armor of Resistance']['lines'] if l not in apparatus_down]
SOURCES['Apparatus of the Crab']['lines'].extend(apparatus_down)
# The full-page weapons table is not part of the preceding Vex description.
SOURCES['Vex']['lines']=[l for l in SOURCES['Vex']['lines'] if l['page']==90]
# Improvised Weapons is a black inset, not part of Light.
SOURCES['Light']['lines']=[l for l in SOURCES['Light']['lines'] if l['page']==89]
# The Giant Fly inset interrupts the figurine entry. Its stat block is excluded
# here, while the item subsections after Golden Lions continue the item.
fly_lines=SOURCES['Giant Fly']['lines']
golden=next(i for i,l in enumerate(fly_lines) if 'Golden Lions (Rare)' in l['text'])
SOURCES['Figurine of Wondrous Power']['lines'].extend(fly_lines[golden:])

def source_name(record,kind):
    name=record.get('name',record.get('abbreviation',''))
    if kind=='itemProperty':return record['entries'][0]['name']
    if kind=='itemType':
        return {'Ranged Weapon':'Range','Vehicle (Air)':'Speed','Vehicle (Water)':'Speed','Tool':'Tool Proficiency','Instrument':'Musical Instrument'}.get(name,name)
    if kind=='magicvariant':
        name=re.sub(r' \(\*\)$','',name)
        if re.match(r'^\+[123] ',name):
            base=name[3:]
            return {'Ammunition':'Ammunition, +1, +2, or +3','Armor':'Armor, +1, +2, or +3','Shield':'Shield, +1, +2, or +3','Weapon':'Weapon, +1, +2, or +3'}[base]
        if name.startswith('Armor of ') and name.endswith(' Resistance'):return 'Armor of Resistance'
        if name.startswith('Armor of Vulnerability ('):return 'Armor of Vulnerability'
    if re.match(r'^\+[123] Wand of',name) or name=='Wand of the War Mage':return 'Wand of the War Mage, +1, +2, or +3'
    families=['Bag of Tricks','Carpet of Flying','Elemental Gem','Figurine of Wondrous Power','Horn of Valhalla','Ioun Stone','Manual of Golems','Feather Token','Ring of Elemental Command']
    for prefix in families:
        if name.startswith(prefix+','):return prefix
    if name.endswith(' Dragon Scale Mail'):return 'Dragon Scale Mail'
    if name.startswith('Belt of ') and name.endswith(' Giant Strength'):return 'Belt of Giant Strength'
    if name.startswith('Potion of ') and name.endswith(' Giant Strength'):return 'Potion of Giant Strength'
    if name.startswith('Potion of ') and name.endswith(' Resistance'):return 'Potion of Resistance'
    if name.startswith('Ring of ') and name.endswith(' Resistance'):return 'Ring of Resistance'
    if name.startswith('Armor of Vulnerability ('):return 'Armor of Vulnerability'
    if name.startswith('Spell Scroll ('):return 'Spell Scroll'
    if name in ['Potion of Healing','Potion of Greater Healing','Potion of Superior Healing','Potion of Supreme Healing','Potions of Healing']:return 'Potions of Healing'
    if name.startswith('Manual of ') and name.endswith(' Golems'):return 'Manual of Golems'
    if name.startswith('Ring of Elemental Command ('):return 'Ring of Elemental Command'
    if name in ['Dice Set','Dragonchess Set','Playing Card Set','Three-Dragon Ante Set']:return 'Gaming Set (Varies)'
    if name in ['Bagpipes','Drum','Dulcimer','Flute','Horn','Lute','Lyre','Pan Flute','Shawm','Viol']:return 'Musical Instrument (Varies)'
    aliases={'Glass Bottle':'Bottle, Glass','Crossbow Bolt Case':'Case, Crossbow Bolt','Map or Scroll Case':'Case, Map or Scroll','Fine Clothes':'Clothes, Fine',"Traveler's Clothes":"Clothes, Traveler's",'Bullseye Lantern':'Lantern, Bullseye','Hooded Lantern':'Lantern, Hooded','Basic Poison':'Poison, Basic','Iron Pot':'Pot, Iron','Portable Ram':'Ram, Portable','Iron Spikes':'Spikes, Iron','Iron Spike':'Spikes, Iron','Stone of Good Luck':'Stone of Good Luck (Luckstone)',"Artisan's Tools":"Artisan's Tools",'Trinket':'Trinkets','Playing Cards':'Gaming Set (Varies)'}
    name=aliases.get(name,name)
    if name in SOURCES:return name
    matches=[h for h in SOURCES if h.startswith(name+' (')]
    return matches[0] if len(matches)==1 else name

def split_source(src,draft):
    meta=[];body=[];phase='meta'
    for l in src['lines']:
        if phase=='meta' and all(f.startswith('Cambria-Italic') for f in l['fonts']):meta.append(l);continue
        phase='body';body.append(l)
    return join_pdf(meta,draft),join_pdf(body,draft),body

def diffs(a,b):
    aa,bb=a.split(),b.split();result=[]
    for op,i,j,k,l in difflib.SequenceMatcher(None,aa,bb,autojunk=False).get_opcodes():
        if op=='equal':continue
        result.append({'operation':op,'official':' '.join(aa[i:j]),'staged':' '.join(bb[k:l]),'official_context':' '.join(aa[max(0,i-6):j+6]),'staged_context':' '.join(bb[max(0,k-6):l+6])})
    return result

def spans(a,b):
    return [{'official_start':m.a,'staged_start':m.b,'length':m.size,'text':a[m.a:m.a+m.size]} for m in difflib.SequenceMatcher(None,a,b,autojunk=False).get_matching_blocks() if m.size]

RESULT=[]
for fn,d in DATA.items():
    for kind,records in d.items():
        if not isinstance(records,list):continue
        for i,r in enumerate(records):
            effective=copy.deepcopy(r)
            if kind=='magicvariant':effective.update(effective.pop('inherits'))
            result={'file':fn,'kind':kind,'index':i,'name':r.get('name',r.get('abbreviation')),'source_name':source_name(r,kind),'record_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'metadata_status':'unverified','metadata_not_proved':{k:v for k,v in effective.items() if k not in {'entries','entriesTemplate','name','source','page','srd52','hasRefs','edition'}},'limitations':[]}
            raw_record=RAW_DATA[fn][kind][i]
            if raw_record!=r:
                result['source_projection_sha256']=result['record_sha256']
                result['record_sha256']=hashlib.sha256(json.dumps(raw_record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                result['approved_layout_normalization']=LAYOUT_RECEIPT['model_sha256']
            try:draft=flatten(effective.get('entries',effective.get('entriesTemplate',[])),effective)
            except Exception as exc:
                result.update(body_status='unverified_template_resolution',error=repr(exc));RESULT.append(result);continue
            result['staged_body']=canonical(draft)
            src=SOURCES.get(result['source_name'])
            if not src:
                result['body_status']='unverified_no_exact_heading_mapping';RESULT.append(result);continue
            result['pages']=sorted(set(x['page'] for x in src['heading_lines']+src['lines']))
            (meta,mc),(body,bc),body_lines=split_source(src,draft)
            result.update(official_metadata=meta,official_body=body,official_body_raw='\n'.join(x['text'] for x in body_lines),metadata_layout_hyphen_decisions=mc,body_layout_hyphen_decisions=bc)
            result['body_status']='exact_after_documented_layout_typography_normalization' if body==canonical(draft) else 'needs_source_alignment_or_content_correction'
            result['differences']=diffs(body,canonical(draft))
            result['exact_matched_spans']=spans(body,canonical(draft))
            if kind=='itemEntry':result['limitations'].append('Template is parameterized; concrete source-family instantiations require individual table and prose checks.')
            if not draft:result['limitations'].append('Record has no prose; printed table fields and inherited type/helper prose still require verification.')
            RESULT.append(result)

summary={'records':len(RESULT),'body_statuses':dict(collections.Counter(x['body_status'] for x in RESULT)),'by_kind':{kind:dict(collections.Counter(x['body_status'] for x in RESULT if x['kind']==kind)) for kind in sorted(set(x['kind'] for x in RESULT))}}
(ROOT/'sources.json').write_text(json.dumps(SOURCES,ensure_ascii=False,indent=2)+'\n',encoding='utf8')
(ROOT/'review-initial.json').write_text(json.dumps({'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'files_sha256':{fn:hashlib.sha256((STAGED/fn).read_bytes()).hexdigest() for fn in FILES},'normalizations':['Whitespace collapsed; physical lines/paragraph boundaries ignored','Curly apostrophes/quotes normalized to ASCII; en dash/minus normalized to hyphen','Printed ellipsis normalized to three dots; whitespace after em dash ignored','End-of-line hyphen decisions recorded; join only when staged spelling establishes it'],'tag_counts':TAGS,'summary':summary,'records':RESULT},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
print(json.dumps(summary,indent=2))
for r in RESULT:
    if r['body_status'].startswith('unverified'):print(r['kind'],r['name'],r['body_status'],r.get('error',''))
