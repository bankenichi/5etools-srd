import contextlib
import copy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from build_srd import Builder
from rule_table_grid import PDF_SHA256
from verify_item_schema_categories import source_inventory,source_facts,audit,require_proof
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent category/schema checks')
class ItemSchemaCategoryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        cls.root=Path(cls.folder.name);cls.data=cls.root/'candidate'
        for name,raw in Builder(ROOT).output().items():
            path=cls.data/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        cls.models=json.loads((ROOT/'source/item-families.json').read_text(encoding='utf8'))['families']
        sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
        try:
            sys.argv=['review_items.py','--pdf',str(PDF),'--data',str(cls.data),'--out',str(cls.root/'extraction')]
            with contextlib.redirect_stdout(io.StringIO()):import review_items
        finally:sys.argv=previous
        cls.addClassCleanup(lambda:sys.modules.pop('review_items',None));cls.addClassCleanup(review_items.doc.close)
        cls.a=review_items;cls.inventory=source_inventory(cls.a,cls.models)
        cls.expected=source_facts(cls.a,cls.inventory);cls.result=audit(cls.a,cls.expected)
        cls.proof=copy.deepcopy(cls.result)
        cls.proof.update(pdf_sha256=PDF_SHA256,scope='Source-bound categories and authored compatibility indexes.',
                         models_sha256=hashlib.sha256((ROOT/'source/item-families.json').read_bytes()).hexdigest(),
                         input_sha256={fn:hashlib.sha256((cls.a.STAGED/fn).read_bytes()).hexdigest() for fn in cls.a.FILES})

    def row(self,name,proof=None):return next(r for r in (self.proof if proof is None else proof)['records'] if r['name']==name)
    def changed(self):return SimpleNamespace(DATA=copy.deepcopy(self.a.DATA),RESULT=copy.deepcopy(self.a.RESULT))
    def record(self,a,name):
        row=next(r for r in a.RESULT if r['name']==name)
        return a.DATA[row['file']][row['kind']][row['index']]

    def test_complete_source_inventory_and_import(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(len(self.result['records']),329)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),570)
        self.assertEqual(len(self.inventory['ordinary']),236)
        self.assertEqual(len(require_proof(self.proof,self.a,self.expected)),329)

    def test_actual_inline_lists_and_cross_column_dulcimer(self):
        lists=self.inventory['source_lists']
        self.assertEqual(len(lists['Gaming Set (Varies)']['entries']),4)
        instruments=lists['Musical Instrument (Varies)']
        self.assertEqual(len(instruments['entries']),10)
        self.assertIn('dulcimer',[r['name'] for r in instruments['entries']])
        self.assertEqual(instruments['layout_joins'][0]['printed'],'dul-\ncimer')
        self.assertNotIn('Gaming Set (Varies)',self.inventory['source_tables'])

    def test_category_rarity_horn_relation_and_helper_mutations_fail(self):
        for name,field,value in [('Acid','type','P|SRD521'),('Acid','rarity','common'),
                                  ('Arcane Focus','rarity',False),('Horn of Blasting','baseItem','horn|XPHB'),
                                  ('Hat of Many Spells','type','INS|SRD521'),('Vehicle (Air)','abbreviation','SHP')]:
            with self.subTest(name=name,field=field):
                changed=self.changed();self.record(changed,name)[field]=value
                self.assertFalse(audit(changed,self.expected)['passed'])

    def test_unbound_absent_rarity_missing_or_duplicate_projection_fail(self):
        changed=self.changed();self.record(changed,'Cloak of Elvenkind')['rarity']='none'
        self.assertFalse(audit(changed,self.expected)['passed'])
        for mode in ('missing','duplicate'):
            with self.subTest(mode=mode):
                changed=self.changed();row=next(r for r in changed.RESULT if r['name']=='Acid')
                if mode=='missing':changed.RESULT.remove(row)
                else:changed.RESULT.append(copy.deepcopy(row))
                self.assertFalse(audit(changed,self.expected)['passed'])

    def test_same_count_duplicate_property_cannot_replace_missing_meaning(self):
        changed=self.changed()
        changed.doc=self.a.doc;changed.SOURCES=self.a.SOURCES
        row=next(r for r in changed.RESULT if r['kind']=='itemProperty' and r['name']=='2H')
        donor=copy.deepcopy(self.record(changed,'H'));donor['name']='2H'
        changed.DATA[row['file']][row['kind']][row['index']]=donor
        with self.assertRaisesRegex(ValueError,'property helper meaning'):source_facts(changed,self.inventory)

    def test_import_rejects_missing_extra_duplicate_or_substituted_identities(self):
        for mode in ('missing','extra','duplicate','substituted'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof)
                if mode=='missing':proof['records'].pop()
                elif mode=='extra':proof['records'].append(dict(proof['records'][0],name='Invented item'))
                elif mode=='duplicate':proof['records'][-1]=copy.deepcopy(proof['records'][0])
                else:proof['records'][-1]['name']='Invented item'
                with self.assertRaisesRegex(ValueError,'identity coverage'):require_proof(proof,self.a,self.expected)

    def test_import_rejects_field_relocation_bad_values_and_source_scope(self):
        for mode in ('moved','value','expected','scope','passed','extra_fact_key'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof);acid=self.row('Acid',proof)
                if mode=='moved':self.row('Hat of Many Spells',proof)['verified_metadata']['rarity']=acid['verified_metadata'].pop('rarity')
                elif mode=='value':acid['verified_metadata']['rarity']['value']=None
                elif mode=='expected':acid['verified_metadata']['rarity']['source_expected']='common'
                elif mode=='scope':acid['source_evidence']={'invented':'source'}
                elif mode=='passed':acid['passed']=1
                else:acid['verified_metadata']['rarity']['invented']=True
                with self.assertRaises(ValueError):require_proof(proof,self.a,self.expected)

    def test_import_requires_every_input_current_model_and_strict_success(self):
        for mode in ('input','model','passed','errors'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof)
                if mode=='input':proof['input_sha256'].pop('decks.json')
                elif mode=='model':proof['models_sha256']='0'*64
                elif mode=='passed':proof['passed']=1
                else:proof['errors']=['Invented success']
                with self.assertRaises(ValueError):require_proof(proof,self.a,self.expected)

    def test_import_rechecks_unbound_absent_rarity_and_type_helper_meaning(self):
        for name,field,value in [('Cloak of Elvenkind','rarity','none'),('Adventuring Gear','name','Invented category')]:
            with self.subTest(name=name):
                changed=self.changed();changed.PDF=self.a.PDF;changed.STAGED=self.a.STAGED;changed.FILES=self.a.FILES
                self.record(changed,name)[field]=value
                with self.assertRaisesRegex(ValueError,'Current category/schema data differs'):require_proof(self.proof,changed,self.expected)

    def test_actual_cli_import_accepts_current_and_rejects_same_count_wrong_source_fact(self):
        proof_path=self.root/'proof.json'
        args=[sys.executable,'-X','utf8',str(ROOT/'tools/item_audit/review_details.py'),
              '--pdf',str(PDF),'--data',str(self.data),'--schema-category-proof',str(proof_path)]
        proof_path.write_text(json.dumps(self.proof,ensure_ascii=False),encoding='utf8')
        good=subprocess.run(args+['--out',str(self.root/'good-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertEqual(good.returncode,0,good.stdout[-1500:])
        review=json.loads((self.root/'good-import/review.json').read_text(encoding='utf8'))
        self.assertIn('rarity',next(r for r in review['records'] if r['name']=='Acid')['verified_metadata'])
        bad=copy.deepcopy(self.proof);self.row('Acid',bad)['verified_metadata']['rarity']['source_expected']='rare'
        proof_path.write_text(json.dumps(bad,ensure_ascii=False),encoding='utf8')
        result=subprocess.run(args+['--out',str(self.root/'bad-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertNotEqual(result.returncode,0,result.stdout[-1500:])
        self.assertIn('Inconsistent category/schema proof fact',result.stdout)


if __name__=='__main__':unittest.main()
