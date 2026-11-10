import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder, UPSTREAM, encode, selected, strings
from validate_srd import validate


class SrdProjectionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder=Builder(ROOT)
        cls.files=cls.builder.output()
        cls.manifest=json.loads(cls.files['manifest.json'])
        cls.data={name:json.loads(value) for name,value in cls.files.items() if name.startswith('data/')}

    def record(self,path,kind,name):
        return next(record for record in self.data[path][kind] if record.get('name')==name)

    def test_only_explicit_2024_marker_selects_entities(self):
        self.assertFalse(selected({'srd':True,'basicRules2024':True}))
        self.assertFalse(selected({'srd52':False}))
        self.assertTrue(selected({'srd52':'Arcane Hand'}))
        self.assertTrue(selected({'inherits':{'srd52':True}}))

    def test_specific_ammunition_equivalence_overrides_general_consumable_value(self):
        # SRD p208: ten enhanced pieces equal one potion of the same rarity;
        # p206 halves the generic rarity value for the potion. Per-piece values
        # are therefore 20/200/2,000 GP, not 200/2,000/20,000 GP.
        for bonus,gp in [(1,20),(2,200),(3,2000)]:
            item=self.record('data/magicvariants.json','magicvariant',f'+{bonus} Ammunition')['inherits']
            self.assertIs(item['consumable'],True)
            self.assertEqual(item['value'],gp*100)
        bead=self.record('data/items.json','item','Bead of Force')
        self.assertIs(bead['consumable'],True)
        self.assertEqual(bead['weight'],1/16)  # One ounce, not half a pound.

    def test_public_records_keep_rules_without_redundant_query_indexes(self):
        forbidden={'miscTags','reqAttuneTags','attachedSpells'}
        for path,payload in self.data.items():
            for items in payload.values():
                if not isinstance(items,list):continue
                for item in items:
                    if not isinstance(item,dict):continue
                    self.assertFalse(forbidden.intersection(item),(path,item.get('name')))
                    self.assertFalse(forbidden.intersection(item.get('inherits',{})),(path,item.get('name')))
        self.assertEqual(self.record('data/items.json','item','Amulet of Health')['reqAttune'],True)
        self.assertIn('Constitution',str(self.record('data/items.json','item','Amulet of Health')['entries']))

    def test_retained_table_structure_follows_the_printed_srd(self):
        tables=self.data['data/generated/gendata-tables.json']['table']
        captions={table['caption'] for table in tables}
        self.assertNotIn('Abilities, Ability Checks, and Saving Throws',captions)
        self.assertNotIn('Typical DCs',captions)
        self.assertTrue({'Ability Descriptions','Ability Check Examples','Saving Throw Examples','Typical Difficulty Classes'}<=captions)
        background=next(table for table in tables if table['caption']=='Ability Scores and Backgrounds')
        self.assertEqual(background['colLabels'],['Ability','Background'])
        # The actual SRD p19/20 table lists these two backgrounds, despite
        # containing four background descriptions elsewhere. Preserve the table.
        self.assertEqual(background['rows'],[[ability,'Soldier'] for ability in ['Strength','Dexterity','Constitution']]+[[ability,'Acolyte'] for ability in ['Intelligence','Wisdom','Charisma']])

    def test_expected_core_coverage_and_empty_non_srd_categories(self):
        for kind,count in {'class':12,'subclass':12,'race':9,'spell':339,'monster':336,'feat':17,'background':4,'language':19}.items():
            self.assertEqual(self.manifest['counts'][kind],count,kind)
        for path in ('deities','bastions','psionics','vehicles'):
            self.assertFalse(any(self.data['data/'+path+'.json'].values()))
        self.assertFalse(any('/book/' in name or '/adventure/' in name or 'prerelease' in name or 'fluff' in name for name in self.files))

    def test_aliases_apply_to_titles_rules_tables_and_links(self):
        orb=self.record('data/items.json','item','Dragon Orb')
        self.assertEqual(orb['srd52'],'Dragon Orb')
        self.assertNotIn('Orb of Dragonkind','\n'.join(strings(orb)))
        crab=self.record('data/items.json','item','Apparatus of the Crab')
        self.assertNotIn('Kwalish','\n'.join(strings(crab)))
        table=next(entry for entry in crab['entries'] if isinstance(entry,dict) and entry.get('type')=='table')
        self.assertEqual(len(table['rows']),10)
        self.record('data/spells/spells-xphb.json','spell','Arcane Hand')
        self.assertFalse(any(record.get('name')=="Bigby's Hand" for record in self.data['data/spells/spells-xphb.json']['spell']))

    def test_orb_uses_srd_prose_without_removing_valid_named_references(self):
        orb=self.record('data/items.json','item','Dragon Orb');text='\n'.join(strings(orb))
        self.assertTrue(orb['entries'][0].startswith('An orb is an etched crystal globe'))
        self.assertNotIn('Dragonlance',text);self.assertNotIn('Random Properties',text)
        self.assertIn('Tiamat',text)
        self.record('data/bestiary/bestiary-srd521.json','monster','Minotaur of Baphomet')
        self.assertIn('Ioun','\n'.join(strings(self.record('data/items-base.json','itemEntry','Ioun Stone'))))

    def test_full_deck_contains_the_official_basilisk_outcome(self):
        deck=self.record('data/decks.json','deck','Deck of Illusions')
        self.assertEqual(len(deck['cards']),33)  # 32 creatures plus the mirrored-card outcome.
        self.assertIn('Basilisk|Deck of Illusions|SRD521',deck['cards'])
        self.assertNotIn('Beholder','\n'.join(strings(deck)))
        card=self.record('data/decks.json','card','Basilisk')
        self.assertEqual((card['source'],card['page']),('SRD521',217))
        self.assertTrue(any('derived directly' in receipt['reason'] and receipt['name']=='Basilisk' for receipt in self.builder.receipts))
        for kind,path in [('item','data/items.json'),('deck','data/decks.json')]:
            table=self.record(path,kind,'Deck of Illusions')['entries'][3]
            self.assertEqual(table['rows'][4],['13–15','Basilisk'])
            self.assertEqual(table['rows'][30],['91–93','Veteran Warrior'])
            self.assertEqual(table['colLabels'],['1d100','Illusion*'])

    def test_wish_preserves_the_srd_multiverse_rule(self):
        wish=self.record('data/spells/spells-xphb.json','spell','Wish')
        text='\n'.join(strings(wish))
        self.assertIn('If your wish would undo the multiverse itself, your wish fails.',text)
        self.assertNotIn('Sigil',text);self.assertNotIn('Lady of Pain',text)

    def test_no_unselected_entity_is_promoted_as_a_dependency(self):
        for payload in self.data.values():
            for kind,records in payload.items():
                if not isinstance(records,list):continue
                for record in records:
                    if kind not in {'itemType','itemProperty','itemEntry'}:self.assertTrue(selected(record),record.get('name'))
        self.assertEqual(self.data['data/bestiary/legendarygroups.json'],{'legendaryGroup':[]})
        ranger=self.record('data/class/class-ranger.json','class','Ranger')
        self.assertNotIn('Pet Specialization','\n'.join(strings(ranger)))
        self.assertEqual(ranger['casterProgression'],'artificer')

    def test_only_needed_reviewed_helpers_and_no_unresolved_copies(self):
        base=self.data['data/items-base.json']
        self.assertEqual({item['name'] for item in base['itemEntry']},{'Armor of Resistance','Dragon Scale Mail','Ioun Stone','Potion of Resistance','Ring of Resistance'})
        self.assertFalse(base['itemTypeAdditionalEntries'])
        self.assertFalse({'AF','BF','RLD'} & {record['abbreviation'] for record in base['itemProperty']})
        for record in base['itemType']:self.assertNotIn('_copy',record)

    def test_source_correct_attunement_speeds_and_familiar_options(self):
        staff=self.record('data/items.json','item','Staff of Withering')
        self.assertIs(staff['reqAttune'],True);self.assertNotIn('reqAttuneTags',staff)
        gloves=self.record('data/items.json','item','Gloves of Swimming and Climbing')
        self.assertIn('Climb Speed and a Swim Speed equal to your Speed',gloves['entries'][0])
        chain=self.record('data/optionalfeatures.json','optionalfeature','Pact of the Chain')
        self.assertNotIn('Slaad Tadpole','\n'.join(strings(chain)))

    def test_languages_keep_srd_table_facts_without_commercial_origins(self):
        for record in self.data['data/languages.json']['language']:
            self.assertNotIn('origin',record);self.assertNotIn('script',record)
            self.assertIn(record['name'],record['entries'][0]['rows'][0][-1])
            self.assertNotIn('Category',record['entries'][0]['colLabels'])
        for table in self.data['data/generated/gendata-tables.json']['table']:
            self.assertNotIn('Origin',table.get('colLabels',[]))

    def test_validator_catches_stale_references_and_unselected_payloads(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            for name,value in self.files.items():
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(value)
            self.assertTrue(validate(root)['passed'])
            path='data/decks.json';deck=copy.deepcopy(self.data[path]);deck['deck'][0]['cards'].append('Unlicensed|Deck of Illusions|XDMG')
            raw=encode(deck);(root/path).write_bytes(raw)
            manifest=copy.deepcopy(self.manifest);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest();(root/'manifest.json').write_bytes(encode(manifest))
            result=validate(root);self.assertFalse(result['passed']);self.assertTrue(any('Deck card:' in error for error in result['errors']))
            path='data/feats.json';feats=copy.deepcopy(self.data[path]);feats['feat'].append({'name':'Not SRD','source':'Commercial','entries':['Not released.']})
            raw=encode(feats);(root/path).write_bytes(raw);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest();(root/'manifest.json').write_bytes(encode(manifest))
            self.assertTrue(any('Unselected entity:' in error for error in validate(root)['errors']))

    def test_pinned_rebuild_is_byte_deterministic(self):
        self.assertEqual(Builder(ROOT).output(),self.files)
        self.assertFalse({'upstream','upstream_commit','selection_receipts','content_corrections'} & self.manifest.keys())

    def test_capacity_item_uids_and_quantities_are_validated_beyond_file_hashes(self):
        cases=[({'item':[{'bolt|srd521':20}]},True,None),
               ({'item':[{'bolt|xphb':20}]},False,'Container item:'),
               ({'item':[{'missing item|srd521':20}]},False,'Container item:'),
               ({'item':[{'bolt|srd521':True}]},False,'Container item quantity:'),
               ({'item':[{'bolt|srd521':0}]},False,'Container item quantity:'),
               ({'item':[[]]},False,'Container capacity compartment shape:'),
               ({'item':{}},False,'Container capacity item shape:'),
               (None,False,'Container capacity shape:')]
        for capacity,valid,message in cases:
            with self.subTest(capacity=capacity),tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                for name,raw in self.files.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                path='data/items.json';payload=copy.deepcopy(self.data[path])
                next(r for r in payload['item'] if r['name']=='Crossbow Bolt Case')['containerCapacity']=capacity
                raw=encode(payload);(root/path).write_bytes(raw)
                manifest=copy.deepcopy(self.manifest);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest()
                (root/'manifest.json').write_bytes(encode(manifest))
                result=validate(root);self.assertEqual(result['passed'],valid,result['errors'])
                if not valid:self.assertTrue(any(message in e for e in result['errors']),result['errors'])

    def test_source_pages_source_ids_and_indexes_are_checked_beyond_file_hashes(self):
        for action,expected_error in [('source','Non-SRD source identity'),('page','Citation page differs'),('index','Incomplete source index'),('class-index','Incomplete source index: class'),('model','source citation model'),('probe','cannot be released')]:
            with self.subTest(action=action),tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                for name,raw in self.files.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                manifest=copy.deepcopy(self.manifest)
                if action in ('source','page'):
                    path='data/items.json';payload=copy.deepcopy(self.data[path]);payload['item'][0]['source' if action=='source' else 'page']='XPHB' if action=='source' else 999
                    raw=encode(payload);(root/path).write_bytes(raw);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest()
                elif action in ('index','class-index'):
                    path='data/class/index.json' if action=='class-index' else 'data/bestiary/index.json'
                    raw=encode({});(root/path).write_bytes(raw);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest()
                elif action=='model':manifest['citation_model_sha256']='0'*64
                else:manifest['provisional_probe']=True
                (root/'manifest.json').write_bytes(encode(manifest))
                result=validate(root)
                self.assertFalse(result['passed']);self.assertTrue(any(expected_error in e for e in result['errors']),result['errors'])

    def test_typed_entity_references_must_resolve_in_retained_data(self):
        cases=[('refFeat','feat','Alert|SRD521',True),
               ('refOptionalfeature','optionalfeature','Agonizing Blast|SRD521',True),
               ('refFeat','feat','Blessed Warrior|SRD521',False),
               ('refOptionalfeature','optionalfeature','Call of the Void|WoW',False),
               ('refFeat','feat','Alert|XPHB',False),
               ('refOptionalfeature','optionalfeature','Agonizing Blast|WoW',False),
               ('refFeat','feat',None,False),
               ('refOptionalfeature','optionalfeature',[],False)]
        for node_type,key,packed,valid in cases:
            with self.subTest(node_type=node_type,packed=packed),tempfile.TemporaryDirectory() as folder:
                root=Path(folder)
                for name,raw in self.files.items():
                    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
                path='data/class/class-paladin.json';payload=copy.deepcopy(self.data[path])
                node={'type':node_type}
                if packed is not None:node[key]=packed
                payload['classFeature'][3]['entries'].append(node)
                raw=encode(payload);(root/path).write_bytes(raw)
                manifest=copy.deepcopy(self.manifest);manifest['sha256'][path]=hashlib.sha256(raw).hexdigest()
                (root/'manifest.json').write_bytes(encode(manifest))
                result=validate(root)
                self.assertEqual(result['passed'],valid,result['errors'])
                if not valid:self.assertTrue(any('Nested entity reference:' in error for error in result['errors']))


if __name__=='__main__':unittest.main()
