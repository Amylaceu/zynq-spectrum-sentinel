"""Polled AXI Quad SPI standard-mode transfers, matching the Z20 base image."""
import threading
import time


class QuadSpi:
    SRR,CR,SR,DTR,DRR,SSR=0x40,0x60,0x64,0x68,0x6c,0x70
    INHIBIT=0x100
    FIFO_RESET=0x60

    def __init__(self,mmio,mode=1,timeout_s=.25,fifo_depth=16):
        if mode not in range(4) or timeout_s<=0 or fifo_depth!=16:
            raise ValueError('Invalid SPI mode/timeout or unexpected base-image FIFO')
        self.mmio,self.timeout_s,self.fifo_depth=mmio,timeout_s,fifo_depth
        self.control=0x86 | ((mode&2)<<2) | ((mode&1)<<4)
        self.lock=threading.RLock()

    def reset(self):
        with self.lock:
            self.mmio.write(self.SRR,0x0a)
            self.mmio.write(self.SSR,0xffffffff)
            self.mmio.write(self.CR,self.control|self.INHIBIT|self.FIFO_RESET)
            self.mmio.write(self.CR,self.control|self.INHIBIT)

    def transfer(self,data):
        data=bytes(data)
        if not data:
            raise ValueError('SPI transfer must contain at least one byte')
        m=self.mmio;result=bytearray()
        with self.lock:
            m.write(self.CR,self.control|self.INHIBIT|self.FIFO_RESET)
            m.write(self.CR,self.control|self.INHIBIT)
            m.write(self.SSR,0xfffffffe)
            try:
                for offset in range(0,len(data),self.fifo_depth):
                    block=data[offset:offset+self.fifo_depth]
                    for byte in block:
                        m.write(self.DTR,byte)
                    m.write(self.CR,self.control)
                    deadline=time.monotonic()+self.timeout_s
                    for _ in block:
                        while True:
                            status=int(m.read(self.SR))
                            if status&0x10:
                                raise IOError('SPI mode fault: SR='+hex(status))
                            if not status&1:
                                break
                            if time.monotonic()>=deadline:
                                raise TimeoutError('SPI receive timeout: SR='+hex(status))
                            time.sleep(.00001)
                        result.append(int(m.read(self.DRR))&255)
                    m.write(self.CR,self.control|self.INHIBIT)
            finally:
                m.write(self.CR,self.control|self.INHIBIT)
                m.write(self.SSR,0xffffffff)
        return bytes(result)

    def read_register(self,address):
        if not isinstance(address,int) or not 0<=address<=0x3ff:
            raise ValueError('AD9361 register address outside 10-bit range')
        # ADI no-OS: AD_READ=(0<<15), AD_ADDR=address&0x3ff, count=1.
        return self.transfer(bytes((address>>8,address&255,0)))[2]
