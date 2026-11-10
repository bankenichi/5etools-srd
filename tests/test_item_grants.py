import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder
from rule_table_grid import PDF_SHA256
from verify_item_grants import source_inventory,audit,compare
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent grant checks')
class ItemGrantSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
        cls.data_root=data;cls.test_root=root
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
        row=self.row(name);return next(r for r in self.a.DATA[row['file']][row['kind']] if r['name']==name)
    def expected(self,name):return {key:fact['source_expected'] for key,fact in self.row(name)['verified_metadata'].items()}

    def test_complete_thirty_four_records_and_thirty_seven_fields(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),34)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),37)

    def test_druidic_focus_keeps_both_printed_classes(self):
        self.assertEqual(self.expected('Druidic Focus')['focus'],['Druid','Ranger'])
        record=copy.deepcopy(self.record('Druidic Focus'));record['focus']=['Druid']
        self.assertFalse(compare(record,self.expected('Druidic Focus'))['passed'])
        self.assertIn('A Druid or Ranger can use',self.row('Druidic Focus')['source_evidence']['source_text'])

    def test_candidate_category_or_class_cannot_choose_a_different_source(self):
        for name,key,value in [('Crystal','scfType','holy'),('Emblem','scfType','arcane'),
                               ('Hat of Many Spells','focus',['Sorcerer']),('Holy Symbol','focus',['Druid','Ranger'])]:
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));record[key]=value
                self.assertFalse(compare(record,self.expected(name))['passed'])

    def test_scroll_levels_cannot_substitute_other_rows_or_boolean_zero(self):
        for name,value in [('Spell Scroll (Cantrip)',False),('Spell Scroll (Level 9)',8),('Spell Scroll (Level 1)','1')]:
            record=copy.deepcopy(self.record(name));record['spellScrollLevel']=value
            self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertTrue(self.inventory['cantrip_zero_source'])
        self.assertEqual(self.row('Spell Scroll (Level 9)')['source_evidence']['source_table_row'][0],'9')

    def test_language_wearing_specific_armor_training_and_hat_components_remain_in_scope(self):
        for name,clauses in [('Belt of Dwarvenkind',['While wearing this belt','You know Dwarvish']),
                             ('Ring of Elemental Command (Fire)',['While wearing the ring','Fire. You know Ignan']),
                             ('Demon Armor',['While wearing this armor','you know Abyssal']),
                             ('Elven Chain',['trained with this armor','even if you lack training']),
                             ('Hat of Many Spells',['While holding the hat','special Somatic component'])]:
            text=self.row(name)['source_evidence']['source_text']
            for clause in clauses:
                with self.subTest(name=name,clause=clause):self.assertIn(clause,text)

    def test_boolean_flags_are_typed_and_not_unconditional_general_grants(self):
        for name,field in [('Belt of Dwarvenkind','grantsLanguage'),('Bracers of Archery','grantsProficiency')]:
            record=copy.deepcopy(self.record(name));record[field]=1
            self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertIn('this particular armor',self.row('Elven Chain')['source_evidence']['legacy_schema_interpretation'])
        self.assertIn('Throne.',self.row('Mysterious Deck')['source_evidence']['indexed_effect'])

    def test_missing_duplicate_and_unexpected_grant_projections_fail(self):
        for change in ('missing','duplicate','unexpected'):
            with self.subTest(change=change):
                data=copy.deepcopy(self.a.DATA);rows=copy.deepcopy(self.a.RESULT)
                selected=next(r for r in rows if r['name']=='Hat of Many Spells')
                if change=='missing':rows.remove(selected)
                if change=='duplicate':rows.append(copy.deepcopy(selected))
                if change=='unexpected':next(r for r in data['items.json']['item'] if r['name']=='Torch')['focus']=['Wizard']
                self.assertFalse(audit(SimpleNamespace(DATA=data,RESULT=rows,doc=self.a.doc,SOURCES=self.a.SOURCES),self.models,self.inventory)['passed'])

    def test_importer_rejects_field_moved_to_null_on_another_real_identity(self):
        proof=copy.deepcopy(self.result)
        proof.update(pdf_sha256=PDF_SHA256,
                     models_sha256=hashlib.sha256((ROOT/'source/item-families.json').read_bytes()).hexdigest(),
                     input_sha256={fn:hashlib.sha256((self.a.STAGED/fn).read_bytes()).hexdigest() for fn in self.a.FILES},
                     scope='Fresh source proof with an intentional field-relocation corruption for rejection testing.')
        druid=next(r for r in proof['records'] if r['name']=='Druidic Focus')
        crystal=next(r for r in proof['records'] if r['name']=='Crystal')
        moved=druid['verified_metadata'].pop('focus');moved.update(value=None,source_expected=None)
        crystal['verified_metadata']['focus']=moved
        path=self.test_root/'corrupted-grants-proof.json';path.write_text(json.dumps(proof,ensure_ascii=False),encoding='utf8')
        result=subprocess.run([sys.executable,'-X','utf8',str(ROOT/'tools/item_audit/review_details.py'),
                               '--pdf',str(PDF),'--data',str(self.data_root),'--out',str(self.test_root/'bad-import'),
                               '--grants-proof',str(path)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertNotEqual(result.returncode,0,result.stdout[-1200:])
        self.assertIn('Grant proof per-record field coverage differs',result.stdout)


if __name__=='__main__':unittest.main()
