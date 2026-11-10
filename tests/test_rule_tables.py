"""Source-integrity checks; set SRD521_PDF to the official pinned PDF."""
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
from verify_rule_tables import compare,inventory_errors

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF to run independent official-source table checks')
class RuleTableSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fitz
        from locate_rule_tables import locate
        from rule_table_grid import Source,PDF_SHA256
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.tables=json.loads(Builder(ROOT).output()['data/generated/gendata-tables.json'])['table']
        cls.sources={};cls.locators={}
        with fitz.open(PDF) as pdf:
            locators,errors=locate(pdf,cls.tables);assert not errors,errors
            source=Source(pdf)
            for locator in locators:
                cls.locators[locator['name']]=locator
                cls.sources[locator['name']]=source.table(locator)

    def verify(self,table):
        try:
            result,_=compare(table,self.sources[table['name']],self.locators[table['name']])
        except (ValueError,AssertionError,KeyError,IndexError,TypeError):return False
        return result['source_content_verified']

    def test_all_source_tables_and_rows(self):
        self.assertEqual(inventory_errors(self.tables),[])
        self.assertEqual(len(self.tables),59)
        self.assertEqual(sum(len(s['rows']) for s in self.sources.values()),629)
        self.assertTrue(all(self.verify(t) for t in self.tables))

    def test_missing_duplicate_and_extra_tables_rejected(self):
        self.assertTrue(inventory_errors(self.tables[:-1]))
        self.assertTrue(inventory_errors(self.tables+[self.tables[0]]))
        extra=copy.deepcopy(self.tables[0]);extra.update(name='Invented',caption='Invented')
        self.assertTrue(inventory_errors(self.tables+[extra]))
        self.assertTrue(inventory_errors([]))

    def test_changed_number_swapped_cells_and_rows_rejected(self):
        original=next(t for t in self.tables if t['caption']=='Ability Modifiers')
        table=copy.deepcopy(original);table['rows'][0][1]='999'
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(original);table['rows'][0].reverse()
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(original);table['rows'][0],table['rows'][1]=table['rows'][1],table['rows'][0]
        self.assertFalse(self.verify(table))

    def test_missing_duplicate_rows_rejected(self):
        table=copy.deepcopy(self.tables[0]);table['rows'].pop()
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(self.tables[0]);table['rows'].append(copy.deepcopy(table['rows'][0]))
        self.assertFalse(self.verify(table))

    def test_false_citation_and_selection_marker_rejected(self):
        for key,value in [('source','XDMG'),('page',999),('srd52',False)]:
            table=copy.deepcopy(self.tables[0]);table[key]=value
            with self.subTest(field=key):self.assertFalse(self.verify(table))

    def test_header_note_and_typography_changes_rejected(self):
        table=copy.deepcopy(next(t for t in self.tables if 'colLabels' in t));table['colLabels'][0]+=' extra'
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(next(t for t in self.tables if t.get('footnotes')));table['footnotes'][0]+=' extra'
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(next(t for t in self.tables if any(isinstance(c,str) and '’' in c for r in t['rows'] if isinstance(r,list) for c in r)))
        table['rows']=[[c.replace('’',"'") if isinstance(c,str) else c for c in r] if isinstance(r,list) else r for r in table['rows']]
        self.assertFalse(self.verify(table))

    def test_wrong_roll_range_and_unreviewed_metadata_rejected(self):
        table=copy.deepcopy(next(t for t in self.tables if any(isinstance(c,dict) and 'roll' in c for r in t['rows'] if isinstance(r,list) for c in r)))
        cell=next(c for r in table['rows'] for c in r if isinstance(c,dict) and 'roll' in c)
        cell['roll'][next(k for k in cell['roll'] if k!='pad')]+=1
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(self.tables[0]);table['invented']='Unprinted text'
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(next(t for t in self.tables if any(isinstance(c,dict) for r in t['rows'] if isinstance(r,list) for c in r)))
        cell=next(c for r in table['rows'] for c in r if isinstance(c,dict));cell['invented']='Unprinted text'
        self.assertFalse(self.verify(table))
        table=copy.deepcopy(next(t for t in self.tables if 'colLabelRows' in t))
        cell=next(c for r in table['colLabelRows'] for c in r if isinstance(c,dict));cell['invented']='Unprinted text'
        self.assertFalse(self.verify(table))


if __name__=='__main__':unittest.main()
