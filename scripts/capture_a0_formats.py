#!/usr/bin/env python3
"""Bounded Android v3/DT-table inventory and AVB hash checks, without signing."""
import hashlib
import struct
import zlib

MAX_IMAGE=128*1024*1024


def require(condition,message):
    if not condition:raise ValueError(message)


def digest(data):return hashlib.sha256(data).hexdigest()


def align(n,page):return (n+page-1)&~(page-1)


def avb(data):
    """Verify descriptor hashes only. No RSA/key trust or boot authorization."""
    require(64<=len(data)<=MAX_IMAGE,'image size outside bound')
    if data[-64:-60]!=b'AVBf':return None
    _,major,minor,original,offset,size=struct.unpack_from('>4sIIQQQ',data,len(data)-64)
    require(major==1 and minor==0 and not any(data[-28:]),'unsupported AVB footer')
    require(0<original<=offset and 256<=size<=1024*1024 and offset+size<=len(data)-64,'AVB footer extent differs')
    meta=data[offset:offset+size]
    require(meta[:4]==b'AVB0','missing vbmeta magic')
    auth,aux=struct.unpack_from('>QQ',meta,12)
    do,ds=struct.unpack_from('>QQ',meta,96)
    require(256+auth+aux==size and do+ds<=aux,'vbmeta block/descriptor bounds differ')
    pos=256+auth+do;end=pos+ds;rows=[]
    for _ in range(128):
        if pos==end:break
        require(pos+16<=end,'truncated AVB descriptor')
        tag,length=struct.unpack_from('>QQ',meta,pos);finish=pos+16+length
        require(length%8==0 and finish<=end,'AVB descriptor extent differs')
        if tag==2:
            require(length>=116,'short AVB hash descriptor')
            image_size=struct.unpack_from('>Q',meta,pos+16)[0]
            algorithm=meta[pos+24:pos+56].split(b'\0')[0].decode('ascii')
            nl,sl,dl,flags=struct.unpack_from('>4I',meta,pos+56)
            require(algorithm in ('sha256','sha512') and dl==hashlib.new(algorithm).digest_size,'unsupported hash/digest size')
            require(nl<=1024 and sl<=1024 and 132+nl+sl+dl<=16+length and not any(meta[pos+72:pos+132]),'AVB hash fields differ')
            require(0<image_size<=len(data),'AVB hash image extent differs')
            payload=meta[pos+132:finish];name=payload[:nl].decode('ascii');salt=payload[nl:nl+sl];wanted=payload[nl+sl:nl+sl+dl]
            h=hashlib.new(algorithm);h.update(salt);h.update(memoryview(data)[:image_size])
            rows.append(dict(partition=name,image_size=image_size,algorithm=algorithm,flags=flags,
                stored_digest=wanted.hex(),computed_digest=h.hexdigest(),matches=h.digest()==wanted,
                extent_matches_footer=image_size==original,extent_before_vbmeta=image_size<=offset))
        pos=finish
    else:raise ValueError('AVB descriptor budget exceeded')
    require(pos==end,'AVB descriptor area not exhausted')
    return dict(offset=offset,bytes=size,original_image_size=original,vbmeta_sha256=digest(meta),
        footer_sha256=digest(data[-64:]),hash_descriptors=rows,
        all_hashes_match=bool(rows) and all(r['matches'] and r['extent_matches_footer'] and r['extent_before_vbmeta'] for r in rows),
        signature_verified=False,trusted_key_established=False)


def layout(data):
    """Return a complete non-overlapping partition of the supplied file bytes."""
    require(type(data) is bytes and 64<=len(data)<=MAX_IMAGE,'image size/type outside bound')
    parts=[];cursor=0
    def part(name,start,end,kind):
        nonlocal cursor
        require(start==cursor and start<=end<=len(data),'layout gap/overlap/truncation')
        if end>start:parts.append(dict(name=name,start=start,end=end,kind=kind,bytes=end-start,sha256=digest(data[start:end])))
        cursor=end
    if data[:8]==b'ANDROID!':
        require(len(data)>=1580,'short boot header')
        kernel,ramdisk,_,hs=struct.unpack_from('<4I',data,8);version=struct.unpack_from('<I',data,40)[0]
        require(version==3 and hs==1580 and not any(data[24:40]),'only boot v3 supported')
        kind='boot_v3';page=4096
        part('header',0,hs,'header');part('header_padding',hs,page,'padding')
        part('kernel',cursor,cursor+kernel,'payload');part('kernel_padding',cursor,align(cursor,page),'padding')
        part('ramdisk',cursor,cursor+ramdisk,'payload');part('ramdisk_padding',cursor,align(cursor,page),'padding')
    elif data[:8]==b'VNDRBOOT':
        require(len(data)>=2112,'short vendor boot header')
        version,page,_,_,ramdisk=struct.unpack_from('<5I',data,8);hs,dtb=struct.unpack_from('<II',data,2096)
        require(version==3 and hs==2112 and page in (2048,4096,8192,16384),'only vendor boot v3 supported')
        kind='vendor_boot_v3'
        part('header',0,hs,'header');part('header_padding',hs,align(hs,page),'padding')
        part('ramdisk',cursor,cursor+ramdisk,'payload');part('ramdisk_padding',cursor,align(cursor,page),'padding')
        part('dtb',cursor,cursor+dtb,'payload');part('dtb_padding',cursor,align(cursor,page),'padding')
    elif data[:4]==b'\xd7\xb7\xab\x1e':
        require(len(data)>=32,'short DT table')
        _,total,hs,es,count,entries,page,version=struct.unpack_from('>8I',data)
        require(version==0 and hs==32 and es==32 and 0<count<=64 and hs<=entries and entries+count*es<=total<=len(data),'DT table bounds/version differ')
        kind='dt_table_v0';table_end=entries+count*es
        rows=[struct.unpack_from('>8I',data,entries+i*es)[:2] for i in range(count)]
        require(all(n>=40 and table_end<=o and o+n<=total for n,o in rows),'DT entry bounds differ')
        require(len({o for n,o in rows})==count,'duplicate DT entry offset')
        part('header',0,hs,'header');part('header_gap',hs,entries,'padding');part('entries',entries,table_end,'header')
        for index,(n,o) in sorted(enumerate(rows),key=lambda item:item[1][1]):
            require(o>=cursor,'overlapping DT entries')
            part(f'gap_before_{index}',cursor,o,'padding')
            require(data[o:o+4]==b'\xd0\x0d\xfe\xed' and struct.unpack_from('>I',data,o+4)[0]==n,'DT entry FDT header size/magic differs')
            part(f'dtb_{index}',cursor,o+n,'payload')
        part('table_padding',cursor,total,'padding')
    else:raise ValueError('unsupported image magic')
    body_end=cursor;verification=avb(data)
    if verification:
        offset,size=verification['offset'],verification['bytes']
        part('opaque_extension',cursor,offset,'opaque')
        part('vbmeta',cursor,offset+size,'opaque');part('tail_padding',cursor,len(data)-64,'padding');part('avb_footer',cursor,len(data),'opaque')
    else:part('opaque_tail',cursor,len(data),'opaque')
    require(cursor==len(data),'layout not exhaustive')
    return dict(kind=kind,bytes=len(data),sha256=digest(data),page_size=page,body_end=body_end,
        parts=parts,avb=verification,dtb_contents_interpreted=False)


def reassemble(parts,pieces,total):
    """No-change reconstruction only: each piece must match its recorded hash."""
    require(type(total) is int and 0<total<=MAX_IMAGE,'reassembly size outside bound')
    require(len(pieces)==len(parts),'piece count differs')
    out=bytearray();names=set()
    for row,piece in zip(parts,pieces):
        require(row['name'] not in names and row['start']==len(out) and row['end']==row['start']+row['bytes'],'piece layout differs')
        require(len(piece)==row['bytes'] and digest(piece)==row['sha256'],'piece bytes differ')
        names.add(row['name']);out.extend(piece)
    require(len(out)==total,'incomplete reassembly')
    return bytes(out)


def compare(before,after):
    a,b=layout(before),layout(after)
    semantic={p['name']:(p['bytes'],p['sha256']) for p in a['parts'] if p['kind'] in ('header','payload')}
    actual={p['name']:(p['bytes'],p['sha256']) for p in b['parts'] if p['kind'] in ('header','payload')}
    metadata_same=bool(a['avb'] and b['avb'] and a['avb']['vbmeta_sha256']==b['avb']['vbmeta_sha256'])
    ranges=[];range_count=0;changed=0;last=-2
    for i,(x,y) in enumerate(zip(before,after)):
        if x!=y:
            changed+=1
            if last!=i-1:
                range_count+=1
                if range_count<=32:ranges.append([i,i+1])
            elif range_count<=32:ranges[-1][1]=i+1
            last=i
    return dict(byte_identical=before==after,before_bytes=len(before),after_bytes=len(after),
        after_sha256=digest(after),header_and_payloads_identical=semantic==actual,
        vbmeta_blob_identical=metadata_same,avb_after=b['avb'],
        different_bytes_in_common_extent=changed,different_range_count=range_count,first_ranges=ranges,
        no_change_gate_passed=before==after and (a['avb'] is None or bool(b['avb'] and b['avb']['all_hashes_match'])),
        signature_or_boot_acceptance_established=False)


def ikconfig(image):
    start=image.find(b'IKCFG_ST');end=image.find(b'IKCFG_ED',start+8)
    require(start>=0 and end>start+8,'IKCONFIG markers missing')
    require(image.find(b'IKCFG_ST',start+8)<0,'duplicate IKCONFIG start')
    dec=zlib.decompressobj(31);raw=dec.decompress(image[start+8:end],1024*1024+1)
    require(len(raw)<=1024*1024 and dec.eof and not dec.unused_data and not dec.unconsumed_tail,'IKCONFIG gzip extent differs')
    raw.decode('utf-8')
    return raw


def config_values(text):
    out={}
    for line in text.splitlines():
        if line.startswith('CONFIG_') and '=' in line:key,value=line.split('=',1)
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):key,value=line[2:-11],'n'
        else:continue
        require(key not in out,'duplicate config key');out[key]=value
    return out


def config_diff(source,stock):
    a,b=config_values(source),config_values(stock)
    return [dict(key=k,source_value_sha256=digest(a[k].encode()) if k in a else None,
        stock_value_sha256=digest(b[k].encode()) if k in b else None) for k in sorted(a.keys()|b.keys()) if a.get(k)!=b.get(k)]
