"""Magic-weapon overrides must retain printed properties and conditions."""
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
from verify_weapon_overrides import source_facts,compare,audit,SOURCE_HEADINGS,TARGET_FIELDS

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent weapon-override checks')
class WeaponOverrideSourceTest(unittest.TestCase):
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
        cls.a=review_items;cls.source=source_facts(SimpleNamespace(SOURCES=cls.a.SOURCES,doc=cls.a.doc))
        cls.result=audit(cls.a,cls.source)

    def record(self,name):return next(r for r in self.a.DATA['items.json']['item'] if r['name']==name)

    def test_all_six_remaining_fields_and_complete_source_override_inventory(self):
        self.assertTrue(self.result['passed'],self.result['errors'])
        self.assertEqual(self.source['source_header_count'],258)
        self.assertEqual(set(self.source['override_headings']),SOURCE_HEADINGS)
        self.assertEqual(len(self.result['records']),3)
        self.assertEqual(sum(len(r['verified_metadata']) for r in self.result['records']),6)
        self.assertEqual(self.source['targets']['Dwarven Thrower']['expected'],{'property':['T','V'],'range':'20/60'})
        self.assertEqual(self.source['targets']['Quarterstaff of the Acrobat']['expected'],{'property':['T','V'],'range':'30/120'})
        self.assertEqual(self.source['targets']['Sun Blade']['expected'],{'property':['F','V'],'dmgType':'R'})

    def test_missing_wrong_and_duplicate_properties_ranges_and_damage_are_rejected(self):
        cases=[('Dwarven Thrower','range','30/120'),('Quarterstaff of the Acrobat','range','20/60'),
               ('Sun Blade','dmgType','S'),('Sun Blade','property',['T|SRD521','V|SRD521']),
               ('Dwarven Thrower','property',['T|SRD521','T|SRD521']),('Sun Blade','property',['F|XPHB','V|SRD521']),
               ('Sun Blade','property',['F|SRD521']),('Dwarven Thrower','range',None)]
        for name,field,value in cases:
            with self.subTest(name=name,field=field,value=value):
                record=copy.deepcopy(self.record(name))
                if value is None:del record[field]
                else:record[field]=value
                result=compare(self.a.DATA,record,self.source['targets'][name])
                self.assertFalse(result['passed']);self.assertTrue(any(d['field']==field for d in result['differences']))

    def test_helper_names_meanings_and_implicit_alias_uniqueness_are_required(self):
        for action in ('meaning','duplicate','conflicting-alias'):
            with self.subTest(action=action):
                data=copy.deepcopy(self.a.DATA);record=copy.deepcopy(self.record('Sun Blade'))
                helpers=data['items-base.json']['itemProperty'];finesse=next(r for r in helpers if r['abbreviation']=='F')
                if action=='meaning':finesse['entries'][0]['name']='Light'
                elif action=='duplicate':helpers.append(copy.deepcopy(finesse))
                else:
                    conflict=copy.deepcopy(finesse);conflict['source']='PHB';helpers.append(conflict)
                    record['property']=['F','V|SRD521']
                self.assertFalse(compare(data,record,self.source['targets']['Sun Blade'])['passed'])

    def test_actual_form_and_blade_conditions_are_in_every_affected_fact(self):
        for name,phrase in [('Quarterstaff of the Acrobat','Quarterstaff Form Only'),('Sun Blade','While the blade exists')]:
            row=next(r for r in self.result['records'] if r['name']==name)
            for field,fact in row['verified_metadata'].items():
                with self.subTest(name=name,field=field):self.assertIn(phrase,fact['source_clause'])

    def test_conditional_throwing_arrows_and_per_hit_choice_are_not_fixed_facts(self):
        clauses=self.source['conditional_only']
        self.assertEqual(set(clauses),{'Energy Bow','Hammer of Thunderbolts','Javelin of Lightning'})
        self.assertIn('You can expend 1 charge',clauses['Hammer of Thunderbolts']['condition_clause'])
        self.assertIn('you can have it deal Lightning damage',clauses['Javelin of Lightning']['condition_clause'])
        self.assertIn('An arrow produced by this weapon',clauses['Energy Bow']['condition_clause'])
        self.assertEqual({r['name'] for r in self.result['records']},set(TARGET_FIELDS))

    def test_missing_duplicate_and_substituted_projections_are_rejected(self):
        for action in ('missing','duplicate','substitution','misindexed'):
            with self.subTest(action=action):
                rows=copy.deepcopy(self.a.RESULT)
                dwarf=next(r for r in rows if r['name']=='Dwarven Thrower')
                if action in {'missing','substitution'}:rows.remove(dwarf)
                if action=='duplicate':rows.append(copy.deepcopy(dwarf))
                if action=='substitution':rows.append(copy.deepcopy(next(r for r in rows if r['name']=='Sun Blade')))
                if action=='misindexed':dwarf['index']=next(r['index'] for r in rows if r['name']=='Sun Blade')
                self.assertFalse(audit(SimpleNamespace(DATA=self.a.DATA,RESULT=rows),self.source)['passed'])


if __name__=='__main__':unittest.main()
