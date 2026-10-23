"""Build a QEMU-only consumer from pinned upstream source and own C guards."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from . import boot_contract as c
from . import fdt_adapter as adapter
from scripts import test_fdt as dt

ROOT = Path(__file__).resolve().parents[2]
REVISION = "8e61187098f2c26c5daee8f9f72b6416aa64b9ab"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def qemu_fdt():
    """Declared synthetic fixture, not a QEMU dump or Samsung memory map."""
    tree = dt.fixture(qemu=True)
    tree[1]["#size-cells"] = dt.u32(2)
    tree[2][0][1]["reg"] = dt.u64(0x40000000, 6 << 30)
    tree[2][1][1]["#size-cells"] = dt.u32(2)
    tree[2][2][2][0][1]["enable-method"] = dt.text("psci")
    tree[2][3][1]["reg"] = dt.u64(0x08000000, 0x10000, 0x080a0000, 0x100000)
    tree[2][4][1]["clock-frequency"] = dt.u32(62500000)
    tree[2].append(dt.node("psci", {"compatible":dt.text("arm,psci-1.0"), "method":dt.text("hvc")}))
    return dt.encode(tree)


def fragment(resource):
    adapter.require(resource.cpus == [0] and resource.method == "hvc" and resource.frequency == 62500000
        and resource.gic == [c.Span(0x08000000,0x10000),c.Span(0x080a0000,0x100000)]
        and resource.ram == [c.Span(0x40000000,6<<30)] and not resource.reserved
        and not resource.unresolved_reserved and not resource.initrd,
        "only the declared one-CPU QEMU fixture is supported")
    tree = resource.project()
    io = tree.at("/arm-io")
    io.properties["ranges"] = adapter.le64(0,0x08000000,0x01001000)
    io.children.append(adapter.node("uart0", {"device_type":b"uart\0", "compatible":b"arm,pl011\0",
                                             "reg":adapter.le64(0x01000000,0x1000)}))
    return tree


def pack(kernel, ramdisk, resource):
    body=bytearray()
    for name,data in (("kernel",kernel),("ramdisk",ramdisk),("adtres",resource),
                      ("cmdline",b"cpus=1 loader_return_after=30\0")):
        body += struct.pack("<16sII",name.encode(),len(data),0)+data+b"\0"*(-len(data)%16)
    body += b"\0"*24
    adapter.require(len(body)+8 <= 64*1024*1024, "payload exceeds 64 MiB")
    return struct.pack("<II",0x50554e58,len(body))+body


def patch_source(source):
    def edit(old,new):
        nonlocal source
        adapter.require(source.count(old)==1,"upstream anchor changed: "+old[:60])
        source=source.replace(old,new)
    edit('#include "efi.h"', '#include "efi.h"\n#include "efi_resources.h"')
    edit('struct payload_info {\n', 'struct payload_info {\n\tconst uint8_t *resource;\n\tuint32_t resource_size;\n')
    start=source.index('static int\nparse_payload(')
    end=source.index('\n/* ------------------------------------------------------------------------ */',start)
    source=source[:start]+'''static int
parse_payload(struct payload_info *pi, int verbose)
{
    struct s21_payload value;
    (void)verbose;
    memset(pi, 0, sizeof(*pi));
    if (!s21_payload_decode((const void *)PAYLOAD_BASE, PAYLOAD_MAX_SIZE, &value)) {
        print("S21 XNU ADAPTER: REJECT payload\\n");
        return 0;
    }
    pi->kernel = value.kernel;
    pi->ramdisk = value.ramdisk;
    pi->ramdisk_size = value.ramdisk_size;
    pi->cmdline = value.cmdline;
    pi->resource = value.resource;
    pi->resource_size = value.resource_size;
    return 1;
}
'''+source[end:]
    edit('\tif (!have_checkpoint) {\n', '''    struct s21_resources adapter;
    if (PLAT != &platform_qemu_virt ||
        !s21_resources_decode(pi.resource, pi.resource_size, &adapter) ||
        !s21_resources_qemu(&adapter, READ_SYSREG(CNTFRQ_EL0), READ_SYSREG(MPIDR_EL1) & 0xff00ffffffULL)) {
        print("S21 XNU ADAPTER: REJECT resources\\n");
        return 0;
    }
    static struct platform lab_platform;
    lab_platform = platform_qemu_virt;
    lab_platform.io_base = adapter.io_base;
    lab_platform.io_size = adapter.io_size;
    lab_platform.gic_dist = adapter.dist;
    lab_platform.gic_redist = adapter.redist;
    lab_platform.uart = adapter.uart;
    lab_platform.psci_hvc = adapter.hvc;
    lab_platform.cores = 1;
    PLAT = &lab_platform;
    print("S21 XNU ADAPTER: resources PASS frequency %d GICR size %x\\n", adapter.frequency, adapter.redist_size);
\tif (!have_checkpoint) {
''')
    edit('uint64_t gic_reg[4] = { plat->gic_dist - plat->io_base, 0x10000, plat->gic_redist - plat->io_base, 0x100000 };',
         'uint64_t gic_reg[4] = { plat->gic_dist - plat->io_base, adapter.dist_size, plat->gic_redist - plat->io_base, adapter.redist_size };')
    edit('\tba->deviceTreeLength = dt_len;\n', '''\tba->deviceTreeLength = dt_len;
    if (!s21_layout_check(phys_base, win_size, kern_lo, kern_hi, rd_pa, rd_size, dt_pa, dt_len, ba_pa, top)) {
        print("S21 XNU ADAPTER: REJECT layout\\n");
        return 0;
    }
    print("S21 XNU ADAPTER: layout PASS before jump\\n");
''')
    return source


def build(kernel_tree, llvm_root, out):
    reference=json.loads((ROOT/"docs/references/hackios-xnu-20261022.json").read_text())
    pinned=next(x for x in reference["sources"] if x["repository"].endswith("-kernel"))
    head=subprocess.check_output(["git","-C",str(kernel_tree),"rev-parse","HEAD"],text=True,timeout=10).strip()
    adapter.require(head==REVISION,"wrong kernel source revision")
    inputs={}
    for name in ("loader.c","efi.h"):
        expected=next(x["sha256"] for x in pinned["files_hashed_for_traceability"] if x["path"]=="xnuloader/"+name)
        data=(kernel_tree/"xnuloader"/name).read_bytes()
        adapter.require(sha(data)==expected,"upstream source hash mismatch: "+name)
        inputs[name]=expected
        (out/name).write_bytes(data)
    # identity.h is tracked alongside the exact pinned loader source.
    identity=subprocess.check_output(["git","-C",str(kernel_tree),"show",REVISION+":xnuloader/identity.h"])
    (out/"identity.h").write_bytes(identity); inputs["identity.h"]=sha(identity)
    (out/"loader.c").write_text(patch_source((out/"loader.c").read_text()))
    for name in ("efi_resources.c","efi_resources.h"):
        shutil.copyfile(ROOT/"lab/xnu"/name,out/name)
    clang=llvm_root/"usr/lib/llvm-19/bin/clang"
    link=llvm_root/"usr/lib/llvm-19/bin/lld-link"
    env=dict(os.environ,LD_LIBRARY_PATH=str(llvm_root/"usr/lib/x86_64-linux-gnu")+":"+str(llvm_root/"usr/lib/llvm-19/lib"))
    commands=[]
    with (out/"build.log").open("wb") as log:
        for name in ("loader","efi_resources"):
            cmd=[str(clang),"--target=aarch64-unknown-windows","-ffreestanding","-fno-builtin",
                 "-fno-stack-protector","-fshort-wchar","-mgeneral-regs-only","-O1","-Wall","-Wextra",
                 "-Wno-unused-parameter","-c",str(out/(name+".c")),"-o",str(out/(name+".obj"))]
            subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=45); commands.append(cmd)
        cmd=[str(link),"/subsystem:efi_application","/entry:efi_main","/nodefaultlib","/base:0xA1000000",
             "/timestamp:0","/out:"+str(out/"loader.efi"),str(out/"loader.obj"),str(out/"efi_resources.obj")]
        subprocess.run(cmd,env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=30); commands.append(cmd)
    binary=(out/"loader.efi").read_bytes(); pe=struct.unpack_from("<I",binary,60)[0]
    adapter.require(binary[pe:pe+4]==b"PE\0\0" and struct.unpack_from("<H",binary,pe+4)[0]==0xaa64
                    and struct.unpack_from("<H",binary,pe+24+68)[0]==10,"not an AArch64 EFI application")
    return {"upstream_revision":head,"upstream_sources":inputs,"commands":commands,
            "patched_source_sha256":sha((out/"loader.c").read_bytes()),"efi_sha256":sha(binary),
            "efi_bytes":len(binary),"clang_version":subprocess.check_output([str(clang),"--version"],env=env,text=True).splitlines()[0]}
