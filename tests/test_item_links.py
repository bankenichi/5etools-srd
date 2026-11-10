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
from verify_item_links import source_expectations,audit,require_proof,members
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent item link checks')
class ItemLinkSourceTest(unittest.TestCase):
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
        cls.proof.update(pdf_sha256=PDF_SHA256,scope='Source links, quantities and explicitly authored compatibility metadata.',
                         models_sha256=hashlib.sha256((ROOT/'source/item-families.json').read_bytes()).hexdigest(),
                         input_sha256={fn:hashlib.sha256((cls.a.STAGED/fn).read_bytes()).hexdigest() for fn in cls.a.FILES})

    def changed(self):
        a=SimpleNamespace(**vars(self.a));a.DATA=copy.deepcopy(self.a.DATA);a.RESULT=copy.deepcopy(self.a.RESULT);return a
    def row(self,name,proof=None,kind=None):return next(r for r in (self.proof if proof is None else proof)['records'] if r['name']==name and (kind is None or r['kind']==kind))
    def record(self,a,name,kind=None):
        row=next(r for r in a.RESULT if r['name']==name and (kind is None or r['kind']==kind))
        return a.DATA[row['file']][row['kind']][row['index']]

    def test_complete_194_fields_and_saved_source_proof_import(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),188)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),194)
        self.assertEqual(len(require_proof(json.loads(json.dumps(self.proof,ensure_ascii=False)),self.a,self.expected)),188)

    def test_group_membership_keeps_existing_case_order_and_rejects_duplicates_foreign_uids(self):
        druid=self.row('Druidic Focus')['verified_metadata']['items']
        self.assertNotEqual(druid['value'],druid['source_expected'])
        self.assertEqual(members(druid['value'],'items'),members(druid['source_expected'],'items'))
        for mode in ('missing','duplicate','foreign','extra'):
            with self.subTest(mode=mode):
                a=self.changed();values=self.record(a,'Arcane Focus')['items']
                if mode=='missing':values.pop()
                elif mode=='duplicate':values[-1]=values[0]
                elif mode=='foreign':values[-1]='Wand|XPHB'
                else:values.append('Quarterstaff|SRD521')
                self.assertFalse(audit(a,self.expected)['passed'])

    def test_pack_units_quantities_and_bundle_quantities_cannot_be_swapped(self):
        for name,member,value in [("Burglar's Pack",6,{'item':'oil|SRD521','quantity':8}),
                                  ("Entertainer's Pack",4,{'item':'costume|SRD521','quantity':True}),
                                  ('Arrows (20)',0,{'item':'bolt|SRD521','quantity':20}),
                                  ('Iron Spikes',0,{'item':'iron spike|SRD521','quantity':9})]:
            with self.subTest(name=name):
                a=self.changed();self.record(a,name)['packContents'][member]=value
                self.assertFalse(audit(a,self.expected)['passed'])
        costume=self.row("Entertainer's Pack")['verified_metadata']['packContents']['source_expected'][4]
        self.assertEqual(costume,{'item':'costume|SRD521','quantity':3})

    def test_card_parents_are_disambiguated_by_source_projection_not_candidate_set(self):
        knights=[r for r in self.proof['records'] if r['kind']=='card' and r['name']=='Knight']
        self.assertEqual(len(knights),2)
        self.assertEqual({r['verified_metadata']['set']['source_expected'] for r in knights},{'Deck of Illusions','Mysterious Deck'})
        for row in knights:
            a=self.changed();card=a.DATA[row['file']][row['kind']][row['index']]
            card['set']='Mysterious Deck' if card['set']=='Deck of Illusions' else 'Deck of Illusions'
            self.assertFalse(audit(a,self.expected)['passed'])

    def test_card_replacement_exception_and_complete_outcomes_are_preserved(self):
        values=self.row('Mysterious Deck',kind='deck')['verified_metadata']['cards']['source_expected']
        self.assertEqual([v for v in values if isinstance(v,str)],['Fool|Mysterious Deck|SRD521','Jester|Mysterious Deck|SRD521'])
        self.assertEqual(len(self.row('Deck of Illusions',kind='deck')['verified_metadata']['cards']['source_expected']),33)
        for mode in ('missing','duplicate','wrong_replacement'):
            a=self.changed();cards=self.record(a,'Mysterious Deck','deck')['cards']
            if mode=='missing':cards.pop()
            elif mode=='duplicate':cards[-1]=copy.deepcopy(cards[0])
            else:cards[cards.index('Fool|Mysterious Deck|SRD521')]={'uid':'Fool|Mysterious Deck|SRD521','replacement':True}
            self.assertFalse(audit(a,self.expected)['passed'])

    def test_details_curses_templates_affixes_and_weight_qualifier_are_bound(self):
        for name,field,value in [('Ring of Fire Resistance','detail1','pearl'),('Black Dragon Scale Mail','detail1','red'),
                                  ('Shield of Missile Attraction','curse',1),('Waterskin','weightNote','(empty)'),
                                  ('A','template','{{item.damage}}')]:
            with self.subTest(name=name):
                a=self.changed();self.record(a,name)[field]=value
                self.assertFalse(audit(a,self.expected)['passed'])
        a=self.changed();self.record(a,'Frost Brand')['inherits']['namePrefix']='Frozen '
        self.assertFalse(audit(a,self.expected)['passed'])

    def test_missing_duplicate_or_invented_current_metadata_projections_fail(self):
        for mode in ('missing','duplicate','invented'):
            a=self.changed();row=next(r for r in a.RESULT if r['name']=='Waterskin')
            if mode=='missing':a.RESULT.remove(row)
            elif mode=='duplicate':a.RESULT.append(copy.deepcopy(row))
            else:self.record(a,'Acid')['curse']=True
            self.assertFalse(audit(a,self.expected)['passed'])

    def test_proof_identity_fields_source_and_typed_success_cannot_be_forged(self):
        for mode in ('missing','duplicate','index_type','field','expected','scope','passed'):
            with self.subTest(mode=mode):
                proof=copy.deepcopy(self.proof);row=self.row('Waterskin',proof)
                if mode=='missing':proof['records'].pop()
                elif mode=='duplicate':proof['records'][-1]=copy.deepcopy(proof['records'][0])
                elif mode=='index_type':row['index']=True
                elif mode=='field':row['verified_metadata'].pop('weightNote')
                elif mode=='expected':row['verified_metadata']['weightNote']['source_expected']='(empty)'
                elif mode=='scope':row['source_evidence']={}
                else:row['passed']=1
                with self.assertRaises(ValueError):require_proof(proof,self.a,self.expected)

    def test_complete_current_inputs_model_and_fresh_data_required(self):
        for mode in ('input','model','passed','current_data'):
            proof=copy.deepcopy(self.proof);a=self.a
            if mode=='input':proof['input_sha256'].pop('decks.json')
            elif mode=='model':proof['models_sha256']='0'*64
            elif mode=='passed':proof['passed']=1
            else:a=self.changed();self.record(a,'Waterskin')['weightNote']='(empty)'
            with self.assertRaises(ValueError):require_proof(proof,a,self.expected)

    def test_pack_targets_must_exist_with_the_actual_correct_source(self):
        for mode in ('missing','wrong_source'):
            with self.subTest(mode=mode):
                a=self.changed();row=next(r for r in a.RESULT if r['name']=='Backpack')
                if mode=='wrong_source':a.DATA[row['file']][row['kind']][row['index']]['source']='WRONG_SOURCE'
                else:
                    a.DATA[row['file']][row['kind']].pop(row['index']);a.RESULT.remove(row)
                    for later in a.RESULT:
                        if later['file']==row['file'] and later['kind']==row['kind'] and later['index']>row['index']:later['index']-=1
                self.assertFalse(audit(a,self.expected)['passed'])
                with self.assertRaises(ValueError):source_expectations(a,self.models)
                with self.assertRaises(ValueError):require_proof(self.proof,a,self.expected)

    def test_pack_target_cannot_be_replaced_with_an_item_group(self):
        a=self.changed();row=next(r for r in a.RESULT if r['name']=='Backpack');old_index=row['index']
        record=a.DATA[row['file']][row['kind']].pop(old_index)
        for later in a.RESULT:
            if later is not row and later['file']==row['file'] and later['kind']==row['kind'] and later['index']>old_index:later['index']-=1
        row['kind']='itemGroup';row['index']=len(a.DATA[row['file']]['itemGroup']);a.DATA[row['file']]['itemGroup'].append(record)
        self.assertFalse(audit(a,self.expected)['passed'])
        with self.assertRaisesRegex(ValueError,'Unresolved retained item/link target'):source_expectations(a,self.models)

    def test_actual_cli_positive_and_corrupted_import(self):
        path=self.root/'proof.json';path.write_text(json.dumps(self.proof,ensure_ascii=False),encoding='utf8')
        args=[sys.executable,'-X','utf8',str(ROOT/'tools/item_audit/review_details.py'),
              '--pdf',str(PDF),'--data',str(self.data),'--links-proof',str(path)]
        good=subprocess.run(args+['--out',str(self.root/'good-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertEqual(good.returncode,0,good.stdout[-1500:])
        review=json.loads((self.root/'good-import/review.json').read_text(encoding='utf8'))
        self.assertIn('weightNote',next(r for r in review['records'] if r['name']=='Waterskin')['verified_metadata'])
        proof=copy.deepcopy(self.proof);self.row('Waterskin',proof)['verified_metadata']['weightNote']['source_expected']='(empty)'
        path.write_text(json.dumps(proof,ensure_ascii=False),encoding='utf8')
        bad=subprocess.run(args+['--out',str(self.root/'bad-import')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
        self.assertNotEqual(bad.returncode,0,bad.stdout[-1500:]);self.assertIn('Item-link proof identity, field or source scope differs',bad.stdout)


if __name__=='__main__':unittest.main()
