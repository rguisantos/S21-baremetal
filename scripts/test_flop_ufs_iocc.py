#!/usr/bin/env python3
"""Check numeric phandle resolution, control masks and pinned-source refusals."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from inspect_flop_ufs_iocc import (C_WITNESSES,DTS,MANIFEST,cells,driver_witnesses,
    dts_nodes,dts_reference,inspect,verify_sources)

FIXTURE='''/dts-v1/;
/ {
 #address-cells = <2>; #size-cells = <1>;
 pmu@15860000 { reg = <0 0x15860000 0x10000>; phandle = <1>; };
 sys@11020000 { reg = <0 0x11020000 0x1000>; phandle = <2>; };
 ufs@0x13100000 {
  reg = <0 0x13100000 0x200>; dma-coherent;
  samsung,pmu-phandle = <1>; samsung,sysreg-phandle = <2>;
  ufs-phy-iso { offset = <0x728>; mask = <1>; val = <1>; };
  ufs-iocc { offset = <0x700>; mask = <0x300000>; val = <0x300000>; };
 };
};'''


class DtsTests(unittest.TestCase):
    def test_phy_and_iocc_resolve_to_distinct_syscons(self):
        r=dts_reference(FIXTURE)
        self.assertEqual(r['phy_isolation']['address'],'0x15860728')
        self.assertEqual(r['iocc']['address'],'0x11020700')
        self.assertEqual((r['iocc']['mask'],r['iocc']['value']),('0x300000','0x300000'))
        self.assertTrue(r['dma_coherent'])

    def test_absent_dma_flag_is_distinguished(self):
        self.assertFalse(dts_reference(FIXTURE.replace('dma-coherent;',''))['dma_coherent'])

    def test_quoted_braces_comments_and_declared_label_do_not_change_paths(self):
        text=FIXTURE.replace('pmu@','pmu_label: pmu@',1).replace('reg = <0 0x15860000','note = "{ ; }"; /* } */ // {\n reg = <0 0x15860000',1)
        self.assertEqual(dts_reference(text)['phy_isolation']['address'],'0x15860728')

    def test_duplicate_node_or_property_refused(self):
        for text in ('/ { a {}; a {}; };','/ { a; a; };'):
            with self.subTest(text=text),self.assertRaisesRegex(ValueError,'duplicate'):dts_nodes(text)

    def test_truncated_unbalanced_and_unsupported_root_directive_refused(self):
        for text in ('/ { a {','/ { a; }};','/include/ "x"; / {};','/ { a = <1> }'):
            with self.subTest(text=text),self.assertRaises(ValueError):dts_nodes(text)

    def test_duplicate_and_unresolved_phandles_refused(self):
        for old,new in (('phandle = <2>','phandle = <1>'),('sysreg-phandle = <2>','sysreg-phandle = <3>')):
            with self.subTest(new=new),self.assertRaises(ValueError):dts_reference(FIXTURE.replace(old,new))

    def test_root_cell_counts_and_scalar_control_fields_are_checked(self):
        for old,new in (('#address-cells = <2>','#address-cells = <1>'),('mask = <1>','mask = <1 2>')):
            with self.subTest(new=new),self.assertRaises(ValueError):dts_reference(FIXTURE.replace(old,new))

    def test_region_bound_alignment_and_value_mask_are_checked(self):
        for old,new in (('offset = <0x700>','offset = <0x1000>'),('offset = <0x700>','offset = <0x701>'),('val = <1>','val = <2>')):
            with self.subTest(new=new),self.assertRaises(ValueError):dts_reference(FIXTURE.replace(old,new))

    def test_dma_coherent_is_a_boolean_property(self):
        with self.assertRaisesRegex(ValueError,'flag'):dts_reference(FIXTURE.replace('dma-coherent;','dma-coherent = <1>;'))

    def test_numeric_cells_reject_labels_expressions_and_overflow(self):
        for value in ('<&sys>','<(1 + 2)>','<0x100000000>','<1, 2>','[]'):
            with self.subTest(value=value),self.assertRaises(ValueError):
                cells(dts_nodes('/ { value = '+value+'; };')['/'],'value')


class SourceTests(unittest.TestCase):
    def test_driver_witnesses_have_distinct_lines(self):
        text='\n'.join(C_WITNESSES.values());rows=driver_witnesses(text)
        self.assertEqual(len(rows),9);self.assertEqual(len({v['line'] for v in rows.values()}),9)

    def test_missing_or_duplicated_update_witness_refused(self):
        text='\n'.join(C_WITNESSES.values());update=C_WITNESSES['iocc_update']
        for changed in (text.replace(update,''),text+'\n'+update):
            with self.assertRaisesRegex(ValueError,'driver witness'):driver_witnesses(changed)

    def test_wrong_source_bytes_fail_before_lk_gnu(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/DTS;p.parent.mkdir(parents=True);p.write_text('bad')
            with patch('inspect_flop_ufs_iocc.inspect_lk') as tool:
                with self.assertRaisesRegex(ValueError,'source bytes differ'):inspect(directory,'missing-sboot')
                tool.assert_not_called()

    def test_manifest_identity_and_file_list_are_checked(self):
        original=json.loads(MANIFEST.read_text())
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'manifest.json'
            for field,value in (('commit','bad'),('repository','bad'),('files',original['files'][:1])):
                manifest=copy.deepcopy(original);manifest[field]=value;p.write_text(json.dumps(manifest))
                with self.subTest(field=field),patch('inspect_flop_ufs_iocc.MANIFEST',p):
                    with self.assertRaisesRegex(ValueError,'manifest'):verify_sources(directory)


if __name__=='__main__':unittest.main()
