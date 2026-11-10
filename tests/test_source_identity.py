"""Source references must change together, with no prose/number mutation."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from source_identity import remap,consolidate_bestiary,apply_citations


class SourceIdentityTest(unittest.TestCase):
    def test_declared_source_fields_and_packed_references_change_together(self):
        original={'source':'XPHB','classSource':'xphb','subclassSource':'XMM',
          'classFeatures':['Spellcasting|Wizard|XPHB|1|XPHB'],
          'cards':['Basilisk|Deck of Illusions|SRD52'],'property':[{'uid':'L|XPHB'}],
          'entries':['{#itemEntry Ioun Stone|XDMG}']}
        frozen=copy.deepcopy(original);result=remap(original)
        self.assertEqual(original,frozen)
        self.assertEqual(result['source'],'SRD521');self.assertEqual(result['classSource'],'SRD521')
        self.assertEqual(result['subclassSource'],'SRD521')
        self.assertEqual(result['classFeatures'],['Spellcasting|Wizard|SRD521|1|SRD521'])
        self.assertEqual(result['cards'],['Basilisk|Deck of Illusions|SRD521'])
        self.assertEqual(result['property'],[{'uid':'L|SRD521'}])
        self.assertEqual(result['entries'],['{#itemEntry Ioun Stone|SRD521}'])

    def test_names_prose_custom_sources_and_numbers_are_preserved(self):
        original={'name':'XPHB','source':'Custom','page':99,'entries':['The identifiers XPHB and SRD52 remain literal prose.'],
          'range':'20/60','requires':[{'type':'M|XPHB'}],'classFeatures':['Level|Wizard|XPHB|9|XPHB']}
        result=remap(original)
        for key in ('name','source','page','entries','range'):self.assertEqual(result[key],original[key])
        self.assertEqual(result['requires'],[{'type':'M|SRD521'}])
        self.assertEqual(result['classFeatures'],['Level|Wizard|SRD521|9|SRD521'])

    def test_filter_structure_and_spell_level_parameters_remain(self):
        original='{@filter Spells|spells|class=Wizard|level=9|source=XPHB}'
        self.assertEqual(remap(original),'{@filter Spells|spells|class=Wizard|level=9|source=SRD521}')
        self.assertEqual(remap('{@filter Metamagic Options|optionalfeatures|feature type=MM|source=XPHB}'),
          '{@filter Metamagic Options|optionalfeatures|feature type=MM|source=SRD521}')
        self.assertEqual(remap({'source':'SRD521','uid':'Example|SRD521'}),{'source':'SRD521','uid':'Example|SRD521'})

    def test_all_statblocks_survive_a_single_source_index(self):
        data={'data/bestiary/bestiary-xdmg.json':{'monster':[{'name':'A','source':'SRD521'}]},
          'data/bestiary/bestiary-xmm.json':{'monster':[{'name':'B','source':'SRD521'}]},
          'data/bestiary/bestiary-xphb.json':{'monster':[{'name':'C','source':'SRD521'}]}}
        result=consolidate_bestiary(data)
        self.assertEqual([r['name'] for r in result['data/bestiary/bestiary-srd521.json']['monster']],['A','B','C'])
        self.assertEqual(result['data/bestiary/index.json'],{'SRD521':'bestiary-srd521.json'})
        bad=copy.deepcopy(data);bad['data/bestiary/bestiary-xmm.json']['monster'][0]['name']='A'
        with self.assertRaises(ValueError):consolidate_bestiary(bad)
        bad=copy.deepcopy(data);bad['data/bestiary/bestiary-xmm.json']['monster'][0]['source']='XMM'
        with self.assertRaises(ValueError):consolidate_bestiary(bad)

    def citation_fixture(self):
        records=[{'name':'Example','source':'XMM','page':999,'hp':{'average':42}}]
        data={'data/bestiary/bestiary-xmm.json':{'monster':records}}
        record=records[0]
        model={'official_pdf_sha256':'fixture-pdf','upstream_commit':'fixture-upstream','records':[{
          'file':'data/bestiary/bestiary-xmm.json','kind':'monster','index':0,'name':'Example',
          'candidate_record_sha256':hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),
          'status':'LOCATED','page':258}]}
        return data,model

    def test_citation_application_keeps_gameplay_values_and_input_intact(self):
        data,model=self.citation_fixture();frozen=copy.deepcopy(data)
        with tempfile.TemporaryDirectory() as folder:
            p=Path(folder)/'citations.json';p.write_text(json.dumps(model))
            result,receipt=apply_citations(data,p,'fixture-pdf','fixture-upstream')
        self.assertEqual(data,frozen)
        self.assertEqual(result['data/bestiary/bestiary-srd521.json']['monster'],[{'name':'Example','source':'SRD521','page':258,'hp':{'average':42}}])
        self.assertEqual(receipt['page_fields_corrected'],1)

    def test_citation_input_drift_invalid_pages_and_missing_recipes_rejected(self):
        for action in ('input','page','missing','duplicate','authority'):
            data,model=self.citation_fixture()
            if action=='input':data['data/bestiary/bestiary-xmm.json']['monster'][0]['hp']['average']=43
            elif action=='page':model['records'][0]['page']=999
            elif action=='missing':model['records']=[]
            elif action=='duplicate':model['records'].append(copy.deepcopy(model['records'][0]))
            else:model['official_pdf_sha256']='different-pdf'
            with self.subTest(action=action),tempfile.TemporaryDirectory() as folder:
                p=Path(folder)/'citations.json';p.write_text(json.dumps(model))
                with self.assertRaises(ValueError):apply_citations(data,p,'fixture-pdf','fixture-upstream')
if __name__=='__main__':unittest.main()
