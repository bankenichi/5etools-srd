"""Independent header facts and adversarial source-model inventory checks."""
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
from verify_item_families import prove_models
from verify_magic_item_headers import audit,audit_record
import verify_item_resources as resources

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF to run official-source item header checks')
class MagicItemHeaderSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
        for name,raw in Builder(ROOT).output().items():
            p=data/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
        try:
            sys.argv=['review_items.py','--pdf',str(PDF),'--data',str(data),'--out',str(root/'extraction')]
            with contextlib.redirect_stdout(io.StringIO()):import review_items
        finally:sys.argv=previous
        cls.a=review_items
        cls.models=json.loads((ROOT/'source/item-families.json').read_text(encoding='utf8'))['families']
        cls.result=audit(cls.a,cls.models)

    def check_changed(self,name,key,value,kind='item',file='items.json'):
        source=next(r for r in self.result['records'] if r['file']==file and r['kind']==kind and r['name']==name)
        record=copy.deepcopy(next(r for r in self.a.DATA[file][kind] if r['name']==name))
        target=record.get('inherits',{}) if key in record.get('inherits',{}) else record
        target[key]=value
        return audit_record(self.a,record,kind,source['source_heading'],self.result['source_headers'][source['source_heading']],self.models)

    def test_all_printed_magic_entries_and_header_projections(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(self.result['source_magic_entries'],258)
        self.assertEqual(self.result['covered_magic_entries'],258)
        self.assertEqual(len(self.result['records']),390)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),1087)

    def test_wrong_fixed_or_variable_rarity_rejected(self):
        for name in ('Amulet of Health','Belt of Fire Giant Strength','Ioun Stone, Strength','Potion of Supreme Healing','Spell Scroll (Level 9)'):
            with self.subTest(name=name):self.assertFalse(self.check_changed(name,'rarity','common')['passed'])
        self.assertFalse(self.check_changed('Belt of Giant Strength','rarity','rare',kind='itemGroup')['passed'])
        self.assertFalse(self.check_changed('+2 Armor','rarity','rare',kind='magicvariant',file='magicvariants.json')['passed'])

    def test_wrong_category_staff_and_wondrous_flags_rejected(self):
        self.assertFalse(self.check_changed('Potion of Supreme Healing','type','RG|SRD521')['passed'])
        self.assertFalse(self.check_changed('Staff of Power','staff',False)['passed'])
        self.assertFalse(self.check_changed('Amulet of Health','wondrous',False)['passed'])

    def test_category_helper_must_mean_the_printed_type(self):
        changed=SimpleNamespace(**vars(self.a));changed.DATA=copy.deepcopy(self.a.DATA)
        helper=next(q for q in changed.DATA['items-base.json']['itemType'] if q['abbreviation']=='P')
        helper['name']='Scroll'
        record=next(q for q in changed.DATA['items.json']['item'] if q['name']=='Potion of Supreme Healing')
        source=next(r for r in self.result['records'] if r['name']==record['name'])
        result=audit_record(changed,record,'item',source['source_heading'],self.result['source_headers'][source['source_heading']],self.models)
        self.assertFalse(result['passed'])

    def test_missing_wrong_and_lowercase_attunement_rejected(self):
        self.assertFalse(self.check_changed('Wand of Fireballs','reqAttune',None)['passed'])
        self.assertFalse(self.check_changed('Wand of Fireballs','reqAttune','by a spellcaster')['passed'])
        self.assertFalse(self.check_changed('Staff of the Woodlands','reqAttune','by a Wizard')['passed'])
        self.assertFalse(self.check_changed('Potion of Supreme Healing','reqAttune',True)['passed'])

    def test_missing_duplicate_or_forged_family_source_rows_rejected(self):
        for action in ('missing','duplicate','forged'):
            models=copy.deepcopy(self.models);rows=models['Belt of Giant Strength']['tables'][0]['rows']
            if action=='missing':rows.pop()
            elif action=='duplicate':rows.append(copy.deepcopy(rows[0]))
            else:rows[0][-1]='Common'
            with self.subTest(action=action):
                _,errors=prove_models(self.a,models)
                self.assertTrue(errors)

    def resource_change(self,name,key,value,remove=False,kind='item',file='items.json'):
        record=copy.deepcopy(next(r for r in self.a.DATA[file][kind] if r['name']==name))
        heading=self.a.source_name(record,kind)
        text,_=resources.source_scope(self.a,record,kind,heading,self.models)
        target=record.get('inherits',{}) if key in record.get('inherits',{}) else record
        if remove:target.pop(key,None)
        else:target[key]=value
        return resources.compare(record,kind,heading,text)

    def test_charge_pools_and_source_restoration(self):
        result=resources.audit(self.a,self.models)
        self.assertTrue(result['passed'],result['errors'])
        self.assertEqual(len(result['records']),59)
        self.assertEqual(sum(len(r['verified_metadata']) for r in result['records']),155)
        robe=next(r for r in result['records'] if r['name']=='Robe of Stars')
        self.assertEqual(robe['source_facts'],{'charges':6,'recharge':'dusk','rechargeAmount':'1d6'})

    def test_wrong_missing_or_conditional_charge_fields_rejected(self):
        self.assertFalse(self.resource_change('Staff of Power','charges',None,remove=True)['passed'])
        self.assertFalse(self.resource_change('Wand of Fireballs','charges',70)['passed'])
        self.assertFalse(self.resource_change('Staff of the Magi','rechargeAmount','1d12 + 1')['passed'])
        self.assertFalse(self.resource_change('Robe of Stars','recharge','dawn')['passed'])
        # Daily use restrictions do not restore a finite charge pool.
        self.assertFalse(self.resource_change('Luck Blade','recharge','dawn',kind='magicvariant',file='magicvariants.json')['passed'])
        # A charge pool in one subtype must not leak into another subtype.
        self.assertFalse(self.resource_change('Figurine of Wondrous Power, Silver Raven','charges',24)['passed'])


if __name__=='__main__':unittest.main()
