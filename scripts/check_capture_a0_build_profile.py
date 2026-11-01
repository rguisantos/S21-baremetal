#!/usr/bin/env python3
"""Reproduce p3s Kconfig controls, preparation and a bounded offline build."""
import argparse
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import tarfile

from capture_a0_build import directory_tree, profile, vdso, partial_versions, patch_tui
from capture_a0_formats import digest, require
from capture_a0_modules import compare_symvers
from check_capture_a0 import PINS, verify_file

TREES = {'clang-r383902':'34feae7abc38fffe258af1842a4c19746368cec6',
         'aarch64-android49':'9959a53ab082bef137916638c48c9871c5d82cfd',
         'arm-android49':'91c70ff36200356813e0992c39b8b0d47d85aa0b'}
CONFIG = 'arch/arm64/configs/exynos2100-p3sxxx_defconfig'


def run(args, env, log, timeout=180):
    """Bound a process group so a timeout cannot leave compiler children running."""
    with log.open('w') as f:
        p = subprocess.Popen(args,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
        try:return dict(returncode=p.wait(timeout=timeout),timed_out=False)
        except subprocess.TimeoutExpired:
            try:os.killpg(p.pid,signal.SIGTERM)
            except ProcessLookupError:pass
            try:p.wait(timeout=5)
            except subprocess.TimeoutExpired:pass
            # A child may ignore TERM even after make has exited.
            try:os.killpg(p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            p.wait()
            return dict(returncode=p.returncode,timed_out=True)


def inspect(archive, toolchains, host, work, compile_kernel=False):
    pins=json.loads(PINS.read_text());verify_file(archive,pins['samsung_source_archive'])
    for path in (toolchains,host,work):
        require(re.fullmatch(r'/[A-Za-z0-9_./-]+',str(path.resolve())), 'unsafe build path')
    identities={n:directory_tree(toolchains/n) for n in TREES}
    require(all(identities[n]['tree']==v for n,v in TREES.items()),'toolchain tree identity differs')
    for n,v in pins['toolchain']['executables'].items():verify_file(toolchains/'clang-r383902/bin'/n,v)
    work.mkdir(parents=True,exist_ok=False);source=work/'source';source.mkdir();logs=work/'logs';logs.mkdir()
    with tarfile.open(archive,'r:gz') as t:t.extractall(source,filter='data')
    baseline=(source/CONFIG).read_text()
    require('export SEC_BUILD_CONF_VENDOR_BUILD_OS=15' in (source/'build_kernel.sh').read_text(), 'vendor OS source setting differs')
    env=dict(PATH=':'.join([str(host/'usr/bin'),str(toolchains/'clang-r383902/bin'),
        str(toolchains/'aarch64-android49/bin'),str(toolchains/'arm-android49/bin'),os.defpath]),
        LC_ALL='C',ARCH='arm64',PLATFORM_VERSION='11',ANDROID_MAJOR_VERSION='r',
        SEC_BUILD_CONF_VENDOR_BUILD_OS='15',BISON_PKGDATADIR=str(host/'usr/share/bison'),
        M4=str(host/'usr/bin/m4'),LD_LIBRARY_PATH=str(host/'usr/lib/x86_64-linux-gnu'),
        KBUILD_BUILD_USER='s21-a0',KBUILD_BUILD_HOST='offline',KBUILD_BUILD_VERSION='1',
        KBUILD_BUILD_TIMESTAMP='Sun Nov 1 00:00:00 UTC 2026')
    common=['make','-C',str(source),'ARCH=arm64','LLVM=1','HOSTCC=gcc','HOSTCXX=g++',
        'CROSS_COMPILE='+str(toolchains/'aarch64-android49/bin/aarch64-linux-android-'),
        'CROSS_COMPILE_COMPAT='+str(toolchains/'arm-android49/bin/arm-linux-androideabi-'),
        'CLANG_TRIPLE=aarch64-linux-gnu-','HOSTCFLAGS=-I'+str(host/'usr/include'),
        'HOSTLDFLAGS=-L'+str(host/'usr/lib/x86_64-linux-gnu')]
    def make(out, targets, name, extra=(), custom_env=None, timeout=180):
        args=common+['O='+str(out),'-j4']+list(extra)+targets
        result=run(args,custom_env or env,logs/(name+'.log'),timeout)
        result['log_sha256']=digest((logs/(name+'.log')).read_bytes())
        return result
    report=dict(schema='S21-CAPTURE-A0-BUILD-PROFILE-v2',
        source_archive_sha256=pins['samsung_source_archive']['sha256'],toolchain_trees=identities,
        stages={},profiles={},a0_complete=False,module_abi_established=False,physical_action=False)
    def save():
        tmp=work/'report.tmp';tmp.write_text(json.dumps(report,indent=2)+'\n');tmp.replace(work/'report.json')
    def success(result):return result['returncode']==0 and not result['timed_out']
    out=work/'complete'
    for name,extra in [('complete',()),('gnu_ld',('LD='+str(toolchains/'aarch64-android49/bin/aarch64-linux-android-ld'),)),('no_compat',('CROSS_COMPILE_COMPAT=',))]:
        dest=work/name;r=make(dest,['exynos2100-p3sxxx_defconfig'],name,extra)
        report['stages'][name]=r;require(success(r),'defconfig failed: '+name)
        report['profiles'][name]=profile(baseline,(dest/'.config').read_text());save()
    no_os=dict(env);no_os.pop('SEC_BUILD_CONF_VENDOR_BUILD_OS')
    report['stages']['no_vendor_os']=make(work/'no_vendor_os',['exynos2100-p3sxxx_defconfig'],'no_vendor_os',custom_env=no_os)
    require(not success(report['stages']['no_vendor_os']),'missing vendor OS was not refused')
    require(not report['stages']['no_vendor_os']['timed_out'] and
            'drivers/gpu/arm/Kconfig' in (logs/'no_vendor_os.log').read_text(),
            'missing vendor OS control failed for a different reason')
    require(report['profiles']['complete']['critical_profile_preserved'],'critical profile lost')
    require(not report['profiles']['gnu_ld']['critical_profile_preserved'] and
            not report['profiles']['no_compat']['critical_profile_preserved'],'negative controls did not lose profile')
    report['stages']['prepare']=make(out,['prepare'],'prepare');save()
    require(success(report['stages']['prepare']),'prepare failed')
    report['prepared_vdsos']={name:vdso((out/('arch/arm64/kernel/'+name+'/vdso.so.dbg')).read_bytes(),klass,machine)
        for name,klass,machine in [('vdso',2,183),('vdso32',1,40)]}
    report['stages']['module_object']=make(out,['kernel/module.o'],'module_object')
    require(success(report['stages']['module_object']),'module.o failed')
    stock=json.loads((PINS.parent/'capture-a0-modules-hzc2.json').read_text())
    report['module_c_partial_versions']=partial_versions((out/'kernel/module.o.symversions').read_bytes(),stock['requirements'])
    targets=['drivers/misc/tui/stui_inf.o','drivers/misc/tui/platforms/exynos2100/stui_hal_display.o']
    report['stages']['tui_original']=make(out,targets,'tui_original')
    require(not success(report['stages']['tui_original']),'expected original TUI failure absent')
    tui_log=(logs/'tui_original.log').read_text()
    require(not report['stages']['tui_original']['timed_out'] and all(
        "'"+header+"' file not found" in tui_log
        for header in ('tee_client_api.h','dynamic_mipi/band_info.h')),
        'original TUI control failed for a different reason')
    p=source/'drivers/misc/tui/Makefile';before=p.read_bytes();after=patch_tui(before);p.write_bytes(after)
    report['tui_patch']=dict(before_sha256=digest(before),after_sha256=digest(after))
    report['stages']['tui_patched']=make(out,targets,'tui_patched')
    require(success(report['stages']['tui_patched']),'patched TUI targets failed')
    report['full_build_requested']=compile_kernel;report['full_build_completed']=False
    report['candidate_comparison']=dict(supplied=False,crc_coverage_passed=False,module_abi_established=False)
    save()
    if compile_kernel:
        report['stages']['full_build']=make(out,['vmlinux','modules'],'full_build',timeout=1800)
        report['full_build_completed']=success(report['stages']['full_build'])
        if report['full_build_completed']:
            report['vmlinux_sha256']=digest((out/'vmlinux').read_bytes())
            report['candidate_comparison']=compare_symvers(stock['requirements'],(out/'Module.symvers').read_text())
            report['built_module_count']=sum(1 for _ in out.rglob('*.ko'))
        save()
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('source','toolchains','host-root','work-dir'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--compile',action='store_true')
    a=p.parse_args()
    try:r=inspect(a.source.resolve(),a.toolchains.resolve(),a.host_root.resolve(),a.work_dir.resolve(),a.compile)
    except (OSError,ValueError,tarfile.TarError,subprocess.SubprocessError) as exc:p.exit(1,'BUILD PROFILE REFUSED: '+str(exc)+'\n')
    print('Profile preserved:',r['profiles']['complete']['critical_profile_preserved'], '; full build:',r['full_build_completed'])
    print('A0 remains open; see report.json for CRC coverage and limits')
    return 2


if __name__ == '__main__':raise SystemExit(main())
