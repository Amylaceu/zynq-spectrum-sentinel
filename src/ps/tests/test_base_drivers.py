import hashlib
import os
import struct
from types import SimpleNamespace

import pytest

from src.ps.sentinel.dma import AdiDmac, XilinxDma, decode_xilinx_status, _ABORTED_BUFFERS
from src.ps.sentinel.mmio import DevMem
from src.ps.sentinel.overlay import SentinelOverlay, validate_artifacts
from src.ps.sentinel.selftest import check_base


class Registers:
    def __init__(self,values=None):
        self.values={} if values is None else dict(values)
        self.writes=[]

    def read(self,offset):
        return self.values.get(offset,0)

    def write(self,offset,value):
        self.values[offset]=value
        self.writes.append((offset,value))


def artifacts(tmp_path):
    bit=tmp_path/'base.bit';hwh=tmp_path/'base.hwh'
    bit.write_bytes(b'example');hwh.write_bytes(b'<xml/>')
    for f in (bit,hwh): os.utime(f,(100,100))
    (tmp_path/'sha256.txt').write_text(''.join(hashlib.sha256(f.read_bytes()).hexdigest()+'  '+f.name+'\n' for f in (bit,hwh)))
    return bit,hwh


def test_mmio_alignment_bounds_and_little_endian(tmp_path):
    path=tmp_path/'memory';path.write_bytes(bytes(8192))
    with DevMem(4,16,str(path)) as m:
        m.write(4,0x12345678)
        assert m.read(4)==0x12345678
        for offset in (-4,2,16):
            with pytest.raises(ValueError): m.read(offset)
        with pytest.raises(ValueError): m.write(0,-1)
    assert path.read_bytes()[8:12]==struct.pack('<I',0x12345678)


def test_artifact_mismatch_rejected_before_programming(tmp_path):
    bit,hwh=artifacts(tmp_path)
    assert validate_artifacts(bit)==bit.resolve()
    os.utime(hwh,(160,160))
    with pytest.raises(ValueError,match='timestamps'): validate_artifacts(bit)
    os.utime(hwh,(100,100));hwh.write_bytes(b'wrong')
    os.utime(hwh,(100,100))
    with pytest.raises(ValueError,match='hash'): validate_artifacts(bit)


def test_custom_ip_contract_and_scratch_restore(tmp_path):
    bit,_=artifacts(tmp_path);regs=Registers({0xfc:0x10002,0x10:0x54})
    factory=lambda *a,**kw: SimpleNamespace(is_loaded=lambda:True,ip_dict={'cfar':{'type':'user:user:cfar_core:1.0','phys_addr':0}})
    with pytest.raises(RuntimeError,match='missing generated'):
        SentinelOverlay(bit,factory=factory,mmio_factory=lambda *a:regs)
    overlay=SentinelOverlay(bit,factory=factory,mmio_factory=lambda *a:regs,
                            contracts={'cfar':{'version':0x10000,'scratch':0x10}})
    assert overlay.check()=={'cfar':'ok'} and regs.read(0x10)==0x54
    assert regs.writes[-1]==(0x10,0x54)
    regs.values[0xfc]=0x20000
    with pytest.raises(RuntimeError,match='version mismatch'): overlay.check()


@pytest.mark.parametrize('check', [True, False])
def test_unloaded_overlay_never_maps_or_reads_custom_registers(tmp_path, check):
    bit,_=artifacts(tmp_path)
    factory=lambda *a,**kw: SimpleNamespace(is_loaded=lambda:False,
        ip_dict={'cfar':{'type':'user:user:cfar_core:1.0','phys_addr':0}})
    with pytest.raises(RuntimeError,match='not loaded'):
        SentinelOverlay(bit,check=check,download=False,factory=factory,
            contracts={'cfar':{'version':0x10000}},
            mmio_factory=lambda *a:pytest.fail('MMIO accessed before loaded-image validation'))


def test_replaced_overlay_rejects_subsequent_register_mapping(tmp_path):
    bit,_=artifacts(tmp_path); state={'loaded':True}
    factory=lambda *a,**kw: SimpleNamespace(is_loaded=lambda:state['loaded'],
        ip_dict={'cfar':{'type':'user:user:cfar_core:1.0','phys_addr':0}})
    overlay=SentinelOverlay(bit,check=False,download=False,factory=factory,
        mmio_factory=lambda *a:pytest.fail('MMIO mapped after overlay changed'))
    state['loaded']=False
    with pytest.raises(RuntimeError,match='not loaded'):overlay.registers('cfar')
    with pytest.raises(RuntimeError,match='not loaded'):overlay.check()


class Buffer:
    physical_address=0x10000000
    nbytes=16
    def __init__(self):self.flushed=False;self.invalidated=False;self.freed=False
    def flush(self):self.flushed=True
    def invalidate(self):self.invalidated=True
    def freebuffer(self):self.freed=True


class CompletingDmac(Registers):
    def __init__(self):
        super().__init__({0x404:2,0x428:4})
        self.request_reads=0;self.trace=[]

    def read(self,offset):
        self.trace.append(offset)
        if offset==0x408 and self.values.get(offset)==1:
            self.request_reads+=1
            return int(self.request_reads==1)
        if offset==0x428:
            assert self.request_reads>=2  # stale done bit is not used before acceptance
        return super().read(offset)


def test_adi_dmac_real_register_offsets_and_acceptance_order():
    mmio=CompletingDmac();buf=Buffer();rx=AdiDmac(mmio,'rx',allocator=lambda n:buf)
    assert rx.recv(16) is buf
    assert (0x410,buf.physical_address) in mmio.writes and (0x418,15) in mmio.writes
    assert (0x84,3) in mmio.writes and (0x80,3) in mmio.writes
    assert buf.invalidated and not rx.inflight


def test_dmac_timeout_retains_ownership_and_disables_controller():
    regs=Registers();buf=Buffer();rx=AdiDmac(regs,'rx',allocator=lambda n:buf)
    with pytest.raises(TimeoutError,match='submit'):
        rx.recv(16,timeout_s=.001)
    assert rx.inflight==[buf] and not buf.freed and regs.writes[-1]==(0x400,0)
    assert any(item is buf for item in _ABORTED_BUFFERS)
    with pytest.raises(RuntimeError,match='Previous transfer'):
        rx._transfer(Buffer(),16,1)


@pytest.mark.parametrize('address,size',[(-8,16),(0xfffffff8,16),(0x10000001,16),(0x10000000,3)])
def test_dmac_invalid_ranges_do_not_write(address,size):
    regs=Registers();buf=Buffer();buf.physical_address=address;buf.nbytes=size
    dma=AdiDmac(regs,'tx')
    with pytest.raises(ValueError):dma.send(buf)
    assert not regs.writes


def test_axi_dma_error_status_and_buffer_retention():
    regs=Registers({0x34:0x20});buf=Buffer()
    channel=SimpleNamespace(idle=False,transfer=lambda buffer:None)
    dma=XilinxDma(SimpleNamespace(mmio=regs,recvchannel=channel),allocator=lambda n:buf)
    with pytest.raises(RuntimeError,match='DMASlvErr'):dma.recv(16)
    assert dma.inflight==[buf] and not buf.freed and regs.writes[-1]==(0x30,0)
    assert decode_xilinx_status(0x61)==['Halted','DMASlvErr','DMADecErr']


def test_base_gpio_probe_changes_only_unused_bit_and_restores():
    devices={'axi_sysid_0':Registers({0:0x10161}), 'axi_ad9361':Registers({0:0xa0300}),
             'axi_ad9361_spi':Registers({0x64:0x25}), 'axi_ad9361_gpio':Registers({0:0})}
    o=SimpleNamespace(registers=lambda name:devices[name])
    readonly=check_base(o,read_only=True)
    assert readonly['gpio_write_test']=='skipped_read_only' and not devices['axi_ad9361_gpio'].writes
    result=check_base(o,read_only=False)
    assert result['gpio_write_test']=='passed_unused_bit15'
    assert devices['axi_ad9361_gpio'].writes==[(0,0x8000),(0,0)]
