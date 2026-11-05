#!/usr/bin/env python3
"""Run pinned AOSP dependency resolution on stock controls with a fake backend.

No Android init, kernel module, syscall loader or device operation is executed.
Only the upstream C++ resolver runs, with declared host adapters below.
"""
import argparse
import json
from pathlib import Path
import re
import stat
import subprocess

from capture_a0_formats import digest, layout, require
from capture_a0_inputs import read_checked, sealed_input
from capture_a0_modules import cpio, gunzip

ROOT=Path(__file__).resolve().parents[1]
COMMIT='6072de17cd812daf238092695f26a552d3122f8c'
SOURCE_PINS={
    'libmodprobe.cpp':dict(bytes=15997,sha256='ae0e51e9827fe9293918f4e83bbc7ee9baf251e4423a39e52ca0699adfcad5f1'),
    'modprobe.h':dict(bytes=3301,sha256='399ca3a67d7106c8a1ef713107e8e98dce5e87d1fe514557ed4f5a27a553ef40')}
CONTROLS=('modules.alias','modules.dep','modules.softdep','modules.load','modules.options','modules.blocklist')

PREAMBLE=r'''
#include <algorithm>
#include <cstring>
#include <fnmatch.h>
#include <functional>
#include <iostream>
#include <map>
#include <set>
#include <string>
#include <unordered_map>
#include <unordered_set>
#include <vector>
static std::map<std::string,std::string> controls;
static std::string failure;
struct NullLog { template<class T> NullLog& operator<<(const T&) { return *this; } };
#define LOG(level) NullLog()
namespace android { namespace base {
enum { INFO, VERBOSE };
inline void SetMinimumLogSeverity(int) {}
inline bool EndsWith(const std::string& s,const std::string& tail) {
 return s.size()>=tail.size() && s.compare(s.size()-tail.size(),tail.size(),tail)==0;
}
inline bool ReadFileToString(const std::string& path,std::string* out,bool=false) {
 auto it=controls.find(path); if(it==controls.end()) return false; *out=it->second; return true;
}
inline std::vector<std::string> Split(const std::string& s,const std::string& separators) {
 std::vector<std::string> out; size_t start=0;
 while(true) { auto at=s.find_first_of(separators,start); out.push_back(s.substr(start,at-start));
 if(at==std::string::npos) return out; start=at+1; }
}
}}
'''

BACKEND=r'''
std::string Modprobe::GetKernelCmdline() { return ""; }
bool Modprobe::Rmmod(const std::string&) { return false; }
bool Modprobe::ModuleExists(const std::string& name) {
 if(blocklist_enabled && module_blocklist_.count(name)) return false;
 return !GetDependencies(name).empty(); // stock path presence is checked in Python
}
bool Modprobe::Insmod(const std::string& path,const std::string&) {
 auto name=MakeCanonical(path);
 if(module_loaded_.count(name)) {
  std::cout << "ATTEMPT " << name << " existing\n"; return true;
 }
 bool ok=name!=failure;
 std::cout << "ATTEMPT " << name << " " << (ok?"success":"failure") << "\n";
 if(!ok) return false;
 module_loaded_.insert(name); ++module_count_; return true;
}
'''


def pin(data):return dict(bytes=len(data),sha256=digest(data))


def literal(data):
    require(type(data) is bytes and len(data)<=1024*1024,'C++ literal input budget')
    return 'std::string("'+''.join('\\x%02x'%v for v in data)+'",'+str(len(data))+')'


def strip_includes(data):
    # Only include directives / pragma once are adapted; resolver bodies stay
    # byte-for-byte as supplied by the pinned upstream files.
    return '\n'.join(line for line in data.decode().splitlines()
                     if not line.startswith(('#include ', '#pragma once')))


def translation_unit(sources,controls):
    require(set(sources)==set(SOURCE_PINS),'source set differs')
    require(set(controls)<=set(CONTROLS),'unexpected control file name')
    for name,p in SOURCE_PINS.items():
        from capture_a0_inputs import checked_buffer
        checked_buffer(sources[name],p)
    assignments='\n'.join('controls["/lib/modules/'+name+'"]='+literal(data)+';'
                           for name,data in sorted(controls.items()))
    main='''
int main(int argc,char** argv) {
 if(argc>1) failure=argv[1];
 %s
 Modprobe loader({"/lib/modules"});
 loader.EnableBlocklist(true);
 bool ok=loader.LoadListedModules(true);
 std::cout << "RESULT " << (ok?"success":"failure") << " " << loader.GetModuleCount() << "\\n";
 return 0;
}
'''%assignments
    return (PREAMBLE+strip_includes(sources['modprobe.h'])+'\n'+
            strip_includes(sources['libmodprobe.cpp'])+BACKEND+main).encode()


def parse_trace(text):
    attempts=[];result=None
    for line in text.splitlines():
        require(result is None,'trace after final result')
        m=re.fullmatch(r'ATTEMPT ([A-Za-z0-9_]+) (success|failure|existing)',line)
        if m:attempts.append(dict(module=m[1],outcome=m[2]));continue
        m=re.fullmatch(r'RESULT (success|failure) ([0-9]+)',line)
        require(m is not None and result is None,'unexpected native trace')
        result=dict(success=m[1]=='success',count=int(m[2]))
    require(result is not None and result['count']==sum(r['outcome']=='success' for r in attempts),'native count/result differs')
    return dict(**result,attempts=attempts)


def replay(vendor,source_dir,output):
    require(not output.exists(),'output directory must be new')
    pins=json.loads((ROOT/'docs/references/capture-a0-pins-hzc2.json').read_text())
    raw=read_checked(vendor,pins['stock_raw']['vendor_boot.img'])
    part=next(p for p in layout(raw)['parts'] if p['name']=='ramdisk')
    entries=cpio(gunzip(raw[part['start']:part['end']]))
    controls={}
    for name in CONTROLS:
        path='lib/modules/'+name
        if path not in entries:continue
        require(entries[path]['kind']==stat.S_IFREG,'control file must be regular')
        controls[name]=entries[path]['data']
    # Constrain the native backend's path-presence adapter to the actual stock
    # files. Duplicate/missing/cyclic dependency tables are refused separately.
    from check_capture_a0_load_plan import inspect as load_audit
    require(load_audit(vendor)['result']['control_files_checks_passed'] is True,'stock structural checks failed')
    sources={name:read_checked(source_dir/name,p) for name,p in SOURCE_PINS.items()}
    unit=translation_unit(sources,controls);output.mkdir(parents=True)
    binary=(output/'resolver').resolve()
    with sealed_input(unit,pin(unit)) as(fd,path):
        build=subprocess.run(['g++','-std=c++17','-O1','-include','string.h','-x','c++',path,'-o',str(binary)],
            pass_fds=(fd,),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=90)
    (output/'build.log').write_bytes(build.stdout);require(build.returncode==0,'host resolver compilation failed')
    runs={}
    for name,failure in [('all_success',''),('first_listed_failure','dss'),('later_module_failure','exynos_acme')]:
        command=[str(binary)]+([failure] if failure else [])
        r=subprocess.run(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=30)
        (output/(name+'.stdout')).write_bytes(r.stdout);(output/(name+'.stderr')).write_bytes(r.stderr)
        require(r.returncode==0,'native resolver crashed or failed')
        runs[name]=parse_trace(r.stdout.decode())
    require(runs['all_success']['success'] and runs['all_success']['count']==274,'all-success coverage differs')
    require(not runs['first_listed_failure']['success'] and runs['first_listed_failure']['count']==0,
        'first listed failure did not stop strict listed loading')
    require(not runs['later_module_failure']['success'],'later explicit target failure not propagated')
    def canonical(path):return path.rsplit('/',1)[-1].removesuffix('.ko').replace('-','_')
    table={}
    for line in controls['modules.dep'].decode().splitlines():
        name,tail=line.split(':',1);table[canonical(name)]=[canonical(p) for p in tail.split()]
    order=[a['module'] for a in runs['all_success']['attempts'] if a['outcome']=='success']
    require(len(order)==len(set(order))==len(table),'success set differs from dependency keys')
    rank={n:i for i,n in enumerate(order)}
    require(all(rank[d]<rank[n] for n,ds in table.items() for d in ds),'hard dependency order violation')
    soft_targets=[];soft_lines=[]
    for line in controls.get('modules.softdep',b'').decode().splitlines():
        if not line or line.startswith('#'):continue
        soft_lines.append(line);fields=line.split();phase=None
        for token in fields[2:]:
            if token in ('pre:','post:'):phase=token[:-1];continue
            soft_targets.append(dict(module=fields[1],phase=phase,target=token,
                direct_dep_key_present=canonical(token) in table))
    result=dict(schema='S21-A0-MODPROBE-HOST-REPLAY-v1',source_commit=COMMIT,source_pins=SOURCE_PINS,
        stock_vendor_boot=pins['stock_raw']['vendor_boot.img'],control_pins={n:pin(b) for n,b in controls.items()},
        absent_controls=sorted(set(CONTROLS)-controls.keys()),translation_unit=pin(unit),runs=runs,
        stock_controls_summary=dict(alias_rules=sum(line.startswith(b'alias ') for line in controls.get('modules.alias',b'').splitlines()),
            softdep_statements=len(soft_lines),softdep_targets=soft_targets,
            hard_dependency_edges=sum(map(len,table.values())),
            all_hard_dependencies_precede_consumers_in_success_model=True),
        assumptions=dict(backend='fake Insmod: success for new modules, EEXIST-equivalent for repeated modules, failure for injected canonical name',kernel_cmdline='',
            blocklist_enabled=True,strict_list=True,regular_path_presence='stock structural validation',
            readfile='map of checked embedded control buffers',logging='no-op',compiler_input_sealed=True),
        android_init_executed=False,kernel_modules_loaded=False,device_accessed=False,
        samsung_binary_equivalence_proven=False,real_init_order_observed=False,a0_complete=False)
    (output/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('vendor-boot','source-dir','output-dir'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    try:r=replay(a.vendor_boot,a.source_dir,a.output_dir)
    except (OSError,ValueError,KeyError,subprocess.SubprocessError) as e:p.exit(1,'HOST REPLAY REFUSED: '+str(e)+'\n')
    print('AOSP reference host replay: all-success',r['runs']['all_success']['count'],'modules; two failure controls PASS')


if __name__=='__main__':main()
