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
from verify_item_predicates import source_expectations,audit,require_proof,evaluate
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent predicate checks')
class ItemPredicateSourceTest(unittest.TestCase):
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
        cls.a=review_items;cls.expected=source_expectations(cls.a,cls.models);cls.result=audit(cls.a,cls.expected)
        cls.proof=copy.deepcopy(cls.result)
        cls.proof.update(pdf_sha256=PDF_SHA256,scope='Printed generic restrictions and authored compatibility indexes.',
                         models_sha256=hashlib.sha256((ROOT/'source/item-families.json').read_bytes()).hexdigest(),
                         input_sha256={fn:hashlib.sha256((cls.a.STAGED/fn).read_bytes()).hexdigest() for fn in cls.a.FILES})

    def changed(self):
        a=SimpleNamespace(**vars(self.a));a.DATA=copy.deepcopy(self.a.DATA);a.RESULT=copy.deepcopy(self.a.RESULT);return a
    def row(self,name,proof=None):return next(r for r in (self.proof if proof is None else proof)['records'] if r['name']==name)
    def record(self,a,name):
        row=next(r for r in a.RESULT if r['name']==name)
        return a.DATA[row['file']][row['kind']][row['index']]

    def test_complete_source_projection_inventory_and_saved_proof_import(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),92)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),108)
        proof=json.loads(json.dumps(self.proof,ensure_ascii=False))
        self.assertEqual(len(require_proof(proof,self.a,self.expected)),92)

    def test_named_constraints_categories_and_hide_exclusion_cannot_broaden(self):
        for name,field,value in [('Energy Bow','requires',[{'name':'Longbow','source':'SRD521'}]),
                                 ('+1 Armor','requires',[{'type':'S|SRD521'}]),
                                 ('Dancing Sword','requires',[{'weapon':True}]),
                                 ('Adamantine Armor','excludes',{'name':'Plate Armor'}),
                                 ('Ammunition of Slaying','ammo',1)]:
            with self.subTest(name=name):
                a=self.changed();self.record(a,name)[field]=value
                self.assertFalse(audit(a,self.expected)['passed'])

    def test_printed_focus_aliases_preserve_existing_equivalent_predicates(self):
        row=self.row('Vicious Weapon');aliases=row['source_evidence']['canonical_physical_aliases']
        self.assertEqual({k:v['canonical'] for k,v in aliases.items()},{'Staff':'Quarterstaff','Wooden Staff':'Quarterstaff'})
        for info in aliases.values():self.assertIn('(also a Quarterstaff)',info['source_cells'][0])
        actual=evaluate(self.record(self.a,'Vicious Weapon'),self.a.DATA['items-base.json']['baseitem'])
        self.assertTrue({'Staff','Wooden Staff'}<=actual)
        normalized={aliases[n]['canonical'] if n in aliases else n for n in actual}
        self.assertEqual(normalized,set(row['source_evidence']['eligible']))
        self.assertEqual(self.row('+1 Weapon')['verified_metadata']['requires']['value'],[{'weapon':True}])
        self.assertEqual(row['verified_metadata']['requires']['value'],[{'weaponCategory':'simple'},{'weaponCategory':'martial'}])

    def test_family_flags_and_weapon_ammunition_relations_are_strictly_typed(self):
        for name,field,value in [('Club','sword',True),('Battleaxe','axe',1),('Musket','ammoType','sling bullet|SRD521'),
                                 ('Sling','ammoType','firearm bullet|SRD521'),('Longbow','ammoType','arrow|XPHB')]:
            with self.subTest(name=name,field=field):
                a=self.changed();self.record(a,name)[field]=value
                self.assertFalse(audit(a,self.expected)['passed'])

    def test_mithral_exception_preserves_full_conditional_source_clause(self):
        row=self.row('Mithral Armor');text=row['source_evidence']['conditional_exception']['source_text']
        self.assertIn('normally imposes Disadvantage on Dexterity (Stealth) checks or has a Strength requirement',text)
        for field,value in [('strength',False),('stealth',0)]:
            a=self.changed();self.record(a,'Mithral Armor')['inherits'][field]=value
            self.assertFalse(audit(a,self.expected)['passed'])

    def test_missing_duplicate_and_extra_predicate_projections_fail(self):
        for mode in ('missing','duplicate','extra'):
            with self.subTest(mode=mode):
                a=self.changed();row=next(r for r in a.RESULT if r['name']=='Energy Bow')
                if mode=='missing':a.RESULT.remove(row)
                elif mode=='duplicate':a.RESULT.append(copy.deepcopy(row))
                else:self.record(a,'Quarterstaff')['sword']=True
                self.assertFalse(audit(a,self.expected)['passed'])

    def test_same_count_fabricated_resistance_variant_cannot_replace_printed_choice(self):
        a=self.changed();row=next(r for r in a.RESULT if r['name']=='Armor of Acid Resistance')
        record=a.DATA[row['file']][row['kind']][row['index']];row['name']=record['name']='Armor of Invented Resistance'
        with self.assertRaisesRegex(ValueError,'Generic source projection inventory'):source_expectations(a,self.models)

    def test_proof_identity_field_value_and_source_corruptions_fail(self):
        for mode in ('missing','duplicate','substituted','field','expected','source','passed','current_data'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof);a=self.a
                if mode=='missing':proof['records'].pop()
                elif mode=='duplicate':proof['records'][-1]=copy.deepcopy(proof['records'][0])
                elif mode=='substituted':proof['records'][-1]['name']='Invented item'
                elif mode=='field':self.row('Energy Bow',proof)['verified_metadata'].pop('requires')
                elif mode=='expected':self.row('Energy Bow',proof)['verified_metadata']['requires']['source_expected']=[]
                elif mode=='source':self.row('Energy Bow',proof)['source_evidence']['eligible']=['Club']
                elif mode=='passed':self.row('Energy Bow',proof)['passed']=1
                else:a=self.changed();self.record(a,'Club')['sword']=True
                with self.assertRaises(ValueError):require_proof(proof,a,self.expected)

    def test_complete_current_input_model_and_boolean_success_bindings_required(self):
        for mode in ('input','model','passed','errors'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof)
                if mode=='input':proof['input_sha256'].pop('decks.json')
                elif mode=='model':proof['models_sha256']='0'*64
                elif mode=='passed':proof['passed']=1
                else:proof['errors']=['Unverified']
                with self.assertRaises(ValueError):require_proof(proof,self.a,self.expected)

    def test_actual_positive_and_corrupted_proof_cli(self):
        path=self.root/'proof.json';path.write_text(json.dumps(self.proof,ensure_ascii=False),encoding='utf8')
        args=[sys.executable,'-X','utf8',str(ROOT/'tools/item_audit/review_details.py'),
              '--pdf',str(PDF),'--data',str(self.data),'--predicate-proof',str(path)]
        good=subprocess.run(args+['--out',str(self.root/'good-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertEqual(good.returncode,0,good.stdout[-1500:])
        review=json.loads((self.root/'good-import/review.json').read_text(encoding='utf8'))
        self.assertIn('requires',next(r for r in review['records'] if r['name']=='Energy Bow')['verified_metadata'])
        proof=copy.deepcopy(self.proof);self.row('Energy Bow',proof)['verified_metadata']['requires']['source_expected']=[]
        path.write_text(json.dumps(proof,ensure_ascii=False),encoding='utf8')
        bad=subprocess.run(args+['--out',str(self.root/'bad-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertNotEqual(bad.returncode,0,bad.stdout[-1500:]);self.assertIn('Predicate proof identity, field or source scope differs',bad.stdout)


if __name__=='__main__':unittest.main()
