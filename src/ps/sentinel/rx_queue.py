"""Prequeued finite RX descriptors on the frozen ADI DMAC (no cyclic mode).

Only the acquisition owner may use this class. A complete descriptor is read
before its allocation is reused; in-flight buffers are quarantined on errors.
Software indices count delivered samples, not lost RF samples.
"""
import time
from .dma import AdiDmac, _retain_for_reset
from .cma import allocate_owned


class QueuedRx:
    def __init__(self, mmio, nbytes=1048576, allocator=allocate_owned,
                 clock=time.monotonic, sleep=time.sleep):
        if nbytes<=0 or nbytes%8 or nbytes>2**24:
            raise ValueError('Require aligned finite RX descriptor')
        self.mmio, self.nbytes, self.clock, self.sleep = mmio, nbytes, clock, sleep
        self.buffers = []
        self.pending = []
        self.started = self.failed = False
        self.closed = False
        try:
            for _ in range(3):
                b = allocator(nbytes)
                self.buffers.append(b)
                address = int(b.physical_address)
                if address%8 or not 0<=address<2**30 or address+nbytes>2**30:
                    raise ValueError('Frozen DMAC has a 30-bit memory address bus')
        except BaseException:
            for b in self.buffers:
                b.freebuffer()
            self.buffers = []
            raise

    def _wait(self, condition, label, timeout=2):
        deadline = self.clock()+timeout
        while not condition():
            if self.clock()>=deadline:
                self.failed = True
                _retain_for_reset(self.buffers)
                self.mmio.write(AdiDmac.CTRL,0)
                raise TimeoutError('Queued RX '+label)
            self.sleep(.0002)

    def _submit(self, buffer):
        m = self.mmio
        self._wait(lambda: not m.read(AdiDmac.SUBMIT)&1, 'request busy')
        identifier = int(m.read(AdiDmac.TRANSFER_ID))&3
        if any(identifier==i for i,_ in self.pending):
            raise RuntimeError('RX ID reused before completion was consumed')
        m.write(AdiDmac.DEST_ADDR,int(buffer.physical_address))
        m.write(AdiDmac.X_LENGTH,self.nbytes-1)
        m.write(AdiDmac.SUBMIT,1)
        # This allocation is hardware-owned even before request acceptance.
        self.pending.append((identifier,buffer))
        self._wait(lambda: not m.read(AdiDmac.SUBMIT)&1, 'request acceptance')

    def start(self):
        if self.started or self.failed or self.closed:
            raise RuntimeError('RX queue cannot be restarted')
        m = self.mmio
        if m.read(AdiDmac.CTRL)&1:
            raise RuntimeError('RX DMAC already owned/enabled')
        self.started = True
        m.write(AdiDmac.CTRL,0); m.write(AdiDmac.CTRL,1)
        m.write(AdiDmac.IRQ_MASK,3); m.write(AdiDmac.IRQ_PENDING,3)
        m.write(AdiDmac.FLAGS,0)
        for buffer in self.buffers:
            self._submit(buffer)

    def consume(self, callback):
        if not self.started or self.failed:
            raise RuntimeError('RX queue unavailable')
        identifier,buffer = self.pending[0]
        self._wait(lambda: bool(self.mmio.read(AdiDmac.TRANSFER_DONE)&(1<<identifier)),
                   'completion')
        self.pending.pop(0)
        if hasattr(buffer,'invalidate'):
            buffer.invalidate()
        callback(buffer)
        self._submit(buffer)
        return identifier

    def close(self):
        if self.failed or self.closed:
            return
        if self.started:
            while self.pending:
                identifier,_ = self.pending[0]
                self._wait(lambda: bool(self.mmio.read(AdiDmac.TRANSFER_DONE)&(1<<identifier)),
                           'drain')
                self.pending.pop(0)
            self.mmio.write(AdiDmac.CTRL,0)
        for buffer in self.buffers:
            buffer.freebuffer()
        self.buffers = []
        self.closed = True

    def __enter__(self):
        try:
            self.start()
            return self
        except BaseException:
            self.close()
            raise

    def __exit__(self,*args):
        self.close()
