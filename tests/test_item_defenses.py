"""Defense metadata must match exact source type, subtype and conditions."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder
from rule_table_grid import PDF_SHA256
from verify_item_defenses import source_inventory,audit,compare

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent defense checks')
class ItemDefenseSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
        for name,raw in Builder(ROOT).output().items():
            path=data/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        cls.models=json.loads((ROOT/'source/item-families.json').read_text(encoding='utf8'))['families']
        sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
        try:
            sys.argv=['review_items.py','--pdf',str(PDF),'--data',str(data),'--out',str(root/'extraction')]
            with contextlib.redirect_stdout(io.StringIO()):import review_items
        finally:sys.argv=previous
        cls.addClassCleanup(lambda:sys.modules.pop('review_items',None));cls.addClassCleanup(review_items.doc.close)
        cls.a=review_items;cls.inventory=source_inventory(cls.a,cls.models);cls.result=audit(cls.a,cls.models,cls.inventory)

    def row(self,name):return next(r for r in self.result['records'] if r['name']==name)
    def record(self,name):
        row=self.row(name);return self.a.DATA[row['file']][row['kind']][next(r['index'] for r in self.a.RESULT if r['name']==name)]
    def expected(self,name):return {key:fact['source_expected'] for key,fact in self.row(name)['verified_metadata'].items()}

    def test_complete_existing_defense_projection_and_damage_type_inventory(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(len(self.result['records']),56)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),58)
        self.assertEqual(len(set(self.inventory['damage_types'])),13)
        self.assertEqual(self.expected('Periapt of Proof against Poison'),{'immune':['poison']})

    def test_legacy_resistance_is_not_immunity_or_flat_damage_reduction(self):
        for name,value in [('Ring of Elemental Command (Fire)','fire'),('Ring of Warmth','cold')]:
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));self.assertNotIn('resist',record)
                record['resist']=[value]
                self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertEqual(self.expected('Ring of Warmth'),{})
        self.assertEqual(self.expected('Ring of Elemental Command (Fire)'),{'immune':['fire']})

    def test_candidate_value_cannot_select_another_table_or_plane_answer(self):
        for name,key,value in [('Armor of Acid Resistance','resist',['fire']),('Black Dragon Scale Mail','resist',['fire']),
                               ('Ring of Elemental Command (Air)','resist',['acid']),
                               ('Ring of Elemental Command (Fire)','immune',['lightning']),
                               ('Armor of Vulnerability (Bludgeoning)','vulnerable',['bludgeoning','slashing'])]:
            with self.subTest(name=name,key=key):
                record=copy.deepcopy(self.record(name));target=record.get('inherits',record);target[key]=value
                self.assertFalse(compare(record,self.expected(name))['passed'])

    def test_all_damage_means_the_full_printed_thirteen_types_without_duplicates(self):
        expected=self.expected('Potion of Invulnerability');self.assertEqual(len(expected['resist']),13)
        for value in [expected['resist'][:-1],expected['resist']+['fire'],expected['resist']+['unknown']]:
            record=copy.deepcopy(self.record('Potion of Invulnerability'));record['resist']=value
            self.assertFalse(compare(record,expected)['passed'])

    def test_source_evidence_retains_gemstone_duration_holding_and_curse_conditions(self):
        for name,clauses in [('Helm of Brilliance',['while wearing the helm','As long as the helm has at least one ruby']),
                             ('Potion of Invulnerability',['For 1 minute after you drink']),
                             ('Potion of Fire Resistance',['When you drink this potion','for 1 hour']),
                             ('Armor of Vulnerability (Slashing)',['While cursed','removing the armor fails to end the curse']),
                             ('Staff of Fire',['while you hold this staff'])]:
            text=self.row(name)['source_evidence']['source_text']
            for clause in clauses:
                with self.subTest(name=name,clause=clause):self.assertIn(clause,text)

    def test_missing_duplicate_or_substituted_projection_fails(self):
        for action in ('missing','duplicate','substitution'):
            with self.subTest(action=action):
                rows=copy.deepcopy(self.a.RESULT);chosen=next(r for r in rows if r['name']=='Ring of Warmth')
                if action!='duplicate':rows.remove(chosen)
                if action=='duplicate':rows.append(copy.deepcopy(chosen))
                if action=='substitution':rows.append(copy.deepcopy(next(r for r in rows if r['name']=='Staff of Fire')))
                self.assertFalse(audit(SimpleNamespace(DATA=self.a.DATA,RESULT=rows,doc=self.a.doc,SOURCES=self.a.SOURCES),self.models,self.inventory)['passed'])

    def test_unexpected_plane_defense_cannot_hide_outside_the_fixed_inventory(self):
        data=copy.deepcopy(self.a.DATA)
        next(r for r in data['items.json']['item'] if r['name']=='Ring of Elemental Command (Water)')['resist']=['cold']
        result=audit(SimpleNamespace(DATA=data,RESULT=self.a.RESULT,doc=self.a.doc,SOURCES=self.a.SOURCES),self.models,self.inventory)
        self.assertFalse(result['passed'])
        self.assertTrue(any(e.get('name')=='Ring of Elemental Command (Water)' for e in result['errors']))


if __name__=='__main__':unittest.main()
