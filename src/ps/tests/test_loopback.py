import numpy as np
import pytest
from src.ps.sentinel.loopback import sequence,compare_cyclic
@pytest.mark.parametrize('kind',['ramp','pn'])
def test_all_words_including_wrap_and_single_bit_corruption(kind):
    a=sequence(kind);b=a[(np.arange(32768)+7181)%8192].copy()
    assert a.nbytes==65536 and a.min()>=-2048 and a.max()<=2047
    result=compare_cyclic(a,b);assert result['passed'] and result['compared_words']==131072
    b[-1,3]^=1
    assert not compare_cyclic(a,b)['passed']
    assert not compare_cyclic(a,np.zeros_like(b))['passed']

def test_cyclic_timeout_keeps_buffer_owned():
    from src.ps.sentinel.dma import AdiCyclicTx
    from src.ps.tests.test_base_drivers import Registers,Buffer
    m=Registers();buf=Buffer();dma=AdiCyclicTx(m)
    dma.start(buf)
    assert dma.inflight==[buf] and buf.flushed
    with pytest.raises(TimeoutError):dma.stop(timeout_s=.001)
    assert dma.inflight==[buf] and not buf.freed
    assert m.writes[-1]==(0x400,0)

def test_cyclic_clears_repeat_and_waits_before_releasing_owner():
    from src.ps.sentinel.dma import AdiCyclicTx
    from src.ps.tests.test_base_drivers import CompletingDmac,Buffer
    m=CompletingDmac();buf=Buffer();dma=AdiCyclicTx(m)
    dma.start(buf);assert dma.inflight
    dma.stop();assert not dma.inflight and not buf.freed
    assert (0x40c,0) in m.writes and m.writes[-1]==(0x400,0)
