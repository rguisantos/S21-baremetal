#!/usr/bin/env python3
"""Confere o patch XNU 0151: construtores de evento de digitalizador com z e inclinação y certos.

  verify_hid_0151.py --s21xnu CLONE [--json r.json]

CLONE: s21xnu no commit fixado (a128f07). O 0058 cria
iokit/Kernel/arm/hid/IOHIDEvent.cpp (nenhum outro patch da série altera o
arquivo). Os três construtores com orientação (Tilt, Polar, Quality) chamam
IOHIDEvent::digitizerEvent() sem o argumento z: tipPressure cai em z,
auxPressure em tipPressure, twist em auxPressure e options em twist. O de
inclinação ainda grava xTilt nos dois eixos. Com pressão auxiliar zero, a
caneta encostada chega ao iOS com pressão de ponta zero.

O verificador recria o arquivo a partir do 0058, aplica o 0151 com
`git apply --check`, extrai as funções reais (antes e depois) e as compila em
C++ no host com o struct IOHIDDigitizerEventData do próprio 0058 e um
IOHIDEvent mínimo. Confere que o código antigo mostra o defeito e que o novo
entrega cada campo no lugar.
"""
import argparse
import json
import pathlib
import re
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
PATCH = HERE / "0151-s21-hid-digitizer-orientation-args.patch"
S21XNU_COMMIT = "a128f07b04987e60f5e13e2ce67b19ae009672cd"
P0058 = "xnu/patches/0058-sweet-hid-event-services.patch"
FILE = "iokit/Kernel/arm/hid/IOHIDEvent.cpp"
FUNCS = ["digitizerEvent", "digitizerEventWithTiltOrientation", "digitizerEventWithPolarOrientation",
         "digitizerEventWithQualityOrientation"]

HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
typedef int32_t IOFixed;
typedef uint32_t UInt32;
typedef uint64_t UInt64;
typedef uint32_t IOOptionBits;
typedef uint32_t IOHIDEventType;
typedef uint32_t IOHIDDigitizerTransducerType;
enum { kIOHIDEventTypeDigitizer = 11 };
enum { kIOHIDEventOptionIsAbsolute = 1u << 2 };
enum { kIOHIDDigitizerTransducerTypeStylus = 0, kIOHIDDigitizerTransducerTypeFinger = 2 };
enum { kIOHIDDigitizerOrientationTypeTilt = 0, kIOHIDDigitizerOrientationTypePolar = 1,
       kIOHIDDigitizerOrientationTypeQuality = 2 };
#define require(c, l) do { if (!(c)) goto l; } while (0)
#define __unused __attribute__((unused))
%STRUCT%
class IOHIDEvent {
public:
	void *_data;
	bool initWithTypeTimeStamp(uint32_t, uint64_t, uint32_t) { _data = calloc(1, sizeof(IOHIDDigitizerEventData)); return _data; }
	void release() {}
	static IOHIDEvent *digitizerEvent(UInt64, UInt32, IOHIDDigitizerTransducerType, bool, UInt32, IOFixed, IOFixed,
	    IOFixed z = 0, IOFixed tipPressure = 0, IOFixed auxPressure = 0, IOFixed twist = 0, IOOptionBits options = 0);
	static IOHIDEvent *digitizerEventWithTiltOrientation(UInt64, UInt32, IOHIDDigitizerTransducerType, bool, UInt32,
	    IOFixed, IOFixed, IOFixed z = 0, IOFixed tipPressure = 0, IOFixed auxPressure = 0, IOFixed twist = 0,
	    IOFixed xTilt = 0, IOFixed yTilt = 0, IOOptionBits options = 0);
	static IOHIDEvent *digitizerEventWithPolarOrientation(UInt64, UInt32, IOHIDDigitizerTransducerType, bool, UInt32,
	    IOFixed, IOFixed, IOFixed z = 0, IOFixed tipPressure = 0, IOFixed auxPressure = 0, IOFixed twist = 0,
	    IOFixed altitude = 0, IOFixed azimuth = 0, IOOptionBits options = 0);
	static IOHIDEvent *digitizerEventWithQualityOrientation(UInt64, UInt32, IOHIDDigitizerTransducerType, bool,
	    UInt32, IOFixed, IOFixed, IOFixed z = 0, IOFixed tipPressure = 0, IOFixed auxPressure = 0, IOFixed twist = 0,
	    IOFixed quality = 0, IOFixed density = 0, IOFixed irregularity = 0, IOFixed majorRadius = 0,
	    IOFixed minorRadius = 0, IOOptionBits options = 0);
};
%FUNCS%
static void show(const char *n, IOHIDEvent *e)
{
	IOHIDDigitizerEventData *d = (IOHIDDigitizerEventData *)e->_data;
	printf("%s x=%d y=%d z=%d tip=%d aux=%d twist=%d otype=%u a=%d b=%d\n", n, d->position.x, d->position.y,
	    d->position.z, d->pressure, d->auxPressure, d->twist, d->orientationType, d->orientation.tilt.x,
	    d->orientation.tilt.y);
}
int main()
{
	/* x 1, y 2, z 11, ponta 22, auxiliar 33, twist 44; inclinação (12, -34); polar (55, 66); quality 77.. */
	show("tilt", IOHIDEvent::digitizerEventWithTiltOrientation(0, 1, kIOHIDDigitizerTransducerTypeStylus, true, 0,
	    1, 2, 11, 22, 33, 44, 12, -34, 0));
	show("tilt-aux0", IOHIDEvent::digitizerEventWithTiltOrientation(0, 1, kIOHIDDigitizerTransducerTypeStylus,
	    true, 0, 1, 2, 11, 22, 0, 0, 12, -34, 0));
	show("polar", IOHIDEvent::digitizerEventWithPolarOrientation(0, 1, kIOHIDDigitizerTransducerTypeStylus, true,
	    0, 1, 2, 11, 22, 33, 44, 55, 66, 0));
	show("quality", IOHIDEvent::digitizerEventWithQualityOrientation(0, 1, kIOHIDDigitizerTransducerTypeFinger,
	    true, 0, 1, 2, 11, 22, 33, 44, 77, 88, 99, 5, 6, 0));
	return 0;
}
'''

WANT_NEW = {
    "tilt": "x=1 y=2 z=11 tip=22 aux=33 twist=44 otype=0 a=12 b=-34",
    "tilt-aux0": "x=1 y=2 z=11 tip=22 aux=0 twist=0 otype=0 a=12 b=-34",
    "polar": "x=1 y=2 z=11 tip=22 aux=33 twist=44 otype=1 a=55 b=66",
    "quality": "x=1 y=2 z=11 tip=22 aux=33 twist=44 otype=2 a=77 b=88",
}
WANT_OLD = {   # o defeito, reproduzido: argumentos deslocados e xTilt nos dois eixos
    "tilt": "x=1 y=2 z=22 tip=33 aux=44 twist=0 otype=0 a=12 b=12",
    "tilt-aux0": "x=1 y=2 z=22 tip=0 aux=0 twist=0 otype=0 a=12 b=12",
}


def git(*args, cwd, check=True):
    return subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True, check=check)


def created_file(patch_bytes, path):
    lines = patch_bytes.split(b"\n")
    i = lines.index(b"+++ b/" + path.encode())
    n = int(re.match(rb"@@ -0,0 \+1,(\d+) @@", lines[i + 1]).group(1))
    body = lines[i + 2:i + 2 + n]
    assert all(l.startswith(b"+") for l in body)
    return b"\n".join(l[1:] for l in body) + b"\n"


def extract_fn(text, name):
    m = re.search(r"^IOHIDEvent \* IOHIDEvent::%s\(" % name, text, re.M)
    return text[m.start():text.index("\n}\n", m.end()) + 3]


def struct_text(patch_text):
    end = patch_text.index("+} IOHIDDigitizerEventData;")
    start = patch_text.rindex("+typedef struct", 0, end)
    return "\n".join(l[1:] for l in patch_text[start:end + len("+} IOHIDDigitizerEventData;")].split("\n"))


def run_case(tmp, cpp_text, struct, tag):
    fns = "\n".join(extract_fn(cpp_text, f) for f in FUNCS)
    src = HARNESS.replace("%STRUCT%", struct).replace("%FUNCS%", fns)
    c, exe = tmp / ("h_%s.cpp" % tag), tmp / ("h_%s" % tag)
    c.write_text(src, encoding="latin-1")
    r = subprocess.run(["c++", "-std=c++17", "-O1", "-w", str(c), "-o", str(exe)], capture_output=True, text=True)
    if r.returncode:
        return None, r.stderr
    out = subprocess.run([str(exe)], capture_output=True, text=True, check=True).stdout
    return {l.split(" ", 1)[0]: l.split(" ", 1)[1] for l in out.splitlines()}, ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--s21xnu", required=True)
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    report = {"schema": "s21xnu-hid-0151/1", "checks": []}
    ok = True

    def check(name, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        report["checks"].append({"check": name, "ok": bool(cond), "detail": str(detail)[:300]})
        print("%s %s %s" % ("PASS" if cond else "FAIL", name, str(detail)[:200]))

    got = git("rev-parse", "HEAD", cwd=a.s21xnu).stdout.strip()
    check("s21xnu fixado", got == S21XNU_COMMIT, got[:12])
    p58 = pathlib.Path(a.s21xnu, P0058).read_bytes()
    others = [p.name for p in sorted(pathlib.Path(a.s21xnu, "xnu/patches").iterdir())
              if p.name != pathlib.Path(P0058).name and re.search(rb"^\+\+\+ b/" + FILE.encode() + rb"$", p.read_bytes(), re.M)]
    check("só o 0058 escreve IOHIDEvent.cpp na série", not others, others)
    with tempfile.TemporaryDirectory() as t:
        tmp = pathlib.Path(t)
        f = tmp / FILE
        f.parent.mkdir(parents=True)
        f.write_bytes(created_file(p58, FILE))
        git("init", "-q", cwd=tmp)
        old = f.read_text(encoding="latin-1")
        r = git("apply", "--check", str(PATCH), cwd=tmp, check=False)
        check("0151 aplica sobre o IOHIDEvent.cpp do 0058", r.returncode == 0, r.stderr.strip())
        if r.returncode:
            return 1
        files = git("apply", "--numstat", str(PATCH), cwd=tmp).stdout.split()[2::3]
        check("0151 muda só IOHIDEvent.cpp", files == [FILE], files)
        git("apply", str(PATCH), cwd=tmp)
        new = f.read_text(encoding="latin-1")
        check("as três chamadas passam z a digitizerEvent()",
              new.count("buttonState, x, y, z, tipPressure, auxPressure, twist, options);") == 3
              and "buttonState, x, y, tipPressure" not in new)
        check("inclinação y = yTilt", "event->orientation.tilt.y = yTilt;" in new and "tilt.y = xTilt" not in new)
        struct = struct_text(p58.decode("latin-1"))
        vo, err = run_case(tmp, old, struct, "old")
        check("código antigo compila no host", vo is not None, err)
        vn, err = run_case(tmp, new, struct, "new")
        check("código com 0151 compila no host", vn is not None, err)
        if vo and vn:
            report["old"], report["new"] = vo, vn
            for k, w in WANT_OLD.items():
                check("antes: %s mostra o defeito (%s)" % (k, w), vo.get(k) == w, vo.get(k))
            for k, w in WANT_NEW.items():
                check("depois: %s com cada campo no lugar" % k, vn.get(k) == w, vn.get(k))
    report["result"] = "PASS" if ok else "FAIL"
    print("RESULTADO", report["result"])
    if a.json:
        pathlib.Path(a.json).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
