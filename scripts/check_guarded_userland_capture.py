#!/usr/bin/env python3
from pathlib import Path
import tempfile,shutil,json,struct,sys,hashlib,dataclasses
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.verify_guarded_userland import verify
from lab.xnu import boot_contract as c,efi_memory as memory
import argparse
p=argparse.ArgumentParser(description='Recheck four semantic mutations of a guarded boot capture, with hashes updated.')
p.add_argument('--run',type=Path,required=True);p.add_argument('--kernel',type=Path,required=True);args=p.parse_args()
work=args.run;kernel=args.kernel
verify(work,kernel)
source=work/('report.json' if (work/'report.json').exists() else 'status.json');baseline=json.loads(source.read_text())
sha=lambda x:hashlib.sha256(x).hexdigest()
result={}
expected={'cmdline':'captured command line differs from typed profile','root-role':'resident image is not the declared md0','headroom':'insufficient userland dynamic tail','ownership':'UEFI ownership missing at handoff'}
for case in ('cmdline','root-role','headroom','ownership'):
 with tempfile.TemporaryDirectory() as folder:
  out=Path(folder);data=json.loads(json.dumps(baseline));cap=data['contract']
  for name in ('boot-args.bin','apple-tree.bin','resident-header.bin',*[x+'.bin' for x in cap['physical_reads']]):shutil.copyfile(work/name,out/name)
  if case in ('cmdline','headroom'):
   boot=c.BootArgs.decode((out/'boot-args.bin').read_bytes())
   if case=='cmdline':boot=dataclasses.replace(boot,cmdline=boot.cmdline.replace('cpus=1','cpus=8'))
   else:boot=dataclasses.replace(boot,top=boot.phys_base+boot.mem_size-0x30000000)
   raw=boot.encode();(out/'boot-args.bin').write_bytes(raw);cap['boot_args_sha256']=sha(raw)
  elif case=='root-role':
   tree=c.decode_tree((out/'apple-tree.bin').read_bytes());props=tree.at('/chosen/memory-map').properties
   props['RAMDisk'],props['RAMDisk1']=props['RAMDisk1'],props['RAMDisk'];raw=c.encode_tree(tree);(out/'apple-tree.bin').write_bytes(raw);cap['tree_sha256']=sha(raw)
  else:
   raw=bytearray((out/'s21_maps.bin').read_bytes());offset=3*(memory.CAPACITY+40);size,stride=struct.unpack_from('<2Q',raw,offset+memory.CAPACITY)
   for index in range(0,size,stride):
    kind,=struct.unpack_from('<I',raw,offset+index);base,virtual,pages=struct.unpack_from('<3Q',raw,offset+index+8)
    if kind==2 and base<=0xfc000000<base+pages*4096:
     struct.pack_into('<I',raw,offset+index,4);break
   else:raise AssertionError('resident descriptor missing')
   (out/'s21_maps.bin').write_bytes(raw);cap['physical_reads']['s21_maps']['sha256']=sha(raw)
  (out/'report.json').write_text(json.dumps(data))
  try:verify(out,kernel)
  except c.ContractError as exc:
   if str(exc)!=expected[case]:raise
   result[case]={'rejected':True,'reason':str(exc),'checksums_updated':True}
  else:raise AssertionError('mutated capture accepted: '+case)
print(json.dumps({'source_run':work.name,'entry_capture_only':True,'controls':result},indent=2))
