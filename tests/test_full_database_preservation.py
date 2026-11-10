import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from capture_full_database import compare_baseline


class FullDatabasePreservationTest(unittest.TestCase):
    def setUp(self):
        self.original={'platform':'desktop','input_sha256':{'data/items.json':'source'},
                       'catalog_sha256':'catalog','protected_sha256':{'card_engine.py':'engine'},
                       'counts':{'card_count':2,'item_count':1},'sheets':1,
                       'cards':[{'title':'Long item 1/2','sha256':'first-half'},
                                {'title':'Long item 2/2','sha256':'second-half'}],
                       'shell_sha256':'layout','html_sha256':'complete'}

    def test_identical_output_passes(self):
        self.assertTrue(compare_baseline(self.original,copy.deepcopy(self.original))['passed'])

    def test_same_count_with_changed_split_boundary_fails(self):
        changed=copy.deepcopy(self.original)
        changed['cards'][0]['sha256']='last-sentence-moved-to-next-card'
        with self.assertRaisesRegex(ValueError,'regression: cards'):compare_baseline(self.original,changed)

    def test_count_order_and_layout_changes_fail(self):
        for key,value in [('counts',{'card_count':3,'item_count':1}),('sheets',2),
                          ('cards',list(reversed(self.original['cards']))),
                          ('shell_sha256','changed-fitting-css'),('html_sha256','changed-document')]:
            with self.subTest(key=key):
                changed=copy.deepcopy(self.original);changed[key]=value
                with self.assertRaisesRegex(ValueError,'regression: '+key):compare_baseline(self.original,changed)

    def test_different_platform_or_input_cannot_approve_regression(self):
        for key,value in [('platform','android'),('input_sha256',{}),('catalog_sha256','different-selection')]:
            with self.subTest(key=key):
                changed=copy.deepcopy(self.original);changed[key]=value
                with self.assertRaisesRegex(ValueError,'precondition differs: '+key):compare_baseline(self.original,changed)

    def test_code_changes_remain_explicit_even_with_identical_output(self):
        changed=copy.deepcopy(self.original);changed['protected_sha256']['card_engine.py']='other-engine'
        self.assertFalse(compare_baseline(self.original,changed)['protected_code_unchanged'])


if __name__=='__main__':unittest.main()
