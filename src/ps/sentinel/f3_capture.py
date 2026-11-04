"""Finite OTA collection; TX state checked between every DMA capture."""
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from .artifacts import atomic_write
from .cma import allocate_owned
from .dma import AdiCyclicTx
from .rf.f3 import attenuation_steps
from .capture_x5 import select_channel
from .app.monitor_x1_guard8 import configure_checked


def collect(hw, radio, directory, output, result, count=50):
    directory, output = Path(directory), Path(output)
    manifest = json.loads((directory/'manifest.json').read_text())
    records = result.setdefault('modulation_captures', [])
    configure_checked(hw, radio, 2450000000)
    hw.reset_channelizer()
    hw.source.configure('noise', rate=3840000)
    hw.lcd.set_bus_phase(2)
    hw.lcd.enable()
    hw.source.start()
    tx = AdiCyclicTx(hw.checked.registers('axi_ad9361_dac_dma'))
    owner = None
    result['capture_scope'] = '50 successive SCAP windows/class on cyclic known waveforms; overlaps/repeats possible'
    try:
        for entry in manifest['waveforms']:
            radio.health()
            path = directory/entry['filename']
            if path.parent != directory or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise ValueError('Waveform integrity')
            with np.load(path, allow_pickle=False) as data:
                words = data['words'].copy()
            if (words.dtype != np.dtype('<i2') or words.shape != (262144, 4)
                    or words[:, 2:].any() or np.any(words.astype(np.int32) % 16)
                    or np.abs(words.astype(np.int32)).max() > 16368):
                raise ValueError('Unsafe waveform format')
            owner = allocate_owned(words.nbytes+128)
            owner[:] = 0xa5
            buf = owner[64:-64]
            buf.view('<i2')[:] = words.reshape(-1)
            owner.flush()
            radio.health()
            tx.start(buf)
            for att in attenuation_steps():
                radio.set_attenuation(att)
            time.sleep(.03)
            packets = []
            readbacks = []
            for n in range(count+2):
                before = radio.health()
                packet = hw.channel_capture.acquire(select_channel(240000), source=3, timeout_s=.6)
                after = radio.health()
                if n >= 2:
                    packets.append(packet['raw_words'])
                    readbacks.append([before['rssi_dbm'], after['rssi_dbm'], after['tx_atten_db']])
            radio.mute()
            tx.stop(timeout_s=.6)
            if not (np.all(owner[:64] == 0xa5) and np.all(owner[-64:] == 0xa5)):
                raise RuntimeError('TX DMA boundary changed')
            del buf
            owner.freebuffer()
            owner = None
            target = output.parent/('class_%02d.npz' % entry['index'])
            raw = np.stack(packets)
            radio.health()
            atomic_write(target, lambda stream: np.savez_compressed(stream,
                words=raw, readbacks=np.asarray(readbacks), fs_hz=np.int64(480000)))
            radio.health()
            records.append(dict(label=entry['label'], index=entry['index'], count=count,
                filename=target.name, sha256=hashlib.sha256(target.read_bytes()).hexdigest(),
                unique_raw_packets=len({hashlib.sha256(a.tobytes()).hexdigest() for a in raw}),
                tx_waveform_sha256=entry['sha256'], tx_attenuation_db=40))
            print('F3_CLASS', records[-1], flush=True)
    finally:
        try:
            radio.mute()
        finally:
            try:
                tx.stop(timeout_s=.6)
            finally:
                hw.source.stop()
                result['capture_tx_quarantined'] = bool(tx.inflight)
                if owner is not None and not tx.inflight:
                    del buf
                    owner.freebuffer()
                if tx.inflight:
                    # Retain Python/CMA ownership; caller must not terminate.
                    result['_retained_tx'] = tx
                    result['_retained_owner'] = owner
