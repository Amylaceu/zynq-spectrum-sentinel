"""Receive-only DMA continuity diagnostic. No audio, TX, or bitstream build.

Runs separately from monitor so there is one RF/MMIO owner. Startup overflow
is cleared once after priming. Never clears overflow inside the measured epoch.
"""
import argparse
from contextlib import ExitStack
import hashlib
import json
from pathlib import Path
import sys
import time
import signal

ROOT = Path(__file__).resolve().parents[1]
if '--root' in sys.argv:
    ROOT = Path(sys.argv[sys.argv.index('--root')+1])
sys.path.insert(0,str(ROOT/'ps'))
import numpy as np
from sentinel.app.runtime_v1 import Session
from sentinel.app.monitor_x1_guard8 import configure_checked
from sentinel.v2 import V2
from sentinel.rx_queue import QueuedRx
from sentinel.telemetry import read_temperature_c
from sentinel.release_support import write_result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=ROOT)
    p.add_argument('--seconds',type=int,choices=(10,600),required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    def stopped(*_):
        raise KeyboardInterrupt('Controlled DMA audit stop')
    signal.signal(signal.SIGTERM,stopped)
    a.out.mkdir(parents=True,exist_ok=False)
    result=dict(status='STARTED',configuration='A',tx_requested=False,
        seconds_requested=a.seconds,source='raw_adi_rx_dma',audio='NOT_STARTED',
        sample_index_scope='delivered descriptors; no embedded ADC sequence counter',
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    q=None
    try:
        with ExitStack() as stack:
            s=stack.enter_context(Session(ROOT/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit',source='rf',
                     lo=96050000,rate=3840000,hw_factory=V2))
            hw=s.hw
            configure_checked(hw,s.radio,96050000)
            adc=hw.checked.registers('axi_ad9361')
            dma=hw.checked.registers('axi_ad9361_adc_dma')
            if dma.read(0x400)&1:
                raise RuntimeError('RX DMA was enabled before diagnostic')
            q=stack.enter_context(QueuedRx(dma,nbytes=4194304))
            warmup=time.monotonic()+1
            while time.monotonic()<warmup:
                q.consume(lambda b: None)
            adc.write(0x88,4)
            if adc.read(0x88)&4:
                raise RuntimeError('RX overflows while prequeued: cannot open measured epoch')
            first=time.monotonic()
            blocks=0
            samples=0
            nonzero=0
            latest=first
            records=[]
            raw_snapshots=[]
            digest=hashlib.sha256()
            while time.monotonic()-first<a.seconds:
                def consume(buffer):
                    nonlocal nonzero
                    data=np.asarray(buffer).view('<i2')
                    nonzero+=int(np.count_nonzero(data[:4096]))
                    if blocks<2:
                        raw_snapshots.append(buffer.tobytes())
                    digest.update(memoryview(buffer)[:4096])
                identifier=q.consume(consume)
                blocks+=1
                samples+=q.nbytes//8
                now=time.monotonic()
                overflow=int(adc.read(0x88))
                if overflow&4:
                    result['overflow_observed']=overflow
                    raise RuntimeError('RX FIFO overflow: exact missing sample count unavailable')
                if now-latest>=1:
                    temperature=read_temperature_c()
                    rssi=s.radio.rssi(0)
                    if temperature is None or temperature>=85 or rssi>-30:
                        raise RuntimeError('RX safety telemetry outside limit')
                    if s.radio.tx_atten!=(89.75,89.75):
                        raise RuntimeError('TX attenuation changed')
                    records.append(dict(elapsed_s=now-first,blocks=blocks,
                        delivered_rx1_samples=samples,descriptor_id=identifier,
                        fifo_overflow_status=overflow,temperature_c=temperature,rssi_dbm=rssi))
                    print(json.dumps(records[-1]),flush=True)
                    latest=now
            elapsed=time.monotonic()-first
            result.update(status='MEASURED',elapsed_s=elapsed,blocks=blocks,
                delivered_rx1_samples=samples,delivered_rate_hz=samples/elapsed,
                observed_overflow_epochs=0,exact_lost_samples=None,
                nonzero_probe_values=nonzero,probe_sha256=digest.hexdigest(),telemetry=records,
                continuity='NO_FIFO_OVERFLOW_OBSERVED; absolute ADC sample sequence unavailable')
            q.close();q=None
            # SD writes are deliberately outside the acquisition epoch.
            for index,data in enumerate(raw_snapshots):
                path=a.out/('raw_%02d.i16'%index)
                path.write_bytes(data)
                Path(str(path)+'.sha256').write_text(hashlib.sha256(data).hexdigest()+'  '+path.name+'\n')
    except BaseException as error:
        result.update(status='FAIL',error=repr(error))
        raise
    finally:
        if q is not None:
            try:q.close()
            except BaseException as error:result['dma_cleanup_error']=repr(error)
        write_result(a.out/'result.json',result)


if __name__=='__main__':
    main()
