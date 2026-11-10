"""Item environment metadata preserves units, source identity and conditions."""
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
from verify_item_environment import source_inventory,audit,compare,light_fact,movement_fact
PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent environment checks')
class ItemEnvironmentSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.folder=tempfile.TemporaryDirectory();cls.addClassCleanup(cls.folder.cleanup)
        root=Path(cls.folder.name);data=root/'candidate'
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

    def test_complete_current_projection_has_seventy_five_verified_fields(self):
        self.assertTrue(self.result['passed'],self.result['errors']);self.assertEqual(len(self.result['records']),61)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),75)
        self.assertEqual(len(self.inventory['poisons']),14);self.assertEqual(len(self.inventory['animals']),8)
        self.assertEqual(len(self.inventory['vehicles']),7)

    def test_dim_outer_extent_is_not_the_additional_annulus(self):
        for name,wrong in [('Sun Blade',[{'bright':15,'dim':15}]),('Lamp',[{'bright':15,'dim':30}]),
                           ('Bullseye Lantern',[{'bright':60,'dim':120}]),
                           ('Hooded Lantern',[{'bright':30,'dim':60}])]:
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));record['light']=wrong
                self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertEqual(self.expected('Bullseye Lantern')['light'][0]['shape'],'cone')

    def test_light_modes_keep_full_conditional_and_form_context(self):
        for name,clauses in [('Frost Brand',['In freezing temperatures']),('Energy Bow',['Until it disappears, the arrow emits']),
                             ('Rod of Alertness',['As a Magic action','after 10 minutes']),
                             ('Helm of Brilliance',['at least one fire opal','until you drop or stow the weapon']),
                             ('Sun Blade',['expand or reduce','to a maximum of 30 feet each or a minimum of 10 feet each'])]:
            text=self.row(name)['source_evidence']['source_text']
            for clause in clauses:
                with self.subTest(name=name,clause=clause):self.assertIn(clause,text)
        self.assertEqual(self.row('Apparatus of the Crab')['source_evidence']['source_lever_row'][2],'The light turns off.')

    def test_poison_source_header_types_and_true_flag_are_not_interchangeable(self):
        for name,field,value in [("Assassin's Blood",'poisonTypes',['injury']),('Crawler Mucus','poisonTypes',['contact','contact']),
                                  ('Basic Poison','poison',1),('Torpor','poison',False)]:
            with self.subTest(name=name,field=field):
                record=copy.deepcopy(self.record(name));record[field]=value
                self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertEqual(self.expected('Burnt Othur Fumes')['poisonTypes'],['inhaled'])
        self.assertEqual(self.expected('Purple Worm Poison')['poisonTypes'],['injury'])

    def test_mount_and_vehicle_values_are_identity_bound_and_keep_their_units(self):
        for name,field,value in [('Camel','speed',40),('Riding Horse','speed',40),('Airship','vehSpeed',4),
                                  ('Rowboat','vehSpeed',1),('Warship','vehSpeed',2)]:
            with self.subTest(name=name):
                record=copy.deepcopy(self.record(name));record[field]=value
                self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertEqual(self.row('Rowboat')['source_evidence']['source_cells'][1],'1½ mph')
        self.assertEqual(self.expected('Rowboat')['vehSpeed'],1.5)
        self.assertEqual(self.row('Camel')['source_evidence']['printed_speed_line']['text'],'Speed 50 ft.')

    def test_source_plane_and_movement_modes_cannot_be_selected_by_candidate_value(self):
        name='Ring of Elemental Command (Air)';record=copy.deepcopy(self.record(name))
        record['modifySpeed']={'static':{'swim':60}}
        self.assertFalse(compare(record,self.expected(name))['passed'])
        self.assertNotIn('Water. You know Aquan',self.row(name)['source_evidence']['source_text'])
        record=copy.deepcopy(self.record('Winged Boots'));record['modifySpeed']={'equal':{'fly':'walk'}}
        self.assertFalse(compare(record,self.expected('Winged Boots'))['passed'])

    def test_speed_floor_duration_and_activation_conditions_are_retained(self):
        for name,clauses in [('Boots of Striding and Springing',['unless your Speed is higher']),
                             ('Winged Boots',['expend 1 charge','for 1 hour','descend at a rate of 30 feet per round']),
                             ('Potion of Flying',['for 1 hour','can hover','when the potion wears off']),
                             ('Slippers of Spider Climbing',['slippery surface'])]:
            text=self.row(name)['source_evidence']['source_text']
            for clause in clauses:
                with self.subTest(name=name,clause=clause):self.assertIn(clause,text)

    def test_missing_duplicate_or_unexpected_projection_fails(self):
        for change in ('missing','duplicate','unexpected'):
            with self.subTest(change=change):
                data=copy.deepcopy(self.a.DATA);rows=copy.deepcopy(self.a.RESULT)
                selected=next(r for r in rows if r['name']=='Lamp')
                if change=='missing':rows.remove(selected)
                if change=='duplicate':rows.append(copy.deepcopy(selected))
                if change=='unexpected':next(r for r in data['items.json']['item'] if r['name']=='Amulet of Health')['light']=[{'bright':10,'dim':20}]
                changed=SimpleNamespace(DATA=data,RESULT=rows,doc=self.a.doc,SOURCES=self.a.SOURCES)
                self.assertFalse(audit(changed,self.models,self.inventory)['passed'])


if __name__=='__main__':unittest.main()
