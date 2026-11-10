"""Rebuild the data-only SRD 5.2.1 projection from a pinned upstream Git tree.

No network, generator code, installed database, or renderer is modified here.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from source_patches import apply_patches
from printed_text import materialize
from source_identity import apply_citations,SOURCE_ID
from layout_overrides import apply_layouts

UPSTREAM = "32ef600fab87a585a61dd1a22e9b02dfc58c728a"
PDF_URL = "https://media.dndbeyond.com/compendium-images/srd/5.2/SRD_CC_v5.2.1.pdf"
PDF_SHA256 = "8974902d109d6e63672d7c490bde9ccf052410503d9cfa768237154fbc5e3d87"
PRIMARY = {
    "actions": ("action",), "backgrounds": ("background",),
    "bastions": ("bastion", "facility"),
    "conditionsdiseases": ("condition", "disease", "status"),
    "decks": ("deck", "card"), "deities": ("deity",),
    "feats": ("feat",), "items": ("item", "itemGroup"),
    "items-base": ("baseitem", "itemMastery"),
    "languages": ("language",), "magicvariants": ("magicvariant",),
    "optionalfeatures": ("optionalfeature",), "psionics": ("psionic",),
    "races": ("race", "subrace"), "senses": ("sense",),
    "skills": ("skill",), "trapshazards": ("trap", "hazard"),
    "variantrules": ("variantrule",), "vehicles": ("vehicle", "vehicleUpgrade"),
}
DROP = {
    "_meta", "_versions", "additionalSources", "otherSources", "referenceSources",
    "reprintedAs", "alias", "basicRules", "basicRules2024", "srd", "hasFluff",
    "hasFluffImages", "fluff", "hasToken", "hasCardArt", "soundClip", "tokenUrl",
    "tokenCredit", "back", "face", "lootTables", "itemsHidden", "legendaryGroup",
    "environment", "treasure", "origin", "script", "foundryTokenScale", "foundryToken", "foundryFlags",
    "seeAlsoVehicle", "seeAlsoDeck", "seeAlsoAction", "optionalfeatures", "chapter", "parentEntity",
}
TAG_KIND = {"spell":"spell", "item":"item", "creature":"monster", "race":"race",
            "feat":"feat", "optfeature":"optionalfeature", "action":"action",
            "condition":"condition", "status":"status", "skill":"skill",
            "sense":"sense", "variantrule":"variantrule", "table":"table",
            "deck":"deck", "card":"card", "itemEntry":"itemEntry", "class":"class",
            "background":"background", "language":"language", "itemProperty":"itemProperty",
            "itemMastery":"itemMastery", "hazard":"hazard"}


def encode(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def selected(record):
    return isinstance(record, dict) and bool(record.get("srd52") or record.get("inherits", {}).get("srd52"))


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value: yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values(): yield from strings(item)


def uid(value):
    return value.get("uid", value.get("item", "")) if isinstance(value, dict) else str(value)


class Builder:
    def __init__(self, source):
        self.source = Path(source).resolve()
        revision = subprocess.check_output(["git", "rev-parse", UPSTREAM + "^{commit}"], cwd=self.source).decode().strip()
        if revision != UPSTREAM: raise ValueError("Unexpected upstream revision")
        self.paths = subprocess.check_output(["git", "ls-tree", "-r", "--name-only", UPSTREAM, "data"], cwd=self.source).decode().splitlines()
        self.cache = {}
        self.data = {}
        self.receipts = []
        self.changes = []
        self.aliases = {}

    def read(self, path):
        if path not in self.cache:
            raw = subprocess.check_output(["git", "show", UPSTREAM + ":" + path], cwd=self.source)
            self.cache[path] = json.loads(raw)
        return self.cache[path]

    def note(self, record, reason):
        self.changes.append({"name":record.get("name", ""), "source":record.get("source", ""), "reason":reason})

    def add(self, path, kind, original, reason="explicit srd52 marker"):
        record = copy.deepcopy(original)
        if kind=="table" and record.get("name")=="Creature Size and Space" and record.get("source")=="XDMG":
            self.note(record,"Exclude duplicate XDMG size table with non-SRD hex column; retain the SRD p14 XPHB table")
            return
        if isinstance(record.get("srd52"), str): self.aliases[record["name"]] = record["srd52"]
        self.correct(record, kind)
        self.data.setdefault(path, {}).setdefault(kind, []).append(record)
        self.receipts.append({"file":path, "kind":kind, "name":original.get("name", original.get("abbreviation", "")),
                              "source":original.get("source", original.get("inherits", {}).get("source", "")),
                              "reason":reason, "upstream_record_sha256":None if reason.startswith("derived directly") else hashlib.sha256(encode(original)).hexdigest()})

    def correct(self, record, kind):
        name = record.get("name")
        if name == "Orb of Dragonkind" and kind == "item":
            entries = record["entries"]
            assert entries[0].startswith("Long ago, in the Dragonlance setting")
            assert entries[3].startswith("An orb is an etched crystal globe")
            assert entries[6]["name"] == "Random Properties"
            record["entries"] = entries[3:6] + entries[7:]
            self.note(record, "SRD p218: remove three introductory non-SRD paragraphs and Random Properties; preserve official Tiamat references")
        if name == "Jack of All Trades" and kind == "classFeature":
            record["entries"] = [entry for entry in record["entries"] if not (isinstance(entry, dict) and entry.get("name") == "A Bard's Repertoire")]
            self.note(record, "SRD p32: exclude A Bard's Repertoire inset")
        if name == "Deck of Many Things" and kind == "item":
            record["entries"] = [entry for entry in record["entries"] if not (isinstance(entry, dict) and entry.get("name") == "A Question of Enmity")]
            self.note(record, "SRD p231-232: exclude A Question of Enmity inset")
        if name == "Fiend Patron" and kind == "subclassFeature":
            old = "You might forge a bargain with a demon lord such as Demogorgon or Orcus; an archdevil such as Asmodeus; or a pit fiend, balor, yugoloth, or night hag that is especially mighty."
            assert old in record["entries"][1]
            record["entries"][1] = record["entries"][1].replace(old, "You might forge a bargain with a demon lord, an archdevil, or another fiend that is especially mighty.")
            self.note(record, "SRD p76: use the published patron examples")
        if name == "Pact of the Chain" and kind == "optionalfeature":
            old = "{@creature Slaad Tadpole|XMM}, "
            assert old in record["entries"][1]
            record["entries"][1] = record["entries"][1].replace(old, "").replace("see appendix B", "see Monsters")
            self.note(record, "SRD p74: remove Slaad Tadpole and point at Monsters")
        if name == "Gloves of Swimming and Climbing" and kind == "item":
            record["entries"] = ["While wearing these gloves, you have a Climb Speed and a Swim Speed equal to your Speed, and you gain a +5 bonus to Strength ({@skill Athletics|XPHB}) checks made to climb or swim."]
            self.note(record, "SRD p224: use the published climb/swim-speed benefit")
        if name == "Staff of Withering" and kind == "item":
            record["reqAttune"] = True
            record.pop("reqAttuneTags", None)
            self.note(record, "SRD p248: attunement has no class restriction")
        if name == "Choose a Background; Ability Scores and Backgrounds" and kind == "table":
            record["rows"] = [[ability, "{@background "+background+"|XPHB}"] for ability,background in
                              [("Strength","Soldier"),("Dexterity","Soldier"),("Constitution","Soldier"),
                               ("Intelligence","Acolyte"),("Wisdom","Acolyte"),("Charisma","Acolyte")]]
            self.note(record, "SRD p19-20: use its ability/background table, not the full PHB list")
        if name == "Multiclassing" and kind == "variantrule":
            def third_casters(value):
                if isinstance(value,list): return [third_casters(item) for item in value if not (isinstance(item,str) and item.startswith("One third of your Fighter or Rogue levels"))]
                if isinstance(value,dict): return {key:third_casters(item) for key,item in value.items()}
                return value
            record.update(third_casters(record))
            self.note(record, "SRD p25: exclude the non-SRD third-caster subclass bullet")
        if name == "Don or Doff a Shield" and kind == "action":
            record["entries"] = ["A {@item Shield|XPHB} can be donned or doffed as a {@action Utilize|XPHB} action."]
            self.note(record, "SRD p92: shield don/doff uses the Utilize action")
        if name == "Telekinesis" and kind == "spell":
            section=record["entries"][2]["entries"]
            assert section[2].startswith("You can exert fine control on objects")
            section[2] = "You can exert fine control on objects with your telekinetic grip, such as manipulating a simple tool."
            self.note(record, "SRD p168 visually verified: exclude upstream continuation after simple tool; close its printed dangling comma with a period")
        if name == "Wish" and kind == "spell":
            section=record["entries"][3]["items"][6]["entries"]
            removed="If your wish would undo the multiverse itself, threaten the City of Sigil, or affect the Lady of Pain in any way, you see an image of her in your mind for a moment; she shakes her head, and your wish fails."
            assert section[0].endswith(removed)
            section[0]=section[0].removesuffix(removed)+"If your wish would undo the multiverse itself, your wish fails."
            self.note(record, "SRD p175: preserve multiverse restriction while excluding the added Sigil/Lady of Pain clause")
        if kind == "table" and record.get("caption") in {"Standard Languages","Rare Languages"}:
            index=record["colLabels"].index("Origin")
            record["colLabels"].pop(index);record["colStyles"].pop(index)
            for row in record["rows"]:row.pop(index)
            self.note(record, "SRD p20: exclude the full-PHB Origin column")
        if kind in {"item","deck"} and name == "Deck of Illusions":
            table=record["entries"][3]
            assert table["rows"][4][1]=="{@creature Beholder|XMM}"
            table["rows"][4][1]="{@creature Basilisk|XMM}"
            if kind=="deck":
                record["cards"]=["Basilisk|Deck of Illusions|SRD52" if uid(value)=="Beholder|Deck of Illusions|XDMG" else value for value in record["cards"]]
            self.note(record, "SRD p217: 13-15 is Basilisk, not Beholder")
        if kind=="table" and name=="Difficulty Class; Typical DCs":
            for row in record["rows"]:
                if row[0]=="Moderate":row[0]="Medium"
            self.note(record,"SRD p6: the DC15 difficulty label is Medium")
        if kind=="table":
            if name=="Ability Modifier; Attack Roll Abilities":
                record["rows"][2][1]=record["rows"][2][1].replace("{@area chapter 7|728|x}",'"Spells"')
            if name=="Mixing Potions; Potion Miscibility":
                record["rows"][1][1]=record["rows"][1][1].replace("{@area chapter 3|0e7|x}",'"Gameplay Toolbox"')
            if name=="Magic Item Values by Rarity; Magic Item Rarities and Values":
                record["footnotes"][0]=record["footnotes"][0].replace("the {@book Player's Handbook|XPHB}",'the "Scribing Spell Scrolls" section of "Equipment"')
            if name=="Magic Item Crafting Time and Cost":
                record["footnotes"][0]=record["footnotes"][0].replace("the {@book Player's Handbook|XPHB}",'"Equipment"')
            if name=="Resolving Outcomes; Abilities, Ability Checks, and Saving Throws":
                record["rows"][1][1]="Agility, reflexes, and balance"
            if name=="Actions":
                record["rows"][2][1]=record["rows"][2][1].replace("{@action Opportunity Attack|XPHB}","{@action Opportunity Attack|XPHB|Opportunity Attacks}")
        if name in {"Firearm Bullet", "Firearm Bullets (10)"} and kind == "baseitem":
            record["entries"] = [entry for entry in record.get("entries", []) if not (isinstance(entry, str) and "modern firearm" in entry)]
            self.note(record, "SRD p94: omit modern-firearm ammunition rule absent from the document")
        if kind=="language":
            caption="Standard Languages" if record.get("type")=="standard" else "Rare Languages"
            source_table=next(table for table in self.read("data/generated/gendata-tables.json")["table"] if table.get("caption")==caption and table.get("source")=="XPHB")
            if caption=="Standard Languages":
                row=next(row for row in source_table["rows"] if re.search(r"\{@language "+re.escape(name)+r"\|", str(row[1])))
                roll=row[0]
                if isinstance(roll,dict):
                    values=roll["roll"]
                    roll=str(values["exact"]) if "exact" in values else f'{values["min"]}–{values["max"]}'
                table={"type":"table","caption":caption,"colLabels":["1d12","Language"],"rows":[[roll,name]]}
            else:
                row=next(row for row in source_table["rows"] if row[0].rstrip("*")==name)
                table={"type":"table","caption":caption,"colLabels":["Language"],"rows":[copy.deepcopy(row[:1])]}
            record["entries"]=[table]
            if name=="Primordial":
                table["footnotes"]=copy.deepcopy(source_table["footnotes"])
                record["dialects"]=["Aquan","Auran","Ignan","Terran"]
            self.note(record,"SRD p20: project the literal language table header, row and applicable footnote; no invented Category column or commercial origin lore")
        def ruin(value):
            if isinstance(value, str):
                return value.replace("If you have a Bastion (see the {@book Dungeon Master's Guide|XDMG|7}), it is destroyed by some calamity beyond your control. ", "")
            if isinstance(value, list): return [ruin(item) for item in value]
            if isinstance(value, dict): return {key:ruin(item) for key,item in value.items()}
            return value
        if name in {"Deck of Many Things", "Ruin"} and kind in {"item", "card"}:
            record.update(ruin(record))
            self.note(record, "SRD p232: exclude the additional Bastion sentence in Ruin")

    def collect(self):
        for stem, kinds in PRIMARY.items():
            path = f"data/{stem}.json"
            original = self.read(path) if path in self.paths else {}
            self.data[path] = {kind:[] for kind in kinds}
            for kind in kinds:
                for record in original.get(kind, []):
                    if selected(record): self.add(path, kind, record)
        # Upstream omits the SRD-only Basilisk illusion card. Derive the minimal
        # record from the official p217 outcome, never from a commercial entity.
        derived={"name":"Basilisk","set":"Deck of Illusions","source":"SRD52","page":217,
                 "srd52":True,"entries":["This card creates an illusion of a {@creature Basilisk|XMM}."]}
        self.add("data/decks.json","card",derived,"derived directly from SRD p217: missing Basilisk illusion outcome")
        for path in self.paths:
            if path.startswith("data/class/class-") and path.endswith(".json"):
                kinds = ("class", "subclass", "classFeature", "subclassFeature")
            elif path.startswith("data/spells/spells-") and path.endswith(".json"):
                kinds = ("spell",)
            elif path.startswith("data/bestiary/bestiary-") and path.endswith(".json"):
                kinds = ("monster",)
            elif path in ("data/generated/gendata-tables.json", "data/generated/gendata-variantrules.json"):
                kinds = ("table", "tableGroup") if "tables" in path else ("variantrule",)
            else: continue
            original = self.read(path)
            for kind in kinds:
                for record in original.get(kind, []):
                    if selected(record): self.add(path, kind, record)

    def records(self):
        for path, payload in self.data.items():
            for kind, records in payload.items():
                if not isinstance(records, list): continue
                for record in records:
                    if isinstance(record, dict): yield path, kind, record

    def helpers(self):
        base = self.read("data/items-base.json")
        # Only modern types represented by retained base gear can constrain
        # variants. Modern/futuristic DMG ammunition is not SRD ammunition.
        types = {str(record.get("type", "")).split("|")[0] for _, kind, record in self.records() if kind == "baseitem"}
        for _, kind, record in self.records():
            if kind == "magicvariant" and "requires" in record:
                record["requires"] = [rule for rule in record["requires"] if not rule.get("type") or str(rule["type"]).split("|")[0] in types]
                if not record["requires"]: raise ValueError("Variant has no SRD-compatible base: " + record["name"])
        needed_types = set()
        needed_properties = set()
        needed_entries = set()
        for _, kind, record in self.records():
            for text in strings(record):
                for ref in re.findall(r"\{[#@]itemEntry ([^{}]+)\}", text):
                    parts = ref.split("|");needed_entries.add((parts[0].lower(), parts[1].upper() if len(parts)>1 and parts[1] else "XDMG"))
            if kind not in {"item", "baseitem", "itemGroup", "magicvariant"}: continue
            for entity in (record, record.get("inherits", {})):
                if entity.get("type"):
                    value = entity["type"]
                    if isinstance(value, str): needed_types.add(value.split("|")[0])
                needed_properties.update(uid(value).split("|")[0] for value in entity.get("property", []))
        # Restrict helper candidates to the SRD-era books; reachability alone
        # never promotes a commercial entity or a legacy helper definition.
        for kind, needed, field in (("itemType", needed_types, "abbreviation"), ("itemProperty", needed_properties, "abbreviation")):
            candidates = {record[field]:record for record in base[kind] if record.get("source") == "XDMG"}
            candidates.update({record[field]:record for record in base[kind] if record.get("source") == "XPHB"})
            for code in sorted(needed):
                if code in {"AF", "BF", "RLD"}: raise ValueError("Non-SRD modern-firearm helper requested")
                if code not in candidates: raise ValueError(f"No SRD {kind} helper for {code}")
                record = copy.deepcopy(candidates[code])
                if "_copy" in record:
                    parent = candidates[record["_copy"][field]]
                    record = {**copy.deepcopy(parent), **record};record.pop("_copy", None)
                self.add("data/items-base.json", kind, record, "referenced modern SRD gear helper")
        entry_map = {(record["name"].lower(), record["source"].upper()):record for record in base["itemEntry"]}
        for key in sorted(needed_entries):
            if key[1] != "XDMG" or key not in entry_map: raise ValueError("Non-SRD itemEntry dependency: " + repr(key))
            if key[0] not in {"armor of resistance", "dragon scale mail", "ioun stone", "potion of resistance", "ring of resistance"}:
                raise ValueError("Unreviewed itemEntry dependency: " + repr(key))
            self.add("data/items-base.json", "itemEntry", entry_map[key], "referenced SRD template; reviewed against official item text")
        self.data["data/items-base.json"]["itemTypeAdditionalEntries"] = []

    def clean(self, value, kind=""):
        if isinstance(value, list): return [self.clean(item, kind) for item in value]
        if not isinstance(value, dict): return value
        result = {}
        for key, item in value.items():
            if key in DROP or key.startswith("foundry"): continue
            if key == "classFeatures" and kind not in {"class", "subclass", "classFeature", "subclassFeature"}: continue
            result[key] = self.clean(item, kind)
        return result

    def prepare(self):
        self.collect()
        self.helpers()
        for path, payload in self.data.items():
            for kind, records in payload.items():
                payload[kind] = [self.clean(record, kind) for record in records]
        alias_patterns = [(re.compile(re.escape(name), re.I), alias) for name, alias in sorted(self.aliases.items(), key=lambda pair:-len(pair[0]))]
        def rename(value):
            if isinstance(value, str):
                for pattern, alias in alias_patterns: value = pattern.sub(lambda match:alias, value)
                return value
            if isinstance(value, list): return [rename(item) for item in value]
            if isinstance(value, dict): return {rename(key):rename(item) for key,item in value.items()}
            return value
        self.data = rename(self.data)
        # Index each public entity, with safe cross-edition link repair only
        # when an already-retained entity supplies that identity.
        self.entities = {}
        for _, kind, record in self.records():
            name=record.get("abbreviation") if kind in {"itemType","itemProperty"} else record.get("name")
            if name:
                public_kind = "item" if kind in {"baseitem", "magicvariant", "itemGroup"} else kind
                self.entities.setdefault((public_kind, name.lower()), []).append(record)
        self.repair_references()
        # Check the original equivalent projections before literal source
        # corrections change punctuation, captions or citations in retained
        # tables. The excluded records have no correction policies.
        self.exclude_unprinted_tables()
        self.changes.extend(apply_patches(self.data, PDF_SHA256))
        # These are generated 5etools search indexes, not printed rules. Neither
        # card application reads them. Keep literal entries, actual attunement
        # requirements, typed references and the source-proven consumable fact.
        # Do this after preconditioned corrections so their frozen preimages
        # remain reproducible and independently auditable.
        lookup_fields={"miscTags","reqAttuneTags","attachedSpells"}
        removed=[];removed_counts={key:0 for key in sorted(lookup_fields)}
        for path,kind,record in self.records():
            fields={}
            for label,target in (("record",record),("inherits",record.get("inherits",{}))):
                keys=sorted(lookup_fields.intersection(target))
                if not keys:continue
                fields[label]=keys
                for key in keys:
                    del target[key];removed_counts[key]+=1
            if fields:removed.append({"file":path,"kind":kind,"name":record.get("name",record.get("abbreviation","")),"removed_fields":fields})
        self.changes.append({"reason":"Exclude redundant generated query indexes, unused by both consumers, while retaining source text and actual source facts/references","fields":sorted(lookup_fields),"counts":removed_counts,"records":removed})
        # The pinned official SRD uses GM throughout (zero standalone DM
        # occurrences). Commercial-source keys such as XDMG are unchanged.
        def gm_terms(value):
            if isinstance(value,str):return re.sub(r'\bDM\b','GM',value)
            if isinstance(value,list):return [gm_terms(item) for item in value]
            if isinstance(value,dict):return {key:gm_terms(item) for key,item in value.items()}
            return value
        self.data=gm_terms(self.data)
        self.changes.append({"reason":"Official SRD 5.2.1 narrative terminology: replace standalone DM with GM; source IDs and enum keys are preserved","official_pdf_sha256":PDF_SHA256})
        self.data=materialize(self.data)
        self.changes.append({"reason":"Materialize display tags as literal source text for compatibility with both unchanged card consumers; preserve structural UIDs and itemEntry parameters"})
        self.class_spell_lists()
        self.data,citation_receipt=apply_citations(self.data,Path(__file__).resolve().parents[1]/"source/citations.json",PDF_SHA256,UPSTREAM)
        self.citation_receipt=citation_receipt
        self.changes.append(citation_receipt)
        # Data-only presentation choices follow the fully guarded source
        # projection. Their exact inverse is checked by source-only audits.
        self.data,self.layout_receipt=apply_layouts(self.data,PDF_SHA256,UPSTREAM)
        self.changes.append(self.layout_receipt)
        self.indexes()

    def class_spell_lists(self):
        # These lists are missing upstream. Keep the actual printed tables as
        # standard tableGroup records, independently of spell-header labels.
        # They must not be repackaged as class progression rows or feature
        # levels: both card consumers have specialized progression handling.
        model=json.loads((Path(__file__).resolve().parents[1]/"source/class-spell-lists.json").read_text(encoding="utf-8"))
        if model["official_pdf_sha256"]!=PDF_SHA256:raise ValueError("Class spell-list source changed")
        groups=model["table_groups"]
        assert len(groups)==8 and len({g["name"] for g in groups})==8
        assert sum(len(g["tables"]) for g in groups)==70
        assert sum(len(t["rows"]) for g in groups for t in g["tables"])==875
        for group in groups:
            self.add("data/generated/gendata-tables.json","tableGroup",group,
                     "derived directly from SRD 5.2.1 printed base-class spell-list tables and their introductory C/R/M legend; verified by fresh PDF cell-grid extraction")

    def exclude_unprinted_tables(self):
        # The full-DMG summary projections are not printed in the SRD. Their
        # every cell is already retained in the actual SRD's three ability
        # tables and Typical Difficulty Classes. Check that lossless coverage
        # before excluding the non-source captions/column packaging.
        tables=self.data["data/generated/gendata-tables.json"]["table"]
        by_caption={table["caption"]:table for table in materialize(copy.deepcopy(tables))}
        descriptions=by_caption["Ability Descriptions"]["rows"]
        checks=dict(by_caption["Ability Check Examples"]["rows"])
        saves=dict(by_caption["Saving Throw Examples"]["rows"])
        summary=by_caption["Abilities, Ability Checks, and Saving Throws"]
        assert summary["source"]=="XDMG" and summary["rows"]==[[ability,description,checks[ability],saves[ability]] for ability,description in descriptions]
        dcs=by_caption["Typical DCs"]
        assert dcs["source"]=="XDMG" and dcs["rows"]==by_caption["Typical Difficulty Classes"]["rows"]
        excluded={summary["name"],dcs["name"]}
        self.data["data/generated/gendata-tables.json"]["table"]=[table for table in tables if table["name"] not in excluded]
        self.changes.append({"reason":"Exclude two nonprinted full-DMG table projections; exact cell coverage is checked against the retained printed SRD tables","excluded_tables":sorted(excluded),"retained_source_tables":["Ability Descriptions","Ability Check Examples","Saving Throw Examples","Typical Difficulty Classes"],"official_pages":[5,6,7]})

    def repair_references(self):
        features = {}
        for _, kind, record in self.records():
            if kind not in {"classFeature", "subclassFeature"}: continue
            key = [record["name"], record["className"], record["classSource"]]
            if kind == "subclassFeature": key += [record["subclassShortName"], record["subclassSource"]]
            key += [str(record["level"]), record["source"]]
            features[(kind, "|".join(key).lower())] = record
        def feature_exists(kind, uid):
            parts = uid.split("|")
            source_index = 6 if kind == "subclassFeature" else 4
            if len(parts) == source_index: parts.append(parts[4] if kind == "subclassFeature" else parts[2])
            return (kind, "|".join(parts).lower()) in features
        def tag(match):
            name, body = match.group(1), match.group(2)
            parts = body.split("|")
            if name in {"book","area"}: return parts[0]
            kind = TAG_KIND.get(name)
            if not kind: return match.group(0)
            candidates = self.entities.get((kind, parts[0].lower()), [])
            if not candidates:
                # An SRD mention is not permission to import the target's stats.
                return parts[2] if len(parts)>2 and parts[2] else parts[0]
            target = next((record for record in candidates if len(parts)>1 and record.get("source", "").lower()==parts[1].lower()), candidates[0])
            if len(parts)<2: parts.append(target.get("source", ""))
            else: parts[1] = target.get("source", parts[1])
            return "{@"+name+" "+"|".join(parts)+"}"
        def walk(value):
            if isinstance(value, str): return re.sub(r"\{@([A-Za-z]+) ([^{}]*)\}", tag, value)
            if isinstance(value, list): return [walk(item) for item in value]
            if isinstance(value, dict):
                result = {}
                for key,item in value.items():
                    if key in {"classFeatures", "subclassFeatures"} and isinstance(item, list):
                        kind = "subclassFeature" if key == "subclassFeatures" else "classFeature"
                        kept=[]
                        for ref in item:
                            uid = ref if isinstance(ref,str) else ref.get(kind, "")
                            if feature_exists(kind,uid): kept.append(ref)
                            else: self.changes.append({"reference":uid,"reason":"unselected structural class feature excluded; no dependency promotion"})
                        item=kept
                    if key == "type" and isinstance(item,str) and item in {"refClassFeature", "refSubclassFeature"}:
                        kind = item[3].lower()+item[4:]
                        if not feature_exists(kind,value.get(kind,"")): raise ValueError("Unselected nested feature reference")
                    result[key]=walk(item)
                return result
            return value
        self.data = walk(self.data)
        card_keys={(record["name"].lower(),record["set"].lower(),record["source"].lower()) for _,kind,record in self.records() if kind=="card"}
        for _,kind,record in self.records():
            if kind=="deck":
                record["cards"]=[packed for packed in record["cards"] if tuple(uid(packed).lower().split('|')) in card_keys]

    def indexes(self):
        self.data["data/class/index.json"] = {Path(path).stem.removeprefix("class-"):Path(path).name for path in sorted(self.data) if path.startswith("data/class/class-")}
        for category, kind in (("spells", "spell"), ("bestiary", "monster")):
            index = {}
            for path, payload in self.data.items():
                if path.startswith(f"data/{category}/{category}-"):
                    for record in payload[kind]: index[record["source"]] = Path(path).name
            self.data[f"data/{category}/index.json"] = dict(sorted(index.items()))
        self.data["data/bestiary/legendarygroups.json"] = {"legendaryGroup":[]}
        self.data["data/bestiary/template.json"] = {"monsterTemplate":[]}

    def output(self):
        self.prepare()
        files = {path:encode(payload) for path,payload in sorted(self.data.items())}
        counts = {}
        for _,kind,record in self.records(): counts[kind] = counts.get(kind,0)+1
        manifest = {"format":"TTRPG Card Generator SRD data", "srd":"5.2.1", "source_id":SOURCE_ID,
                    "citation_model_sha256":self.citation_receipt['citation_model_sha256'],
                    "layout_model_sha256":self.layout_receipt['model_sha256'],
                    "official_pdf":PDF_URL, "official_pdf_sha256":PDF_SHA256,
                    "counts":dict(sorted(counts.items())),
                    "sha256":{path:hashlib.sha256(data).hexdigest() for path,data in files.items()}}
        files["manifest.json"] = encode(manifest)
        return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    output = args.out.resolve()
    if output == args.upstream.resolve(): raise ValueError("Build into a separate staging directory")
    files = Builder(args.upstream).output()
    for name,data in files.items():
        path = output/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    print(json.dumps({"output":str(output),"files":len(files),"counts":json.loads(files['manifest.json'])["counts"]},indent=2))


if __name__ == "__main__": main()
