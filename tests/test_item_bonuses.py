"""Printed baseline, conditional and configurable item bonuses stay distinct."""
import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder
from rule_table_grid import PDF_SHA256
from verify_item_resources import source_scope
from verify_item_bonuses import audit,compare,extract_facts

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent item-bonus checks')
class ItemBonusSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
        for name,raw in Builder(ROOT).output().items():
            path=data/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
        try:
            sys.argv=['review_items.py','--pdf',str(PDF),'--data',str(data),'--out',str(root/'extraction')]
            with contextlib.redirect_stdout(io.StringIO()):import review_items
        finally:sys.argv=previous
        cls.addClassCleanup(lambda:sys.modules.pop('review_items',None));cls.addClassCleanup(review_items.doc.close)
        cls.a=review_items;cls.models=json.loads((ROOT/'source/item-families.json').read_text(encoding='utf8'))['families']
        cls.result=audit(cls.a,cls.models)

    def source(self,name):
        review=next(r for r in self.a.RESULT if r['name']==name and r['kind'] in {'item','magicvariant','itemGroup'})
        record=self.a.DATA[review['file']][review['kind']][review['index']]
        text,_=source_scope(self.a,record,review['kind'],review['source_name'],self.models)
        header=review.get('official_metadata','')
        return record,review['kind'],text,header

    def test_all_retained_bonus_scalars_match_source(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(len(self.result['records']),68)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),81)

    def test_configurable_transfer_and_example_never_become_fixed_ac(self):
        record,kind,text,header=self.source('Defender')
        self.assertNotIn('bonusAc',record['inherits'])
        self.assertNotIn('{=bonusAc}',json.dumps(record['inherits']['entries']))
        example='For example, you could reduce the bonus to your attack rolls and damage rolls to +1 and gain a +2 bonus to Armor Class.'
        self.assertIn(example,self.a.flatten(record['inherits']['entries'],record['inherits']))
        self.assertIn(example,text)
        values,_,dynamic=extract_facts(text,header,record['name'],kind)
        self.assertEqual(values['bonusWeapon'],{'+3'});self.assertNotIn('bonusAc',values)
        self.assertIn('bonusAc',dynamic)
        for number in ('+1','+2','+3'):
            with self.subTest(number=number):
                changed=copy.deepcopy(record);changed['inherits']['bonusAc']=number
                result=compare(changed,kind,text,header)
                self.assertFalse(result['passed']);self.assertEqual(result['differences'][0]['field'],'bonusAc')

    def test_other_ioun_stone_rules_do_not_leak_into_selected_subtype(self):
        for name,expected,excluded in [('Ioun Stone, Mastery','bonusProficiencyBonus','bonusAc'),('Ioun Stone, Protection','bonusAc','bonusProficiencyBonus')]:
            record,kind,text,header=self.source(name);values,_,_=extract_facts(text,header,name,kind)
            self.assertEqual(values[expected],{'+1'});self.assertNotIn(excluded,values)
        record,kind,text,header=self.source('Ioun Stone, Mastery')
        _,clauses,_=extract_facts(text,header,record['name'],kind)
        self.assertIn('while this pale green prism orbits your head.',' '.join(clauses['bonusProficiencyBonus']))

    def test_advantage_on_saves_is_not_a_numeric_save_bonus(self):
        record,kind,text,header=self.source('Black Dragon Scale Mail');values,_,_=extract_facts(text,header,record['name'],kind)
        self.assertEqual(values['bonusAc'],{'+1'});self.assertNotIn('bonusSavingThrow',values)

    def test_combined_targets_and_archmagi_pair_are_complete(self):
        for name,fields in [('Staff of Power',{'bonusAc','bonusSavingThrow','bonusSpellAttack','bonusWeapon'}),
                            ('Robe of the Archmagi',{'bonusSpellSaveDc','bonusSpellAttack'})]:
            record,kind,text,header=self.source(name);values,_,_=extract_facts(text,header,name,kind)
            self.assertTrue(fields<=values.keys())
            for field in fields:self.assertEqual(values[field],{'+2'})
        record,kind,text,header=self.source('Robe of the Archmagi');_,clauses,_=extract_facts(text,header,record['name'],kind)
        for field in ('bonusSpellAttack','bonusSpellSaveDc'):
            self.assertIn('You gain these benefits while wearing the robe.',' '.join(clauses[field]))

    def test_damage_only_and_conditional_increase_are_not_universal_attack_bonus(self):
        record,kind,text,header=self.source('Bracers of Archery');values,_,_=extract_facts(text,header,record['name'],kind)
        self.assertEqual(values['bonusWeaponDamage'],{'+2'});self.assertNotIn('bonusWeapon',values)
        record,kind,text,header=self.source('Mace of Smiting');values,_,_=extract_facts(text,header,record['name'],kind)
        self.assertEqual(values['bonusWeapon'],{'+1'})
        changed=copy.deepcopy(record);changed['bonusWeapon']='+3';self.assertFalse(compare(changed,kind,text,header)['passed'])
        record,kind,text,header=self.source('Oil of Sharpness');_,clauses,_=extract_facts(text,header,record['name'],kind)
        context=' '.join(clauses['bonusWeapon'])
        self.assertIn('nonmagical and deal Slashing or Piercing damage',context)
        self.assertIn('Applying the oil takes 1 minute',context)

    def test_wrong_or_malformed_retained_bonus_fails(self):
        record,kind,text,header=self.source('Robe of Stars')
        for value in ('+2',1,True,[]):
            with self.subTest(value=value):
                changed=copy.deepcopy(record);changed['bonusSavingThrow']=value
                self.assertFalse(compare(changed,kind,text,header)['passed'])

    def test_absent_optional_query_field_is_not_invented(self):
        record,kind,text,header=self.source('Robe of Stars');changed=copy.deepcopy(record);del changed['bonusSavingThrow']
        result=compare(changed,kind,text,header)
        self.assertTrue(result['passed']);self.assertNotIn('bonusSavingThrow',result['verified_metadata'])
        self.assertEqual(result['optional_source_fields_not_encoded']['bonusSavingThrow'],['+1'])


if __name__=='__main__':unittest.main()
