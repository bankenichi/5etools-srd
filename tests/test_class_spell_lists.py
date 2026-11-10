"""Verify complete class spell-list data against fresh official source grids."""
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
from class_spell_lists import extract,verify
from rule_table_grid import PDF_SHA256

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF to run official-source class spell-list checks')
class ClassSpellListSourceTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fitz
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.actual=json.loads(Builder(ROOT).output()['data/generated/gendata-tables.json'])['tableGroup']
        with fitz.open(PDF) as pdf:cls.official,cls.evidence=extract(pdf)

    def test_all_eight_classes_and_seventy_tables_are_literal(self):
        self.assertEqual(verify(self.actual,self.official),[])
        self.assertEqual(sum(len(g['tables']) for g in self.actual),70)
        self.assertEqual(sum(len(t['rows']) for g in self.actual for t in g['tables']),875)
        self.assertEqual([sum(len(t['rows']) for t in g['tables']) for g in self.actual],[129,109,124,38,48,138,72,217])

    def test_missing_duplicate_reordered_class_groups_rejected(self):
        for groups in ([],self.actual[:-1],self.actual+[self.actual[0]],list(reversed(self.actual))):
            self.assertTrue(verify(groups,self.official))

    def test_missing_duplicate_reordered_tables_or_rows_rejected(self):
        for kind in ('missing_table','duplicate_table','swap_table','missing_row','duplicate_row','swap_row'):
            groups=copy.deepcopy(self.actual);tables=groups[0]['tables'];rows=tables[0]['rows']
            if kind=='missing_table':tables.pop()
            elif kind=='duplicate_table':tables.append(copy.deepcopy(tables[0]))
            elif kind=='swap_table':tables[0],tables[1]=tables[1],tables[0]
            elif kind=='missing_row':rows.pop()
            elif kind=='duplicate_row':rows.append(copy.deepcopy(rows[0]))
            elif kind=='swap_row':rows[0],rows[1]=rows[1],rows[0]
            with self.subTest(kind=kind):self.assertTrue(verify(groups,self.official))

    def test_wrong_school_flag_spell_name_legend_and_page_rejected(self):
        for field in ('name','school','flag','legend','page','selection','unknown'):
            groups=copy.deepcopy(self.actual);table=groups[0]['tables'][0]
            if field in ('name','school','flag'):table['rows'][0][{'name':0,'school':1,'flag':2}[field]]='Invented'
            elif field=='legend':table['intro'][0]+=' Invented rule.'
            elif field=='page':table['page']=999
            elif field=='selection':groups[0]['srd52']=False
            else:table['unprinted']='Invented rule.'
            with self.subTest(field=field):self.assertTrue(verify(groups,self.official))


if __name__=='__main__':unittest.main()
