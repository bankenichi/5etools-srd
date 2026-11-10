"""Approved portrait flags must have an exact, guarded source-text inverse."""
import copy
import json
from pathlib import Path
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import build_srd
from layout_overrides import apply_layouts,source_projection,load_model


class LayoutOverrideTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        original=build_srd.apply_layouts;captured={}
        def observe(data,*args):captured.update(copy.deepcopy(data));return original(data,*args)
        try:
            build_srd.apply_layouts=observe;builder=build_srd.Builder(ROOT);files=builder.output()
        finally:build_srd.apply_layouts=original
        indexer=copy.copy(builder);indexer.data=captured;indexer.indexes()
        cls.source=captured;cls.wrapped={name:json.loads(raw) for name,raw in files.items() if name.startswith('data/')}
        cls.model,_=load_model();cls.spec=cls.model['records'][0]

    def target(self,data):
        return next(r for r in data[self.spec['file']][self.spec['kind']] if r['name']==self.spec['name'])

    def paragraph_parent(self,record):
        path=self.spec['paragraph_path'];node=record
        for part in path[:-1]:node=node[part]
        return node,path[-1]

    def test_all_source_values_preserved_and_round_trip_is_exact(self):
        frozen=copy.deepcopy(self.wrapped)
        normalized,receipt=source_projection(self.wrapped,require_all=True,require_applied=True)
        self.assertEqual(normalized,self.source);self.assertEqual(self.wrapped,frozen)
        self.assertEqual(len(receipt['annotations_removed']),6)
        repeated,_=apply_layouts(normalized,build_srd.PDF_SHA256,build_srd.UPSTREAM)
        self.assertEqual(repeated,self.wrapped)

    def test_changed_source_preimage_is_rejected(self):
        changed=copy.deepcopy(self.source);self.target(changed)['name']='Changed source identity'
        with self.assertRaises(ValueError):apply_layouts(changed,build_srd.PDF_SHA256,build_srd.UPSTREAM)

    def test_changed_wrapped_rule_text_is_rejected(self):
        changed=copy.deepcopy(self.wrapped);parent,key=self.paragraph_parent(self.target(changed))
        parent[key]['entry']+=' Unprinted text.'
        with self.assertRaises(ValueError):source_projection(changed,require_all=True,require_applied=True)

    def test_wrong_flag_and_extra_wrapper_fields_are_rejected(self):
        for action in ('numeric-true','false','extra','landscape'):
            with self.subTest(action=action):
                changed=copy.deepcopy(self.wrapped);parent,key=self.paragraph_parent(self.target(changed));wrapper=parent[key]
                if action=='numeric-true':wrapper['_force_portrait']=1
                elif action=='false':wrapper['_force_portrait']=False
                elif action=='extra':wrapper['hidden']='Unreviewed'
                else:del wrapper['_force_portrait'];wrapper['_force_landscape']=True
                with self.assertRaises(ValueError):source_projection(changed,require_all=True,require_applied=True)

    def test_missing_applied_override_and_duplicate_record_are_rejected(self):
        with self.assertRaises(ValueError):source_projection(self.source,require_all=True,require_applied=True)
        changed=copy.deepcopy(self.wrapped);changed[self.spec['file']][self.spec['kind']].append(copy.deepcopy(self.target(changed)))
        with self.assertRaises(ValueError):source_projection(changed,require_all=True,require_applied=True)

    def test_unreviewed_marker_on_other_record_is_rejected(self):
        changed=copy.deepcopy(self.wrapped);changed['data/items.json']['item'][0]['_force_portrait']=True
        with self.assertRaises(ValueError):source_projection(changed)

    def test_unannotated_audit_inputs_are_not_modified_or_certified_as_layouts(self):
        changed=copy.deepcopy(self.source);self.target(changed)['source']='Uncited audit input'
        normalized,receipt=source_projection(changed)
        self.assertEqual(normalized,changed);self.assertFalse(receipt['annotations_removed'])
        with self.assertRaises(ValueError):source_projection(changed,require_all=True,require_applied=True)


if __name__=='__main__':unittest.main()
