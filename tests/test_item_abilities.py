"""Ability index facts must retain their source identity, limits and conditions."""
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
from verify_item_abilities import source_inventory,audit,compare,exact
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent ability checks')
class ItemAbilitySourceTest(unittest.TestCase):
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
        row=self.row(name)
        return next(r for r in self.a.DATA[row['file']][row['kind']] if r['name']==name)
    def expected(self,name):return self.row(name)['verified_metadata']['ability']['source_expected']

    def test_all_thirty_existing_ability_fields_proved_from_source(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),30)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),30)

    def test_numeric_changes_and_boolean_aliases_fail(self):
        def alter(value):
            if type(value) is int:return value+1
            if isinstance(value,dict):
                key=next(k for k,v in value.items() if not isinstance(v,list));return {**value,key:alter(value[key])}
            raise AssertionError(value)
        for row in self.result['records']:
            with self.subTest(name=row['name']):
                expected=self.expected(row['name']);record=copy.deepcopy(self.record(row['name']))
                record.get('inherits',record)['ability']=alter(expected)
                self.assertFalse(compare(record,expected)['passed'])
        self.assertFalse(exact({'count':True},{'count':1}))

    def test_candidate_score_cannot_choose_a_different_giant_row(self):
        for name in ('Belt of Fire Giant Strength','Potion of Cloud Giant Strength'):
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));record['ability']={'static':{'str':21}}
                self.assertFalse(compare(record,self.expected(name))['passed'])

    def test_complete_conditions_and_caps_are_attached_to_indexed_effects(self):
        for name,clauses in [('Potion of Hill Giant Strength',['for 1 hour','has no effect']),
                             ('Belt of Dwarvenkind',['While wearing this belt','to a maximum of 20']),
                             ('Ioun Stone, Agility',['while this deep-red sphere orbits your head','to a maximum of 20']),
                             ('Manual of Bodily Health',['48 hours','6 days or fewer','to a maximum of 30']),
                             ('Hammer of Thunderbolts',['also attuned','bestowed by your Belt','to a maximum of 30']),
                             ('Mysterious Deck',['Star. Increase one of your ability scores by 2, to a maximum of 24.'])]:
            text=self.row(name)['source_evidence']['source_text']
            for clause in clauses:
                with self.subTest(name=name,clause=clause):self.assertIn(clause,text)

    def test_missing_duplicate_or_wrong_kind_projection_fails(self):
        for action in ('missing','duplicate','wrong_kind'):
            with self.subTest(action=action):
                rows=copy.deepcopy(self.a.RESULT);chosen=next(r for r in rows if r['name']=='Amulet of Health')
                if action=='missing':rows.remove(chosen)
                if action=='duplicate':rows.append(copy.deepcopy(chosen))
                if action=='wrong_kind':chosen['file']='decks.json';chosen['kind']='deck';chosen['index']=0
                changed=SimpleNamespace(DATA=self.a.DATA,RESULT=rows,doc=self.a.doc,SOURCES=self.a.SOURCES)
                self.assertFalse(audit(changed,self.models,self.inventory)['passed'])

    def test_unreviewed_added_ability_field_cannot_hide(self):
        data=copy.deepcopy(self.a.DATA);next(r for r in data['items.json']['item'] if r['name']=='Torch')['ability']={'str':2}
        changed=SimpleNamespace(DATA=data,RESULT=self.a.RESULT,doc=self.a.doc,SOURCES=self.a.SOURCES)
        self.assertFalse(audit(changed,self.models,self.inventory)['passed'])


if __name__=='__main__':unittest.main()
