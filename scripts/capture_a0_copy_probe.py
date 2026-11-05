#!/usr/bin/env python3
"""Bounded copy observations, with no claim of writer identity from inotify."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import resource
import select
import struct
import threading
import time

from capture_a0_formats import digest, require
from capture_a0_inputs import read_checked

DHD_PIN=dict(bytes=51582680,sha256='8b35af1011201872809d2679fc1f23ed75498ed21019fcc0a4c4160e561a78fd')


def stat_record(info):
    return dict(device=info.st_dev,inode=info.st_ino,bytes=info.st_size,
        mtime_ns=info.st_mtime_ns,ctime_ns=info.st_ctime_ns)


def observe(path,expected):
    started=time.monotonic_ns()
    with path.open('rb') as file:
        before=stat_record(os.fstat(file.fileno()));data=file.read(len(expected)+1)
        after=stat_record(os.fstat(file.fileno()))
    try: named=stat_record(path.stat())
    except FileNotFoundError:named=None
    return dict(monotonic_ns=started,read_completed_monotonic_ns=time.monotonic_ns(),
        bytes=len(data),sha256=digest(data),matches=data==expected,
        is_expected_prefix=bool(data) and len(data)<len(expected) and expected.startswith(data),
        descriptor_before=before,descriptor_after=after,named_object_after=named,
        identity_stable_during_read=before==after and after==named),data


def decode_events(raw):
    result=[];position=0
    while position<len(raw):
        require(position+16<=len(raw),'short inotify event header')
        wd,mask,cookie,size=struct.unpack_from('iIII',raw,position);position+=16
        require(position+size<=len(raw),'short inotify event name')
        name=raw[position:position+size].split(b'\0',1)[0].decode(errors='replace');position+=size
        result.append(dict(watch=wd,mask=mask,cookie=cookie,name=name))
    return result


class Watch:
    def __init__(self,directory):
        self.rows=[];self.error=None;self.fd=-1;self.closed=False
        self.stop=threading.Event();self.thread=None
        lib=ctypes.CDLL(None,use_errno=True)
        try:
            self.fd=lib.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
            if self.fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
            self.add=lib.inotify_add_watch
            self.add.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32]
            self.mask=0x2|0x4|0x8|0x40|0x80|0x100|0x200|0x400|0x800
            if self.add(self.fd,os.fsencode(directory),self.mask)<0:
                raise OSError(ctypes.get_errno(),'inotify directory watch')
            self.thread=threading.Thread(target=self.collect,daemon=True);self.thread.start()
        except (OSError,AttributeError) as exc:self.error=str(exc)

    def file(self,path):
        if self.error is None and self.add(self.fd,os.fsencode(path),self.mask)<0:
            self.error=str(OSError(ctypes.get_errno(),'inotify file watch'))

    def collect(self):
        try:
            while not self.stop.is_set():
                if not select.select([self.fd],[],[],0.05)[0]:continue
                for row in decode_events(os.read(self.fd,65536)):
                    self.rows.append(dict(monotonic_ns=time.monotonic_ns(),**row))
        except OSError as exc:self.error=str(exc)

    def finish(self):
        # Drain one final bounded interval before reporting a complete window.
        time.sleep(0.1);self.stop.set()
        if self.thread:self.thread.join(timeout=1)
        if self.fd>=0:os.close(self.fd)
        self.closed=True
        return dict(events=self.rows,error=self.error,observation_completed=self.error is None,
            queue_overflow_observed=any(r['mask']&0x4000 for r in self.rows),writer_pid_attributed=False)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('source','target','report'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--pause',type=float,default=0.06)
    p.add_argument('--observe-seconds',type=float,default=7)
    a=p.parse_args();require(0<=a.pause<=0.1 and 0<a.observe_seconds<=15,'probe timing bounds')
    source=read_checked(a.source,DHD_PIN);require(not a.target.exists() and not a.report.exists(),'probe output must be new')
    a.target.parent.mkdir(parents=True,exist_ok=True);a.report.parent.mkdir(parents=True,exist_ok=True)
    watch=Watch(a.target.parent);writes=[];started=time.monotonic_ns()
    try:
        with a.target.open('xb') as file:
            watch.file(a.target)
            for offset in range(0,len(source),1024*1024):
                chunk=source[offset:offset+1024*1024];count=file.write(chunk)
                require(count==len(chunk),'probe short write');file.flush()
                writes.append(dict(monotonic_ns=time.monotonic_ns(),offset=offset,bytes=count))
                time.sleep(a.pause)
            os.fsync(file.fileno())
        closed=time.monotonic_ns();immediate,_=observe(a.target,source)
        print(json.dumps(dict(phase='immediate',**immediate)),flush=True)
        time.sleep(a.observe_seconds)
        later,bad=observe(a.target,source)
    finally:events=watch.finish()
    refused=None
    if not later['matches']:
        refused=a.report.with_suffix('.refused-prefix.bin')
        with refused.open('xb') as file:require(file.write(bad)==len(bad),'refused snapshot short write')
    record=dict(schema='S21-A0-COPY-PAIRED-PROBE-v1',input=DHD_PIN,pid=os.getpid(),
        write_started_monotonic_ns=started,write_closed_monotonic_ns=closed,writes=writes,
        immediate=immediate,later=later,inotify=events,rlimit_fsize=list(resource.getrlimit(resource.RLIMIT_FSIZE)),
        refused_snapshot=refused.name if refused else None,underlying_writer_identified=False,
        historical_mali_cause_attributed=False)
    a.report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(dict(phase='later',**later)),flush=True)


if __name__=='__main__':main()
