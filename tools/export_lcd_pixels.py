"""Independent integer pixel reference for the560x160 spectrum and waterfall row."""
import hashlib,json
from pathlib import Path
import numpy as np
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'data/reference/lcd';out.mkdir(parents=True,exist_ok=True)
    x=np.arange(560);rng=np.random.default_rng(20261105)
    dbfs=-94+rng.integers(-5,6,560)+65*np.exp(-((x-120)/17)**2)+48*np.exp(-((x-360)/28)**2)
    spectrum=np.rint(23119+dbfs*256).astype(np.int64)
    threshold=np.rint(23119+(-58+8*np.sin(x/90))*256).astype(np.int64)
    spectrum[:5]=[-32768,32767,-2481,23119,0]
    threshold[:5]=[-32768,32767,-2481,23119,0]
    def ordinate(value):
        delta=23119-int(value)
        return 159 if value==-32768 or delta>=25600 else (0 if delta<=0 else delta//160)
    pixels=[];wf=[]
    for y in range(160):
        for col in range(560):
            cy,py,ty=ordinate(spectrum[col]),ordinate(spectrum[max(0,col-1)]),ordinate(threshold[col])
            color=0x18c3 if y%32==0 or col%80==0 else 0
            if min(cy,py)<=y<=max(cy,py):color=0x07e0
            if y==ty and col%8<4:color=0xf800
            pixels.append(color)
    for value in spectrum:
        delta=23119-int(value)
        level=0 if value==-32768 or delta>=25600 else (255 if delta<=0 else 255-delta//100)
        band=level//64;t=level%64
        r,g,b=((0,0,t//2),(0,t,31),(t//2,63,31-t//2),(31,63-t,0))[band]
        wf.append((r<<11)|(g<<5)|b)
    files={}
    for name,values in [('n4_pixel_spec',spectrum),('n4_pixel_thr',threshold),('n4_pixel_expected',pixels),('n4_waterfall_expected',wf)]:
        raw=''.join(f'{int(v)&65535:04x}\n' for v in values).encode()
        p=out/(name+'.hex');p.write_bytes(raw);files[p.name]=hashlib.sha256(raw).hexdigest()
    (out/'n4_pixels_manifest.json').write_bytes((json.dumps(dict(width=560,height=160,sha256=files),indent=2)+'\n').encode())
    rgb565=np.array(pixels,dtype=np.uint16).reshape(160,560)
    rgb=np.stack((((rgb565>>11)&31)*255//31,((rgb565>>5)&63)*255//63,(rgb565&31)*255//31),axis=-1).astype(np.uint8)
    (ROOT/'report/figures').mkdir(exist_ok=True)
    Image.fromarray(rgb).save(ROOT/'report/figures/n4_trace_simulation.png')
    print('LCD_PIXELS_REFERENCE_PASS',len(pixels),len(wf))


if __name__=='__main__':main()
