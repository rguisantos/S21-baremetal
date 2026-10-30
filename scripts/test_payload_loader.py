#!/usr/bin/env python3
"""Run one-CPU QEMU firmware -> S21R10 container -> production R10 main.
GDB observes memory before handoff and after real timer IRQs. No phone access.
"""
import os
from pathlib import Path
import signal
import select
import struct
import subprocess
import tempfile
import time
ROOT=Path(__file__).resolve().parent.parent

class Remote:
    def __init__(self,reader,writer):
        self.reader,self.writer=reader,writer
        self.buffer=b'';self.offset=0
        self.command('?')
    def write_packet(self,data):
        self.writer.write(data);self.writer.flush()
    def byte(self):
        if self.offset==len(self.buffer):
            if not select.select([self.reader],[],[],10)[0]:raise TimeoutError('GDB pipe timeout')
            self.buffer=os.read(self.reader.fileno(),4096);self.offset=0
            if not self.buffer:raise RuntimeError('GDB disconnected')
        b=self.buffer[self.offset:self.offset+1];self.offset+=1
        return b
    def send(self,message):
        data=message.encode();self.write_packet(b'$'+data+b'#'+f'{sum(data)%256:02x}'.encode())
    def receive(self):
        while self.byte()!=b'$':pass # ACKs may precede a reply/stop packet.
        data=bytearray()
        while True:
            c=self.byte()
            if c==b'#':break
            data+=c
        checksum=self.byte()+self.byte()
        assert int(checksum,16)==sum(data)%256,'GDB checksum mismatch'
        self.write_packet(b'+');return data.decode()
    def command(self,message):
        self.send(message);return self.receive()
    def resume(self):self.send('c')
    def stop(self):
        self.write_packet(b'\x03');return self.receive()
    def read(self,address,size):
        out=bytearray()
        for offset in range(0,size,1024):
            n=min(1024,size-offset);reply=self.command(f'm{address+offset:x},{n:x}')
            assert len(reply)==2*n,reply
            out+=bytes.fromhex(reply)
        return bytes(out)
    def write(self,address,data):
        for offset in range(0,len(data),512):
            part=data[offset:offset+512]
            assert self.command(f'M{address+offset:x},{len(part):x}:{part.hex()}')=='OK'
    def integer(self,address,size=4):return int.from_bytes(self.read(address,size),'little')
    def close(self):self.writer.close();self.reader.close()

def symbols(elf):
    listing=subprocess.check_output(['readelf','-sW',str(elf)],text=True,
                                    env=dict(os.environ,LC_ALL='C'))
    # Identify numbered symbol rows, never translated column headings.
    return {fields[-1]:int(fields[1],16) for line in listing.splitlines()
            if len(fields:=line.split())>=8 and fields[0].endswith(':')
            and fields[0][:-1].isdigit()}

def expected_memory(elf,blob):
    # Independently read ELF PT_LOADs, not the C consumer's plan.
    _,_,_,_,entry,phoff,_,_,_,phsize,count,*_=struct.unpack_from('<16sHHIQQQIHHHHHH',elf)
    base,wire_entry,dt_off,dt_size,end,physical,size=struct.unpack_from('<7Q',blob,16)
    assert base==physical and entry==wire_entry
    memory=bytearray(size)
    for i in range(count):
        kind,_,off,va,_,filesz,memsz,_=struct.unpack_from('<II6Q',elf,phoff+i*phsize)
        if kind==1 and memsz:memory[va-base:va-base+filesz]=elf[off:off+filesz]
    memory[end-base:end-base+dt_size]=blob[dt_off:dt_off+dt_size]
    return base,end,dt_off,dt_size,bytes(memory)

def main():
    with tempfile.TemporaryDirectory(prefix='r10-loader-') as directory:
        td=Path(directory);build=td/'arm'
        subprocess.run(['make','-C',str(ROOT/'r8'),f'BUILD={build}',str(build/'r10_loader_test.elf')],
                       check=True,stdout=subprocess.DEVNULL)
        loader=symbols(build/'r10_loader_test.elf');target=symbols(build/'r10_qemu_payload.elf')
        blob=(build/'r10_qemu.payload').read_bytes();elf=(build/'r10_qemu_payload.elf').read_bytes()
        base,end,dt_off,dt_size,memory=expected_memory(elf,blob)
        dtb=(build/'r10-test.dtb').read_bytes();reserve=struct.unpack_from('>I',dtb,16)[0]
        assert struct.unpack_from('>QQ',dtb,reserve)==(0x47f00000,4096)
        cases=[('valid',None),('bad-magic',-1),('protected-destination',-4),
               ('different-fdt',-2),('reserved-ram',-3),('wrong-el',-10)]
        for name,status in cases:
            log=td/(name+'.log');serial=td/(name+'.serial')
            with log.open('wb') as output:
                process=subprocess.Popen(['make','--silent','--no-print-directory','-C',str(ROOT/'r8'),f'BUILD={build}',
                                          f'SERIAL_LOG={serial}',
                                          'LOADER_VIRTUALIZATION='+('off' if name=='wrong-el' else 'on'),
                                          'run_r10_loader_test'],
                                         stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=output,start_new_session=True)
                remote=None
                try:
                    remote=Remote(process.stdout,process.stdin)
                    marker=b'\xa5'*len(memory);guards=b'\x77'*16
                    remote.write(base,marker);remote.write(base-16,guards)
                    remote.write(base+len(memory),guards)
                    if name=='bad-magic':remote.write(loader['loader_payload'],b'X')
                    elif name=='protected-destination':
                        remote.write(loader['loader_protected']+16,struct.pack('<QQ',base,16))
                    elif name=='different-fdt':
                        remote.write(loader['loader_payload']+dt_off+24,struct.pack('>I',17))
                    elif name=='reserved-ram':
                        reservation=struct.pack('>QQ',base,4096)
                        remote.write(loader['loader_firmware']+reserve,reservation)
                        remote.write(loader['loader_payload']+dt_off+reserve,reservation)
                    if name=='wrong-el':
                        sentinel=struct.pack('<I',0x12345678)
                        remote.write(loader['loader_status'],sentinel)
                        point=loader['loader_park']
                        assert remote.command(f'Z0,{point:x},4')=='OK'
                        reply=remote.command('c');assert reply.startswith(('T','S')),reply
                        assert int.from_bytes(bytes.fromhex(remote.command('p1')),'little')==4
                        assert remote.read(loader['loader_status'],4)==sentinel
                        assert remote.read(base,len(marker))==marker
                        assert remote.read(base-16,16)==guards
                        assert remote.read(base+len(marker),16)==guards
                        print('EL1 ENTRY REJECT PASS: before BSS clear, destination untouched')
                    elif status is None:
                        point=loader['loader_enter']
                        assert remote.command(f'Z0,{point:x},4')=='OK'
                        reply=remote.command('c');assert reply.startswith(('T','S')),reply
                        assert remote.integer(loader['loader_status'])==2
                        assert remote.integer(loader['loader_observed_el'],8)==8
                        assert remote.read(base,len(memory))==memory,'loaded bytes/BSS/stack extent mismatch'
                        assert remote.read(base-16,16)==guards
                        assert remote.read(base+len(memory),16)==guards
                        assert remote.command(f'z0,{point:x},4')=='OK'
                        print('EL2 MATERIALIZE PASS: exact PT_LOADs, BSS, stacks, FDT and guards')
                        limit=time.monotonic()+5
                        while True:
                            remote.resume();time.sleep(.03);remote.stop()
                            boot=remote.integer(target['r10_boot_status'])
                            ticks=remote.integer(target['r10_timer_ticks'],8)
                            if boot==1 and ticks>=5:break
                            if boot & 0x80000000 or time.monotonic()>limit:
                                raise AssertionError(f'R10 did not boot: status={boot:x}, ticks={ticks}')
                        assert remote.integer(target['g_fdt'],8)==end
                        assert remote.integer(target['r10_qemu_observed_el'],8)==4
                        assert remote.read(end,dt_size)==dtb
                        print(f'R10 CONTAINER HANDOFF PASS: production main at EL1, raw FDT, {ticks} timer IRQs')
                    else:
                        limit=time.monotonic()+5
                        while True:
                            remote.resume();time.sleep(.03);remote.stop()
                            actual=remote.integer(loader['loader_status'])
                            if actual:break
                            if time.monotonic()>limit:raise AssertionError('loader never decided')
                        assert actual==(status&0xffffffff),(name,actual,status)
                        assert remote.read(base,len(marker))==marker,'rejection changed destination'
                        assert remote.read(base-16,16)==guards
                        assert remote.read(base+len(marker),16)==guards
                        print(f'EL2 REJECT PASS: {name}, destination untouched')
                except Exception:
                    output.flush();print(log.read_text(errors='replace'))
                    if serial.exists():print(serial.read_text(errors='replace'))
                    raise
                finally:
                    if remote:remote.close()
                    if process.poll() is None:os.killpg(process.pid,signal.SIGTERM)
                    try:process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid,signal.SIGKILL);process.wait()
                assert 'R10 FATAL' not in serial.read_text(errors='replace')
        print('PAYLOAD LOADER QEMU PASS: 1 production handoff + 5 refusal cases, one CPU')
if __name__=='__main__':main()
