"""Receive-only Y3 raw/PFB snapshots; no codec enable or audio playback.

Use the already audited, loaded image and unchanged configuration A. Raw and
PFB blocks are separate snapshots, NOT a continuous recording or paired samples.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import sys
import time

import numpy as np


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Preserve previous snapshots')
    if os.geteuid() != 0:
        parser.error('Use PYNQ Python with sudo')
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    os.environ['XILINX_XRT'] = '/usr'
    from sentinel.app.runtime_v1 import Session
    from sentinel.app.monitor_x1_guard8 import configure_checked
    from sentinel.v2 import V2
    from sentinel.capture_x5 import Selection, select_channel
    from sentinel.dma import AdiDmac
    from sentinel.artifacts import atomic_json

    def stop(*_):
        raise InterruptedError('Diagnostic interrupted')
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    args.out.mkdir(parents=True)
    result = dict(status='started', configuration='A', RF_TX_requested=False,
                  audio_playback_requested=False, sample_rate_hz=3840000,
                  station_hz=95800000, captures=[],
                  script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    dma = None
    session = Session(str(args.bit), 'rf', False, 96050000, 3840000, hw_factory=V2)

    def save(name, **arrays):
        path = args.out/name
        np.savez_compressed(path, **arrays)
        return dict(file=name, sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    try:
        with session:
            hw, radio = session.hw, session.radio
            hw.audio.disable(release_pins=True)
            radio.check_rssi()
            result.update(actual_lo_hz=radio.rx_lo, rate_hz=radio.rate,
                          tx_attenuation_db=list(radio.tx_atten), rssi_dbm=radio.rssi(0))
            if radio.tx_atten != (89.75, 89.75) or radio.rate != 3840000:
                raise RuntimeError('RF readback mismatch')
            adc = hw.checked.registers('axi_ad9361')
            result['adc_control'] = [adc.read(0x400+64*i) for i in range(4)]
            dma = AdiDmac(hw.checked.registers('axi_ad9361_adc_dma'), 'rx')
            for block in range(2):
                radio.check_rssi()
                buf = dma.recv(1048576*8, timeout_s=3)
                try:
                    raw = np.asarray(buf).view('<i2').reshape(-1, 4).copy()
                finally:
                    buf.freebuffer()
                result['captures'].append(dict(kind='raw_adc', **save('raw_%02d.npz'%block, raw=raw)))
            dma.mmio.write(dma.CTRL, 0)
            hw.reset_channelizer()
            configure_checked(hw, radio, 96050000)
            hw.lcd.set_bus_phase(2)
            hw.lcd.enable()
            result['receive_startup_after_raw'] = hw.prepare_receive()
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('rf', rate=3840000)
            hw.source.start()
            time.sleep(.1)
            wanted = select_channel(95800000-radio.rx_lo)
            # FCW=0 exposes exactly the pre-NCO PFB IQ seen by the audio tap.
            for channel in (wanted.channel, (-wanted.channel)%16):
                for block in range(8):
                    radio.check_rssi()
                    capture = hw.channel_capture.acquire(Selection(channel, 0, 0., 0.), source=0)
                    result['captures'].append(dict(kind='pfb', channel=channel,
                        timestamp_cycles=capture['timestamp_cycles'],
                        **save('pfb_%02d_%02d.npz'%(channel, block),
                               words=capture['raw_words'], iq=capture['iq'])))
            result.update(status='PASS_CAPTURE_ONLY', health=hw.channel_health(),
                          pfb_status=int(hw.x5_status.read(0)),
                          final_rssi_dbm=radio.rssi(0),
                          final_tx_attenuation_db=list(radio.tx_atten))
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if dma is not None:
            dma.mmio.write(dma.CTRL, 0)
        # Session closes before this finally: RF and source are stopped first.
        if session.hw is not None:
            result['source_ctrl_after'] = session.hw.src_regs.read(0)
            result['audio_control_after'] = session.hw.audio.control.read(0)
            result['gpio_after'] = session.hw.checked.registers('axi_ad9361_gpio').read(0)
        result['buffers_quarantined'] = bool(dma is not None and dma.inflight)
        atomic_json(args.out/'result.json', result)
        path = args.out/'result.json'
        path.with_name(path.name+'.sha256').write_text(
            hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')
        print(json.dumps(result), flush=True)
        if result['buffers_quarantined']:
            # Keep timed-out CMA buffers allocated until explicit reset recovery.
            while True:
                time.sleep(10)


if __name__ == '__main__':
    main()
