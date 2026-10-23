"""Explicit QEMU XR24 profile. No Samsung framebuffer address is inferred."""
from dataclasses import dataclass
from . import boot_contract as c


@dataclass(frozen=True)
class Framebuffer:
    pixels: c.Span
    allocation: c.Span
    stride: int
    width: int
    height: int


def decode(fields):
    if len(fields) != 6:
        raise c.ContractError('six video fields required')
    for field in fields: c.integer(field)
    base, display, stride, width, height, depth = fields
    if not base or base % 4096 or (display,stride,width,height,depth) != (1,4500,1125,2436,32):
        raise c.ContractError('unsupported QEMU XR24 video profile')
    pixels = c.Span(base, stride*height)
    return Framebuffer(pixels,c.Span(base,(pixels.size+4095)&~4095),stride,width,height)


def verify_maps(fields, snapshots, claim, window, payload):
    frame = decode(fields)
    phase=claim.get('after_stage')
    expected={'base':frame.allocation.base,'size':frame.allocation.size}
    if phase is not None:expected['after_stage']=phase
    if claim != expected:
        raise c.ContractError('framebuffer differs from successful ramfb allocation')
    if frame.allocation.overlaps(window) or frame.allocation.overlaps(payload):
        raise c.ContractError('framebuffer overlaps kernel window or payload')
    if set(snapshots) != set(range(4)):
        raise c.ContractError('four framebuffer snapshots required')
    if phase is None:
        # Historical runs allocated the framebuffer before snapshot zero.
        if not all(s.covers(frame.allocation,2) for s in snapshots.values()):
            raise c.ContractError('framebuffer is not LoaderData across all UEFI snapshots')
    else:
        if type(phase) is not int or phase not in (0,1) or not all(
                s.covers(frame.allocation,7 if i<=phase else 2) for i,s in snapshots.items()):
            raise c.ContractError('framebuffer allocation phase/ownership mismatch')
    return frame
