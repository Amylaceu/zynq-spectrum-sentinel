"""Sentinel v1 address/clock contracts and explicit source control (Python3.8)."""
import time
from .overlay import SentinelOverlay
from .drivers.regs import src_ctrl as S,spec_ctrl as F,perf_ctrl as P,lcd_ctrl as L
from .drivers.cfar import Cfar
from .drivers.perf import Performance
from .lcd_direct import DirectLCD
from .mmio import make_mmio
from .params import LEGACY_DSP_CLK_HZ

CONTRACTS={'src_mux_0':{'version':0x53520001},'spec_front_0':{'version':0x53500001},
    'cfar_core_0':{'version':0x43460001},'perf_mon_0':{'version':0x50460001},'lcd_engine':{'version':0x4c430001}}
ADDRESSES={'src_mux_0':0x43c00000,'spec_front_0':0x43c10000,'cfar_core_0':0x43c20000,
    'lcd_engine':0x43c60000,'perf_mon_0':0x43c70000,'axi_dma_replay':0x40400000,
    'axi_capture_ctrl':0x41220000,'axi_sentinel_intc':0x41800000,'axi_ad9361_gpio':0x41200000}
DSP_HZ=LEGACY_DSP_CLK_HZ

class Source:
    def __init__(self,mmio,dsp_clk_hz=LEGACY_DSP_CLK_HZ):
        self.mmio=mmio
        if type(dsp_clk_hz) is not int or dsp_clk_hz<=0: raise ValueError('Invalid DSP clock')
        self.dsp_clk_hz=dsp_clk_hz
        if mmio.read(S.VERSION)!=0x53520001:raise ValueError('Source IP version mismatch')
    def stop(self):self.mmio.write(S.CTRL,self.mmio.read(S.CTRL)&~1)
    def configure(self,mode,rate=30720000,bins=(64,),amplitudes=(8192,),frames=0):
        modes={'rf':0,'replay':1,'test':2,'noise':3}
        if mode not in modes or not 0<rate<=self.dsp_clk_hz or not isinstance(frames,int) or not 0<=frames<=0xffffffff:
            raise ValueError('Invalid source configuration')
        if len(bins)!=len(amplitudes) or not 1<=len(bins)<=3 or any(not isinstance(b,int) or not -1024<=b<=1023 for b in bins):
            raise ValueError('Expected1..3 FFT-bin offsets')
        if any(not isinstance(a,int) or not 0<=a<=65535 for a in amplitudes):raise ValueError('UnsignedQ1.15 amplitudes required')
        if self.mmio.read(S.CTRL)&1:raise RuntimeError('Stop and drain source before reconfiguration')
        divider=round(self.dsp_clk_hz*65536/rate)
        if not 65536<=divider<=0xffffffff:raise ValueError('Rate divider out of range')
        self.mmio.write(S.RATE_DIV,divider);self.mmio.write(S.FRAME_LIMIT,frames)
        for i in range(3):
            self.mmio.write(S.FCW0+4*i,((bins[i]*2097152)&0xffffffff) if i<len(bins) else 0)
            self.mmio.write(S.AMP0+4*i,amplitudes[i] if i<len(amplitudes) else 0)
        self.mmio.write(S.NOISE_AMP,0)
        self.mmio.write(S.ARM_TOKEN,(self.mmio.read(S.ARM_TOKEN)+1)&0xffffffff)
        self.mmio.write(S.CTRL,modes[mode]<<1)
        return self.dsp_clk_hz*65536/divider
    def start(self):self.mmio.write(S.CTRL,self.mmio.read(S.CTRL)|1)

def wait_until(predicate,timeout=5.0,label='hardware operation'):
    deadline=time.monotonic()+timeout
    while not predicate():
        if time.monotonic()>=deadline:raise TimeoutError(label+' timed out')
        time.sleep(.001)

class V1:
    def __init__(self,bit='/home/xilinx/sentinel/overlay/sentinel_v1/sentinel_v1.bit',download=False):
        self.checked=SentinelOverlay(bit,download=download,contracts=CONTRACTS)
        self.overlay=self.checked.overlay
        for name,base in ADDRESSES.items():
            if name not in self.checked.ip_dict or int(self.checked.ip_dict[name]['phys_addr'])!=base:
                raise RuntimeError('Unexpected v1 address: '+name)
        self.src_regs=self.checked.registers('src_mux_0');self.spec=self.checked.registers('spec_front_0')
        self.source=Source(self.src_regs);self.cfar=Cfar(self.checked.registers('cfar_core_0'))
        self.perf=Performance(self.checked.registers('perf_mon_0'))
        self.lcd=DirectLCD(self.checked.registers('lcd_engine'),make_mmio(0x42000000,32768))
        self.capture=make_mmio(0x42010000,8192);self.capture_ctrl=self.checked.registers('axi_capture_ctrl')
    def enable_processing(self,average_shift=3):
        if not isinstance(average_shift,int) or not 0<=average_shift<=15:raise ValueError('Invalid average shift')
        self.spec.write(F.AVG_SHIFT,average_shift);self.spec.write(F.DISP_DECIM,1)
        self.cfar.configure();self.spec.write(F.CTRL,1)
    def arm_capture(self):
        status=self.capture_ctrl.read(8)
        if status&2:raise RuntimeError('Power-frame capture framing error')
        if (status&1)!=(self.capture_ctrl.read(0)&1):raise RuntimeError('Previous capture is pending')
        token=(status^1)&1;self.capture_ctrl.write(0,token)
        return token
    def read_capture(self,token,timeout=5.0):
        import numpy as np
        wait_until(lambda:(self.capture_ctrl.read(8)&1)==token,timeout,'power snapshot')
        if self.capture_ctrl.read(8)&2:raise RuntimeError('Capture error')
        return np.array([self.capture.read(4*i) for i in range(2048)],dtype=np.uint32)
