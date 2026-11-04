"""Single-shot simple DMA wrappers; never free a possibly in-flight buffer."""
import time


_ABORTED_BUFFERS=[]


def _retain_for_reset(buffers):
    # Preserve allocations even if the driver object is garbage-collected.
    # Only a documented hardware-reset recovery may release this quarantine.
    for buf in buffers:
        if not any(item is buf for item in _ABORTED_BUFFERS):
            _ABORTED_BUFFERS.append(buf)


def decode_xilinx_status(word):
    names={0:'Halted',1:'Idle',4:'DMAIntErr',5:'DMASlvErr',6:'DMADecErr',
           8:'SGIntErr',9:'SGSlvErr',10:'SGDecErr',12:'IOC_Irq',13:'Dly_Irq',14:'Err_Irq'}
    return [name for bit,name in names.items() if word & (1<<bit)]


def _allocate(n):
    from .cma import allocate_owned
    return allocate_owned(n)


class XilinxDma:
    def __init__(self, dma, allocator=_allocate):
        self.dma,self.allocator=dma,allocator
        self.inflight=[]

    def _wait(self, channel, status_offset, control_offset, timeout_s):
        if timeout_s <= 0:
            raise ValueError('Timeout must be positive')
        deadline=time.monotonic()+timeout_s
        while True:
            status=int(self.dma.mmio.read(status_offset))
            if status & 0x770:
                _retain_for_reset(self.inflight)
                self.dma.mmio.write(control_offset,0)
                raise RuntimeError('AXI DMA: '+str(decode_xilinx_status(status)))
            if channel.idle:
                return
            if time.monotonic()>=deadline:
                _retain_for_reset(self.inflight)
                self.dma.mmio.write(control_offset,0)
                raise TimeoutError('AXI DMA timeout: '+str(decode_xilinx_status(status)))
            time.sleep(.0001)

    def recv(self,n_bytes,timeout_s=1):
        if not isinstance(n_bytes,int) or n_bytes<=0 or timeout_s<=0:
            raise ValueError('Invalid transfer size/timeout')
        buf=self.allocator(n_bytes)
        self.inflight.append(buf)
        self.dma.recvchannel.transfer(buf)
        self._wait(self.dma.recvchannel,0x34,0x30,timeout_s)
        if hasattr(buf,'invalidate'):
            buf.invalidate()
        self.inflight=[item for item in self.inflight if item is not buf]
        return buf

    def send(self,buf,timeout_s=1):
        if timeout_s<=0:
            raise ValueError('Invalid timeout')
        self.inflight.append(buf)
        if hasattr(buf,'flush'):
            buf.flush()
        self.dma.sendchannel.transfer(buf)
        self._wait(self.dma.sendchannel,0x04,0,timeout_s)
        self.inflight=[item for item in self.inflight if item is not buf]


class AdiDmac:
    CTRL=0x400
    TRANSFER_ID=0x404
    SUBMIT=0x408
    FLAGS=0x40c
    DEST_ADDR=0x410
    SRC_ADDR=0x414
    X_LENGTH=0x418
    TRANSFER_DONE=0x428
    IRQ_MASK=0x80
    IRQ_PENDING=0x84

    def __init__(self,mmio,direction,allocator=_allocate,alignment=8,max_length=2**24):
        if direction not in ('rx','tx') or alignment<1 or alignment&(alignment-1):
            raise ValueError('Invalid DMAC direction/alignment')
        self.mmio,self.direction,self.allocator=mmio,direction,allocator
        self.alignment,self.max_length=alignment,max_length
        self.inflight=[]

    def _transfer(self,buf,n_bytes,timeout_s):
        address=int(buf.physical_address)
        if n_bytes<=0 or n_bytes>self.max_length or n_bytes%self.alignment or address%self.alignment or address<0 or address+n_bytes>2**32 or timeout_s<=0:
            raise ValueError('Invalid simple DMAC transfer range/alignment/timeout')
        if self.inflight:
            raise RuntimeError('Previous transfer still owns its buffer; reset/recover first')
        self.inflight.append(buf)
        m=self.mmio
        m.write(self.CTRL,0);m.write(self.CTRL,1)
        m.write(self.IRQ_MASK,3)
        m.write(self.IRQ_PENDING,3)
        transfer_id=int(m.read(self.TRANSFER_ID))&3
        m.write(self.FLAGS,0)
        m.write(self.DEST_ADDR if self.direction=='rx' else self.SRC_ADDR,address)
        m.write(self.X_LENGTH,n_bytes-1)
        if self.direction=='tx' and hasattr(buf,'flush'):
            buf.flush()
        m.write(self.SUBMIT,1)
        deadline=time.monotonic()+timeout_s
        # Wait for request acceptance BEFORE consulting the completion bitmap:
        # an old ID completion bit may otherwise be mistaken for this transfer.
        while m.read(self.SUBMIT)&1:
            if time.monotonic()>=deadline:
                self._timeout('submit')
            time.sleep(.0001)
        while not (m.read(self.TRANSFER_DONE)&(1<<transfer_id)):
            if time.monotonic()>=deadline:
                self._timeout('completion')
            time.sleep(.0001)
        if self.direction=='rx' and hasattr(buf,'invalidate'):
            buf.invalidate()
        self.inflight.clear()

    def _timeout(self,phase):
        _retain_for_reset(self.inflight)
        status={hex(offset):int(self.mmio.read(offset)) for offset in
                (self.CTRL,self.SUBMIT,self.TRANSFER_DONE,self.IRQ_PENDING)}
        self.mmio.write(self.CTRL,0)
        raise TimeoutError('ADI DMAC '+phase+' timeout: '+str(status))

    def recv(self,n_bytes,timeout_s=1):
        if self.direction!='rx' or not isinstance(n_bytes,int) or n_bytes<=0 or n_bytes>self.max_length or n_bytes%self.alignment or timeout_s<=0:
            raise ValueError('Invalid receive request')
        buf=self.allocator(n_bytes)
        self._transfer(buf,n_bytes,timeout_s)
        return buf

    def send(self,buf,timeout_s=1):
        if self.direction!='tx':
            raise ValueError('Not a TX DMAC')
        self._transfer(buf,int(buf.nbytes),timeout_s)


class AdiCyclicTx(AdiDmac):
    """Hardware cyclic TX; clear CYCLIC then await a finite completion before release."""
    def __init__(self,mmio,**kwargs):
        super().__init__(mmio,'tx',**kwargs)
    def start(self,buf):
        n=int(buf.nbytes);address=int(buf.physical_address)
        if self.inflight or n<=0 or n>self.max_length or n%8 or address%8 or address<0 or address+n>2**32:
            raise ValueError('Invalid cyclic transfer or previous transfer still active')
        m=self.mmio;m.write(self.CTRL,0);m.write(self.CTRL,1)
        m.write(self.FLAGS,1)
        if m.read(self.FLAGS)&1!=1:raise RuntimeError('Hardware cyclic mode unsupported')
        self.inflight.append(buf)
        if hasattr(buf,'flush'):buf.flush()
        m.write(self.IRQ_MASK,3);m.write(self.IRQ_PENDING,3)
        self._cyclic_id=int(m.read(self.TRANSFER_ID))&3
        m.write(self.SRC_ADDR,address);m.write(self.X_LENGTH,n-1);m.write(self.SUBMIT,1)
    def stop(self,timeout_s=2):
        if not self.inflight:return
        m=self.mmio;m.write(self.FLAGS,0)
        deadline=time.monotonic()+timeout_s
        while m.read(self.SUBMIT)&1 or not m.read(self.TRANSFER_DONE)&(1<<self._cyclic_id):
            if time.monotonic()>deadline:self._timeout('cyclic drain')
            time.sleep(.0001)
        m.write(self.CTRL,0)
        self.inflight.clear()
