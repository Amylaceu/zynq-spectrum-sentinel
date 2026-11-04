"""RX descriptor ownership and request sequence with simulated MMIO."""
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sentinel.rx_queue import QueuedRx
from sentinel.dma import AdiDmac as D, _ABORTED_BUFFERS


class Buffer:
    def __init__(self,address):
        self.physical_address=address
        self.freed=False
        self.invalidated=0
    def invalidate(self):self.invalidated+=1
    def freebuffer(self):self.freed=True


class MMIO:
    def __init__(self):
        self.values={D.CTRL:0,D.SUBMIT:0,D.TRANSFER_ID:0,D.TRANSFER_DONE:0}
        self.writes=[]
        self.complete=True
    def read(self,offset):return self.values.get(offset,0)
    def write(self,offset,value):
        self.writes.append((offset,value))
        self.values[offset]=value
        if offset==D.SUBMIT and value:
            identifier=self.values[D.TRANSFER_ID]
            self.values[D.TRANSFER_DONE]&=~(1<<identifier)
            self.values[D.SUBMIT]=0
            self.values[D.TRANSFER_ID]=(identifier+1)&3
            if self.complete:self.values[D.TRANSFER_DONE]|=1<<identifier


def queue(m):
    buffers=[]
    def allocate(n):
        b=Buffer(0x100000+len(buffers)*n);buffers.append(b);return b
    return QueuedRx(m,allocator=allocate),buffers


def test_prequeue_wrap_and_release_after_drain():
    m=MMIO();q,buffers=queue(m)
    q.start()
    assert len(q.pending)==3
    seen=[]
    for i in range(10):
        q.consume(lambda b: seen.append(b))
        assert len(q.pending)==3
        assert all(not b.freed for b in buffers)
    q.close()
    assert len(seen)==10
    assert all(b.freed for b in buffers)
    assert m.read(D.CTRL)==0
    # Exactly one startup disable and one final stop, no per-block reset.
    assert m.writes.count((D.CTRL,0))==2


def test_timeout_quarantines_inflight_never_releases():
    m=MMIO();m.complete=False
    q,buffers=queue(m)
    tick=[0.]
    q.clock=lambda:tick[0]
    q.sleep=lambda dt:tick.__setitem__(0,tick[0]+1)
    q.start()
    with pytest.raises(TimeoutError):q.consume(lambda b: None)
    q.close()
    assert not any(b.freed for b in buffers)
    assert all(any(x is b for x in _ABORTED_BUFFERS) for b in buffers)
    # Remove only this test's mock buffers from the process quarantine.
    _ABORTED_BUFFERS[:]=[b for b in _ABORTED_BUFFERS if all(b is not x for x in buffers)]


def test_enabled_dmac_refused():
    m=MMIO();m.values[D.CTRL]=1
    q,_=queue(m)
    with pytest.raises(RuntimeError,match='already owned'):q.start()
    assert not m.writes
    q.close()


def test_partial_allocation_failure_releases_only_unsubmitted_buffers():
    buffers=[]
    def allocate(n):
        if len(buffers)==2:
            raise MemoryError('CMA unavailable')
        b=Buffer(0x100000+len(buffers)*n)
        buffers.append(b)
        return b
    m=MMIO()
    with pytest.raises(MemoryError):QueuedRx(m,allocator=allocate)
    assert all(b.freed for b in buffers)
    assert not m.writes


def test_invalid_physical_address_rejected_before_dma_access():
    b=Buffer(2**30)
    m=MMIO()
    with pytest.raises(ValueError,match='30-bit'):QueuedRx(m,allocator=lambda n:b)
    assert b.freed and not m.writes


def test_close_is_idempotent_and_prevents_restart():
    m=MMIO();q,_=queue(m)
    q.start();q.close()
    writes=list(m.writes)
    q.close()
    assert m.writes==writes
    with pytest.raises(RuntimeError):q.start()
