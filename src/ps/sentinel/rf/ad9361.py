"""Shared ctypes contract and context-managed muted RF control (Python3.8)."""
import atexit
import ctypes as ct
import os
from .safety import TxGuard

U32=ct.POINTER(ct.c_uint32);I32=ct.POINTER(ct.c_int32);U64=ct.POINTER(ct.c_uint64)
SIGNATURES={
 'z20_ad9361_open':[], 'z20_ad9361_close':[],
 'z20_get_sample_rate':[U32], 'z20_get_ensm_mode':[U32],
 'z20_get_tx_attenuation':[ct.c_uint8,U32], 'z20_set_tx_attenuation':[ct.c_uint32],
 'z20_configure_receive':[ct.c_uint64,ct.c_uint32,ct.c_uint32],
 'z20_start_receive':[ct.c_uint64], 'z20_get_rx_lo':[U64],
 'z20_get_rx_gain':[ct.c_uint8,I32], 'z20_get_rx_rssi':[ct.c_uint8,I32],
 'z20_set_rx_gain_mode':[ct.c_uint32], 'z20_read_register':[ct.c_uint32],
 'z20_rx_test_tone':[ct.c_int], 'z20_check_rx_prbs':[ct.c_uint32,U32],
 'z20_scan_rx_delays':[ct.c_uint32,U32], 'z20_bist_loopback':[ct.c_int]}
def bind_library(path):
    lib=ct.CDLL(str(path))
    for name,args in SIGNATURES.items():
        fn=getattr(lib,name);fn.argtypes=args;fn.restype=None if name=='z20_ad9361_close' else ct.c_int
    return lib

class AD9361:
    def __init__(self,lib=None,guard=None,backend=None):
        if lib is None:
            lib=os.environ.get('SENTINEL_RF_LIBRARY', '/home/xilinx/sentinel/ps/libad9361_pynq/libad9361_pynq.so')
        self.lib=backend if backend is not None else bind_library(lib)
        self.guard=guard or TxGuard();self._opened=False
        self._rate=30720000;self._rx_lo=98000000;self._bw=24000000;self._gain_mode=2
    @staticmethod
    def _check(code,label):
        if code<0:raise RuntimeError(label+': '+str(code))
    def open(self,rate=30720000,rx_lo=98000000,bandwidth=24000000):
        if self._opened:raise RuntimeError('RF already opened')
        self._check(self.lib.z20_ad9361_open(),'init')
        self._opened=True;atexit.register(self.close)
        try:
            self.tx_atten=89.75
            self.configure(rx_lo,rate,bandwidth)
        except BaseException:
            self.close();raise
        return self
    def configure(self,lo,rate,bw):
        self._check(self.lib.z20_configure_receive(int(lo),int(rate),int(bw)),'configure RX')
        self._rx_lo,self._rate,self._bw=int(lo),int(rate),int(bw)
        self._gain_mode=2
    def close(self):
        if self._opened:
            try:self.lib.z20_set_tx_attenuation(89750)
            finally:
                self.lib.z20_ad9361_close();self._opened=False;atexit.unregister(self.close)
    def __enter__(self):return self.open()
    def __exit__(self,*_):self.close()
    @property
    def tx_atten(self):
        values=[]
        for ch in (0,1):
            v=ct.c_uint32();self._check(self.lib.z20_get_tx_attenuation(ch,ct.byref(v)),'attenuation');values.append(v.value/1000.)
        return tuple(values)
    @tx_atten.setter
    def tx_atten(self,db):
        self.guard.check(db)
        if self.guard.mode!='air':raise PermissionError('Cable execution disabled: C1 SKIPPED')
        mdb=round(db*1000)
        if mdb%250:raise ValueError('AD9361 attenuation step is0.25dB')
        self._check(self.lib.z20_set_tx_attenuation(mdb),'set attenuation')
    @property
    def rx_lo(self):
        v=ct.c_uint64();self._check(self.lib.z20_get_rx_lo(ct.byref(v)),'LO');return v.value
    @rx_lo.setter
    def rx_lo(self,value):self.configure(value,self._rate,self._bw)
    @property
    def rate(self):
        v=ct.c_uint32();self._check(self.lib.z20_get_sample_rate(ct.byref(v)),'rate');return v.value
    @rate.setter
    def rate(self,value):self.configure(self._rx_lo,value,min(self._bw,int(value)))
    @property
    def rx_gain_mode(self):return self._gain_mode
    @rx_gain_mode.setter
    def rx_gain_mode(self,mode):
        if mode not in (0,1,2,3):raise ValueError('Invalid gain mode')
        self._check(self.lib.z20_set_rx_gain_mode(mode),'gain mode');self._gain_mode=mode
    def rssi(self,channel=0):
        if channel not in (0,1):raise ValueError('Invalid channel')
        v=ct.c_int32();self._check(self.lib.z20_get_rx_rssi(channel,ct.byref(v)),'RSSI');return v.value/1000.
    def check_rssi(self):
        try:
            for ch in (0,1):self.guard.check_rssi(self.rssi(ch))
        except BaseException:self.close();raise
    def bist_loopback(self,on):
        if not isinstance(on,bool):raise ValueError('Expected boolean')
        if self.tx_atten!=(89.75,89.75):raise PermissionError('Diagnostic requires maximum attenuation')
        self._check(self.lib.z20_bist_loopback(int(on)),'internal loopback')
    def bist_prbs(self,duration_ms=500):
        s=(ct.c_uint32*4)();self._check(self.lib.z20_check_rx_prbs(duration_ms,s),'RX PRBS');return list(s)
