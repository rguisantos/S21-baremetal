import json
from pathlib import Path
import random
import unittest

from test_newtime_dmc_method12 import RawThumb
from test_newtime_dmc_loader import fixture as loader_fixture

ROOT=Path(__file__).resolve().parent.parent
REPORT=json.loads((ROOT/'docs/references/newtime-dmc-table-services-hzc2.json').read_text())
S=0x381c8;P=0x90000;G0=0x80000000;G4=0x90000000;U32=0xffffffff


def overlay(m):
    for row in REPORT['witnesses']:m.code[int(row['pc'],16)]=bytes.fromhex(row['bytes'])
    m.literals.update({int(a,16):v for a,v in REPORT['literals'].items()})
    return m


def records(m,p,items):
    for i,(value,ident) in enumerate(items):
        for j,b in enumerate((value,ident,0xaa,0x55)):m.mem[(p+4*i+j)&U32]=b


def fixture(items=()):
    m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001
    m.mem[S]=len(items);m.word(S+8,P);m.mem[S+0x209]=2;m.mem[S+0x229]=0
    records(m,P,items)
    for i,v in enumerate(REPORT['consumer']['filter_ids']):m.mem[0x3801c+i]=v
    for a,v in ((0x37fb4+16,0x369a5),(0x37fb4+40,0x369d1),
                (0x37d40+100,0x33ded),(0x37d40+104,0x34471),
                (0x37df8,G0),(0x37df8+16,G4),(G0,0x87654321)):
        m.word(a,v)
    m.read_result=7;m.external_reads=[];return m


def nested(m,pc,to):
    ret=pc+len(m.code[pc]);m.r[14]=ret|1
    mapping={0x369a4:0x641a4,0x369d0:0x641d0,0x33dec:0x615ec,
        0x63f94:0x63f94,0x63fb0:0x63fb0,0x60c6c:0x60c6c,0x64a64:0x64a64}
    if to in mapping:
        if m.run(mapping[to],set(),nested)!=ret:raise ValueError('wrong nested return')
    elif to==0x34470:
        m.external_reads.append(tuple(m.r[:3]));m.r[0]=m.read_result
        for r in (1,2,3,12):m.r[r]=0xcccccccc
    else:raise ValueError(f'unmodeled frontier {to:#x}')


def payloads(m):return [v for pc,a,v in m.stores if pc==0x6162c]


def published_ids(m):return [(v>>20)&127 for pc,a,v in m.stores if pc==0x61628]


class TableServiceTests(unittest.TestCase):
    def test_getter_first_match_and_miss(self):
        for ident,want in ((11,7),(3,99),(4,U32)):
            m=fixture([(7,11),(8,11),(99,3)]);m.r[0]=ident;m.run(0x641a4,set())
            self.assertEqual(m.r[0],want);self.assertTrue(all(p==0x641a6 for p,a,v in m.stores));self.assertEqual(m.calls,[])

    def test_setter_updates_all_duplicates_low8_and_preserves_padding(self):
        m=fixture([(7,11),(8,11),(99,3)]);m.r[:2]=[11,0x1234abcd];m.run(0x641d0,set())
        self.assertEqual([m.mem[P+4*i] for i in range(3)],[0xcd,0xcd,99])
        self.assertEqual([m.mem[P+i] for i in (1,2,3)],[11,0xaa,0x55])
        self.assertEqual(m.r[0],11);self.assertEqual(m.calls,[])

    def test_full_id_input_is_not_truncated_to_a_byte(self):
        for method in (0x641a4,0x641d0):
            m=fixture([(7,11)]);m.r[:2]=[0x10b,0xff];m.run(method,set())
            self.assertEqual(m.r[0],U32 if method==0x641a4 else 0x10b)
            self.assertEqual(m.mem[P],7)

    def test_empty_table_and_setter_miss_do_not_encode_match_count(self):
        for items in ([],[(7,11)]):
            m=fixture(items);m.r[:2]=[3,0x12];m.run(0x641d0,set())
            self.assertEqual(m.r[0],3);self.assertTrue(all(p==0x641d0 for p,a,v in m.stores))
        m=fixture();m.r[0]=3;m.run(0x641a4,set());self.assertEqual(m.r[0],U32)

    def test_getter_captures_count_and_pointer_before_scanning(self):
        m=fixture([(7,11),(8,3)]);old=m._load
        def read(a,byte=False,half=False):
            if m.pc==0x641b8:m.mem[S]=0;m.word(S+8,0xbad00000)
            return old(a,byte=byte,half=half)
        m._load=read;m.r[0]=3;m.run(0x641a4,set())
        self.assertEqual(m.r[0],8)
        self.assertEqual(sum(a==S for p,a,n in m.reads),1)
        self.assertEqual(sum(a==S+8 for p,a,n in m.reads),1)

    def test_setter_alias_to_count_can_grow_the_iteration_bound(self):
        m=fixture();m.mem[S]=1;m.mem[S+1]=11;m.word(S+8,S)
        records(m,S+4,[(0x77,11)]);m.r[:2]=[11,2];m.run(0x641d0,set())
        self.assertEqual((m.mem[S],m.mem[S+4]),(2,2))
        self.assertEqual(sum(p==0x641e4 for p,a,v in m.stores),2)

    def test_setter_alias_to_count_can_stop_after_first_store(self):
        m=fixture();m.mem[S]=3;m.mem[S+1]=11;m.word(S+8,S)
        records(m,S+4,[(0x77,11)]);m.r[:2]=[11,0];m.run(0x641d0,set())
        self.assertEqual((m.mem[S],m.mem[S+4]),(0,0x77));self.assertEqual(sum(p==0x641e4 for p,a,v in m.stores),1)

    def test_setter_pointer_is_captured_even_when_a_store_changes_its_cell(self):
        m=fixture();m.mem[S]=2;m.word(S+8,S+8);records(m,S+12,[(9,0x81)])
        m.r[:2]=[0x81,7];m.run(0x641d0,set())
        self.assertEqual(m.mem[S+12],7);self.assertEqual(m.word(S+8),0x38107)

    def test_missing_record_preserves_prior_setter_effects(self):
        m=fixture([(7,11),(8,11)]);del m.mem[P+5];m.r[:2]=[11,9]
        with self.assertRaises(KeyError):m.run(0x641d0,set())
        self.assertEqual(m.mem[P],9);self.assertEqual(m.mem[P+4],8)

    def test_random_getter_and_setter_duplicates(self):
        rng=random.Random(0x641a4)
        for _ in range(80):
            items=[(rng.randrange(256),rng.randrange(16)) for i in range(rng.randrange(20))]
            ident=rng.randrange(16);value=rng.randrange(1<<32);m=fixture(items);m.r[:2]=[ident,value]
            m.run(0x641d0,set());self.assertEqual(m.r[0],ident)
            expected=[(value&255 if ident==i else v,i) for v,i in items]
            self.assertEqual([m.mem[P+4*j] for j in range(len(items))],[v for v,i in expected])
            m.r[0]=ident;m.r[14]=0xdead0001;m.run(0x641a4,set())
            self.assertEqual(m.r[0],next((v for v,i in expected if i==ident),U32))

    def test_loader_tail_only_stages_values_then_consumer_publishes_them(self):
        m=overlay(loader_fixture(control2=(1<<24)|5|(1<<26)|(3<<8)))
        table=0x3a600+0x1700+32*7
        items=[(0x80,11),(0x11,41),(0,18),(0xa0,17),(0xf0,3),(0x70,3),(0xaa,16),(0x99,33)]
        records(m,table,items);m.run(0x647ac,set(),nested)
        self.assertEqual(payloads(m),[])
        self.assertEqual((m.mem[table],m.mem[table+8]),(0x85,3))
        # Publisher roots are provided only for the separate consumer invocation.
        m.word(0x37d40+100,0x33ded);m.word(0x37df8,G0);m.word(0x37df8+16,G4);m.word(G0,0)
        m.r[0]=0;m.r[14]=0xdead0001;m.run(0x63fb0,set(),nested)
        self.assertEqual(published_ids(m),[11,41,18,17,3,3,33])
        self.assertEqual(payloads(m),[0x85,0x11,3,0xa0,0xf0,0x70,0x99])

    def test_publisher_channel4_reads_entry0_and_writes_distinct_entry4(self):
        m=fixture();m.r[:4]=[4,0xff,0xff,0xdeadbeef];m.run(0x615ec,set())
        config=(((0x87654321&0xcfffffff)|(3<<28))&0xf80fffff)|(127<<20)
        self.assertEqual([(a,v) for p,a,v in m.stores if p!=0x615ec],[(G4,config),(G4+56,22),(G4+8,0xdeadbeef),(G4+4,16)])
        self.assertEqual(m.word(G0),0x87654321);self.assertEqual(m.r[0],0)
        self.assertFalse(any(a in (G4+4,G4+8,G4+56) for p,a,n in m.reads))

    def test_invalid_publisher_channel_returns_minus1_without_memory(self):
        for channel in (5,255,0x80000000,U32):
            m=RawThumb(REPORT);m.r[13]=0x20000;m.r[14]=0xdead0001;m.r[0]=channel
            m.run(0x615ec,set());self.assertEqual(m.r[0],U32)
            self.assertFalse(any(p in range(0x615f2,0x61632) for p,a,n in m.reads))

    def test_consumer_skips16_and_uses_captured_first18_for_duplicates(self):
        m=fixture([(0x21,18),(0x99,18),(0xaa,16)]);m.mem[S+0x229]=1;m.r[0]=0
        def hook(sim,pc,to):
            nested(sim,pc,to)
            if pc==0x64016:sim.mem[P]=0x80
        m.run(0x63fb0,set(),hook)
        self.assertEqual(published_ids(m),[18,18]);self.assertEqual(payloads(m),[0x31,0x31])

    def test_consumer_reloads_pointer_or_count_after_a_publication(self):
        for change in ('count','pointer'):
            m=fixture([(1,11),(2,17)]);m.r[0]=0;records(m,P+0x100,[(3,99),(0xcc,3)])
            def hook(sim,pc,to):
                nested(sim,pc,to)
                if pc==0x640ce and len(payloads(sim))==1:
                    if change=='count':sim.mem[S]=1
                    else:sim.word(S+8,P+0x100)
            m.run(0x63fb0,set(),hook)
            self.assertEqual(payloads(m),[1] if change=='count' else [1,0xcc])

    def test_id18_accumulator_keeps_bit4_after_flag_clears(self):
        for flags,want in (([1,0],[0x31,0x31]),([0,1,0],[0x21,0x31,0x31])):
            m=fixture([(0x21 if i==0 else 0x99,18) for i in range(len(flags))])
            m.mem[S+0x229]=flags[0];m.r[0]=0
            def hook(sim,pc,to):
                nested(sim,pc,to)
                count=len(payloads(sim))
                if pc==0x64016 and count<len(flags):sim.mem[S+0x229]=flags[count]
            m.run(0x63fb0,set(),hook)
            self.assertEqual(payloads(m),want)
            accumulated=[(a,v) for pc,a,v in m.stores if pc==0x64004]
            self.assertEqual(len(accumulated),1);self.assertEqual(accumulated[0][1],0x31)
            self.assertEqual(m.word(accumulated[0][0]),0x31)

    def test_nonzero_argument_enables_ordinary_id_filter(self):
        for argument,want in ((0,[11,13]),(1,[11])):
            m=fixture([(7,11),(8,13)]);m.r[0]=argument;m.run(0x63fb0,set(),nested)
            self.assertEqual(published_ids(m),want)

    def test_id21_uses_low3_of_read_return_as_guard(self):
        for result,want in ((0,[]),(6,[]),(7,[0x99]),(U32,[0x99])):
            m=fixture([(0x99,21)]);m.r[0]=0;m.read_result=result;m.run(0x63fb0,set(),nested)
            self.assertEqual(m.external_reads,[(0,1,21)]);self.assertEqual(payloads(m),want)

    def test_nominal_method0_calls_the_selected_consumer_after_id16_publish(self):
        m=fixture([(0xa0,16),(7,11)]);m.r[:2]=[3,1];m.run(0x640e8,set(),nested)
        self.assertEqual(published_ids(m),[16,11]);self.assertEqual(payloads(m),[0xad,7])
        self.assertEqual(m.mem[P],0xa0)

    def test_consumer_return_depends_on_path_not_an_aggregate_status(self):
        for items,want in (([],U32),([(7,16)],U32),([(7,11)],0)):
            m=fixture(items);m.r[0]=0;m.run(0x63fb0,set(),nested);self.assertEqual(m.r[0],want)

    def test_adcs_raw_word_carry_overflow_and_input_carry(self):
        for a,b,carry,value,c,v in ((1,U32,0,0,True,False),(0,0,1,1,False,False),
            (0x7fffffff,0,1,0x80000000,False,True),(0x80000000,0xffffffff,0,0x7fffffff,True,True)):
            m=RawThumb(REPORT);m.r[1]=a;m.r[3]=b;m.c=bool(carry)
            m.run(0x63fc4,{0x63fc6});self.assertEqual((m.r[1],m.c,m.v),(value,c,v))
