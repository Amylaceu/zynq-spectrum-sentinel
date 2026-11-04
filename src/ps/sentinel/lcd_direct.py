"""Fixed-region2-bit UI for SSD1963 direct rendering; no overlay/RF side effects."""
import math
import time
import numpy as np
from .drivers.regs import lcd_ctrl as R


def pack_ui(list_pixels, status_pixels):
    blocks=[]
    for values,shape in ((list_pixels,(160,240)),(status_pixels,(80,800))):
        a=np.asarray(values)
        if a.shape!=shape or not np.issubdtype(a.dtype,np.integer) or np.any(a<0) or np.any(a>3):
            raise ValueError('UI must be integer palette0..3 in160x240 and80x800 regions')
        blocks.append(a.astype(np.uint32).reshape(-1))
    pixels=np.concatenate(blocks).reshape(-1,16)
    words=np.zeros(8192,dtype=np.uint32)
    for lane in range(16):words[:len(pixels)] |= pixels[:,lane] << (2*lane)
    return words


class DirectLCD:
    def __init__(self, registers, ui_memory):
        if registers.read(R.VERSION)!=0x4c430001:
            raise ValueError('LCD engine version mismatch')
        self.registers,self.ui_memory=registers,ui_memory

    def enable(self,enabled=True):
        self.registers.write(R.CTRL,int(bool(enabled)))

    def set_bus_phase(self,cycles):
        if not isinstance(cycles,int) or not 1<=cycles<=255:
            raise ValueError('BUS_PHASE must be1..255')
        self.registers.write(R.BUS_PHASE,cycles)

    def submit_ui(self,list_pixels,status_pixels):
        token=self.registers.read(R.UI_EPOCH)
        if self.registers.read(R.UI_APPLIED)!=token:
            raise RuntimeError('Previous UI update is still being read by LCD')
        if self.registers.read(R.STATUS)&0x1c:
            raise RuntimeError('LCD engine reports a framing/region error')
        words=pack_ui(list_pixels,status_pixels)
        if hasattr(self.ui_memory,'array'):
            if len(self.ui_memory.array)<8192:raise ValueError('UI mapping must cover32KiB')
            self.ui_memory.array[:8192]=words
        else:
            for i,word in enumerate(words):self.ui_memory.write(4*i,int(word))
        # Complete/verify MMIO visibility before publishing the update token.
        if self.ui_memory.read(0)!=int(words[0]) or self.ui_memory.read(25596)!=int(words[6399]):
            raise IOError('UI BRAM readback mismatch')
        token=(token+1)&0xffffffff
        self.registers.write(R.UI_EPOCH,token)
        return token

    def wait_ui(self,token,timeout=5.0):
        deadline=time.monotonic()+timeout
        while self.registers.read(R.UI_APPLIED)!=token:
            if time.monotonic()>=deadline:raise TimeoutError('LCD UI update not acknowledged')
            time.sleep(.005)


def draw_ui(targets,lo_hz,rate_hz,page=0,frame=0,fps=0.0,overflow=0,font_path=None,temperature_c=None):
    from PIL import Image,ImageDraw,ImageFont
    if rate_hz<=0 or lo_hz<0 or page<0:raise ValueError('Invalid UI tuning or page')
    try:
        font=ImageFont.truetype(font_path or '/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf',12)
    except OSError:font=ImageFont.load_default()
    images=[Image.new('L',(240,160),0),Image.new('L',(800,80),0)]
    drawers=[ImageDraw.Draw(im) for im in images]
    for d in drawers:d.fontmode='1'
    pages=max(1,(len(targets)+5)//6);page%=pages
    drawers[0].text((6,5),'SIGNALS %d  PAGE %d/%d'%(len(targets),page+1,pages),font=font,fill=2)
    for row,t in enumerate(targets[page*6:(page+1)*6]):
        frequency=lo_hz+((t.start+t.stop)*.5-1024)*rate_hz/2048
        bw=(t.stop-t.start+1)*rate_hz/2048
        peak=10*math.log10(t.peak_power)-30*10*math.log10(2) if t.peak_power else -128.0
        drawers[0].text((6,27+row*21),'%8.3fM %6.1fk %5.1fdB'%(frequency/1e6,bw/1e3,peak),font=font,fill=1)
    drawers[1].text((8,8),'PL FFT/CFAR   LO %.3f MHz   RATE %.3f MSPS'%(lo_hz/1e6,rate_hz/1e6),font=font,fill=3)
    drawers[1].text((8,34),'FRAME %d   DISPLAY %.2f FPS   OVERFLOW %d'%(frame,fps,overflow),font=font,fill=2 if not overflow else 1)
    temperature = ('%.1f C'%temperature_c) if temperature_c is not None and math.isfinite(temperature_c) else 'N/A'
    drawers[1].text((8,56),'SOC TEMP '+temperature,font=font,fill=2)
    return tuple(np.asarray(im,dtype=np.uint8) for im in images)
