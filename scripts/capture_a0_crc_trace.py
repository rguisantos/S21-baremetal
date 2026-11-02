#!/usr/bin/env python3
"""Read-only sampling of CRC producers and LTO aggregates during a native build."""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import threading
import time

from capture_a0_formats import require

SYMBOLS = ('nf_conntrack_destroy','nf_register_net_hooks','nf_unregister_net_hooks',
           'ieee80211_rx_irqsafe','ieee80211_rx_napi','ieee80211_sta_ps_transition')
PATHS = ('net/netfilter/core.o.symversions','net/mac80211/rx.o.symversions',
         'net/netfilter/netfilter.o.symversions','net/netfilter/built-in.a.symversions',
         'net/mac80211/mac80211.o.symversions','net/mac80211/built-in.a.symversions',
         'net/built-in.a.symversions','.tmp_lto.lds','Module.symvers')
MAX_BYTES = 16*1024*1024


def assignments(data):
    """Only report observed values of the six names; never choose a duplicate."""
    text=data.decode('utf-8',errors='replace');found=defaultdict(set)
    names='('+'|'.join(map(re.escape,SYMBOLS))+')'
    for name,crc in re.findall(r'\b__crc_'+names+r'\s*=\s*(0x[0-9a-fA-F]{1,8})\s*;',text):
        found[name].add(f'0x{int(crc,16):08x}')
    for crc,name in re.findall(r'^(0x[0-9a-fA-F]{8})\s+'+names+r'\s+\S+\s+EXPORT_\S+',text,re.M):
        found[name].add(crc.lower())
    return {name:sorted(values) for name,values in sorted(found.items())}


def identity(s):
    return s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns


def snapshot(path):
    """Bound reads and reject links/special files, including replacement races."""
    try:
        before=path.lstat()
        if not stat.S_ISREG(before.st_mode):return dict(state='non_regular')
        if before.st_size>MAX_BYTES:return dict(state='oversized',bytes=before.st_size)
        fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        with os.fdopen(fd,'rb') as f:
            opened=os.fstat(f.fileno())
            if not stat.S_ISREG(opened.st_mode) or identity(before)!=identity(opened):
                return dict(state='unstable')
            data=f.read(MAX_BYTES+1);after=os.fstat(f.fileno())
        # A rename after opening must not masquerade as the current path.
        current=path.lstat()
        if len(data)>MAX_BYTES or identity(opened)!=identity(after) or identity(after)!=identity(current):
            return dict(state='unstable')
        return dict(state='regular',bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),
                    mtime_ns=after.st_mtime_ns,inode=after.st_ino,assignments=assignments(data))
    except FileNotFoundError:return dict(state='missing')
    except OSError as exc:return dict(state='read_error',errno=exc.errno)


class VersionTrace:
    """Sampler, not an exhaustive write trace; no source/build file is modified."""
    def __init__(self, output, log, interval=.1, limit=4096, progress=False):
        require(.01<=interval<=10 and 1<=limit<=100000,'trace bounds')
        self.output=Path(output);self.log=Path(log);self.interval=interval;self.limit=limit
        require(not self.log.resolve().is_relative_to(self.output.resolve()),
                'trace log must be outside the object tree')
        self.progress=progress;self.events=[];self.last={};self.limit_reached=False
        self.stop_event=threading.Event();self.worker=None;self.stream=None
        self.failure=None;self.started=None;self.last_sample=None;self.max_gap=0.;self.next_progress=0.

    def sample(self):
        now=time.monotonic()
        if self.last_sample is not None:self.max_gap=max(self.max_gap,now-self.last_sample)
        self.last_sample=now
        for name in PATHS:
            value=snapshot(self.output/name)
            if self.last.get(name)==value:continue
            self.last[name]=value
            if len(self.events)>=self.limit:self.limit_reached=True;continue
            event=dict(seconds=round(time.monotonic()-self.started,3),path=name,**value)
            self.events.append(event);self.stream.write(json.dumps(event,sort_keys=True)+'\n');self.stream.flush()
        elapsed=now-self.started
        if self.progress and elapsed>=self.next_progress:
            states=[]
            for name in PATHS[:2]:
                row=self.last[name];states.append(name+': '+str(row.get('bytes',row['state']))+
                    ' bytes/'+str(len(row.get('assignments',{})))+' CRC names')
            states.append('LTO script: '+str(self.last['.tmp_lto.lds'].get('bytes','absent')))
            states.append('Module.symvers: '+str(self.last['Module.symvers'].get('bytes','absent')))
            objects=sum(1 for _ in self.output.rglob('*.o'))
            print(f'CRC TRACE {elapsed:.0f}s, objects={objects}: '+ '; '.join(states),flush=True)
            self.next_progress=elapsed+60

    def _observe(self):
        try:
            while not self.stop_event.wait(self.interval):self.sample()
        except Exception as exc:self.failure=type(exc).__name__

    def __enter__(self):
        require(self.worker is None,'trace cannot be reused')
        self.stream=self.log.open('x',encoding='utf-8');self.started=time.monotonic()
        try:
            self.sample();self.worker=threading.Thread(target=self._observe,daemon=True);self.worker.start()
        except BaseException:self.stream.close();raise
        return self

    def __exit__(self,*exc):
        self.stop_event.set();self.worker.join(timeout=10)
        require(not self.worker.is_alive(),'CRC sampler did not stop')
        try:
            if self.failure is None:self.sample()
        finally:self.stream.close()
        return False

    def summary(self):
        require(self.worker is not None and not self.worker.is_alive() and self.stream.closed,
                'trace summary requires stopped sampler')
        return dict(schema='S21-CAPTURE-A0-CRC-TRACE-v1',interval_seconds=self.interval,
            max_sample_gap_seconds=round(self.max_gap,3),event_limit_reached=self.limit_reached,
            observer_error=self.failure,transitions_between_samples_may_be_missed=True,
            log_sha256=hashlib.sha256(self.log.read_bytes()).hexdigest(),events=self.events,
            final=self.last,source_modified_by_observer=False,module_abi_established=False)
