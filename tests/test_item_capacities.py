"""Capacity metadata must preserve exact units, compartments and valid UIDs."""
import contextlib
import copy
import hashlib
import io
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
from verify_item_capacities import audit,compare,facts,LIQUID
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent capacity checks')
class ItemCapacitySourceTest(unittest.TestCase):
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
        cls.a=review_items;cls.result=audit(cls.a)

    def row(self,name):return next(r for r in self.result['records'] if r['name']==name)
    def expected(self,name):return facts(name,self.row(name)['source_evidence']['source_text'])[0]
    def record(self,name):return next(r for r in self.a.DATA['items.json']['item'] if r['name']==name)
    def refs(self,name):return {r:1 for r in self.row(name)['resolved_item_references']}

    def test_nineteen_source_scopes_thirteen_exact_indexes_six_guarded_absences(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),19)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),13)
        self.assertEqual(sum(r['verified_absence'] for r in self.result['records']),6)
        self.assertEqual(sum(len(r['resolved_item_references']) for r in self.result['records']),11)

    def test_rounded_fluid_and_assumed_ounce_mass_values_are_rejected(self):
        for name in LIQUID:
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));record['containerCapacity']={'weight':[0.25]} if name=='Vial' else {'volume':[0.1]}
                self.assertFalse(compare(record,None,{})['passed'])
                record['containerCapacity']=None;self.assertFalse(compare(record,None,{})['passed'])

    def test_unprinted_pouch_ammunition_and_extra_capacity_fields_fail(self):
        record=copy.deepcopy(self.record('Pouch'));record['containerCapacity']['item']=[{'needle|srd521':50}]
        self.assertFalse(compare(record,self.expected('Pouch'),{'needle|srd521':1})['passed'])
        record=copy.deepcopy(self.record('Backpack'));record['containerCapacity']['volume']=[999]
        self.assertFalse(compare(record,self.expected('Backpack'),{})['passed'])

    def test_changed_compartment_order_limits_and_weightless_semantics_fail(self):
        record=copy.deepcopy(self.record('Handy Haversack'));expected=self.expected('Handy Haversack')
        for change in ({'weight':[500,200,200],'weightless':True},{'weight':[200,200,500],'weightless':False},
                       {'weight':[200,200,True],'weightless':True}):
            with self.subTest(change=change):
                record['containerCapacity']=change;self.assertFalse(compare(record,expected,{})['passed'])
        source=self.row('Handy Haversack')['source_evidence']
        self.assertEqual(source['fixed_container_weight_lb'],5);self.assertEqual(source['additional_printed_volume_cuft'],[25,25,64])

    def test_foreign_unresolved_duplicate_item_uids_and_wrong_quantities_fail(self):
        name='Efficient Quiver';expected=self.expected(name);refs=self.refs(name)
        for change in ('foreign','unresolved','duplicate_identity','wrong_quantity'):
            with self.subTest(change=change):
                record=copy.deepcopy(self.record(name));identities=copy.deepcopy(refs)
                item=record['containerCapacity']['item'][0]
                if change=='foreign':item['bolt|xphb']=item.pop('bolt|srd521')
                if change=='unresolved':identities.pop('bolt|srd521')
                if change=='duplicate_identity':identities['bolt|srd521']=2
                if change=='wrong_quantity':item['bolt|srd521']=59
                self.assertFalse(compare(record,expected,identities)['passed'])

    def test_alternatives_and_full_weight_volume_context_are_retained(self):
        for name in ('Efficient Quiver','Map or Scroll Case'):
            self.assertTrue(self.row(name)['source_evidence']['alternatives_not_additive'])
        self.assertEqual(self.row('Bag of Holding')['source_evidence']['additional_printed_volume_cuft'],64)
        self.assertEqual(self.row('Efficient Quiver')['source_evidence']['maximum_container_weight_lb'],2)
        self.assertNotIn('fixed_container_weight_lb',self.row('Efficient Quiver')['source_evidence'])
        self.assertIn('or up to 4 cubic feet of dry goods',self.row('Barrel')['source_evidence']['source_text'])

    def test_missing_duplicate_and_unreviewed_capacity_projection_fail(self):
        for change in ('missing','duplicate','unexpected'):
            with self.subTest(change=change):
                data=copy.deepcopy(self.a.DATA);rows=copy.deepcopy(self.a.RESULT)
                selected=next(r for r in rows if r['name']=='Barrel')
                if change=='missing':rows.remove(selected)
                if change=='duplicate':rows.append(copy.deepcopy(selected))
                if change=='unexpected':next(r for r in data['items.json']['item'] if r['name']=='Torch')['containerCapacity']={'weight':[30]}
                self.assertFalse(audit(SimpleNamespace(DATA=data,RESULT=rows,doc=self.a.doc,SOURCES=self.a.SOURCES))['passed'])


if __name__=='__main__':unittest.main()
