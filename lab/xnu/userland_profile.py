"""Fixed one-CPU QEMU iOS userland profile and read-only loader capture ABI."""
import struct
from . import boot_contract as c, efi_memory as memory
MAGIC=b'S21ULAB\0'
TAG=b's21_userland_v1\0'
SECONDS=900
TAIL=1<<30
FIRST_EPOCH=1577836800
LAST_EPOCH=4102444800


def encode(epoch):
    if type(epoch) is not int or not FIRST_EPOCH<=epoch<LAST_EPOCH:
        raise c.ContractError('userland epoch outside 2020..2099')
    return struct.pack('<8sIIQQ',MAGIC,1,1,epoch,0)


def decode(raw):
    if len(raw)!=32:raise c.ContractError('userland profile length')
    magic,version,ident,epoch,reserved=struct.unpack('<8sIIQQ',raw)
    if magic!=MAGIC or version!=1 or ident!=1 or reserved or encode(epoch)!=raw:
        raise c.ContractError('unsupported userland profile')
    return {'id':ident,'epoch':epoch,'cpus':1,'seconds':SECONDS,'virtio_input':1,'minimum_tail':TAIL}


def cmdline(epoch):
    encode(epoch)
    return f'cpus=1 loader_return_after=900 virtio_input=1 epoch={epoch}'


def snapshots(raw):
    stride=memory.CAPACITY+40
    if len(raw)!=4*stride:raise c.ContractError('loader snapshot buffer length')
    result={}
    for stage in range(4):
        start=stage*stride;size,desc_stride,key,status,version,captured=struct.unpack_from('<4Q2I',raw,start+memory.CAPACITY)
        if captured!=1 or status or not 0<size<=memory.CAPACITY:
            raise c.ContractError('loader snapshot incomplete or failed')
        result[stage]=memory.Snapshot(raw[start:start+size],desc_stride,version,key)
    return result


def verify(args,tree,profile,small_bytes):
    declared=decode(encode(profile['epoch']))
    if declared['id']!=profile['id'] or args.cmdline!='debug=0x8 serial=3 rd=md0 '+cmdline(profile['epoch']):
        raise c.ContractError('captured command line differs from typed profile')
    if args.phys_base+args.mem_size-args.top<TAIL:raise c.ContractError('insufficient userland dynamic tail')
    cpus=tree.at('/cpus').children
    if len(cpus)!=1 or c.cells(cpus[0],'reg',1,bits=32)!=(0,):raise c.ContractError('userland profile requires cpu0 only')
    disks=tree.at('/chosen/memory-map')
    if c.cells(disks,'RAMDisk1',2)[1]!=((small_bytes+0x3fff)&~0x3fff):
        raise c.ContractError('small ramdisk size mismatch')
    return {'verified':True,'id':1,'epoch':profile['epoch'],'seconds':SECONDS,'cpus':1,'virtio_input':1,
            'dynamic_tail_bytes':args.phys_base+args.mem_size-args.top,'minimum_tail_bytes':TAIL}
