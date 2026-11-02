#!/usr/bin/env python3
"""ELF metadata bounds and source-derived module policy controls."""
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

import capture_a0_module_policy as m
from check_capture_a0_module_policy import candidate_inputs

CONFIG='CONFIG_MODVERSIONS=y\n# CONFIG_MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS is not set\n'
MAGIC='5.4.242 SMP modversions aarch64'


def fixture(imports=(('service',1),),namespace=None,section='__ksymtab',versions=None,debug=0):
    fields=b'name=fixture\0vermagic='+MAGIC.encode()+b'\0depends=\0license=GPL\0'
    rows=versions if versions is not None else [('module_layout',0x11),('service',0x22)]
    ver=b''.join(struct.pack('<Q',v)+n.encode().ljust(56,b'\0') for n,v in rows)
    strings=bytearray(b'\0');offset={}
    for name in ['exp','__crc_exp',*[n for n,_ in imports]]:
        offset[name]=len(strings);strings.extend(name.encode()+b'\0')
    symbols=bytearray(24)
    symbols.extend(struct.pack('<IBBHQQ',0,3,0,6,0,0))
    symbols.extend(struct.pack('<IBBHQQ',offset['exp'],0x12,0,11,0,4))
    symbols.extend(struct.pack('<IBBHQQ',offset['__crc_exp'],0x10,0,0xfff1,0x1234,0))
    for name,binding in imports:symbols.extend(struct.pack('<IBBHQQ',offset[name],binding<<4,0,0,0,0))
    expstrings=b'exp\0'+(namespace.encode()+b'\0' if namespace is not None else b'')
    reloc=struct.pack('<QQq',0,(2<<32)|257,0)+struct.pack('<QQq',8,(1<<32)|257,0)
    if namespace is not None:reloc+=struct.pack('<QQq',16,(1<<32)|257,4)
    crc=struct.pack('<QQq',0,(3<<32)|258,0)
    # name,type,data,link,info,entsize
    secs=[('.shstrtab',3,b'',0,0,0),('.modinfo',1,fields,0,0,0),('__versions',1,ver,0,0,0),
          ('.strtab',3,bytes(strings),0,0,0),('.symtab',2,bytes(symbols),4,2,24),
          ('__ksymtab_strings',1,expstrings,0,0,0),(section,1,bytes(24),0,0,0),
          (section.replace('__ksymtab','__kcrctab'),1,bytes(4),0,0,0),
          ('.rela.exports',4,reloc,5,7,24),('.rela.crcs',4,crc,5,8,24),('.text',1,b'\xc0\x03\x5f\xd6',0,0,0)]
    if debug:secs.append(('.debug.fixture',1,bytes(debug),0,0,0))
    names=b'\0';name_offsets={}
    for n,*_ in secs:name_offsets[n]=len(names);names+=n.encode()+b'\0'
    secs[0]=('.shstrtab',3,names,0,0,0)
    data=bytearray(64);headers=[bytes(64)];locations={}
    for name,typ,raw,link,info,entsize in secs:
        data.extend(bytes((-len(data))%8));locations[name]=len(data)
        headers.append(struct.pack('<IIQQQQIIQQ',name_offsets[name],typ,0,0,len(data),len(raw),link,info,8,entsize));data.extend(raw)
    shoff=len(data);data.extend(b''.join(headers));data[:7]=b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HHI',data,16,1,183,1);struct.pack_into('<Q',data,40,shoff);struct.pack_into('<6H',data,52,64,0,0,64,len(headers),1)
    return bytes(data),locations,shoff


def subject(name='client',imports=None,licenses=None,exports=None,depends=None,versions=None):
    return dict(name=name,vermagic=MAGIC,versions=versions if versions is not None else {'module_layout':'0x00000011','service':'0x00000022'},
        imports=imports if imports is not None else {'service':'strong'},licenses=licenses if licenses is not None else ['GPL'],
        import_namespaces=[],exports=exports or {},depends=depends or [])


def export(crc='0x00000022',kind='EXPORT_SYMBOL',namespace=None):return dict(crc=crc,export=kind,namespace=namespace)


def kernel():return {'module_layout':export('0x00000011'),'service':export()}


class MetadataTests(unittest.TestCase):
    def test_real_metadata_layout(self):
        data,_,_=fixture(namespace='TEST_NS',section='__ksymtab_gpl')
        r=m.module(data)
        self.assertEqual(r['name'],'fixture');self.assertEqual(r['imports'],{'service':'strong'})
        self.assertEqual(r['exports'],{'exp':export('0x00001234','EXPORT_SYMBOL_GPL','TEST_NS')})

    def test_debug_above_old_reader_limit_is_not_metadata(self):
        data,_,_=fixture(debug=33*1024*1024)
        self.assertEqual(m.module(data)['exports']['exp']['crc'],'0x00001234')

    def test_weak_import_binding(self):
        data,_,_=fixture(imports=(('service',2),))
        self.assertEqual(m.module(data)['imports'],{'service':'weak'})

    def test_elf_profile_and_table_refusals(self):
        original,_,_=fixture()
        for off,value in [(4,1),(5,2),(16,3),(18,62)]:
            data=bytearray(original);data[off]=value
            with self.subTest(off=off),self.assertRaises(ValueError):m.module(data)
        with self.assertRaises(ValueError):m.module(original[:-10])

    def test_bad_symbol_string_and_link_refused(self):
        original,loc,table=fixture()
        data=bytearray(original);struct.pack_into('<I',data,loc['.symtab']+4*24,0xffffffff)
        with self.assertRaises(ValueError):m.module(data)
        data=bytearray(original);struct.pack_into('<I',data,table+5*64+40,2)
        with self.assertRaises(ValueError):m.module(data)

    def test_crc_relocation_type_and_identity_refused(self):
        original,loc,_=fixture()
        for value in ((3<<32)|257,(2<<32)|258):
            data=bytearray(original);struct.pack_into('<Q',data,loc['.rela.crcs']+8,value)
            with self.subTest(value=value),self.assertRaises(ValueError):m.module(data)

    def test_missing_name_relocation_and_namespace_pointer_refused(self):
        original,loc,_=fixture()
        data=bytearray(original);struct.pack_into('<Q',data,loc['.rela.exports']+24,0)
        with self.assertRaises(ValueError):m.module(data)
        data=bytearray(original);data[loc['__ksymtab']+16]=1
        with self.assertRaises(ValueError):m.module(data)

    def test_metadata_relocation_cannot_escape_target(self):
        original,loc,_=fixture();data=bytearray(original)
        struct.pack_into('<Q',data,loc['.rela.exports'],4096)
        with self.assertRaises(ValueError):m.module(data)

    def test_export_value_requires_pointer_relocation(self):
        original,loc,_=fixture();data=bytearray(original)
        struct.pack_into('<Q',data,loc['.rela.exports']+8,(2<<32)|258)
        with self.assertRaises(ValueError):m.module(data)

    def test_metadata_budget_is_separate_from_ignored_debug(self):
        original,loc,table=fixture(debug=33*1024*1024);data=bytearray(original)
        struct.pack_into('<Q',data,table+4*64+24,loc['.debug.fixture'])
        struct.pack_into('<Q',data,table+4*64+32,m.MAX_METADATA)
        with self.assertRaisesRegex(ValueError,'metadata read bound'):m.module(data)

    def test_version_duplicates_width_and_layout_required(self):
        for versions in ([('module_layout',1),('module_layout',2)],[('x',1)],[('module_layout',2**32)]):
            data,_,_=fixture(versions=versions)
            with self.subTest(versions=versions),self.assertRaises(ValueError):m.module(data)

    def test_common_symbol_refused(self):
        data,loc,_=fixture();data=bytearray(data);struct.pack_into('<H',data,loc['.symtab']+4*24+6,0xfff2)
        with self.assertRaises(ValueError):m.module(data)

    def test_unpinned_archive_refused_before_tar(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'wrong';p.write_bytes(b'wrong')
            with patch('check_capture_a0_module_policy.tarfile.open') as open_tar:
                with self.assertRaises(ValueError):candidate_inputs(p,{'bytes':1,'sha256':'0'*64})
                open_tar.assert_not_called()


class PolicyTests(unittest.TestCase):
    def evaluate(self,mods=None,k=None,requested=None,config=CONFIG):
        mods=mods or {'client':subject()};return m.evaluate(mods,k or kernel(),requested or list(mods),MAGIC,config)

    def test_release_prefix_ignored_only_with_crc_profile(self):
        stock='5.4.242-HZC2 SMP modversions aarch64'
        self.assertTrue(m.same_magic(stock,MAGIC,True))
        self.assertFalse(m.same_magic(stock,MAGIC,False))
        self.assertFalse(m.same_magic(stock,MAGIC,True,False))
        self.assertFalse(m.same_magic(stock,MAGIC.replace('SMP','UP'),True))

    def test_pass_does_not_approve_abi(self):
        r=self.evaluate();self.assertTrue(r['strict_plan_checks_passed']);self.assertFalse(r['module_abi_established']);self.assertFalse(r['a0_complete'])

    def test_crc_mismatch_rejected(self):
        r=self.evaluate(mods={'client':subject(versions={'module_layout':'0x00000011','service':'0x00000023'})})
        self.assertIn(['client','crc_mismatch','service'],r['errors'])

    def test_missing_version_is_source_warning_and_plan_gap(self):
        r=self.evaluate(mods={'client':subject(versions={'module_layout':'0x00000011'})})
        self.assertTrue(r['modeled_source_checks_passed']);self.assertFalse(r['strict_plan_checks_passed'])
        self.assertIn(['client','crc_coverage_not_established','service'],r['plan_blocks'])
        self.assertEqual(r['unversioned_imports'],[dict(module='client',symbol='service',provider='vmlinux',
            provider_crc='0x00000022',consumer_version_record_present=False)])

    def test_strong_missing_and_weak_missing_are_different(self):
        r=self.evaluate(mods={'client':subject(imports={'absent':'strong'})});self.assertTrue(r['errors'])
        r=self.evaluate(mods={'client':subject(imports={'absent':'weak'})});self.assertFalse(r['errors']);self.assertEqual(r['weak_unresolved'],{'client':['absent']})

    def test_available_weak_policy_is_explicitly_not_modeled(self):
        r=self.evaluate(mods={'client':subject(imports={'service':'weak'},licenses=['Proprietary'])},k={'module_layout':export('0x00000011'),'service':export(kind='EXPORT_SYMBOL_GPL')})
        self.assertFalse(r['strict_plan_checks_passed']);self.assertFalse(r['errors'])
        self.assertIn(['client','available_weak_resolution_order_not_modeled','service'],r['plan_blocks'])

    def test_namespace_rules_and_permissive_source_setting(self):
        k=kernel();k['service']['namespace']='NS';r=self.evaluate(k=k);self.assertTrue(r['errors'])
        a=subject();a['import_namespaces']=['NS'];self.assertTrue(self.evaluate({'client':a},k)['strict_plan_checks_passed'])
        r=self.evaluate(k=k,config='CONFIG_MODVERSIONS=y\nCONFIG_MODULE_ALLOW_MISSING_NAMESPACE_IMPORTS=y\n')
        self.assertTrue(r['strict_plan_checks_passed']);self.assertTrue(r['warnings'])

    def test_empty_namespace_pointer_is_not_null(self):
        k=kernel();k['service']['namespace']='';self.assertTrue(self.evaluate(k=k)['errors'])

    def test_gpl_restriction_and_mixed_licenses(self):
        k=kernel();k['service']['export']='EXPORT_SYMBOL_GPL'
        for licenses in ([],['Proprietary'],['GPL','Proprietary']):
            with self.subTest(licenses=licenses):self.assertTrue(self.evaluate({'client':subject(licenses=licenses)},k)['errors'])

    def test_future_gpl_export_warns_without_rejecting(self):
        k=kernel();k['service']['export']='EXPORT_SYMBOL_GPL_FUTURE'
        r=self.evaluate({'client':subject(licenses=['Proprietary'])},k)
        self.assertTrue(r['strict_plan_checks_passed']);self.assertTrue(r['warnings'])

    def test_provider_taint_is_transitive(self):
        k=kernel();k['service']['export']='EXPORT_SYMBOL_GPL'
        provider=subject('provider',imports={},licenses=['Proprietary'],exports={'other':export('0x00000033')})
        client=subject(imports={'service':'strong','other':'strong'},versions={'module_layout':'0x00000011','service':'0x00000022','other':'0x00000033'})
        r=self.evaluate({'client':client,'provider':provider},k);self.assertTrue(r['errors'])
        self.assertIn('client',r['proprietary_taint_closure'])

    def test_declared_only_dependency_does_not_inherit_taint(self):
        k=kernel();k['service']['export']='EXPORT_SYMBOL_GPL'
        mods={'client':subject(depends=['provider']), 'provider':subject('provider',imports={},licenses=['Proprietary'])}
        self.assertTrue(self.evaluate(mods,k)['strict_plan_checks_passed'])

    def test_aliases_dependency_order_and_cycle(self):
        mods={'client':subject(depends=['provider-name']),'provider_name':subject('provider_name',imports={})}
        self.assertEqual(self.evaluate(mods)['dependency_order'],['provider_name','client'])
        mods['provider_name']['depends']=['client'];self.assertFalse(self.evaluate(mods)['strict_plan_checks_passed'])

    def test_extra_module_can_be_excluded_only_when_not_needed(self):
        mods={'client':subject(),'extra':subject('extra',imports={})}
        self.assertTrue(self.evaluate(mods,requested=['client'])['strict_plan_checks_passed'])
        mods['client']['depends']=['extra'];self.assertTrue(self.evaluate(mods,requested=['client'])['plan_blocks'])

    def test_duplicate_exports_are_not_chosen_silently(self):
        mods={'client':subject(exports={'service':export()})};self.assertTrue(self.evaluate(mods)['duplicate_exports'])

    def test_relative_abi_and_duplicate_requests_refused(self):
        with self.assertRaises(ValueError):self.evaluate(config=CONFIG+'CONFIG_MODULE_REL_CRCS=y\n')
        with self.assertRaises(ValueError):self.evaluate(requested=['client','client'])

    def test_symvers_format_and_duplicate_refusals(self):
        text='0x00000011 module_layout vmlinux EXPORT_SYMBOL\n'
        self.assertEqual(m.symvers(text)['module_layout']['crc'],'0x00000011')
        for invalid in (text+text,'bad',''):
            with self.subTest(invalid=invalid),self.assertRaises(ValueError):m.symvers(invalid)


if __name__=='__main__':unittest.main()
