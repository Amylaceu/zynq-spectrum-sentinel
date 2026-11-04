import pytest

from src.ps.sentinel.quad_spi import QuadSpi


class SpiRegisters:
    def __init__(self,stuck=False):
        self.writes=[];self.tx=[];self.rx=[];self.stuck=stuck

    def write(self,offset,value):
        self.writes.append((offset,value))
        if offset==0x60 and value&0x60:
            self.tx.clear();self.rx.clear()
        if offset==0x68:
            self.tx.append(value)
        if offset==0x60 and not value&0x100:
            self.rx.extend(self.tx);self.tx.clear()

    def read(self,offset):
        if offset==0x64:return 0x25 if self.stuck or not self.rx else 0x24
        if offset==0x6c:return self.rx.pop(0)
        return 0


def test_mode1_command_and_full_duplex_chunking():
    regs=SpiRegisters();spi=QuadSpi(regs)
    spi.reset()
    assert (0x60,0x196) in regs.writes
    assert spi.read_register(0x037)==0
    assert [v for a,v in regs.writes if a==0x68]==[0,0x37,0]
    regs.writes.clear()
    data=bytes(range(40));assert spi.transfer(data)==data
    assert [v for a,v in regs.writes if a==0x70]==[0xfffffffe,0xffffffff]
    assert regs.writes[-2:]==[(0x60,0x196),(0x70,0xffffffff)]


def test_spi_timeout_always_releases_chip_select():
    regs=SpiRegisters(stuck=True);spi=QuadSpi(regs,timeout_s=.001)
    with pytest.raises(TimeoutError):spi.transfer(b'abc')
    assert regs.writes[-2:]==[(0x60,0x196),(0x70,0xffffffff)]
