"""Source receipts must not silently accept invented or stale provenance."""
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
from projection_provenance import check_family,check_equipment,family_tables,require_identity_coverage,require_imported_fact
from verify_item_families import prove_models,parts
PDF=Path(os.environ.get('SRD521_PDF',''))


class ProjectionProofImportTest(unittest.TestCase):
    def setUp(self):
        self.ids={('items.json','item','Actual item')}
        self.structural={('items.json','itemGroup','Actual group')}
        self.proof={'records':[{'file':'items.json','kind':'item','name':'Actual item','literal_projection_verified':True},
                               {'file':'items.json','kind':'itemGroup','name':'Actual group','literal_projection_verified':False,'structural_delegation_verified':True}]}

    def test_complete_literal_and_structural_identity_sets_pass(self):
        self.assertEqual(len(require_identity_coverage(self.proof,self.ids,self.structural)),2)

    def test_same_counts_cannot_hide_substituted_missing_duplicate_or_wrong_flags(self):
        for change in ('fake_literal','fake_structural','duplicate','missing','false_literal','truthy_literal','ambiguous_flags'):
            with self.subTest(change=change):
                proof=copy.deepcopy(self.proof)
                if change=='fake_literal':proof['records'][0]['name']='NONEXISTENT'
                elif change=='fake_structural':proof['records'][1]['name']='NONEXISTENT'
                elif change=='duplicate':proof['records'][1]=copy.deepcopy(proof['records'][0])
                elif change=='missing':proof['records'].pop()
                elif change=='false_literal':proof['records'][0]['literal_projection_verified']=False
                elif change=='truthy_literal':proof['records'][0]['literal_projection_verified']=1
                else:proof['records'][0]['structural_delegation_verified']=True
                with self.assertRaises(ValueError):require_identity_coverage(proof,self.ids,self.structural)

    def test_proof_cannot_publish_a_different_source_expectation(self):
        record={'_srd521':{'version':'5.2.1','paragraph_indexes':[0]}}
        fact={'value':copy.deepcopy(record['_srd521']),'source_expected':copy.deepcopy(record['_srd521']),'interpretation':'Authored provenance.'}
        require_imported_fact(record,'_srd521',fact)
        for change in ('wrong_version','wrong_value','extra_fact_key','boolean_alias'):
            with self.subTest(change=change):
                mutated=copy.deepcopy(fact)
                if change=='wrong_version':mutated['source_expected']['version']='5.1'
                elif change=='wrong_value':mutated['value']['version']='5.1'
                elif change=='extra_fact_key':mutated['unexpected']=True
                else:
                    mutated['value']['paragraph_indexes']=[False];mutated['source_expected']['paragraph_indexes']=[False]
                with self.assertRaises(ValueError):require_imported_fact(record,'_srd521',mutated)


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent provenance checks')
class ProjectionProvenanceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
        for name,raw in Builder(ROOT).output().items():
            path=data/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(raw)
        cls.models=json.loads((ROOT/'source/item-families.json').read_text(encoding='utf8'))['families']
        cls.equipment=json.loads((ROOT/'source/item-equipment.json').read_text(encoding='utf8'))['records']
        sys.path.insert(0,str(ROOT/'tools/item_audit'));previous=sys.argv
        try:
            sys.argv=['review_items.py','--pdf',str(PDF),'--data',str(data),'--out',str(root/'extraction')]
            with contextlib.redirect_stdout(io.StringIO()):import review_items
        finally:sys.argv=previous
        cls.addClassCleanup(lambda:sys.modules.pop('review_items',None));cls.addClassCleanup(review_items.doc.close)
        cls.a=review_items;_,errors=prove_models(cls.a,cls.models);assert not errors,errors
        cls.family=[(kind,r) for payload in cls.a.DATA.values() for kind,rows in payload.items() if isinstance(rows,list)
                    for r in rows if isinstance(r,dict) and '_srd521' in r]

    def model(self,record,kind):return self.models[self.a.source_name(record,kind)]
    def record(self,name):return next((kind,r) for kind,r in self.family if r['name']==name)

    def test_all_receipts_and_identity_selected_body_tables_match(self):
        self.assertEqual(len(self.family),150);self.assertEqual(len(self.equipment),27)
        for kind,record in self.family:
            with self.subTest(name=record['name'],kind=kind):
                model=self.model(record,kind);check_family(self.a,record,kind,model)
                effective={**record,**record.get('inherits',{})}
                entries=effective.get('entriesTemplate',[]) if kind=='itemEntry' else effective.get('entries',[])
                self.assertEqual(parts(entries)[1],family_tables(record,kind,model))
        for model in self.equipment:
            record=next(r for r in self.a.DATA[model['file']][model['kind']] if r['name']==model['name'])
            check_equipment(record,model)

    def test_version_pdf_heading_header_pages_and_note_mutations_fail(self):
        kind,original=self.record('Belt of Cloud Giant Strength');model=self.model(original,kind)
        for key,value in [('version','5.1'),('official_pdf_sha256','0'*64),('heading','Potion of Giant Strength'),
                          ('printed_header','Wondrous Item, Common'),('pages',[1]),('projection','Invented receipt')]:
            with self.subTest(key=key):
                changed=copy.deepcopy(original);changed['_srd521'][key]=value
                with self.assertRaises(ValueError):check_family(self.a,changed,kind,model)

    def test_missing_extra_and_boolean_paragraph_indexes_fail(self):
        kind,original=self.record('Belt of Cloud Giant Strength');model=self.model(original,kind)
        for change in ('missing','extra','boolean_index','duplicate_index'):
            with self.subTest(change=change):
                changed=copy.deepcopy(original)
                if change=='missing':del changed['_srd521']['version']
                elif change=='extra':changed['_srd521']['invented_rule']='Never printed'
                elif change=='boolean_index':changed['_srd521']['paragraph_indexes']=[False]
                else:changed['_srd521']['paragraph_indexes']=[0,0]
                with self.assertRaises(ValueError):check_family(self.a,changed,kind,model)

    def test_giant_variant_cannot_borrow_another_valid_printed_row(self):
        for name,other in [('Belt of Cloud Giant Strength','Belt of Hill Giant Strength'),
                           ('Potion of Fire Giant Strength','Potion of Frost Giant Strength')]:
            with self.subTest(name=name):
                kind,record=self.record(name);other_kind,donor=self.record(other)
                changed=copy.deepcopy(record);changed['_srd521']['printed_tables']=copy.deepcopy(donor['_srd521']['printed_tables'])
                with self.assertRaises(ValueError):check_family(self.a,changed,kind,self.model(record,kind))
                wanted=family_tables(changed,kind,self.model(record,kind))
                self.assertEqual(wanted,record['_srd521']['printed_tables'])

    def test_concrete_projection_does_not_accept_full_family_tables_or_missing_rows(self):
        kind,record=self.record('Belt of Cloud Giant Strength');model=self.model(record,kind)
        for tables in (model['tables'],[],[dict(record['_srd521']['printed_tables'][0],rows=[])]):
            with self.subTest(tables=tables):
                changed=copy.deepcopy(record);changed['_srd521']['printed_tables']=copy.deepcopy(tables)
                with self.assertRaises(ValueError):check_family(self.a,changed,kind,model)

    def test_equipment_unit_list_hash_pdf_and_unknown_field_mutations_fail(self):
        model=next(r for r in self.equipment if r['name']=='Vehicle (Air)')
        original=next(r for r in self.a.DATA[model['file']][model['kind']] if r['name']==model['name'])
        for key,value in [('source_units',['Speed']),('source_units',list(reversed(original['_srd521Equipment']['source_units']))),
                          ('projection_sha256','0'*64),('official_pdf_sha256','0'*64),('unknown',True)]:
            with self.subTest(key=key,value=value):
                changed=copy.deepcopy(original);changed['_srd521Equipment'][key]=value
                with self.assertRaises(ValueError):check_equipment(changed,model)

    def test_fresh_source_page_inventory_cannot_be_changed_with_receipt(self):
        kind,record=self.record('Belt of Cloud Giant Strength');model=copy.deepcopy(self.model(record,kind))
        model['pages']=[1];changed=copy.deepcopy(record);changed['_srd521']['pages']=[1]
        with self.assertRaisesRegex(ValueError,'physical source'):check_family(self.a,changed,kind,model)


if __name__=='__main__':unittest.main()
