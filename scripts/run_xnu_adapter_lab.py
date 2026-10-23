#!/usr/bin/env python3
"""Compile and exercise the QEMU-only EFI resource consumer; no phone commands."""
import argparse
import copy
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from lab.xnu import boot_contract as c
from lab.xnu import fdt_adapter as adapter
from lab.xnu import efi_lab as efi
from lab.xnu import efi_memory as memory
from scripts import run_xnu_lab as lab
from scripts.capture_xnu_contract import Reader, ARM_INIT


def variant(tree,name):
    value=copy.deepcopy(tree)
    if name=="counter": value.at("/cpus").children[0].properties["timebase-frequency"]=adapter.le64(62500001)
    if name=="gic": value.at("/arm-io/gic").properties["reg"]=adapter.le64(0,0x10000,0xb0000,0x100000)
    raw=c.encode_tree(value)
    return raw[:-4] if name=="truncated" else raw


def run_case(work,name,loader,kernel,ramdisk,tree,resources,tools,code,vars_template,timeout):
    work.mkdir()
    (work/"esp/EFI/BOOT").mkdir(parents=True)
    shutil.copyfile(loader,work/"esp/EFI/BOOT/BOOTAA64.EFI")
    shutil.copyfile(vars_template,work/"vars.fd")
    raw=variant(tree,name)
    payload=efi.pack(kernel,ramdisk,raw)
    if name=="duplicate":
        changed=bytearray(payload)
        # adtres follows the kernel and ramdisk entries; retain all lengths.
        at=8
        for _ in range(2): at+=24+((struct.unpack_from("<I",changed,at+16)[0]+15)&~15)
        changed[at:at+16]=b"kernel".ljust(16,b"\0");payload=bytes(changed)
    if name=="kernel-bounds":
        changed=bytearray(payload);struct.pack_into("<I",changed,8+24+32+4,0);payload=bytes(changed)
    (work/"payload.bin").write_bytes(payload)
    (work/"resource.adt").write_bytes(raw)
    command=lab.tool_commands(tools)["qemu"]
    command += ["-L",str(tools/"usr/share/qemu"),"-M","virt,gic-version=3","-cpu","cortex-a76",
        "-smp","1","-m","6G","-accel","tcg,tb-size=128",
        "-drive",f"if=pflash,format=raw,readonly=on,file={code}",
        "-drive",f"if=pflash,format=raw,file={work/'vars.fd'}",
        "-drive",f"file=fat:rw:{work/'esp'},format=raw,if=virtio",
        "-device",f"loader,file={work/'payload.bin'},addr=0xF0000000,force-raw=on",
        "-display","none","-serial",f"file:{work/'serial.log'}","-monitor","none","-no-reboot","-nic","none"]
    capture=None
    with (work/"stderr.log").open("wb") as err:
        if name=="positive":
            command += ["-S","-gdb","stdio"]
            process=subprocess.Popen(command,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=err)
            try:
                reader=Reader(process,timeout)
                adapter.require(reader.command(f"Z1,{ARM_INIT:x},4")=="OK","breakpoint failed")
                reader.send("c");adapter.require(reader.packet().startswith("T05"),"unexpected stop")
                regs=bytes.fromhex(reader.command("g"));adapter.require(len(regs)>=268,"short register packet")
                x0,=struct.unpack_from("<Q",regs);pc,pstate=struct.unpack_from("<QI",regs,256)
                adapter.require(pc==ARM_INIT and (pstate&0xc)==4,"not arm_init EL1")
                raw_args=reader.memory(x0,c.BOOT_SIZE);args=c.BootArgs.decode(raw_args)
                raw_tree=reader.memory(args.tree_va,args.tree_size);actual=c.decode_tree(raw_tree)
                adapter.require(args.encode()==raw_args and c.encode_tree(actual)==raw_tree,"capture does not round-trip")
                (work/"boot-args.bin").write_bytes(raw_args);(work/"apple-tree.bin").write_bytes(raw_tree)
                capture={"pc":hex(pc),"x0_virtual":hex(x0),"pstate":hex(pstate),
                         "boot_args_sha256":efi.sha(raw_args),"tree_sha256":efi.sha(raw_tree),
                         "tree_bytes":len(raw_tree),"read_only_gdb":True}
                adapter.require(reader.command(f"z1,{ARM_INIT:x},4")=="OK","cannot remove breakpoint")
                reader.send("c");returncode=process.wait(timeout=timeout)
            finally:
                if process.poll() is None: process.kill();process.wait()
                process.stdin.close();process.stdout.close()
        else:
            returncode=subprocess.run(command,stdin=subprocess.DEVNULL,stdout=err,stderr=err,timeout=timeout).returncode
    serial=(work/"serial.log").read_bytes()
    snapshots,claims=memory.parse_serial(serial)
    for stage,snapshot in snapshots.items(): (work/f"efi-map-{stage}.bin").write_bytes(snapshot.raw)
    ownership=None
    if name=="positive":
        checked,ownership=memory.verify(snapshots,claims,args,actual,args.physical(x0,c.BOOT_SIZE).base,kernel)
        adapter.require(checked["gic"]==[[hex(x.base),hex(x.size)] for x in resources.gic],"GIC differs from input")
        adapter.require(checked["psci_method"]==resources.method and checked["cpus"]==["0x0"],"CPU/PSCI differs")
        adapter.require(c.cells(actual.at("/cpus").children[0],"timebase-frequency",1)==(resources.frequency,),"counter differs")
        adapter.require(c.cells(actual.at("/arm-io"),"ranges",3)==c.cells(tree.at("/arm-io"),"ranges",3),"I/O differs")
        adapter.require(c.cells(actual.at("/arm-io/uart0"),"reg",2)==c.cells(tree.at("/arm-io/uart0"),"reg",2),"UART differs")
        capture.update(profile=checked,resource_fields_match=True)
        checks=lab.assess_log(serial,returncode,False)
        checks.update(native_resources=b"S21 XNU ADAPTER: resources PASS" in serial,
                      native_layout=b"S21 XNU ADAPTER: layout PASS before jump" in serial,
                      no_native_rejection=b"S21 XNU ADAPTER: REJECT" not in serial and b"S21 UEFI: REJECT" not in serial,
                      native_memory_before_copy=b"S21 UEFI: ownership PASS before copy" in serial,
                      uefi_maps_and_allocations=ownership["verified"])
    else:
        reason={"truncated":b"S21 XNU ADAPTER: REJECT resources", "counter":b"S21 XNU ADAPTER: REJECT resources",
                "gic":b"S21 XNU ADAPTER: REJECT resources", "duplicate":b"S21 XNU ADAPTER: REJECT payload",
                "kernel-bounds":b"S21 XNU ADAPTER: REJECT payload",
                "uefi-payload-busy":b"S21 UEFI: REJECT payload not free",
                "uefi-window-busy":b"S21 UEFI: REJECT window ownership stage 2",
                "uefi-payload-released":b"S21 UEFI: REJECT payload ownership stage 2"}[name]
        checks={"exit_zero":returncode==0,"rejected":reason in serial,
                "no_jump":b"jumping to " not in serial,"no_kernel_copy":b"kernel loaded at pa" not in serial,
                "no_darwin":b"Darwin Kernel Version" not in serial,"no_user_init":b"S21 XNU LAB:" not in serial}
        if name.startswith("uefi-"):
            checks["fault_api_succeeded"]=f"S21 UEFI TEST: {name[5:]} status 0\r\n".encode() in serial
    report={"case":name,"passed":all(checks.values()),"checks":checks,"capture":capture,
            "qemu_returncode":returncode,"command":command,"serial_sha256":efi.sha(serial),
            "resource_sha256":efi.sha(raw),"payload_sha256":efi.sha(payload),"hardware_ready":False,
            "memory_audit":ownership,"memory_snapshots":{memory.STAGES[i]:s.report() for i,s in snapshots.items()}}
    (work/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    print(f"{name}: {'PASS' if report['passed'] else 'FAIL'}",flush=True)
    return report


def run(args):
    source=args.lab_run.resolve(strict=True);previous=json.loads((source/"report.json").read_text())
    adapter.require(previous.get("passed") and not previous.get("negative_fixture"),"positive baseline required")
    for path,expected in previous["own_sources_sha256"].items(): lab.verified(ROOT/path,expected)
    ref=json.loads(lab.REFERENCE.read_text())
    expected=next(x["sha256"] for x in ref["kernel_prebuilt_integrity"]["checks"] if x["path"]=="prebuilt/mach.development.bcm2837")
    kp=Path(previous["inputs"]["prebuilt/mach.development.bcm2837"]["path"]);lab.verified(kp,expected)
    lab.verified(source/"root.apfs",previous["artifacts"]["root.apfs"]["sha256"])
    lab.verified(args.efi_code,lab.EFI_HASHES["code"]);lab.verified(args.efi_vars,lab.EFI_HASHES["vars"])
    work=args.out.resolve();adapter.require("," not in str(work) and "," not in str(args.efi_code.resolve()),"comma in QEMU path")
    work.mkdir(parents=True,exist_ok=False);(work/"build").mkdir()
    built=efi.build(args.kernel_tree.resolve(),args.llvm_root.resolve(),work/"build")
    fdt=efi.qemu_fdt();(work/"fixture.dtb").write_bytes(fdt)
    resource=adapter.extract(fdt,adapter.build_probe(work));tree=efi.fragment(resource)
    kernel=kp.read_bytes();ramdisk=(source/"root.apfs").read_bytes()
    cases={}
    for name in ("positive","truncated","counter","gic","duplicate","kernel-bounds"):
        cases[name]=run_case(work/name,name,work/"build/loader.efi",kernel,ramdisk,tree,resource,
            args.tools.resolve(),args.efi_code.resolve(),args.efi_vars.resolve(),args.timeout)
    fault_builds={}
    for fault,name in enumerate(("uefi-payload-busy","uefi-window-busy","uefi-payload-released"),1):
        output=work/("build-"+name);output.mkdir()
        fault_builds[name]=efi.build(args.kernel_tree.resolve(),args.llvm_root.resolve(),output,memory_test=fault)
        cases[name]=run_case(work/name,name,output/"loader.efi",kernel,ramdisk,tree,resource,
            args.tools.resolve(),args.efi_code.resolve(),args.efi_vars.resolve(),args.timeout)
    report={"schema_version":2,"scope":"Rebuilt EFI consumer in one-CPU QEMU; UEFI allocation snapshots, synthetic resources, pinned XNU, own init",
            "passed":all(x["passed"] for x in cases.values()),"build":built,"cases":cases,
            "memory_fault_builds":fault_builds,
            "fixture":resource.report(),"kernel_sha256":efi.sha(kernel),"ramdisk_sha256":efi.sha(ramdisk),
            "own_sources_sha256":{p:lab.sha256(ROOT/p) for p in ("lab/xnu/efi_resources.c","lab/xnu/efi_resources.h",
                "lab/xnu/efi_lab.py","lab/xnu/ramfb.py","lab/xnu/efi_video.c","lab/xnu/efi_video.h","lab/xnu/video.py","lab/xnu/efi_memory.c","lab/xnu/efi_memory.h","lab/xnu/efi_memory_loader.inc",
                "lab/xnu/efi_memory.py","scripts/run_xnu_adapter_lab.py","lab/xnu/fdt_adapter.py",
                "lab/xnu/boot_contract.py","scripts/capture_xnu_contract.py","scripts/run_xnu_lab.py","scripts/test_fdt.py",
                "lab/xnu/fdt_probe.c","r8/r10_payload/fdt.c","r8/r10_payload/fdt.h","scripts/inspect_proton.py","tools/mkpayload.py")},
            "memory_scope":"Full GetMemoryMap snapshots before/after exact-address allocations, before copy and at handoff; UEFI remains resident; Samsung not tested",
            "hardware_ready":False,"iOS_gui_tested":False,"Samsung_tested":False}
    (work/"report.json").write_text(json.dumps(report,indent=2)+"\n")
    return 0 if report["passed"] else 1


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("lab-run","kernel-tree","llvm-root","efi-code","efi-vars","out"):
        p.add_argument("--"+name,type=Path,required=True)
    p.add_argument("--tools",type=Path,default=ROOT/"tools/root");p.add_argument("--timeout",type=int,default=90)
    args=p.parse_args()
    if not 10<=args.timeout<=180:p.error("timeout must be 10..180")
    try:return run(args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"Adapter lab error: {exc}",file=sys.stderr);return 2


if __name__=="__main__": raise SystemExit(main())
