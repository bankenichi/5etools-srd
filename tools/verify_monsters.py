"""Read-only exact SRD monster audit. Writes only beside this script.

PDF layout is parsed independently of the source records. Prose comparisons are
full-string comparisons after documented typography/layout normalization; no
fuzzy score or ngram coverage is used as proof.
"""
import collections
import argparse
import csv
import difflib
import hashlib
import json
import re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from layout_overrides import source_projection

import fitz

parser=argparse.ArgumentParser(description='Compare every retained monster statblock and feature with the official SRD PDF.')
parser.add_argument('--pdf',type=Path,required=True)
parser.add_argument('--data',type=Path,required=True)
parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args()
OUT=args.out.resolve();OUT.mkdir(parents=True,exist_ok=True)
ROOT=args.data.resolve().parent
DATA=args.data.resolve()/'data/bestiary'
PDF=args.pdf.resolve()
assert hashlib.sha256(PDF.read_bytes()).hexdigest()=='8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87','Official PDF changed'
AB = {"str": "Strength", "dex": "Dexterity", "con": "Constitution", "int": "Intelligence", "wis": "Wisdom", "cha": "Charisma"}
SECTIONS = {"Traits": "trait", "Actions": "action", "Bonus Actions": "bonus", "Reactions": "reaction", "Legendary Actions": "legendary"}


def dump(name, data):
    (OUT / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def typography(s):
    return s.translate(str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "−": "-", "–": "-", "\u00a0": " ", "ﬁ": "fi", "ﬂ": "fl", "\u00ad": ""}))


def norm(s):
    """Case and punctuation are preserved; normalize typography and whitespace.

    Extracted physical line endings inside a word may be discretionary hyphens.
    Those are marked U+E000 by joined(), and are removed only in pdf_variants().
    """
    return re.sub(r"\s+", " ", typography(s)).strip()


def joined(lines):
    result = ""
    for line in lines:
        s = line["text"] if isinstance(line, dict) else line
        if result.endswith("-"):
            result = result[:-1] + "\ue000" + s.lstrip()
        else:
            result += (" " if result else "") + s.strip()
    return result


def equal_pdf(expected, official):
    """Compare exactly, allowing ONLY PDF end-of-line hyphen disambiguation."""
    e, p = norm(expected), norm(official)
    # Each physical line-break hyphen can be either a real hyphen or a layout
    # hyphen. Use a literal expression, with only those locations optional.
    pattern = re.escape(p).replace("\ue000", "-?")
    return re.fullmatch(pattern, e) is not None


def display_pdf(p):
    return norm(p).replace("\ue000", "")


def decode(s):
    def tag(m):
        kind, _, value = m.group(1).partition(" ")
        parts = value.split("|")
        if kind in {"spell", "creature", "condition", "status", "action", "skill", "variantrule", "hazard", "item"}:
            return parts[2] if len(parts) > 2 and parts[2] else parts[0]
        if kind in {"damage", "dice"}:
            return (parts[1] if len(parts) > 1 and parts[1] else parts[0]).replace('summonSpellLevel',"the spell's level")
        if kind == "dc": return "DC " + (parts[1] if len(parts) > 1 and parts[1] else parts[0])
        if kind == "hit": return ("+" if not value.startswith(("-", "+")) else "") + value
        if kind == "hitYourSpellAttack": return value
        if kind in {"atk", "atkr"}:
            modes = value.split(",")
            mode = {"m": "Melee", "r": "Ranged", "mw": "Melee Weapon", "rw": "Ranged Weapon", "ms": "Melee Spell", "rs": "Ranged Spell"}
            return " or ".join(mode[x] for x in modes) + (" Attack Roll:" if kind == "atkr" else " Attack:")
        if kind == "h": return "Hit: "
        if kind == "hom": return "Hit or Miss: "
        if kind == "actSave": return AB[value] + " Saving Throw:"
        if kind == "actSaveFail": return {"1": "First Failure:", "2": "Second Failure:"}.get(value, "Failure:")
        if kind == "actSaveSuccess": return "Success:"
        if kind == "actSaveSuccessOrFail": return "Failure or Success:"
        if kind == "actSaveFailBy": return "Failure by " + value + " or More:"
        if kind == "actTrigger": return "Trigger:"
        if kind == "actResponse": return "Response" + ("—" if "d" in value else ":")
        if kind == "recharge": return "(Recharge " + (value + "-6" if value and value != "6" else "6") + ")"
        raise ValueError("Unknown display tag " + kind)
    old = None
    while old != s:
        old = s
        s = re.sub(r"\{@([^{}]+)\}", tag, s)
    return s


def flatten(x):
    if isinstance(x, str): return decode(x)
    if isinstance(x, list): return " ".join(flatten(a) for a in x)
    if isinstance(x, dict):
        name = decode(x["name"]) + ". " if x.get("name") else ""
        if "entries" in x: return name + flatten(x["entries"])
        if "entry" in x: return name + flatten(x["entry"])
        if "items" in x: return name + flatten(x["items"])
        raise ValueError("Unknown entries shape " + repr(x))
    raise ValueError("Unknown entry " + repr(x))


def extract():
    document = fitz.open(PDF)
    all_lines = []
    for pi, page in enumerate(document):
        chunks = []
        for block in page.get_text("dict")["blocks"]:
            for ln in block.get("lines", []):
                if ln["bbox"][1] >= 735: continue
                spans = ln["spans"]
                if not any(s["text"].strip() for s in spans): continue
                # Baselines are reliable across fonts. Some Cambria spans have
                # huge ascenders that make bbox tops overlap earlier stat rows.
                y = min(s['origin'][1] for s in spans if s['text'].strip())
                chunks.append({"page": pi + 1, "col": int(ln["bbox"][0] >= 300), "y": y, "x": ln["bbox"][0], "spans": spans})
        chunks.sort(key=lambda l: (l["col"], l["y"], l["x"]))
        merged = []
        for l in chunks:
            if merged and merged[-1]["col"] == l["col"] and abs(merged[-1]["y"] - l["y"]) < 1:
                merged[-1]["spans"].extend(l["spans"])
            else:
                merged.append(l)
        for l in merged:
            l["spans"].sort(key=lambda s: s["bbox"][0])
            # Geometry matters when PDF splits one row into independent lines.
            text = ""
            previous_right = None
            for s in l["spans"]:
                if previous_right is not None and s["bbox"][0] - previous_right > 1 and text and not text[-1].isspace() and not s["text"].startswith(" "):
                    text += " "
                text += s["text"]
                previous_right = s["bbox"][2]
            l["text"] = text
            all_lines.append(l)
    blocks = {}
    current = None
    for l in all_lines:
        statheading = any(s["font"] == "GillSans-SemiBold" and 14 < s["size"] < 16 for s in l["spans"])
        if statheading:
            current = {"name": norm(l["text"]), "page": l["page"], "lines": [], "heading": l}
            if current["name"] in blocks: raise ValueError("Duplicate PDF name " + current["name"])
            blocks[current["name"]] = current
            continue
        if current:
            # Stop on main-book typography, which also handles item prose
            # resuming immediately after Giant Fly without another heading.
            if any((s["font"].startswith("Cambria") or (s["font"] == "GillSans-SemiBold" and s["size"] >= 11)) for s in l["spans"]):
                current = None
            else:
                current["lines"].append(l)
    dump("official-statblocks-layout.json", blocks)
    return blocks


def parse_block(b):
    result = {"core": [], "entries": [], "section_headers": [], "legendary_header": []}
    section = None
    entry = None
    for l in b["lines"]:
        s = norm(l["text"])
        if s in SECTIONS and any(11.9 < t["size"] < 12.1 for t in l["spans"]):
            section = SECTIONS[s]
            entry = None
            result["section_headers"].append(section)
            continue
        if section is None:
            result["core"].append(l)
            continue
        # Only feature names start at left column and use BoldItalic. Inline
        # emphasized text (including save outcomes) does not create an entry.
        nonempty = [t for t in l["spans"] if t["text"].strip()]
        starts = nonempty and nonempty[0]["font"] == "Optima-BoldItalic" and abs(nonempty[0]["bbox"][0] - (313.4988 if l["col"] else 63)) < 1
        if starts and entry and '.' not in joined(entry['lines']):
            entry['lines'].append(l)
        elif starts:
            entry = {"section": section, "page": l["page"], "lines": [l]}
            result["entries"].append(entry)
        elif entry:
            entry["lines"].append(l)
        elif section == "legendary":
            result["legendary_header"].append(l)
        else:
            result.setdefault("unparsed", []).append(l)
    for e in result["entries"]:
        e["text"] = joined(e["lines"])
        e["name"] = norm(e["text"].split(".", 1)[0])
    return result


def spell_entry(s):
    text = decode(s["name"]) + ". " + flatten(s.get("headerEntries", []))
    hidden = s.get("hidden", [])
    if s.get("will") and "will" not in hidden:
        text += " At Will: " + ", ".join(decode(v) for v in s["will"])
    for k, values in sorted(s.get("daily", {}).items(), key=lambda pair: int(pair[0].rstrip('e')), reverse=True):
        if "daily" not in hidden:
            text += f" {k.rstrip('e')}/Day" + (" Each" if k.endswith("e") else "") + ": " + ", ".join(decode(v) for v in values)
    if s.get("footerEntries"): text += " " + flatten(s["footerEntries"])
    extra = set(s) - {"name", "type", "headerEntries", "will", "daily", "ability", "displayAs", "hidden", "footerEntries"} - set(hidden)
    if extra: raise ValueError("Unrendered spellcasting keys " + repr(extra))
    return text


def core_checks(record, p):
    core = p["core"]
    text = joined(core)
    checks = []
    def add(field, expected, official, equal=None):
        checks.append({"field": field, "expected": expected, "official": display_pdf(official) if isinstance(official, str) else official,
                       "status": "VERIFIED" if (equal if equal is not None else equal_pdf(str(expected), str(official))) else "UNVERIFIED"})
    # AC, HP, Speed, Initiative are read from named independent PDF rows.
    fields = {}
    active = None
    for l in core:
        st = norm(l["text"])
        m = re.match(r"^(AC|HP|Speed|Skills|Resistances|Vulnerabilities|Immunities|Senses|Languages|CR|Gear)\b", st)
        if m:
            active = m.group(1)
            fields[active] = st[len(active):].strip()
        elif re.match(r"^(Str|Int|MOD)", st):
            active = None
        elif active:
            fields[active] += " " + st
    acstr = fields.get("AC", "")
    initiative = re.search(r"Initiative\s*([+−-]\d+)\s*\((\d+)\)", acstr)
    if initiative:
        fields["AC"] = acstr[:initiative.start()].strip()
    ac = record["ac"]
    if len(ac) == 1 and isinstance(ac[0], int): exac = str(ac[0])
    elif len(ac) == 1 and "special" in ac[0]: exac = decode(ac[0]["special"])
    else: exac = json.dumps(ac)
    add("ac", exac, fields.get("AC", "<missing>"))
    hp = record["hp"]
    exhp = decode(hp["special"]) if "special" in hp else f"{hp['average']} ({hp['formula']})"
    add("hp", exhp, fields.get("HP", "<missing>"))
    # Exact ability/saves parsed from geometry-combined table rows.
    for st in (norm(l["text"]) for l in core):
        for ab, score, mod, save in re.findall(r"\b(Str|Dex|Con|Int|Wis|Cha)\s*(\d+)\s*([+-]\d+)\s*([+-]?\d+)", st):
            key = ab.lower()
            expected_save = int(record.get("save", {}).get(key, (record[key] - 10) // 2))
            add(key, record[key], int(score), record[key] == int(score))
            add("save." + key, expected_save, int(save), expected_save == int(save))
            add("modifier." + key, (record[key] - 10) // 2, int(mod), (record[key] - 10) // 2 == int(mod))
    checked = {c['field'] for c in checks}
    for key in AB:
        if key not in checked: add(key, record[key], "<unparsed>", False)
    cr = record.get("cr", "None")
    crvalue = cr.get("cr") if isinstance(cr, dict) else cr
    crline = fields.get("CR", "")
    crline_parse = re.sub(r'\(([\d,]+) XP;', r'(XP \1;',crline)
    m = re.match(r"(None|\d+(?:/\d+)?) \(XP ([\d,]+)(?:, or ([\d,]+) in lair)?; PB (.*?)\)", crline_parse)
    xpmap = {"0": 10,"1/8":25,"1/4":50,"1/2":100,"1":200,"2":450,"3":700,"4":1100,"5":1800,"6":2300,"7":2900,"8":3900,"9":5000,"10":5900,"11":7200,"12":8400,"13":10000,"14":11500,"15":13000,"16":15000,"17":18000,"18":20000,"19":22000,"20":25000,"21":33000,"22":41000,"23":50000,"24":62000,"25":75000,"26":90000,"27":105000,"28":120000,"29":135000,"30":155000}
    pb = 2 if crvalue in {"0", "1/8", "1/4", "1/2", "None"} else 2 + (int(crvalue)-1)//4
    if m:
        add("cr", crvalue, m[1])
        xp = cr.get("xp", xpmap.get(crvalue, 0)) if isinstance(cr, dict) else xpmap.get(crvalue, 0)
        add("xp", xp, int(m[2].replace(",", "")), xp == int(m[2].replace(",", "")))
        lairxp = cr.get("xpLair") if isinstance(cr, dict) else None
        offlair = int(m[3].replace(",", "")) if m[3] else None
        add("xpLair", lairxp, offlair, lairxp == offlair)
        pbtext = record.get("pbNote", f"+{pb}")
        add("pb", pbtext, m[4])
    else:
        add("cr", crvalue, crline or "<missing>", False)
    if initiative:
        init = record.get("initiative", {})
        score = (record["dex"] - 10)//2 + init.get("proficiency", 0)*pb + init.get("bonus", 0)
        if "initiative" in init: score = init["initiative"]
        add("initiative", score, int(typography(initiative[1])), score == int(typography(initiative[1])))
        passive_init=record.get('initiativePassive',score+10+({'adv':5,'dis':-5}.get(init.get('advantageMode'),0)))
        add("initiativePassive", passive_init, int(initiative[2]), passive_init == int(initiative[2]))
    elif "initiative" in record:
        add("initiative", record["initiative"], "<missing>", False)
    speed = []
    for k,v in record['speed'].items():
        if k == 'canHover': continue
        if k == 'alternate':
            for altmode,altvalues in v.items():
                for alt in altvalues:
                    speed.append(('' if altmode=='walk' else altmode.title()+' ')+str(alt['number'])+' ft. '+alt['condition'])
            continue
        if k == 'choose':
            speed.append(' or '.join(m.title() for m in v['from'])+' '+str(v['amount'])+' ft. '+v.get('note',''))
            continue
        if k not in {'walk','burrow','climb','fly','swim'}:
            speed.append('<unrendered '+k+'>');continue
        pre = '' if k == 'walk' else k.title()+' '
        if isinstance(v,dict):
            speed.append(pre+str(v['number'])+' ft.'+((' '+v.get('condition','')) if v.get('condition') else ''))
        else: speed.append(pre+str(v)+' ft.'+(' (hover)' if k=='fly' and record['speed'].get('canHover') else ''))
    add('speed', ', '.join(speed), fields.get('Speed','<missing>'))
    exskills = ', '.join(k.title().replace(' Of ',' of ')+' '+v for k,v in record.get('skill',{}).items())
    add('skill', exskills, fields.get('Skills',''))
    def render_immunities(values,field):
        rendered=[]
        for value in values:
            if isinstance(value,str):rendered.append(value.title())
            elif 'special' in value:rendered.append(decode(value['special']))
            else:
                rendered.append(render_immunities(value.get(field,[]),field)+(' '+decode(value['note']) if value.get('note') else ''))
        return ', '.join(rendered)
    for k,label in [('resist','Resistances'),('vulnerable','Vulnerabilities')]:
        values = record.get(k,[])
        expected = render_immunities(values,k)
        add(k,expected,fields.get(label,''))
    damage = render_immunities(record.get('immune',[]),'immune')
    conditions = render_immunities(record.get('conditionImmune',[]),'conditionImmune')
    im = damage+('; ' if damage and conditions else '')+conditions
    add('immune/conditionImmune',im,fields.get('Immunities',''))
    senses = ', '.join(decode(v) for v in record.get('senses',[]))
    senses += ('; ' if senses else '')+'Passive Perception '+str(record['passive'])
    offsenses=fields.get('Senses','<missing>')
    # Senses and passive are separate structured facts. The book uses both
    # comma and semicolon separators, which do not change those facts.
    add('senses/passive',senses,offsenses,equal_pdf(senses.replace('; Passive',', Passive'),offsenses.replace('; Passive',', Passive')))
    languages = ', '.join(record.get('languages',[])) or 'None'
    languages=languages[0].upper()+languages[1:]
    add('languages',languages,fields.get('Languages','<missing>'))
    size = {'T':'Tiny','S':'Small','M':'Medium','L':'Large','H':'Huge','G':'Gargantuan'}
    header=norm(core[0]['text']) if core else '<missing>'
    size_end=re.match(r'(Tiny|Small|Medium|Large|Huge|Gargantuan)(?: or (Tiny|Small|Medium|Large|Huge|Gargantuan|Smaller))? ',header)
    if size_end:
        offsizes=[key for key,val in size.items() if val in size_end.groups()]
        if size_end[2]=='Smaller':offsizes=list(size)[:list(size.values()).index(size_end[1])+1]
        add('size',record['size'],offsizes,set(record['size'])==set(offsizes))
        remaining=header[size_end.end():]
    else:
        add('size',record['size'],header,False)
        remaining=header
    typ=record['type']
    if isinstance(typ,str):typtext=typ.title()
    elif isinstance(typ,dict):
        if isinstance(typ.get('type',''),str):typtext=typ.get('type','').title()
        elif isinstance(typ.get('type'),dict) and 'choose' in typ['type']:
            typechoices=[v.title() for v in typ['type']['choose']]
            typtext=', '.join(typechoices[:-1])+', or '+typechoices[-1]+' (Your Choice)'
        else:typtext=json.dumps(typ['type'])
        if typ.get('swarmSize'):typtext='Swarm of '+size[typ['swarmSize']]+' '+typtext+('s' if typtext!='Undead' else '')
        if typ.get('tags'):typtext+=' ('+', '.join(v.title() if isinstance(v,str) else json.dumps(v) for v in typ['tags'])+')'
    else:typtext=json.dumps(typ)
    aligns = {('U',):'Unaligned',('N',):'Neutral',('L','G'):'Lawful Good',('L','N'):'Lawful Neutral',('L','E'):'Lawful Evil',('N','G'):'Neutral Good',('N','E'):'Neutral Evil',('C','G'):'Chaotic Good',('C','N'):'Chaotic Neutral',('C','E'):'Chaotic Evil',('A',):'Any Alignment'}
    try:align=aligns.get(tuple(record['alignment']),json.dumps(record['alignment']))
    except TypeError:align=json.dumps(record['alignment'])
    # Header choice ordering is storage representation. Compare type/alignment
    # content separately from the independently verified size choices.
    off_type, _, off_alignment=remaining.rpartition(', ')
    add('type',typtext,off_type)
    add('alignment',align,off_alignment,norm(align).casefold()==norm(off_alignment).casefold())
    # Gear is source-backed printable text. Metadata tags are intentionally
    # excluded from proof and cannot substitute for any checked field.
    gear=[]
    for value in record.get('gear',[]):
        if isinstance(value,str):name=value.split('|')[0];q=None
        else:name=value['item'].split('|')[0];q=value.get('quantity')
        plural={'handaxe':'handaxes','javelin':'javelins','dagger':'daggers','light hammer':'light hammers','spear':'spears'}
        gear.append((plural.get(name,name+'s') if q else name).title()+(f' ({q})' if q else ''))
    add('gear',', '.join(gear),fields.get('Gear',''))
    return checks, fields


def main():
    blocks = extract()
    rows = []
    for file in sorted(DATA.glob('bestiary-*.json')):
        payload=json.loads(file.read_text(encoding='utf-8'));relative=file.relative_to(args.data.resolve()).as_posix()
        projected,layout_receipt=source_projection({relative:payload});records=projected[relative]['monster']
        for index,r in enumerate(records):
            b=blocks.get(norm(r['name']))
            row={'name':r['name'],'source':r['source'],'file':str(file.relative_to(args.data.resolve())).replace('\\','/'),'index':index,'record_sha256':hashlib.sha256(json.dumps(r,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'status':'UNVERIFIED'}
            raw_record=payload['monster'][index]
            if raw_record!=r:
                row['source_projection_sha256']=row['record_sha256']
                row['record_sha256']=hashlib.sha256(json.dumps(raw_record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
                row['approved_layout_normalization']=layout_receipt['model_sha256']
            if not b:
                row['reason']='No unique exact statblock heading';rows.append(row);continue
            row['official_page']=b['page']
            row['official_pages']=sorted({l['page'] for l in b['lines']})
            p=parse_block(b)
            checks,fields=core_checks(r,p)
            row['core_checks']=checks
            # Every official value is printed evidence. Expected values may be
            # explicit storage, computed defaults, or renderer conventions.
            for c in checks:
                field=c['field']
                basis='explicit structured data or decoded printable string'
                if field.startswith('modifier.'):
                    basis='computed: floor((ability score - 10) / 2)'
                elif field.startswith('save.') and field[5:] not in r.get('save',{}):
                    basis='computed default: unlisted save equals ability modifier'
                elif field=='xp' and not (isinstance(r.get('cr'),dict) and 'xp' in r['cr']):
                    basis='computed default: standard CR-to-XP table'
                elif field=='pb' and 'pbNote' not in r:
                    basis='computed default: standard CR-to-Proficiency-Bonus table'
                elif field=='initiative':
                    basis='computed: Dexterity modifier plus stored proficiency multiplier; explicit initiative overrides if present'
                elif field=='initiativePassive':
                    basis='explicit printed initiativePassive source fact' if 'initiativePassive' in r else 'computed renderer convention: 10 + initiative bonus; stored advantageMode adds 5 or subtracts 5'
                elif field in {'size','alignment'}:
                    basis='structured source-fact comparison: size choice set or alignment codes; typography/case/order not mechanics'
                elif field=='gear':
                    basis='structured source-fact comparison: item identities and stored quantities; pluralized item labels'
                elif field=='senses/passive':
                    basis='structured source-fact comparison: decoded senses and passive Perception; comma/semicolon separators normalized'
                c['expected_basis']=basis
                c['official_basis']='printed PDF statblock; source page(s) recorded on this record'
            row['official_fields']=fields
            row['core_status']='VERIFIED' if all(c['status']=='VERIFIED' for c in checks) else 'UNVERIFIED'
            expected=[]
            for section in SECTIONS.values():
                for entry in r.get(section,[]):expected.append({'section':section,'name':decode(entry['name']),'text':flatten(entry)})
                for entry in r.get('spellcasting',[]):
                    if entry.get('displayAs','trait')==section:
                        expected.append({'section':section,'name':decode(entry['name']),'text':spell_entry(entry)})
            unmatched=list(p['entries'])
            entries=[]
            for e in expected:
                options=[o for o in unmatched if o['section']==e['section'] and equal_pdf(e['name'],o['name'])]
                entry={**e,'status':'UNVERIFIED'}
                if len(options)==1:
                    official=options[0];unmatched.remove(official)
                    entry['official_page']=official['page']
                    entry['official']=display_pdf(official['text'])
                    entry['status']='VERIFIED' if equal_pdf(e['text'],official['text']) else 'UNVERIFIED'
                    if entry['status']=='UNVERIFIED':
                        entry['diff']=list(difflib.unified_diff(norm(e['text']).split(),display_pdf(official['text']).split(),fromfile='staging',tofile='official',n=4))
                else:entry['reason']='No unique exact feature heading (possible layout split, missing feature, or heading change)'
                entries.append(entry)
            row['entries']=entries
            row['unmatched_official_entries']=[{'name':o['name'],'section':o['section'],'page':o['page'],'text':display_pdf(o['text'])} for o in unmatched]
            row['unparsed_pdf_lines']=[o['text'] for o in p.get('unparsed',[])]
            if r.get('legendary'):
                shortname=re.sub(r'(adult|ancient|young) \w+ (dragon|dracolich)',r'\2',r['name'].lower())
                ex=f"Legendary Action Uses: 3"+(f" ({r['legendaryActionsLair']} in Lair)" if r.get('legendaryActionsLair') else '')+f". Immediately after another creature's turn, the {shortname} can expend a use to take one of the following actions. The {shortname} regains all expended uses at the start of each of its turns."
                if r.get('legendaryHeader'):ex=flatten(r['legendaryHeader'])
                off=joined(p['legendary_header'])
                row['legendary_header']={'expected':ex,'official':display_pdf(off),'status':'VERIFIED' if equal_pdf(ex,off) else 'UNVERIFIED'}
            row['prose_status']='VERIFIED' if all(e['status']=='VERIFIED' for e in entries) and not unmatched and not p.get('unparsed') and row.get('legendary_header',{}).get('status','VERIFIED')=='VERIFIED' else 'UNVERIFIED'
            if row['core_status']=='VERIFIED' and row['prose_status']=='VERIFIED':row['status']='VERIFIED'
            rows.append(row)
    summary={'pdf_sha256':hashlib.sha256(PDF.read_bytes()).hexdigest(),'source_files_sha256':{str(f.relative_to(args.data.resolve())).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in sorted(DATA.glob('bestiary-*.json'))},'records':len(rows),'official_statblocks':len(blocks),'statuses':dict(collections.Counter(r['status'] for r in rows)),'core_statuses':dict(collections.Counter(r.get('core_status','UNVERIFIED') for r in rows)),'prose_statuses':dict(collections.Counter(r.get('prose_status','UNVERIFIED') for r in rows)),'core_check_totals':dict(collections.Counter(c['status'] for r in rows for c in r.get('core_checks',[]))),'entry_totals':dict(collections.Counter(e['status'] for r in rows for e in r.get('entries',[]))),'core_field_coverage':dict(sorted(collections.Counter(c['field'] for r in rows for c in r.get('core_checks',[])).items()))}
    assert len(rows)==len(blocks)==336
    for ability in AB:
        for prefix in ['', 'modifier.', 'save.']:
            assert summary['core_field_coverage'][prefix+ability]==336,(prefix,ability)
    dump('comparison.json',{'summary':summary,'records':rows})
    dump('official-statblocks-parsed.json',{n:parse_block(b) for n,b in blocks.items()})
    with (OUT/'coverage.csv').open('w',encoding='utf-8',newline='') as out:
        writer=csv.DictWriter(out,fieldnames=['name','source','official_page','status','core_status','prose_status','unverified_core_fields','unverified_prose_entries'])
        writer.writeheader()
        for r in rows:writer.writerow({**{k:r.get(k) for k in ['name','source','official_page','status','core_status','prose_status']},'unverified_core_fields':'; '.join(c['field'] for c in r.get('core_checks',[]) if c['status']!='VERIFIED'),'unverified_prose_entries':'; '.join(e['name'] for e in r.get('entries',[]) if e['status']!='VERIFIED')})
    print(json.dumps(summary,indent=2))
    print('Unverified core fields:',collections.Counter(c['field'] for r in rows for c in r.get('core_checks',[]) if c['status']!='VERIFIED'))
    print('Unmatched official entries:',sum(len(r.get('unmatched_official_entries',[])) for r in rows))


if __name__=='__main__':main()
