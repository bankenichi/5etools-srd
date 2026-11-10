"""Source-page edge cases: shared pages, table continuations and schema helpers."""
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from locate_source_citations import Source,locate,helper_scope,canon
from build_srd import Builder
from rule_table_grid import PDF_SHA256

PDF=Path(os.environ.get('SRD521_PDF',''))


@unittest.skipUnless(PDF.is_file(),'Set SRD521_PDF for independent citation checks')
class SourceCitationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import fitz
        assert hashlib.sha256(PDF.read_bytes()).hexdigest()==PDF_SHA256
        cls.pdf=fitz.open(PDF);cls.addClassCleanup(cls.pdf.close);cls.source=Source(cls.pdf)

    def test_subclass_prefixes_and_shared_page_boundaries(self):
        for name,parent,page in [('Champion','Fighter',49),('Hunter','Ranger',61),('Thief','Rogue',64)]:
            result=locate(self.source,name,'subclass',{'className':parent})
            with self.subTest(name=name):
                self.assertEqual(result['status'],'LOCATED');self.assertEqual(result['page'],page)
        self.assertEqual(locate(self.source,'Champion','subclass',{'className':'Bard'})['status'],'PENDING')
        self.assertEqual(locate(self.source,"Thief's Reflexes",'subclassFeature',{'className':'Rogue','level':17})['page'],64)

    def test_repeated_feature_name_uses_its_printed_level_context(self):
        for level,page in [(2,50),(10,52)]:
            result=locate(self.source,'Patient Defense','classFeature',{'className':'Monk','level':level})
            with self.subTest(level=level):self.assertEqual(result['page'],page)

    def test_special_font_and_statblock_title_citations(self):
        result=locate(self.source,'Acid Splash','spell',{'page':999})
        self.assertEqual(result['page'],107)
        self.assertEqual(locate(self.source,'Giant Fly','monster',{})['page'],222)
        self.assertEqual(locate(self.source,'Acid Splazh','spell',{})['status'],'PENDING')

    def test_source_rows_use_their_real_continuation_page(self):
        self.assertEqual(self.source.table_row('Ammunition','Arrows')['page'],96)
        self.assertEqual(self.source.table_row('Food, Drink, and Lodging','Common')['page'],102)
        self.assertEqual(self.source.table_row('Ammunition','Arrow')['status'],'PENDING')

    def test_empty_schema_helper_does_not_get_a_fictional_source_page(self):
        result=helper_scope(self.source,{'name':'Generic Variant','abbreviation':'GV','page':999})
        self.assertEqual(result['status'],'SCHEMA_HELPER');self.assertIsNone(result['page'])
        self.assertIsNone(helper_scope(self.source,{'name':'Generic Variant','abbreviation':'GV','entries':['Unprinted rules']}))
        self.assertEqual(helper_scope(self.source,{'name':'Potion'})['page'],204)

    def test_inline_fighting_style_alternatives_keep_the_complete_printed_rules(self):
        files=Builder(ROOT).output()
        for slug,page,block,label in [('paladin',54,8,'Blessed Warrior'),('ranger',59,3,'Druidic Warrior')]:
            with self.subTest(label=label):
                payload=json.loads(files[f'data/class/class-{slug}.json'])
                feature=next(r for r in payload['classFeature'] if r['name']=='Fighting Style')
                alternative=feature['entries'][1]
                self.assertEqual(alternative['name'],label)
                self.assertEqual(alternative['type'],'entries')
                self.assertEqual(len(alternative['entries']),1)
                lines=self.pdf[page-1].get_text('dict')['blocks'][block]['lines'][4:12]
                raw='\n'.join(''.join(s['text'] for s in line['spans']) for line in lines)
                printed=' '.join(re.sub(r'(?<=\w)-\n(?=\w)','',raw).split())
                self.assertEqual(label+'. '+alternative['entries'][0],printed)

    def test_invocation_references_match_the_entire_printed_option_inventory(self):
        payload=json.loads(Builder(ROOT).output()['data/class/class-warlock.json'])
        feature=next(r for r in payload['classFeature'] if r['name']=='Eldritch Invocation Options')
        nodes=feature['entries'][1]['entries']
        lo=self.source.position(next(h for h in self.source.headings if h['text']=='Eldritch Invocation Options'))
        hi=self.source.position(next(h for h in self.source.headings if h['text']=='Warlock Spell List'))
        names=[canon(h['text']) for h in self.source.headings if h['strength']=='heading'
               and h['sizes']==[12.0] and lo<self.source.position(h)<hi]
        self.assertEqual(len(names),28)
        self.assertEqual([canon(node['optionalfeature'].split('|')[0]) for node in nodes],names)
        self.assertTrue(all(node['type']=='refOptionalfeature' and node['optionalfeature'].endswith('|SRD521') for node in nodes))


if __name__=='__main__':unittest.main()
