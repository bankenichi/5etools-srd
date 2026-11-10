"""Base-item bindings must follow printed subtypes and Quarterstaff rules."""
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
from verify_item_base_bindings import source_facts,check_record,audit,STAFF_RULE

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent base-binding checks')
class ItemBaseBindingSourceTest(unittest.TestCase):
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
        cls.addClassCleanup(lambda:sys.modules.pop('review_items',None))
        cls.addClassCleanup(review_items.doc.close)
        cls.a=review_items;cls.source=source_facts(cls.a);cls.result=audit(cls.a,cls.source)

    def test_all_declared_bindings_and_quarterstaff_defaults(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(self.result['counts'],{'fixed_concrete_base_binding':30,'staff_normal_quarterstaff_use':12,'focus_also_quarterstaff':2})
        self.assertEqual(len(self.result['records']),44)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),167)
        self.assertEqual(self.source['staff_rule'],STAFF_RULE)
        self.assertIn('nonmagical Quarterstaff',self.source['staff_rule'])
        self.assertEqual(self.source['fixed']['Sun Blade']['base_name'],'Longsword')

    def test_resolving_but_wrong_base_uid_or_category_is_rejected(self):
        for name,key,value in [('Sun Blade','baseItem','greatsword|SRD521'),('Sun Blade','baseItem','longsword|XPHB'),
                               ('Animated Shield','type','HA|SRD521'),('Dwarven Thrower','weaponCategory','simple')]:
            with self.subTest(name=name,key=key):
                row=next(r for r in self.result['records'] if r['name']==name)
                record=copy.deepcopy(next(r for r in self.a.DATA[row['file']][row['kind']] if r['name']==name));record[key]=value
                expected={k:v['source_expected'] for k,v in row['verified_metadata'].items()}
                _,errors=check_record(self.a.DATA,record,expected)
                self.assertTrue(any(e['field']==key for e in errors),errors)

    def test_staff_damage_property_and_mastery_must_match_printed_base(self):
        for key,value in [('dmg1','1d8'),('dmg2','1d10'),('dmgType','S'),('property',['T|SRD521']),
                          ('mastery',['Vex|SRD521']),('weaponCategory','martial'),('type','R|SRD521')]:
            with self.subTest(key=key):
                record=copy.deepcopy(next(r for r in self.a.DATA['items.json']['item'] if r['name']=='Staff of Power'))
                record[key]=value
                _,errors=check_record(self.a.DATA,record,self.source['defaults'])
                self.assertTrue(any(e['field']==key for e in errors),errors)

    def test_helper_identity_and_meaning_are_checked(self):
        original=next(r for r in self.a.DATA['items.json']['item'] if r['name']=='Staff of Fire')
        for action in ('property-meaning','duplicate-property','conflicting-default-property','mastery-source','type-meaning'):
            with self.subTest(action=action):
                record=copy.deepcopy(original)
                data=copy.deepcopy(self.a.DATA);base=data['items-base.json']
                versatile=next(r for r in base['itemProperty'] if r['abbreviation']=='V')
                if action=='property-meaning':versatile['entries'][0]['name']='Light'
                elif action=='duplicate-property':base['itemProperty'].append(copy.deepcopy(versatile))
                elif action=='conflicting-default-property':
                    conflicting=copy.deepcopy(versatile);conflicting['source']='PHB';conflicting['entries'][0]['name']='Light'
                    base['itemProperty'].append(conflicting)
                    record['property']=['V']
                elif action=='mastery-source':next(r for r in base['itemMastery'] if r['name']=='Topple')['source']='XPHB'
                else:next(r for r in base['itemType'] if r['abbreviation']=='M')['name']='Ranged Weapon'
                _,errors=check_record(data,record,self.source['defaults'])
                self.assertTrue(errors)

    def test_missing_and_duplicate_binding_projections_are_rejected(self):
        for name,action in [('Staff of Fire','missing'),('Black Dragon Scale Mail','missing'),('Staff of Fire','duplicate')]:
            with self.subTest(name=name,action=action):
                records=copy.deepcopy(self.a.RESULT)
                if action=='missing':records=[r for r in records if r['name']!=name]
                else:records.append(copy.deepcopy(next(r for r in records if r['name']==name)))
                result=audit(SimpleNamespace(DATA=self.a.DATA,RESULT=records),self.source)
                self.assertFalse(result['passed'],result['errors'])

    def test_missing_projection_cannot_be_hidden_by_duplicate_substitution(self):
        for missing,duplicate in [('Staff of Fire','Staff of Frost'),('Black Dragon Scale Mail','Blue Dragon Scale Mail'),('Staff','Wooden Staff')]:
            with self.subTest(missing=missing):
                records=[copy.deepcopy(r) for r in self.a.RESULT if r['name']!=missing]
                records.append(copy.deepcopy(next(r for r in records if r['name']==duplicate)))
                result=audit(SimpleNamespace(DATA=self.a.DATA,RESULT=records),self.source)
                self.assertFalse(result['passed'])
                self.assertTrue(any('Duplicate binding projection' in e.get('error','') for e in result['errors']))

    def test_extra_bonuses_horns_and_generic_shields_are_not_certified(self):
        names={r['name'] for r in self.result['records']}
        self.assertNotIn('Horn of Blasting',names)
        self.assertFalse(any(r['kind']=='magicvariant' for r in self.result['records']))
        power=next(r for r in self.result['records'] if r['name']=='Staff of Power')
        self.assertNotIn('bonusWeapon',power['verified_metadata'])
        self.assertNotIn('bonusAc',power['verified_metadata'])
        self.assertIn('Special forms',power['source_evidence']['scope'])


if __name__=='__main__':unittest.main()
