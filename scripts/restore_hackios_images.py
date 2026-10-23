#!/usr/bin/env python3
"""Reassemble a private APFS checkpoint and verify every part and full image."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def restore(manifest,directory,out):
    data=json.loads(manifest.read_text())
    if data.get('schema_version')!=1:raise ValueError('unsupported checkpoint version')
    out.mkdir(parents=True,exist_ok=False);results={}
    for role in ('root','system'):
        info=data['images'][role];parts=info.get('parts',[info]);total=0;full=hashlib.sha256()
        target=out/(role+'.apfs');pending=target.with_suffix('.apfs.partial')
        try:
            with pending.open('wb') as dst:
                for part in parts:
                    name=part['file_name']
                    if name!=Path(name).name or name in ('.','..'):raise ValueError('unsafe part filename')
                    path=directory/name;hasher=hashlib.sha256();size=0
                    with path.open('rb') as src:
                        for block in iter(lambda:src.read(8<<20),b''):
                            dst.write(block);hasher.update(block);full.update(block);size+=len(block)
                    if size!=part['bytes'] or hasher.hexdigest()!=part['sha256']:raise ValueError('corrupt checkpoint part: '+name)
                    total+=size
            if total!=info['bytes'] or full.hexdigest()!=info['sha256']:raise ValueError('complete image digest mismatch: '+role)
            with pending.open('rb') as stream:stream.seek(32);magic=stream.read(4)
            if magic!=b'NXSB':raise ValueError('checkpoint is not APFS')
            pending.rename(target);results[role]={'bytes':total,'sha256':full.hexdigest(),'path':str(target)}
        except Exception:
            if pending.exists():pending.unlink()
            raise
    (out/'restore-report.json').write_text(json.dumps({'verified':True,'images':results},indent=2)+'\n')
    return results


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True);p.add_argument('--directory',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    try:print(json.dumps(restore(args.manifest,args.directory,args.out),indent=2))
    except (OSError,ValueError,KeyError) as exc:p.exit(2,'Checkpoint error: '+str(exc)+'\n')
