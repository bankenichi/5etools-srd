"""Ordinary item categories require their actual complete printed table scope."""
import copy
import hashlib
import json
import os
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder
from rule_table_grid import PDF_SHA256
from verify_equipment_categories import source_categories,audit_payload

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent equipment-category checks')
class EquipmentCategorySourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fitz
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        with fitz.open(PDF) as pdf:cls.categories=source_categories(pdf)
        cls.payload=json.loads(Builder(ROOT).output()['data/items-base.json'])

    def test_every_printed_weapon_armor_and_shield_row_is_verified(self):
        result=audit_payload(self.payload,self.categories)
        self.assertTrue(result['passed'],result['errors'])
        self.assertEqual(len(result['records']),51)
        self.assertEqual(sum(len(r['verified_metadata']) for r in result['records']),139)
        self.assertEqual(self.categories['Quarterstaff']['source_category'],'Simple Melee Weapons')
        self.assertEqual(self.categories['Pistol']['source_category'],'Martial Ranged Weapons')
        self.assertEqual(self.categories['Plate Armor']['facts'],{'type':'HA','armor':True})

    def test_wrong_row_category_and_flag_types_are_rejected(self):
        for name,key,value in [('Quarterstaff','weaponCategory','martial'),('Pistol','type','M|SRD521'),
                               ('Plate Armor','type','LA|SRD521'),('Longsword','weapon',1),('Shield','armor',True),
                               ('Quarterstaff','armor',True),('Quarterstaff','armor',0),
                               ('Plate Armor','weapon',True),('Shield','weapon',True),
                               ('Plate Armor','weaponCategory','martial'),('Shield','weaponCategory','simple')]:
            with self.subTest(name=name,key=key):
                payload=copy.deepcopy(self.payload)
                next(r for r in payload['baseitem'] if r['name']==name)[key]=value
                result=audit_payload(payload,self.categories)
                self.assertFalse(result['passed']);self.assertTrue(any(e['name']==name for e in result['errors']))

    def test_explicit_false_flags_do_not_assert_an_incompatible_category(self):
        payload=copy.deepcopy(self.payload)
        for name,key in [('Quarterstaff','armor'),('Plate Armor','weapon'),('Shield','weapon'),('Shield','armor')]:
            next(r for r in payload['baseitem'] if r['name']==name)[key]=False
        result=audit_payload(payload,self.categories)
        self.assertTrue(result['passed'],result['errors'])
        self.assertEqual(sum(len(r['verified_metadata']) for r in result['records']),139)

    def test_missing_duplicate_and_extra_base_weapon_rows_are_rejected(self):
        for action in ('missing','duplicate','extra'):
            with self.subTest(action=action):
                payload=copy.deepcopy(self.payload)
                if action=='missing':payload['baseitem']=[r for r in payload['baseitem'] if r['name']!='Pistol']
                elif action=='duplicate':payload['baseitem'].append(copy.deepcopy(next(r for r in payload['baseitem'] if r['name']=='Shield')))
                else:
                    extra=copy.deepcopy(next(r for r in payload['baseitem'] if r['name']=='Quarterstaff'))
                    extra['name']='Unprinted Weapon';payload['baseitem'].append(extra)
                self.assertFalse(audit_payload(payload,self.categories)['passed'])

    def test_typed_helper_must_have_the_source_category_meaning(self):
        for action in ('meaning','source','missing','duplicate'):
            with self.subTest(action=action):
                payload=copy.deepcopy(self.payload)
                helper=next(h for h in payload['itemType'] if h['abbreviation']=='M')
                if action=='meaning':helper['name']='Ranged Weapon'
                elif action=='source':helper['source']='XPHB'
                elif action=='missing':payload['itemType'].remove(helper)
                else:payload['itemType'].append(copy.deepcopy(helper))
                self.assertFalse(audit_payload(payload,self.categories)['passed'])


if __name__=='__main__':unittest.main()
