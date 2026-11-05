#!/usr/bin/env python3
"""Mutation fuzz of the file parsers (.bsp decompiler, .pth, LZ77, .skd/.skb/.skc, .tik,
.shader). Builds minimal structurally valid seeds, corrupts them at random, and reports any
exception type that ISN'T one the parser declares (BspError, ValueError, struct.error ...)
and any case that runs past its time budget. A clean run lists only "ok" / "expected"
counts and no samples under "unexpected outcomes".

Usage (POSIX only: the time budget uses SIGALRM):  python tests/fuzz_parsers.py bin [seed]
Limit: the .skd / .skb seeds have no bones or surfaces, so the deeper mesh code is only
reached by mutations; real-model fuzzing needs game files, which can't ship here."""
import sys, os, random, struct, signal, collections, tempfile, traceback
sys.path.insert(0, sys.argv[1]); sys.setrecursionlimit(5000)
import mohaa_bsp as MB, mohaa_view as MV, mohaa_textures as MT
random.seed(int(sys.argv[2]) if len(sys.argv)>2 else 1)
class Hang(Exception): pass
def _alarm(*a): raise Hang()
signal.signal(signal.SIGALRM, _alarm)
res=collections.defaultdict(collections.Counter); samples={}
def run(name, fn, data, expected, budget=3):
    signal.alarm(budget)
    try: fn(data)
    except Hang: res[name]["HANG"]+=1; samples.setdefault((name,"HANG"),data[:64])
    except expected: res[name]["expected"]+=1
    except MemoryError: res[name]["MemoryError"]+=1
    except Exception as e:
        k=type(e).__name__; res[name][k]+=1
        if (name,k) not in samples: samples[(name,k)]=traceback.format_exc().strip().splitlines()[-3:]
    else: res[name]["ok"]+=1
    finally: signal.alarm(0)
def mutate(b):
    b=bytearray(b)
    for _ in range(random.randint(1,12)):
        r=random.random()
        if r<0.5 and b: i=random.randrange(len(b)); b[i]=random.randrange(256)
        elif r<0.7 and len(b)>8: i=random.randrange(0,len(b)-4); b[i:i+4]=struct.pack("<i",random.choice([-1,0x7fffffff,-0x80000000,random.randrange(-1000,100000)]))
        elif r<0.85: b=b[:random.randrange(len(b)+1)]
        else: b+=os.urandom(random.randrange(64))
    return bytes(b)
# --- BSP seed: header + small lumps
def bsp_seed(ver=19):
    lumps=[b""]*29
    lumps[0]=b"common/caulk".ljust(64,b"\0")+struct.pack("<3i",0,1,0)+b"\0"*64
    lumps[1]=struct.pack("<4f",1,0,0,64)+struct.pack("<4f",-1,0,0,64)+struct.pack("<4f",0,1,0,64)+struct.pack("<4f",0,-1,0,64)+struct.pack("<4f",0,0,1,64)+struct.pack("<4f",0,0,-1,64)
    lumps[11]=b"".join(struct.pack("<3i",i,0,0) for i in range(6))
    br=12 if ver>18 else 12
    lumps[12]=struct.pack("<3i",0,6,0)
    mi=13 + (1 if ver<=18 else 0); ei=14+(1 if ver<=18 else 0)
    lumps[mi]=struct.pack("<6f4i",-64,-64,-64,64,64,64,0,0,0,1)
    lumps[ei]=b'{\n"classname" "worldspawn"\n}\n{\n"classname" "info_pathnode"\n"origin" "0 0 0"\n}\n\0'
    hdr=b"2015"+struct.pack("<ii",ver,0); ofs=12+8*29; body=b""; dirs=b""
    for l in lumps: dirs+=struct.pack("<ii",ofs+len(body),len(l)); body+=l; body+=b"\0"*((-len(body))%4)
    return hdr+dirs+body
def bsp_full(d):
    b=MB.Bsp(d,"f.bsp"); MB.decompile(b); MB.static_model_light(b)
for ver in (17,19,21):
    s=bsp_seed(ver); run("bsp:seed%d"%ver,bsp_full,s,(MB.BspError,))
    for _ in range(600): run("bsp.decompile",bsp_full,mutate(s),(MB.BspError,struct.error,IndexError))
ent=bsp_seed()[12+8*29:]
for _ in range(400): run("parse_entity_string",lambda d:MB.parse_entity_string(d.decode("latin-1")),mutate(ent),(MB.BspError,ValueError))
for _ in range(400): run("lz77",lambda d:MB._lz77_unpack(d,4096),os.urandom(random.randrange(1,200)),(MB.BspError,ValueError,IndexError))
for _ in range(400): run("read_path_file",MB.read_path_file,os.urandom(random.randrange(0,300)),(MB.BspError,ValueError,struct.error))
# write_bsp_entities on a mutated bsp (round trip)
td=tempfile.mkdtemp()
for _ in range(150): run("write_bsp_entities",lambda d:MB.write_bsp_entities(d,'{\n"classname" "info_pathnode"\n"origin" "8 8 8"\n}\n',os.path.join(td,"o.bsp")),mutate(bsp_seed()),(MB.BspError,))
# --- SKD/SKB/SKC via files
def as_file(fn,suffix):
    def f(d):
        p=os.path.join(td,"x"+suffix); open(p,"wb").write(d); fn(p)
    return f
skd=b"SKMD"+struct.pack("<i",6)+b"\0"*0x200
skb=b"SKL "+struct.pack("<i",4)+b"\0"*0x200
skc=b"SKAN"+struct.pack("<i",13)+b"\0"*0x300
for seed,nm in ((skd,"skd"),(skb,"skb")):
    for _ in range(500): run("parse_skd:"+nm,as_file(MV.parse_skd,".skd"),mutate(seed),(ValueError,struct.error))
for _ in range(500): run("parse_skc",as_file(MV.parse_skc,".skc"),mutate(skc),(ValueError,struct.error))
# --- text parsers
tik=b'''TIKI\nsetup\n{\n scale 1.0\n path models/x\n skelmodel x.skd\n surface all shader x\n}\ninit\n{\n server { classname Item }\n client { tagspawn "tag_x" ( spawnrate 10 model fx.spr ) }\n}\nanimations\n{\n idle idle.skc\n {\n  client { first { sound x } }\n }\n}\n$include models/a.tik\n'''
txtp=[("tik_emitters",MV.parse_tik_emitters),("tik_anims",MV.parse_tik_animations),("tik_skelmodels",MV.parse_tik_skelmodels),
      ("tik_setsize",MV.parse_tik_setsize),("tik_static_nodraw",MV.parse_tik_static_nodraw),("tik_setup",MT.parse_tik_setup),
      ("shader_file",MT.parse_shader_file),("shader_props",MT.parse_shader_props_file)]
shader=b"textures/x\n{\n qer_editorimage textures/x.tga\n surfaceparm nonsolid\n {\n map $lightmap\n rgbGen wave sin 0 1 0 1\n tcMod scroll 1 1\n }\n}\n"
for nm,fn in txtp:
    seed=shader if nm.startswith("shader") else tik
    for _ in range(400): run(nm,lambda d,fn=fn:fn(d.decode("latin-1")),mutate(seed),(ValueError,))
for k in sorted(res): print(f"{k:24s}", dict(res[k]))
print("\n--- samples of unexpected outcomes")
for k,v in samples.items(): print(k, v)
