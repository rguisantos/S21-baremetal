#!/usr/bin/env python3
"""Execute available A0 checks and emit a proposal, without adopting a package."""
import argparse
import json
from pathlib import Path
import subprocess
import tarfile

from capture_a0_container import template
from capture_a0_formats import digest, require
from capture_a0_inputs import read_checked, select_members, unique_object
from capture_a0_package_plan import package_options, validate_consumption

ROOT=Path(__file__).resolve().parents[1]
REFERENCE='e0aa2e16346ca09473071c3ffaaccd46e987568a'


def inspect(stock,source,sizes_report):
    references={}
    def reference(name):
        path='docs/references/'+name
        raw=subprocess.check_output(['git','show',REFERENCE+':'+path],cwd=ROOT)
        require(len(raw) <= 4*1024*1024,'reference budget')
        references[path]=digest(raw)
        return json.loads(raw,object_pairs_hook=unique_object)
    pins=reference('capture-a0-pins-hzc2.json')
    old=reference('capture-a0-payload-sizes-hzc2.json')
    inventory=reference('capture-a0-stock-hzc2.json')['images']
    aligned=reference('capture-a0-aligned-full-audit-hzc2.json')
    kmi=reference('capture-a0-kmi-hzc2.json')
    delta=reference('capture-a0-image-producer-hzc2.json')
    with sizes_report.open('rb') as file: report_bytes=file.read(4*1024*1024+1)
    require(len(report_bytes) <= 4*1024*1024,'sizing report budget')
    measured=json.loads(report_bytes,object_pairs_hook=unique_object)
    consumption=validate_consumption(measured,old)
    signatures={}
    for name in ('boot.img','vendor_boot.img'):
        raw=read_checked(stock/name,pins['stock_raw'][name]);p=template(raw);inv=p['inventory']
        opaque=raw[inv['body_end']:inv['avb']['offset']]
        signatures[name]=dict(stock_sha256=digest(raw),stock_digest_and_embedded_rsa_valid=True,
            embedded_key_sha256=digest(p['key']),signed_extent_bytes=p['extent'],
            signer_marker_offset_in_opaque=opaque.find(b'SignerVer03'),
            signer_signature_validated=False,modified_payload_acceptance_demonstrated=False)
    archive=read_checked(source,pins['samsung_source_archive'])
    names=('kernel/module.c','kernel/cfi.c','include/linux/cfi.h')
    members,_=select_members(archive,names,source_tree=True);del archive
    require(digest(members['kernel/module.c']) == kmi['source_members']['kernel/module.c']['sha256'],
        'module source identity differs')
    needles={'kernel/module.c':('cfi_init(mod);','cfi_module_add(mod, module_addr_min, module_addr_max);',
        'uh_call(UH_APP_RKP, RKP_MODULE_LOAD, RKP_MODULE_PXN_SET,','uh_call(UH_APP_RKP, RKP_MODULE_LOAD, RKP_MODULE_PXN_CLEAR,'),
        'kernel/cfi.c':('CONFIG_CFI_PERMISSIVE','void cfi_module_add(')}
    evidence=[]
    for name,wanted in needles.items():
        lines=members[name].decode().splitlines()
        for needle in wanted:
            hits=[i+1 for i,line in enumerate(lines) if needle in line]
            require(hits,'source hook absent: '+needle);evidence.append(dict(file=name,needle=needle,lines=hits))
    require(delta['source_producer_cause_identified'] is False,'unexpected attribution state')
    return dict(schema='S21-A0-PLAN-EXECUTION-v1',reference_commit=REFERENCE,reference_sha256=references,
        implementation_sha256={n:digest(Path(__file__).with_name(n).read_bytes()) for n in
            ('capture_a0_inputs.py','capture_a0_sizes.py','check_capture_a0_sizes.py',
                'capture_a0_package_plan.py','check_capture_a0_plan.py')},
        phase1=dict(status='documentary_exit_non_identified',upstream_delta_bytes=delta['pre_alignment_delta_bytes'],
            upstream_producer_identified=False,alignment_mechanism_already_documented=True,new_binary_attribution_claim=False),
        phase2=dict(status='proposal_awaiting_user_choice',options=package_options(inventory,old),
            recommended_research_option='natural_lengths_strip_debug',recommendation_is_not_adoption=True),
        phase3=dict(status='blocked_no_demonstrated_acceptance',stock_signatures=signatures,
            parent_vbmeta_supplied=False,lab_key_is_device_trust=False,physical_action=False),
        phase4=dict(status='blocked_kmi_provenance_and_runtime',missing_list_inputs=kmi['missing_list_inputs'],
            whitelist_names_without_list_origin=kmi['raw_not_in_available_union'],
            policy_proposal=dict(same_aligned_build_kernel_and_274_modules=True,
                excluded_additional_names=aligned['candidate_module_set']['additional_names'],
                module_loading_force_allowed=False,security_settings=aligned['kernel_build_settings'],
                critical_config=aligned['profile']['selected_config'],modules_dep_closure_not_revalidated_here=True),
            source_hooks=evidence,source_members={n:dict(bytes=len(b),sha256=digest(b)) for n,b in members.items()},
            source_hook_presence_is_not_runtime_validation=True,cfi_rkp_runtime_verified=False),
        phase5=dict(status='sizing_runner_frontiers_corrected',consumption=consumption,
            sizing_report_sha256=digest(report_bytes),tools=measured['tools'],
            artifact_hashes=dict(Image=measured['image']['sha256'],
                ramdisk_as_built=measured['profiles']['as_built']['gzip_sha256'],
                ramdisk_strip_debug=measured['profiles']['strip_debug']['gzip_sha256']),
            remaining_scope=['other runners with verify then reopen','external archive verification on user machine'],
            external_user_verification_completed=False),
        a0_complete=False,a1_implemented=False,package_adopted=False,boot_container_built=False,
        padding_applied=False,geometry_adopted=False,oem_decision=False,physical_action=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('stock-dir','source','sizing-report','output'):p.add_argument('--'+name,required=True,type=Path)
    a=p.parse_args()
    try:
        require(not a.output.exists(),'output must be new')
        result=inspect(a.stock_dir,a.source,a.sizing_report)
        a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    except (OSError,ValueError,KeyError,tarfile.TarError,subprocess.SubprocessError) as e:p.exit(1,'A0 PLAN REFUSED: '+str(e)+'\n')
    print('A0 phase 1 documentary exit; phase 2 proposal; phases 3/4 blocked; phase 5 sizing frontiers corrected')
    return 2


if __name__=='__main__':raise SystemExit(main())
