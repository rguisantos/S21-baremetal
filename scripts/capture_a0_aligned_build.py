#!/usr/bin/env python3
"""Consistency guards and metadata at the boundaries of a completed full build."""
from capture_a0_build import profile
from capture_a0_formats import digest, require
from capture_a0_module_stages import imports, MODPOST_SHA
from capture_a0_stack_versions import version_rows

ALIGNED_SHA='5c577cd70b59082e5b66faa3aef3856458d9d9958642c800fff11c3746c42d30'


def completed_build(report, config, exports, makefile, reference_config):
    full=report.get('stages',{}).get('full_build',{})
    require(report.get('full_build_completed') and report.get('build_result_state')=='finished'
            and full.get('returncode')==0 and full.get('timed_out') is False,
            'full build not completed successfully')
    require(report.get('module_prelink_patch')==dict(before_sha256=MODPOST_SHA,after_sha256=ALIGNED_SHA)
            and digest(makefile)==ALIGNED_SHA,'aligned prelink patch not demonstrated')
    require(report.get('final_config_unchanged') and config==reference_config,
            'reference configuration changed')
    p=profile(config.decode(),config.decode())
    require(p['critical_profile_preserved'] and report['final_profile']['critical_profile_preserved']
            and digest(config)==report['final_profile']['generated_config_sha256'],
            'critical/final configuration differs')
    require(digest(exports)==report['candidate_comparison']['sha256'],'final symvers differs')
    return {k:v for k,v in p.items() if k not in ('source_defconfig_equal','config_differences')} | dict(reference_config_equal=True)


def phase_metadata(prelink, generated, final):
    before=imports(prelink);rows=version_rows(generated)
    require(rows==final['versions'],'final versions differ from generated source')
    effective=before.keys()-{'__this_module','_GLOBAL_OFFSET_TABLE_'}
    return dict(prelink_imports=len(effective),generated_version_records=len(rows),
        final_imports=len(final['imports']),
        imports_added_after_modpost=sorted(final['imports'].keys()-effective),
        imports_removed_after_modpost=sorted(effective-final['imports'].keys()),
        prelink_imports_without_generated_version=sorted(effective-rows.keys()),
        final_imports_without_version=sorted(final['imports'].keys()-rows.keys()),
        unused_version_records=sorted(rows.keys()-final['imports'].keys()-{'module_layout'}),
        generated_versions_preserved=True,prelink_sha256=digest(prelink),
        generated_source_sha256=digest(generated.encode()))


def metadata_changes(reference, current):
    require(reference.keys()==current.keys(),'reference/current module names differ')
    fields=('imports','exports','versions','depends','licenses','import_namespaces','vermagic')
    differences={k:sorted(n for n in reference if reference[n][k]!=current[n][k]) for k in fields}
    versions={}
    for name in differences['versions']:
        old=reference[name]['versions'];new=current[name]['versions']
        versions[name]=dict(added={n:new[n] for n in sorted(new.keys()-old.keys())},
            removed={n:old[n] for n in sorted(old.keys()-new.keys())},
            changed={n:dict(before=old[n],after=new[n]) for n in sorted(old.keys()&new.keys()) if old[n]!=new[n]})
    return dict(differences=differences,version_changes=versions)
