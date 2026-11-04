"""Deterministic N4 source/noise/DDS fixtures, based on P2 noise contract."""
import argparse,json,sys,hashlib
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from sim.golden.siggen import add_noise_fixed


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clock-hz',type=int,default=150_000_000)
    parser.add_argument('--rate-hz',type=int,default=30_720_000)
    parser.add_argument('--out',type=Path,default=ROOT/'data/reference/src_mux')
    args=parser.parse_args()
    if not 0<args.rate_hz<=args.clock_hz:parser.error('rate must fit the DSP clock')
    divider=round(args.clock_hz*65536/args.rate_hz)
    if not 65536<=divider<=0xffffffff:parser.error('divider does not fit the source register')
    out=args.out if args.out.is_absolute() else ROOT/args.out
    out.mkdir(exist_ok=True,parents=True)
    sine=np.rint(np.sin(2*np.pi*np.arange(1024)/1024)*32767).astype(np.int64)
    rng=np.random.default_rng(0x20261104)
    inputs=[];expected=[];configs=[];metadata=[]
    for case,mode in enumerate((0,1,2,3,3,3,2,3)):
        iq=rng.integers(-32768,32768,(2048,2),dtype=np.int16)
        iq[:4]=[[-32768,-32768],[32767,32767],[0,0],[-1,1]]
        amplitudes=(65535,65535,65535) if case==6 else (6000,9000,5000)
        frequencies=[64<<21,(-160<<21)&0xffffffff,350<<21]
        noise=(0,0,0,0,32768,65535,0,12345)[case]
        seeds=[0x12345678+case,0x87654321+case]
        cfg=[(mode<<1)|1,divider,*frequencies,*amplitudes,noise,*seeds]
        if mode==2:
            values=np.zeros((2048,2),dtype=np.int64)
            for fcw,amp in zip(frequencies,amplitudes):
                phase=((np.arange(2048,dtype=np.uint64)*fcw)&0xffffffff)>>22
                values[:,0]+=(sine[(phase.astype(int)+256)%1024]*amp)>>15
                values[:,1]+=(sine[phase.astype(int)]*amp)>>15
            result=np.clip(values,-32768,32767).astype(np.int16)
        elif mode==3:result=add_noise_fixed(iq.reshape(-1),noise,*seeds).reshape(-1,2)
        else:result=iq
        pack=lambda a: ((a[:,0].astype(np.int64)&65535)|((a[:,1].astype(np.int64)&65535)<<16)).tolist()
        inputs.extend(pack(iq));expected.extend(pack(result));configs.extend(cfg)
        metadata.append(dict(mode=mode,noise_amp=noise,seed_i=seeds[0],seed_q=seeds[1],amplitudes=amplitudes))
    hashes={}
    for name,words,width in [('n4_src_input',inputs,8),('n4_src_expected',expected,8),('n4_src_config',configs,8),('n4_sine',sine,4)]:
        raw=''.join(f'{int(v)&((1<<(width*4))-1):0{width}x}\n' for v in words).encode()
        p=out/(name+'.hex');p.write_bytes(raw);hashes[p.name]=hashlib.sha256(raw).hexdigest()
    (out/'manifest.json').write_bytes((json.dumps(dict(cases=metadata,sha256=hashes,
        clock_hz=args.clock_hz,rate_hz=args.rate_hz,rate_divider=divider),indent=2)+'\n').encode())
    print('N4_SOURCE_VECTORS_PASS',len(expected))


if __name__=='__main__':main()
