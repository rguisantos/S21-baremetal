import json
from pathlib import Path
import struct
import unittest

from inspect_newtime_dmc_method12_hzc2 import (
    DMC_PLUGIN, U32, NEG1, core_to_file, dispatch, dvfs_first8, dvfs_pair,
    dvfs_terminal, fields, fmask, handler8, handler9, relay_gates, signed,
    thumb_file,
)

REPORT = Path(__file__).resolve().parent.parent / 'docs/references/newtime-dmc-method12-hzc2.json'
def read_table(base_core, count):
    """Hash-bound table words exported from firmware; no blob needed in CI."""
    if base_core != 0x37CD0:
        raise ValueError('unknown table')
    words = json.loads(REPORT.read_text())['dmc_interface']['handler_words']
    return [words[str(i)] for i in range(count)]


class RawThumb:
    """Independent raw-halfword evaluator for the DMC dispatch/handler/poll slices.

    Words are decoded from the JSON witness bytes, never from extractor
    formulas. BL/BLX are opaque hooks. Missing memory, unsupported words and
    the host budget fail closed; host budgets are not firmware timeouts.
    """

    def __init__(self, report):
        self.code = {int(r['pc'], 16): bytes.fromhex(r['bytes']) for r in report['witnesses']}
        self.literals = {int(k, 16): v for k, v in report['literals'].items()}
        self.r = [0xA5A50000 + i for i in range(16)]
        self.mem = {}
        self.pc = 0
        self.n = self.z = self.c = self.v = False
        self.calls = []
        self.stores = []
        self.reads = []

    def word(self, address, value=None):
        address &= U32
        if value is None:
            self.reads.append((self.pc, address, 4))
            return sum(self.mem[(address + i) & U32] << (8 * i) for i in range(4))
        for i in range(4):
            self.mem[(address + i) & U32] = (value >> (8 * i)) & 255

    def nz(self, x):
        self.n, self.z = bool(x & (1 << 31)), x == 0

    def sub(self, a, b, borrow=0):
        x = (a - b - borrow) & U32
        self.nz(x)
        self.c = a >= b + borrow
        self.v = bool((a ^ b) & (a ^ x) & (1 << 31))
        return x

    def add(self, a, b):
        value = a + b
        x = value & U32
        self.nz(x)
        self.c = value > U32
        self.v = bool((~(a ^ b) & (a ^ x)) & (1 << 31))
        return x

    def shift(self, value, count, left):
        if count:
            self.c = bool((value >> (32-count if left else count-1)) & 1) if count <= 32 else False
        x = ((value << count) & U32 if left else value >> count) if count < 32 else 0
        self.nz(x)
        return x

    def cond(self, k):
        n, z, c, v = self.n, self.z, self.c, self.v
        return (z, not z, c, not c, n, not n, v, not v, c and not z, not c or z,
                n == v, n != v, not z and n == v, z or n != v)[k]

    @staticmethod
    def sgn(x, bits):
        return x - (1 << bits) if x & (1 << (bits - 1)) else x

    def _load(self, a, byte=False, half=False):
        a &= U32
        if byte:
            self.reads.append((self.pc, a, 1))
            return self.mem[a]
        if half:
            self.reads.append((self.pc, a, 2))
            return self.mem[a] | (self.mem[(a + 1) & U32] << 8)
        return self.word(a)

    def _store(self, a, v, byte=False, half=False):
        a &= U32
        if byte:
            self.mem[a] = v & 255
            self.stores.append((self.pc, a, v & 255))
        elif half:
            self.mem[a] = v & 255
            self.mem[(a + 1) & U32] = (v >> 8) & 255
            self.stores.append((self.pc, a, v & 0xFFFF))
        else:
            self.word(a, v)
            self.stores.append((self.pc, a, v))

    def run(self, start, stops, hook=None, budget=20000):
        self.pc = start
        for _ in range(budget):
            p = self.pc
            if p in stops:
                return p
            raw = self.code[p]
            h = struct.unpack_from('<H', raw)[0]
            q = p + len(raw)
            if len(raw) == 4:
                b = struct.unpack_from('<H', raw, 2)[0]
                top = (h >> 11) & 31
                if h & 0xF800 == 0xF000 and b & 0xD000 == 0xD000:      # BL/BLX imm
                    sign = (h >> 10) & 1
                    imm = (sign << 24 | (1 ^ ((b >> 13) & 1) ^ sign) << 23
                           | (1 ^ ((b >> 11) & 1) ^ sign) << 22
                           | (h & 1023) << 12 | (b & 2047) << 1)
                    target = p + 4 + self.sgn(imm, 25)
                    self.calls.append((p, target, tuple(self.r[:4])))
                    if hook is None:
                        raise ValueError('opaque BL needs a hook')
                    hook(self, p, target)
                    q = p + 4
                elif top == 0x1E and (h >> 5) & 0x1F == 0x12:        # MOVW
                    imm = (((h & 15) << 12) | (((h >> 10) & 1) << 11)
                           | (((b >> 12) & 7) << 8) | (b & 255))
                    self.r[(b >> 8) & 15] = imm & U32
                elif top == 0x1E and (h >> 5) & 0x1F == 0x16:        # MOVT
                    imm = (((h & 15) << 12) | (((h >> 10) & 1) << 11)
                           | (((b >> 12) & 7) << 8) | (b & 255))
                    d = (b >> 8) & 15
                    self.r[d] = ((self.r[d] & 0xFFFF) | (imm << 16)) & U32
                else:
                    raise ValueError(f'unsupported wide word {h:#x} at {p:#x}')
                self.pc = q
                continue
            family = h & 0xF800
            if h & 0xFF00 in (0xB400, 0xB500):                         # push
                n = bin(h & 0x1FF).count('1')
                new_sp = (self.r[13] - 4 * n) & U32
                base = new_sp
                for i in range(9):
                    if h & (1 << i):
                        self._store(base, self.r[14 if i == 8 else i])
                        base = (base + 4) & U32
                self.r[13] = new_sp
            elif h & 0xFF00 in (0xBC00, 0xBD00):                       # pop
                base = self.r[13]
                for i in range(8):
                    if h & (1 << i):
                        self.r[i] = self._load(base)
                        base = (base + 4) & U32
                self.r[13] = base
                if h & 0x100:
                    self.pc = self._load(base) & ~1
                    self.r[13] = (base + 4) & U32
                    return self.pc
            elif h & 0xFF00 == 0xB000:                                 # add/sub sp
                if h & 0x80:                                            # SUB sp,#imm7*4
                    self.r[13] = (self.r[13] - (h & 0x7F) * 4) & U32
                else:                                                   # ADD sp,#imm8*4
                    self.r[13] = (self.r[13] + (h & 255) * 4) & U32
            elif h & 0xF800 == 0xA800:                                 # add rd,sp,#imm8*4
                self.r[(h >> 8) & 7] = (self.r[13] + (h & 255) * 4) & U32
            elif h & 0xFC00 in (0x4400, 0x4500, 0x4600, 0x4700):
                d = (h & 7) | ((h >> 4) & 8)
                s = (h >> 3) & 15
                op = (h >> 8) & 3
                if op == 0:
                    self.r[d] = (self.r[d] + self.r[s]) & U32
                elif op == 1:
                    self.sub(self.r[d], self.r[s])
                elif op == 2:
                    self.r[d] = self.r[s]
                else:                                                  # BX/BLX reg
                    target = self.r[s] & ~1
                    if h & 0x80:                                       # BLX rm
                        self.calls.append((p, target, tuple(self.r[:4])))
                        if hook is None:
                            raise ValueError('opaque BLX needs a hook')
                        hook(self, p, target)
                        q = p + 2
                    else:                                              # BX rm
                        if s == 14:
                            return self.r[14] & ~1
                        self.pc = target
                        continue
            elif h & 0xFC00 == 0x4000:                                 # data proc
                d, s = h & 7, (h >> 3) & 7
                op = (h >> 6) & 15
                if op == 0:
                    self.r[d] &= self.r[s]
                    self.nz(self.r[d])
                elif op == 1:
                    self.r[d] ^= self.r[s]
                    self.nz(self.r[d])
                elif op == 2:                                          # LSL reg
                    shift = self.r[s] & 255
                    self.r[d] = self.shift(self.r[d], shift, True)
                    self.nz(self.r[d])
                elif op == 3:                                          # LSR reg
                    shift = self.r[s] & 255
                    self.r[d] = self.shift(self.r[d], shift, False)
                    self.nz(self.r[d])
                elif op == 4:                                          # ASR register not covered
                    raise ValueError('ASR register is outside this slice evaluator')
                elif op == 8:                                          # TST
                    self.nz(self.r[d] & self.r[s])
                elif op == 9:                                          # NEGS
                    self.r[d] = self.sub(0, self.r[s])
                elif op == 10:                                         # CMP imm reg form
                    self.sub(self.r[d], self.r[s])
                elif op == 12:
                    self.r[d] |= self.r[s]
                    self.nz(self.r[d])
                elif op == 15:
                    self.r[d] = U32 ^ self.r[s]
                    self.nz(self.r[d])
                else:
                    raise ValueError(f'unsupported ALU op {op} at {p:#x}')
            elif family == 0x2000:                                     # MOVS imm
                self.r[(h >> 8) & 7] = h & 255
                self.nz(self.r[(h >> 8) & 7])
            elif family == 0x2800:                                     # CMP imm
                self.sub(self.r[(h >> 8) & 7], h & 255)
            elif family == 0x3000:                                     # ADDS imm
                self.r[(h >> 8) & 7] = self.add(self.r[(h >> 8) & 7], h & 255)
                self.nz(self.r[(h >> 8) & 7])
            elif family == 0x3800:                                     # SUBS imm
                self.r[(h >> 8) & 7] = self.sub(self.r[(h >> 8) & 7], h & 255)
            elif family == 0x0000:                                     # LSL imm
                d, s, bits = h & 7, (h >> 3) & 7, (h >> 6) & 31
                self.r[d] = self.shift(self.r[s], bits, True)
                self.nz(self.r[d])
            elif family == 0x0800:                                     # LSR imm
                d, s, bits = h & 7, (h >> 3) & 7, (h >> 6) & 31
                bits = bits or 32
                self.r[d] = self.shift(self.r[s], bits, False)
                self.nz(self.r[d])
            elif h & 0xFE00 == 0x1C00:                                 # ADD imm3
                d, n = h & 7, (h >> 3) & 7
                self.r[d] = self.add(self.r[n], (h >> 6) & 7)
                self.nz(self.r[d])
            elif h & 0xFE00 == 0x1E00:                                 # SUB imm3
                d, n = h & 7, (h >> 3) & 7
                self.r[d] = self.sub(self.r[n], (h >> 6) & 7)
            elif h & 0xFE00 == 0x1800:                                 # ADD reg
                d, n, m = h & 7, (h >> 3) & 7, (h >> 6) & 7
                self.r[d] = self.add(self.r[n], self.r[m])
                self.nz(self.r[d])
            elif h & 0xFE00 == 0x1A00:                                 # SUB reg
                d, n, m = h & 7, (h >> 3) & 7, (h >> 6) & 7
                self.r[d] = self.sub(self.r[n], self.r[m])
            elif family == 0x4800:                                     # LDR literal
                at = ((p + 4) & ~3) + (h & 255) * 4
                if at not in self.literals:
                    raise ValueError(f'literal {at:#x} missing for {p:#x}')
                self.r[(h >> 8) & 7] = self.literals[at]
            elif h & 0xE000 == 0x6000:                                 # 011x block
                d, n = h & 7, (h >> 3) & 7
                load = bool(h & 0x0800)                                 # bit11 = L
                byte = bool(h & 0x1000)                                 # bit12 = B
                a = (self.r[n] + ((h >> 6) & 31) * (1 if byte else 4)) & U32
                if load:
                    self.r[d] = self._load(a, byte=byte)
                else:
                    self._store(a, self.r[d], byte=byte)
            elif h & 0xF800 == 0x5000 or h & 0xF800 == 0x5800:         # 0101 block
                d, n, m = h & 7, (h >> 3) & 7, (h >> 6) & 7
                op = (h >> 9) & 7
                a = (self.r[n] + self.r[m]) & U32
                if op == 0:                                            # STR reg
                    self._store(a, self.r[d])
                elif op == 1:                                          # STRH reg
                    self._store(a, self.r[d], half=True)
                elif op == 2:                                          # STRB reg
                    self._store(a, self.r[d], byte=True)
                elif op == 4:                                          # LDR reg
                    self.r[d] = self._load(a)
                elif op == 5:                                          # LDRH reg
                    self.r[d] = self._load(a, half=True)
                elif op == 6:                                          # LDRB reg
                    self.r[d] = self._load(a, byte=True)
                else:
                    raise ValueError(f'unsupported 0101 op {op} at {p:#x}')
            elif family == 0x9000:                                     # STR sp imm8
                a = (self.r[13] + (h & 255) * 4) & U32
                self._store(a, self.r[(h >> 8) & 7])
            elif family == 0x9800:                                     # LDR sp imm8
                self.r[(h >> 8) & 7] = self._load(self.r[13] + (h & 255) * 4)
            elif h & 0xF500 in (0xB100, 0xB900):                       # CBZ/CBNZ
                if (self.r[h & 7] == 0) != bool(h & 0x0800):
                    q = p + 4 + ((h >> 9) & 1) * 64 + ((h >> 3) & 31) * 2
            elif h & 0xF000 == 0xD000 and (h >> 8) & 15 < 14:          # Bcc
                if self.cond((h >> 8) & 15):
                    q = p + 4 + 2 * self.sgn(h & 255, 8)
            elif family == 0xE000:                                     # B
                q = p + 4 + 2 * self.sgn(h & 2047, 11)
            else:
                raise ValueError(f'unsupported word {h:#x} at {p:#x}')
            self.pc = q
        raise ValueError('host slice budget exhausted (not a firmware timeout)')


def load():
    return json.loads(REPORT.read_text())


class GateTests(unittest.TestCase):
    def test_file_state_gates_pass_for_dvfs_to_dmc(self):
        g = relay_gates(13, 1, 0x31F59, 0x8B4, 7)
        self.assertTrue(g['allowed'])

    def test_count_equal_target_fails_unsigned(self):
        for count in (9, 0, 8):
            self.assertFalse(relay_gates(count, 1, 0x31F59, 0x8B4, 7)['allowed'])

    def test_disabled_or_missing_method_fails(self):
        self.assertFalse(relay_gates(13, 0, 0x31F59, 0x8B4, 7)['allowed'])
        self.assertFalse(relay_gates(13, 1, 0, 0x8B4, 7)['allowed'])
        self.assertTrue(relay_gates(13, 1, 0, 0x8B4, 7)['fail_return_10'])

    def test_caller_mask_bit_selects(self):
        self.assertFalse(relay_gates(13, 1, 0x31F59, 0x8B4 & ~0x80, 7)['allowed'])
        self.assertTrue(relay_gates(13, 1, 0x31F59, 0x8B4, 2)['allowed'])   # fvp bit
        self.assertFalse(relay_gates(13, 1, 0x31F59, 0x8B4, 0)['allowed'])  # bit0 clear

    def test_shift_by_32_or_more_zeroes_the_bit(self):
        self.assertFalse(relay_gates(13, 1, 0x31F59, 0xFFFFFFFF, 32)['allowed'])
        self.assertFalse(relay_gates(13, 1, 0x31F59, 0xFFFFFFFF, 255)['allowed'])


class DispatchTests(unittest.TestCase):
    HANDLERS = {i: v for i, v in enumerate(read_table(0x37CD0, 20))}

    def test_table_file_values_match_the_expected_handlers(self):
        self.assertEqual(thumb_file(self.HANDLERS[8]), 0x5FADC)
        self.assertEqual(thumb_file(self.HANDLERS[9]), 0x5FBBC)
        self.assertEqual(self.HANDLERS[3], 0)
        for cmd in range(10, 17):
            self.assertEqual(self.HANDLERS[cmd], 0x32295)
        self.assertEqual(thumb_file(self.HANDLERS[0]), 0x5F81C)

    def test_subcommands_8_and_9_select_the_two_handlers(self):
        self.assertEqual(dispatch(8, self.HANDLERS)['handler_file'], 0x5FADC)
        self.assertEqual(dispatch(9, self.HANDLERS)['handler_file'], 0x5FBBC)

    def test_null_entry_returns_minus_one(self):
        d = dispatch(3, self.HANDLERS)
        self.assertIsNone(d['handler'])
        self.assertEqual(d['return_value'], NEG1)
        self.assertFalse(d['out_of_table'])

    def test_wide_index_wraps_and_reads_outside_the_table(self):
        d = dispatch(0xFFFFFFFF, self.HANDLERS)
        self.assertEqual(d['address'], 'core 0x37ccc')   # wraps onto the state object
        d2 = dispatch(0x40000000, self.HANDLERS)
        self.assertEqual(d2['address'], 'core 0x37cd0')  # 4*cmd wraps to zero
        self.assertTrue(d2['out_of_table'])


class FmaskTests(unittest.TestCase):
    def test_bit_set_returns_the_byte(self):
        self.assertEqual(fmask(5, 1 << 5), 5)
        self.assertEqual(fmask(0, 0xFFFFFFFF), 0)

    def test_bit_clear_or_zero_mask_returns_minus_one(self):
        self.assertEqual(fmask(5, 0), NEG1)
        self.assertEqual(fmask(5, 1 << 4), NEG1)

    def test_shift_counters_of_32_and_above_zero_the_result(self):
        self.assertEqual(fmask(32, 0xFFFFFFFF), NEG1)
        self.assertEqual(fmask(255, 0xFFFFFFFF), NEG1)

    def test_bit31_uses_a_signed_compare_and_fails(self):
        self.assertEqual(fmask(31, 1 << 31), NEG1)

    def test_bytes_of_32_and_above_cannot_be_selected_at_all(self):
        self.assertEqual(fmask(200, 1 << 8), NEG1)   # shift by 200 zeroes the bit
        self.assertEqual(fmask(200, 0xFFFFFFFF), NEG1)

    def test_selected_bytes_are_never_signed_negative(self):
        for byte in range(31):
            v = fmask(byte, 1 << byte)
            self.assertGreaterEqual(signed(v), 0)
        self.assertEqual(fmask(0, 1), 0)
        self.assertEqual(signed(fmask(31, 1 << 31)), -1)  # bit31 exception


class HandlerTests(unittest.TestCase):
    MASK = (1 << 2) | (1 << 5)          # levels 2 and 5 valid

    def test_handler8_sel1_calls_p_and_q_and_keeps_minus_one(self):
        v = (1 << 16) | (5 << 8) | 3    # sel1: byte1=5 valid, byte0=3 invalid
        r = handler8(v, self.MASK)
        self.assertIn('p645bc', r['path'])
        self.assertIn('q64510', r['path'])
        self.assertEqual(r['result'], NEG1)

    def test_handler8_sel0_with_h_value(self):
        v = (0 << 16) | (3 << 8) | 5    # sel0: byte1 invalid, byte0 valid
        r = handler8(v, self.MASK, h_value=0x1234)
        self.assertIn('g64618', r['path'])
        self.assertIn('h64658', r['path'])
        self.assertEqual(r['result'], 0x1234)

    def test_handler8_sel2_with_h_value(self):
        v = (2 << 16) | (5 << 8) | 3    # sel2: byte1=5 valid, byte0=3 invalid
        r = handler8(v, self.MASK, h_value=7)
        self.assertIn('r64530', r['path'])
        self.assertEqual(r['result'], 7)

    def test_handler8_same_signs_take_no_branch(self):
        both_valid = (1 << 16) | (5 << 8) | 2
        for sel in range(4):
            r = handler8(both_valid | (sel << 16), self.MASK)
            self.assertEqual(r['result'], NEG1)
        both_invalid = (0 << 16) | (3 << 8) | 4
        self.assertEqual(handler8(both_invalid, self.MASK)['result'], NEG1)

    def test_handler8_sel0_requires_current_invalid_and_target_valid(self):
        v = (0 << 16) | (3 << 8) | 5    # byte1 (current) invalid, byte0 valid
        self.assertIn('g64618', handler8(v, self.MASK)['path'])
        v2 = (0 << 16) | (5 << 8) | 3   # current valid, target invalid: no path
        self.assertNotIn('g64618', handler8(v2, self.MASK)['path'])

    def test_handler8_sel1_and_sel2_require_opposite_signs(self):
        v = (1 << 16) | (5 << 8) | 3    # byte1 valid, byte0 invalid
        self.assertIn('p645bc', handler8(v, self.MASK)['path'])
        v2 = (2 << 16) | (5 << 8) | 3
        self.assertIn('r64530', handler8(v2, self.MASK)['path'])

    def test_handler9_sel0_and_sel1_comparisons(self):
        v0 = (0 << 16) | (2 << 8) | 5   # sel0 needs g2(byte1) > g2(byte0)
        r0 = handler9(v0, self.MASK, g2_byte0=100, g2_byte1=300, t_field=1, u_field=0)
        self.assertEqual(r0['result'], 100)
        r0b = handler9(v0, self.MASK, g2_byte0=300, g2_byte1=100, t_field=1, u_field=0)
        self.assertEqual(r0b['result'], NEG1)
        v1 = (1 << 16) | (2 << 8) | 5   # sel1 needs g2(byte0) > g2(byte1)
        r1 = handler9(v1, self.MASK, g2_byte0=300, g2_byte1=100, t_field=1, u_field=0)
        self.assertEqual(r1['result'], 300)
        r1b = handler9(v1, self.MASK, g2_byte0=100, g2_byte1=300, t_field=1, u_field=0)
        self.assertEqual(r1b['result'], NEG1)

    def test_handler9_tail_w_selection(self):
        v = (0 << 16) | (2 << 8) | 5
        self.assertEqual(handler9(v, self.MASK, 9, 8, 1, 0)['w_arg'], 0)
        for t, u in ((1, 1), (0, 0), (2, 0)):
            self.assertEqual(handler9(v, self.MASK, 9, 8, t, u)['w_arg'], 1)

    def test_handler9_sel2_and_3_have_no_tail_or_result(self):
        for sel in (2, 3):
            r = handler9((sel << 16) | 0x505, self.MASK, 9, 8, 1, 0)
            self.assertEqual(r['result'], NEG1)
            self.assertIsNone(r['w_arg'])

    def test_handler9_ignores_invalid_levels(self):
        v = (0 << 16) | (3 << 8) | 4    # both levels masked out
        r = handler9(v, self.MASK, 9, 8, 1, 0)
        self.assertEqual(r['result'], NEG1)

    def test_handler9_result_uses_byte0_table_word_in_both_sels(self):
        v = (0 << 16) | (2 << 8) | 5
        self.assertEqual(handler9(v, self.MASK, 111, 222, 1, 0)['result'], 111)
        v1 = v | (1 << 16)
        self.assertEqual(handler9(v1, self.MASK, 111, 99, 1, 0)['result'], 111)

    def test_fields_extraction(self):
        f = fields((1 << 16) | 0xAB02)
        self.assertEqual(f, dict(sel=1, byte1=0xAB, byte0=2))


class ReturnPropagationTests(unittest.TestCase):
    def test_pair_ignores_subcmd8_and_reports_only_subcmd9(self):
        r = dvfs_pair(NEG1, 5)
        self.assertEqual(r['subcmd8_used'], 'ignored; r0 overwritten at 0x59578')
        self.assertTrue(r['notify9']['issued'])
        self.assertEqual(r['notify9']['cmd'], 4)
        self.assertFalse(r['subcmd9_gated_by_subcmd8'])

    def test_pair_negative_or_zero_subcmd9_is_silent(self):
        for ret9 in (NEG1, 0):
            self.assertFalse(dvfs_pair(0, ret9)['notify9']['issued'])

    def test_first8_failure_still_continues(self):
        r = dvfs_first8(NEG1)
        self.assertFalse(r['notify']['issued'])
        self.assertTrue(r['continues_to_pair'])
        self.assertFalse(r['rollback'])
        self.assertTrue(dvfs_first8(10)['notify']['issued'])
        self.assertEqual(dvfs_first8(10)['notify']['cmd'], 5)

    def test_terminal_runs_9_then_8_with_independent_notifications(self):
        r = dvfs_terminal(NEG1, 3)
        self.assertEqual(r['order'], '9 at 0x5980c then 8 at 0x59828')
        self.assertFalse(r['notify9']['issued'])
        self.assertTrue(r['notify8']['issued'])
        self.assertFalse(r['subcmd8_gated_by_subcmd9'])
        self.assertFalse(r['rollback'])

    def test_hang_frontier_is_not_a_return_failure(self):
        report = load()
        self.assertIn('non-returning call', report['returns']['hangs'])
        self.assertIn('unbounded polls', report['returns']['hangs'])


class WitnessStructureTests(unittest.TestCase):
    """Structural facts proven from the byte witnesses, independent of models."""

    @classmethod
    def setUpClass(cls):
        cls.report = load()
        cls.ops = {int(w['pc'], 16): (w['op'], w['args']) for w in cls.report['witnesses']}

    def test_no_branch_between_the_two_paired_bl_calls(self):
        """0x59572 bl 0x581fc ... 0x5957a bl 0x58214 with no control flow between."""
        self.assertEqual(self.ops[0x59572][0], 'bl')
        self.assertEqual(self.ops[0x5957A][0], 'bl')
        for pc in (0x59576, 0x59578):
            op, _ = self.ops[pc]
            self.assertNotIn(op, ('b.n', 'beq.n', 'bne.n', 'ble.n', 'bge.n',
                                  'blt.n', 'bgt.n', 'cbz', 'cbnz', 'bl', 'blx'))
        self.assertIn('#28', self.ops[0x59576][1])   # ldr r1,[sp,#28]: arg2 source
        self.assertIn('r0, r7', self.ops[0x59578][1])  # r0 overwritten by the packed value

    def test_wrappers_send_subcommands_8_and_9_to_plugin_9(self):
        movs8 = {pc: args for pc, (op, args) in self.ops.items()
                 if 0x581FC <= pc < 0x58212 and op == 'movs'}
        self.assertEqual(movs8[0x58202], 'r3, #8')
        self.assertEqual(movs8[0x58208], 'r0, #9')
        movs9 = {pc: args for pc, (op, args) in self.ops.items()
                 if 0x58214 <= pc < 0x5822A and op == 'movs'}
        self.assertEqual(movs9[0x5821C], 'r3, #9')
        self.assertEqual(movs9[0x58220], 'r0, #9')
        self.assertIn('r2, r1', list(movs9.values()))  # subcmd 9 forwards arg2 in r2

    def test_handler9_never_reads_back_the_stored_arg2(self):
        """0x5fbe8 copies arg2 (frame+0) into frame+20; neither is read again."""
        reads20 = [pc for pc, (op, args) in sorted(self.ops.items())
                   if 0x5FBBE <= pc < 0x5FCBE and op == 'ldr' and '[r7, #20]' in args]
        reads0_after = [pc for pc, (op, args) in sorted(self.ops.items())
                        if pc > 0x5FBEA and 0x5FBBE <= pc < 0x5FCBE
                        and op == 'ldr' and '[r7, #0]' in args]
        self.assertEqual(reads20, [])
        self.assertEqual(reads0_after, [])
        self.assertEqual(self.ops[0x5FBEA][0], 'str')

    def test_handler8_publishes_the_framework_critical_pair(self):
        self.assertEqual(self.ops[0x5FB2C][0], 'ldr')
        self.assertIn('#56', self.ops[0x5FB2C][1])
        self.assertEqual(self.ops[0x5FB30][0], 'str')
        self.assertIn('#68', self.ops[0x5FB30][1])

    def test_dmc_initializer_installs_methods_and_descriptor_cell(self):
        self.assertEqual(self.ops[0x5F610][0], 'str')
        self.assertIn('#12', self.ops[0x5F610][1])
        self.assertEqual(self.ops[0x5F616][0], 'str')

    def test_dvfs_init_publishes_its_descriptor_into_the_relay_cell(self):
        self.assertEqual(self.ops[0x56E04][0], 'str')
        self.assertIn('#12', self.ops[0x56E04][1])
        self.assertEqual(self.ops[0x56E08][0], 'str')

    def test_relay_58170_resolves_the_interface_through_the_cell(self):
        self.assertEqual(self.ops[0x5817E][0], 'ldr')
        self.assertEqual(self.ops[0x58180][0], 'ldr')
        self.assertIn('#8', self.ops[0x58180][1])
        self.assertEqual(self.ops[0x58186][0], 'ldr')
        self.assertIn('#28', self.ops[0x58186][1])

    def test_generic_relay_gate_instructions(self):
        self.assertEqual(self.ops[0x38B22][0], 'cmp')       # count vs target
        self.assertEqual(self.ops[0x38B32][0], 'ldrb')      # enabled byte +32
        self.assertEqual(self.ops[0x38B58][0], 'ldr')       # desc+12 methods
        self.assertEqual(self.ops[0x38B5A][0], 'ldr')       # methods+12
        self.assertEqual(self.ops[0x38B64][0], 'ldr')       # allow mask +20
        self.assertEqual(self.ops[0x38B68][0], 'tst')

    def test_poll_instructions(self):
        self.assertEqual(self.ops[0x65186][0], 'tst')
        self.assertEqual(self.ops[0x65188][0], 'bne.n')
        self.assertEqual(self.ops[0x65198][0], 'lsrs')
        self.assertIn('#9', self.ops[0x65198][1])
        self.assertEqual(self.ops[0x6519C][0], 'cmp')
        self.assertIn('#15', self.ops[0x6519C][1])

    def test_mapping_helpers(self):
        self.assertEqual(core_to_file(0x37CD0), 0x654D0)
        self.assertEqual(core_to_file(0x7300), 0x3B300)
        self.assertEqual(thumb_file(0x31F59), 0x5F758)
        with self.assertRaises(ValueError):
            core_to_file(0x3A660)      # beyond the copied image
        with self.assertRaises(ValueError):
            core_to_file(0x9000)

    def test_extractor_ranges_include_all_key_pcs(self):
        for pc in (0x58170, 0x581FC, 0x58214, 0x38B04, 0x5944C, 0x5954A, 0x59572,
                   0x5957A, 0x5980C, 0x59828, 0x5F600, 0x5F758, 0x5FADC, 0x5FBBC,
                   0x64620, 0x6463C, 0x64658, 0x6467C, 0x65170, 0x651B0, 0x651C0,
                   0x3998C, 0x39B48, 0x38E46, 0x38E90, 0x56E00, 0x64400):
            self.assertIn(pc, self.ops)


class RawThumbTests(unittest.TestCase):
    """The interpreter decodes witness bytes directly; hooks are opaque."""

    @classmethod
    def setUpClass(cls):
        cls.report = load()

    def _method12(self, cmd, handler_value=0x77, table=None):
        m = RawThumb(self.report)
        slot_cmd, slot_a1, slot_a2 = 0x1008, 0x100C, 0x1010
        m.word(slot_cmd, cmd)
        m.word(slot_a1, 0x2000)      # a1: pointer to the packed word
        m.word(slot_a2, 0x1234)      # a2: by value
        m.word(0x2000, 0xBEEF)
        for i, v in enumerate(table if table is not None else read_table(0x37CD0, 20)):
            m.word(0x37CD0 + 4 * i, v)
        m.r = [slot_a1, slot_a2, slot_cmd] + [0] * 12 + [0x400, 0xA5A50000]
        seen = {}

        def hook(sim, pc, target):
            seen['target'] = target              # core Thumb pointer, bit0 cleared
            seen['r0'] = sim.r[0]
            seen['r1'] = sim.r[1]
            sim.r[0] = handler_value

        stop = m.run(0x5F758, {0x5F79A}, hook=hook)
        self.assertEqual(stop, 0x5F79A)
        self.assertEqual(m.r[0], handler_value)
        self.assertEqual(m.word(0x2000), 0xBEEF)    # no write through the buffer ptr
        self.assertEqual(m.word(slot_cmd), cmd)     # slots unmodified by the method
        self.assertEqual(m.word(slot_a1), 0x2000)
        self.assertEqual(m.word(slot_a2), 0x1234)
        return m, seen

    def test_method12_dispatches_subcommand_8(self):
        m, seen = self._method12(8)
        self.assertEqual(seen['target'], 0x322DC)   # core handler pointer
        self.assertEqual(thumb_file(0x322DD), 0x5FADC)
        self.assertEqual(seen['r0'], 0x2000)        # *slot_a1: the buffer pointer
        self.assertEqual(seen['r1'], 0x1234)        # *slot_a2: by value

    def test_method12_dispatches_subcommand_9(self):
        m, seen = self._method12(9, handler_value=0x99)
        self.assertEqual(seen['target'], 0x323BC)   # core handler pointer
        self.assertEqual(thumb_file(0x323BD), 0x5FBBC)

    def test_method12_null_handler_returns_minus_one(self):
        m = RawThumb(self.report)
        slot_cmd, slot_a1, slot_a2 = 0x1008, 0x100C, 0x1010
        m.word(slot_cmd, 3)          # cmd 3: handler table entry is zero
        m.word(slot_a1, 0x2000)
        m.word(slot_a2, 0)
        m.word(0x2000, 0)
        for i, v in enumerate(read_table(0x37CD0, 20)):
            m.word(0x37CD0 + 4 * i, v)
        m.r = [slot_a1, slot_a2, slot_cmd] + [0] * 13
        stop = m.run(0x5F758, {0x5F79A})
        self.assertEqual(stop, 0x5F79A)
        self.assertEqual(m.r[0], NEG1)
        self.assertEqual(m.calls, [])

    def test_method12_reads_the_table_through_the_computed_index(self):
        m, seen = self._method12(0, handler_value=5)
        self.assertEqual(seen['target'], 0x3201C)   # core handler pointer
        self.assertEqual(thumb_file(0x3201D), 0x5F81C)

    def test_fmask_slice_matches_the_model(self):
        for byte, mask, expected in ((5, 1 << 5, 5), (5, 0, NEG1), (5, 1 << 4, NEG1),
                                     (31, 1 << 31, NEG1), (32, 0xFFFFFFFF, NEG1),
                                     (2, 1 << 2, 2), (200, 1 << 8, NEG1)):
            m = RawThumb(self.report)
            m.word(0x3A660, mask)                 # the bitmask cell the helper reads
            m.r[0] = byte
            m.run(0x64620, {0x64634})
            self.assertEqual(m.r[0] & U32, expected, f'byte={byte} mask={mask:#x}')

    def test_handler9_sel0_slice(self):
        """Execute the sel0 block of handler 9 with opaque f2/g2/t/u/w hooks."""
        m = RawThumb(self.report)
        frame = 0x800
        m.r[7] = frame
        m.word(frame + 12, 2)             # preceding f2(byte1)
        m.word(frame + 16, 5)             # preceding f2(byte0)
        m.word(frame + 36, NEG1)          # preceding result initialization
        m.word(frame + 24, 5)             # byte0
        m.word(frame + 28, 2)             # byte1
        m.word(frame + 32, 0)             # sel0
        m.word(frame + 0, 0xABCD)         # arg2
        m.word(frame + 20, 0xABCD)        # copy made by the 0x5fbea store
        g2 = {5: 100, 2: 300}
        results = {}

        def hook(sim, pc, target):
            if target == 0x6463C:
                sim.r[0] = sim.r[0] if sim.r[0] in (2, 5) else NEG1
            elif target == 0x6467C:
                sim.r[0] = g2[sim.r[0]]
            elif target == 0x651B0:
                sim.r[0] = 1               # t() == 1
            elif target == 0x651C0:
                sim.r[0] = 0               # u() == 0
            elif target == 0x64554:
                results['w_arg'] = sim.r[0]
            else:
                raise ValueError(f'unexpected hook target {target:#x}')

        stop = m.run(0x5FC0A, {0x5FCBE}, hook=hook)
        self.assertEqual(stop, 0x5FCBE)
        self.assertEqual(m.r[0], 100)      # result = g2(byte0)
        self.assertEqual(results['w_arg'], 0)
        self.assertEqual(m.word(frame + 20), 0xABCD)   # arg2 copy, never consumed

    def test_handler9_sel1_slice_skips_u_when_t_differs(self):
        m = RawThumb(self.report)
        frame = 0x800
        m.r[7] = frame
        m.word(frame + 12, 2)             # preceding f2(byte1)
        m.word(frame + 16, 5)             # preceding f2(byte0)
        m.word(frame + 36, NEG1)          # preceding result initialization
        m.word(frame + 24, 5)
        m.word(frame + 28, 2)
        m.word(frame + 32, 1)              # sel1
        g2 = {5: 300, 2: 100}
        results = {}

        def hook(sim, pc, target):
            if target == 0x6463C:
                sim.r[0] = sim.r[0] if sim.r[0] in (2, 5) else NEG1
            elif target == 0x6467C:
                sim.r[0] = g2[sim.r[0]]
            elif target == 0x651B0:
                sim.r[0] = 0               # t() != 1
            elif target == 0x651C0:
                raise AssertionError('u must not be read when t()!=1')
            elif target == 0x64554:
                results['w_arg'] = sim.r[0]
            else:
                raise ValueError(f'unexpected hook target {target:#x}')

        m.run(0x5FC60, {0x5FCBE}, hook=hook)
        self.assertEqual(m.r[0], 300)      # g2(byte0)=300 > g2(byte1)=100
        self.assertEqual(results['w_arg'], 1)

    def test_handler8_sel1_slice_returns_minus_one_and_publishes(self):
        m = RawThumb(self.report)
        frame = 0x700
        m.r[7] = frame
        packed = (1 << 16) | (5 << 8) | 3  # sel1, byte1=5 valid, byte0=3 invalid
        m.word(frame + 4, 0x2000)          # handler r0: &packed
        m.word(0x2000, packed)
        obj = 0x37C84
        m.word(obj + 68, 0)
        m.word(obj + 72, 0)
        m.word(0x384D4, 0x7300)            # DMC descriptor cell -> &desc9
        m.word(0x7300 + 8, 0x710C)         # desc9+8 -> framework API
        m.word(0x710C + 56, 0x440D)        # API+0x38 enter critical
        m.word(0x710C + 60, 0x441D)        # API+0x3c exit critical

        def hook(sim, pc, target):
            if target == 0x64620:
                sim.r[0] = sim.r[0] if sim.r[0] in (2, 5) else NEG1
            else:
                sim.r[0] = 0

        stop = m.run(0x5FAE6, {0x5FBAE}, hook=hook)
        self.assertEqual(stop, 0x5FBAE)
        self.assertEqual(m.r[0], NEG1)     # sel1 keeps -1
        self.assertEqual(m.word(obj + 68), 0x440D)   # critical pair published
        self.assertEqual(m.word(obj + 72), 0x441D)
        self.assertEqual(m.word(0x2000), packed)     # buffer not mutated

    def test_poll_slice_busy_register_spins_then_exits(self):
        m = RawThumb(self.report)
        m.r[0] = 0
        m.word(0xA5863A20, 0x55)
        m.word(0xA5863A30, 0x1E00)        # busy bits initially set
        Counter = type('C', (), {'n': [0]})
        original_word = RawThumb.word

        def timed_word(address, value=None):
            if value is not None:
                return original_word(m, address, value)
            if (address & U32) == 0xA5863A30:
                Counter.n[0] += 1
                if Counter.n[0] in (3, 4):
                    original_word(m, address, 0)       # hardware clears the bits
                elif Counter.n[0] >= 5:
                    original_word(m, address, 0x1E00)  # poll 2 exit value 0xF
            return original_word(m, address)

        m.word = timed_word
        stop = m.run(0x65170, {0x651A2})
        self.assertEqual(stop, 0x651A2)
        self.assertEqual(m.r[0], 0)
        # the helper masked the control word and then set bits 9..12
        self.assertEqual(m.word(0xA5863A20), (0x55 & 0xE1FF) | 0x1E00)
        self.assertGreaterEqual(Counter.n[0], 5)     # both polls actually spun

    def test_poll_second_loop_waits_for_fifteen(self):
        m = RawThumb(self.report)
        m.r[0] = 0
        m.word(0xA5863A20, 0)
        m.word(0xA5863A30, 0)             # first poll exits immediately
        Counter = type('C', (), {'n': [0]})
        original_word = RawThumb.word

        def timed_word(address, value=None):
            if value is not None:
                return original_word(m, address, value)
            if (address & U32) == 0xA5863A30:
                Counter.n[0] += 1
                if Counter.n[0] >= 4:
                    original_word(m, address, 0x1E00)   # bits 9..12 -> 0xF
            return original_word(m, address)

        m.word = timed_word
        stop = m.run(0x65170, {0x651A2})
        self.assertEqual(stop, 0x651A2)
        self.assertGreaterEqual(Counter.n[0], 4)
        self.assertEqual(m.word(0xA5863A20), 0x1E00)

    def test_systick_read_slice(self):
        m = RawThumb(self.report)
        m.word(0xE000E018, 0x1234)
        m.r[0] = 0
        stop = m.run(0x3A3C8, stops=set())
        self.assertEqual(m.r[0], 0x1234)

    def test_wrapper_581fc_builds_subcmd8_arguments(self):
        m = RawThumb(self.report)
        m.r[13] = 0x900
        m.r[0] = 0x13579                             # packed value
        seen = {}

        def hook(sim, pc, target):
            if target == 0x58170:
                seen['args'] = (sim.r[0], sim.r[1], sim.r[2], sim.r[3])
                seen['slot_addr'] = sim.r[1]
                seen['slot'] = sim.word(sim.r[1])
                sim.r[0] = 0
            else:
                raise ValueError(f'unexpected target {target:#x}')

        stop = m.run(0x581FC, {0x5820E}, hook=hook)
        self.assertEqual(stop, 0x5820E)
        self.assertEqual(seen['args'][0], 9)          # plugin 9
        self.assertEqual(seen['args'][2], 0)          # a2 = 0 for subcmd 8
        self.assertEqual(seen['args'][3], 8)          # subcommand 8
        self.assertEqual(seen['slot'], 0x13579)       # r1 -> wrapper sp+4
        self.assertLess(seen['slot_addr'], 0x900)     # below the initial sp
        self.assertEqual(m.word(seen['slot_addr']), 0x13579)  # stored on the frame

    def test_wrapper_58214_builds_subcmd9_arguments(self):
        m = RawThumb(self.report)
        m.r[13] = 0x900
        m.r[0] = 0x2468A
        m.r[1] = 0x777                               # the 0x5adb0 helper result
        seen = {}

        def hook(sim, pc, target):
            if target == 0x58170:
                seen['args'] = (sim.r[0], sim.r[1], sim.r[2], sim.r[3])
                seen['slot_addr'] = sim.r[1]
                sim.r[0] = 0

        stop = m.run(0x58214, {0x58226}, hook=hook)
        self.assertEqual(stop, 0x58226)
        self.assertEqual(seen['args'][0], 9)
        self.assertEqual(seen['args'][2], 0x777)      # a2 = helper result by value
        self.assertEqual(seen['args'][3], 9)          # subcommand 9
        self.assertEqual(m.word(seen['slot_addr']), 0x2468A)

    def test_relay_58170_plumbing(self):
        m = RawThumb(self.report)
        m.r[0] = 9
        m.r[1] = 0x900                               # &value
        m.r[2] = 0x777                               # arg2
        m.r[3] = 9                                   # cmd
        m.r[13] = 0x600
        m.word(0x2FBF0, 0x72A0)                      # DVFS descriptor
        m.word(0x72A0 + 8, 0x710C)                   # API installed at desc+8
        m.word(0x710C + 28, 0x4B05)                  # API+28 -> 0x38b04
        seen = {}

        def hook(sim, pc, target):
            seen['target'] = target
            seen['args'] = (sim.r[0], sim.r[1], sim.r[2], sim.r[3], sim.word(sim.r[13]))
            sim.r[0] = 0x42

        stop = m.run(0x58170, {0x58192}, hook=hook)
        self.assertEqual(stop, 0x58192)
        self.assertEqual(seen['target'], 0x4B04)     # core Thumb ptr, bit0 cleared
        self.assertEqual(thumb_file(0x4B05), 0x38B04)  # = file 0x38b04
        self.assertEqual(seen['args'][0], 0x72A0)    # caller descriptor from the cell
        self.assertEqual(seen['args'][1], 9)         # plugin id
        frame20, frame16 = seen['args'][2], seen['args'][3]
        frame12 = seen['args'][4]
        # r2/r3/stack point at the relay frame slots holding the wrapper arguments
        self.assertEqual(m.word(frame20), 0x900)     # slot holds &value
        self.assertEqual(m.word(frame16), 0x777)     # slot holds arg2
        self.assertEqual(m.word(frame12), 9)         # slot holds the subcommand
        self.assertNotEqual(frame20, 0x900)          # distinct addresses
        self.assertEqual(m.r[0], 0x42)               # return propagated untouched


class ArgChainTests(unittest.TestCase):
    """The three-level pointer plumbing executed end to end on raw words."""

    def test_wrapper_relay_method_handler_chain(self):
        report = load()
        packed = 0x13579

        # stage 1: wrapper 0x581fc builds (plugin=9, a1=&value, a2=0, a3=8)
        m1 = RawThumb(report)
        m1.r[13] = 0x900
        m1.r[0] = packed
        relay_args = {}

        def wrapper_hook(sim, pc, target):
            relay_args['r0'] = sim.r[0]
            relay_args['r1'] = sim.r[1]
            relay_args['r2'] = sim.r[2]
            relay_args['r3'] = sim.r[3]
            relay_args['slot'] = sim.word(sim.r[1])
            sim.r[0] = 0

        m1.run(0x581FC, {0x5820E}, hook=wrapper_hook)
        self.assertEqual(relay_args['r0'], 9)
        self.assertEqual(relay_args['r2'], 0)
        self.assertEqual(relay_args['r3'], 8)
        self.assertEqual(relay_args['slot'], packed)

        # stage 2: relay 0x58170 frames the slots and calls 0x38b04
        m2 = RawThumb(report)
        m2.r[0], m2.r[1], m2.r[2], m2.r[3] = (relay_args['r0'], relay_args['r1'],
                                              relay_args['r2'], relay_args['r3'])
        m2.r[13] = 0x600
        m2.word(0x2FBF0, 0x72A0)
        m2.word(0x72A0 + 8, 0x710C)
        m2.word(0x710C + 28, 0x4B05)
        relay38 = {}

        def relay_hook(sim, pc, target):
            relay38['r0'] = sim.r[0]
            relay38['r1'] = sim.r[1]
            relay38['r2'] = sim.r[2]
            relay38['r3'] = sim.r[3]
            relay38['stack'] = sim.word(sim.r[13])
            sim.r[0] = 0

        m2.run(0x58170, {0x58192}, hook=relay_hook)
        self.assertEqual(relay38['r0'], 0x72A0)
        self.assertEqual(relay38['r1'], 9)
        slot_a1, slot_a2, slot_a3 = relay38['r2'], relay38['r3'], relay38['stack']
        self.assertEqual(m2.word(slot_a1), relay_args['r1'])   # &value
        self.assertEqual(m2.word(slot_a2), 0)                  # a2 value
        self.assertEqual(m2.word(slot_a3), 8)                  # cmd

        # stage 3: method+12 dereferences the slots and calls the handler
        m3 = RawThumb(report)
        m3.r = [slot_a1, slot_a2, slot_a3] + [0] * 12 + [0x400, 0]
        m3.word(slot_a1, relay_args['r1'])   # the slot holds &value
        m3.word(slot_a2, 0)                  # the slot holds a2
        m3.word(slot_a3, 8)                  # the slot holds the subcommand
        m3.word(relay_args['r1'], packed)    # the buffer holds the packed word
        for i, v in enumerate(read_table(0x37CD0, 20)):
            m3.word(0x37CD0 + 4 * i, v)
        handler_seen = {}

        def handler_hook(sim, pc, target):
            handler_seen['target'] = target
            handler_seen['r0'] = sim.r[0]
            handler_seen['r1'] = sim.r[1]
            handler_seen['value'] = sim.word(sim.r[0])
            sim.r[0] = 0x5A

        m3.run(0x5F758, {0x5F79A}, hook=handler_hook)
        self.assertEqual(handler_seen['target'], 0x322DC)      # core handler ptr
        self.assertEqual(handler_seen['r0'], relay_args['r1'])  # &value, one deref down
        self.assertEqual(handler_seen['r1'], 0)                 # a2 by value
        self.assertEqual(handler_seen['value'], packed)         # packed word
        self.assertEqual(m3.r[0], 0x5A)                         # return propagated
        self.assertEqual(m3.word(relay_args['r1']), packed)     # buffer not mutated

    def test_arg2_is_a_copy_not_a_pointer(self):
        r = handler9((1 << 16) | 0x502, (1 << 2) | (1 << 5), 9, 8, 1, 0)
        self.assertTrue(r['arg2_stored_but_never_read'])

    def test_handler_does_not_mutate_the_argument_buffer(self):
        report = load()
        m = RawThumb(report)
        slot_cmd, slot_a1, slot_a2 = 0x1008, 0x100C, 0x1010
        m.word(slot_cmd, 8)
        m.word(slot_a1, 0x2000)
        m.word(slot_a2, 0)
        m.word(0x2000, 0xBEEF)
        for i, v in enumerate(read_table(0x37CD0, 20)):
            m.word(0x37CD0 + 4 * i, v)
        m.r = [slot_a1, slot_a2, slot_cmd] + [0] * 12 + [0x400, 0]

        def hook(sim, pc, target):
            sim.r[0] = 1

        m.run(0x5F758, {0x5F79A}, hook=hook)
        self.assertEqual(m.word(0x2000), 0xBEEF)
        stores_to_buffer = [s for s in m.stores if (s[1] & U32) == 0x2000]
        self.assertEqual(stores_to_buffer, [])


class ReportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = load()

    def test_report_identity(self):
        self.assertEqual(self.report['source_base'], '5ec3ea2a2a8a0e72975bb97ee09b3d3e5f6b2079')
        self.assertEqual(self.report['sboot_sha256'],
                         'a11c3da07011384415cc07f2b9c2c582ea608b286389a5fbd4bad5965fc87a91')

    def test_chain_links_present(self):
        self.assertEqual(self.report['dmc_interface']['method12']['file'], '0x5f758')
        self.assertEqual(self.report['handlers']['subcmd8']['file'], '0x5fadc')
        self.assertEqual(self.report['handlers']['subcmd9']['file'], '0x5fbbc')
        self.assertIn('M32[core0x2fbf0]', self.report['dvfs_side']['relay_58170'])
        self.assertIn('0x38b04', self.report['dvfs_side']['relay_58170'])

    def test_frontiers_recorded(self):
        self.assertTrue(any('0x3a660' in f for f in self.report['frontiers']))
        self.assertTrue(any('slot 47' in f for f in self.report['frontiers']))
        self.assertFalse(self.report['firmware_executed'])
        self.assertFalse(self.report['slot47_resolved'])

    def test_polls_recorded_with_masks_and_no_timeout(self):
        polls = self.report['polls']
        self.assertEqual(len(polls), 3)
        for p in polls[:2]:
            self.assertEqual(p['address'], '0xa5863a30')
            self.assertIn('none in the analyzed path', p['timeout'])

    def test_gnu_round_trip_stats(self):
        g = self.report['gnu']
        self.assertGreater(g['instructions'], 1400)
        self.assertGreater(g['relative_branches'], 100)
        self.assertGreater(g['literal_loads'], 40)
        self.assertGreaterEqual(g['selected'], 100)



class AuditRegressionTests(unittest.TestCase):
    """Independent checks for defects missed by the submitted 65 tests."""

    def test_relay_error_precedence_matches_raw_words(self):
        import itertools
        for count, enabled, method, mask in itertools.product((9,13),(0,1),(0,0x31f59),(0,0x80)):
            m=RawThumb(load());m.r[0:4]=[0x72a0,9,0x1000,0x1004];m.r[13]=0x10000
            for a,v in ((0x8014,count),(0x8000,0x7150),(0x8010,0),(0x72a0,7),(0x7320,enabled),(0x730c,0x37c40),(0x37c4c,method),(0x7314,mask)):m.word(a,v)
            def log(sim,pc,target):
                self.assertEqual(target,0x38684)
                for r in (0,1,2,3,12):sim.r[r]=0xcccccccc
            stop=m.run(0x38b04,{0x38b74,0x38b4c},log)
            g=relay_gates(count,enabled,method,mask,7)
            if stop==0x38b74:self.assertTrue(g['allowed'])
            else:
                want=10 if g['fail_return_10'] else (-11 & U32)
                self.assertEqual(m.r[0],want)
                self.assertEqual(g['fail_return_neg11'],want==(-11 & U32))
                self.assertFalse(g['fail_return_10'] and g['fail_return_neg11'])

    def test_register_shift_uses_low_byte_of_caller_id(self):
        for caller in (0,7,31,32,255,256,263,287,288,U32):
            m=RawThumb(load());m.r[0]=caller;m.r[3]=U32;m.r[2]=1
            m.run(0x38b66,{0x38b6a})
            self.assertEqual(relay_gates(13,1,1,U32,caller)['allowed'],not m.z)

    def test_unknown_memory_is_not_a_zero_word_byte_or_halfword(self):
        for width in (1,2,4):
            m=RawThumb(load())
            with self.assertRaises(KeyError):m._load(0x3a660,byte=width==1,half=width==2)
        m.word(0x1000,0);self.assertEqual(m.word(0x1000),0)
        with self.assertRaises(KeyError):m.word(0x1001)

    def test_dispatch_wrap_alias_and_unknown_result_match_raw_words(self):
        h={i:v for i,v in enumerate(read_table(0x37cd0,20))}
        for cmd in (0,0x40000000,0x80000000,0xc0000000):
            self.assertEqual(dispatch(cmd,h)['handler'],h[0])
            m=RawThumb(load());m.r[0:3]=[0x1000,0x1004,0x1008];m.r[13]=0x10000
            for a,v in ((0x1000,0x2000),(0x1004,17),(0x1008,cmd),(0x37cd0,h[0])):m.word(a,v)
            targets=[]
            def hook(sim,pc,target):targets.append(target);sim.r[0]=0x42
            m.run(0x5f758,{0x5f79a},hook)
            self.assertEqual(targets,[h[0]&~1]);self.assertEqual(m.r[0],0x42)
        self.assertIsNone(dispatch(U32,h)['return_value']);self.assertFalse(dispatch(U32,h)['memory_known'])
        m.word(0x1008,U32)
        with self.assertRaises(KeyError):m.run(0x5f758,{0x5f79a},hook)

    def test_unknown_h_is_not_a_claimed_failure(self):
        r=handler8(0x305,1<<5)
        self.assertIn('h64658',r['path']);self.assertIsNone(r['result'])
        self.assertEqual(handler8(0x305,1<<5,NEG1)['result'],NEG1)

    def test_handler9_full_path_arg2_is_dead_with_clobbering_hooks(self):
        import itertools
        for sel,arg2 in itertools.product(range(4),(0,1,0x12345678,U32)):
            m=RawThumb(load());m.r[0:2]=[0x2000,arg2];m.r[13]=0x10000
            packed=(sel<<16)|0x205;m.word(0x2000,packed);seen=[]
            def hook(sim,pc,target):
                a=sim.r[0];seen.append((target,a))
                if target==0x6463c:ret=a
                elif target==0x6467c:ret={5:100,2:300}[a]
                elif target==0x651b0:ret=1
                elif target==0x651c0:ret=0
                elif target==0x64554:ret=0x7777
                else:raise AssertionError(hex(target))
                for r in (1,2,3,12):sim.r[r]=0xcccccccc
                sim.r[0]=ret
            m.run(0x5fbbc,{0x5fcbe},hook)
            want=handler9(packed,(1<<2)|(1<<5),100,300,1,0)
            self.assertEqual(m.r[0],want['result']);frame=0x10000-12-44
            self.assertEqual(m.word(frame+20),arg2)
            self.assertFalse(any(pc>0x5fbea and pc<0x5fcbe and a in (frame,frame+20) for pc,a,w in m.reads))
            self.assertEqual(m.word(0x2000),packed)
            self.assertEqual([a for t,a in seen if t==0x64554],[] if sel>=2 else [0])

    def test_host_budget_is_not_a_firmware_timeout(self):
        m=RawThumb(load());m.word(0xa5863a20,0);m.word(0xa5863a30,0x1e00)
        with self.assertRaisesRegex(ValueError,'host slice budget'):m.run(0x65170,{0x651a2},budget=100)

    def test_push_pop_preserve_lr_and_stack(self):
        m=RawThumb(load());m.r[13]=0x10000;m.r[14]=0x1235;m.r[8]=0x8888
        m.run(0x5f758,{0x5f75a});self.assertEqual(m.word(0xfffc),0x1235)
        self.assertEqual(m.run(0x5f79a,set()),0x1234);self.assertEqual(m.r[13],0x10000)

    def test_movw_preserves_flags(self):
        m=RawThumb(load());m.n,m.z,m.c,m.v=True,True,False,True
        m.run(0x38b06,{0x38b0a});self.assertEqual((m.n,m.z,m.c,m.v),(True,True,False,True))

    def test_unimplemented_asr_fails_instead_of_being_cmp(self):
        m=RawThumb(load());m.code[0]=bytes.fromhex('0841')
        with self.assertRaisesRegex(ValueError,'ASR'):m.run(0,{2})

    def test_add_carry_and_overflow_from_encoded_words(self):
        for a,result,carry,overflow in ((U32,0,True,False),(0x7fffffff,0x80000000,False,True)):
            m=RawThumb(load());m.code[0]=bytes.fromhex('0130');m.r[0]=a;m.run(0,{2})
            self.assertEqual((m.r[0],m.c,m.v),(result,carry,overflow))

    def test_shift_carry_from_encoded_words(self):
        for count,result,carry in ((0,0x80000001,False),(1,2,True),(32,0,True),(33,0,False),(256,0x80000001,False)):
            m=RawThumb(load());m.code[0]=bytes.fromhex('8840');m.r[0]=0x80000001;m.r[1]=count;m.run(0,{2})
            self.assertEqual((m.r[0],m.c),(result,carry))

    def test_runtime_roots_are_explicit_conditions(self):
        report=load()
        self.assertFalse(any('no writer anywhere' in x for x in report['frontiers']))
        self.assertTrue(any('initializers' in x and 'preserved' in x for x in report['conditions']))
        self.assertIsInstance(report['dmc_interface']['handler_words']['8'],int)


if __name__ == '__main__':
    unittest.main()
