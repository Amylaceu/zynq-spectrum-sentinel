"""Fixed-parameter PL detector observations; never tunes CFAR or the model."""
import time
import numpy as np
from .f3_signal import cw_words
from .rf.f3 import attenuation_steps
from .app.monitor_x1_guard8 import configure_checked
from .cma import allocate_owned
from .dma import AdiCyclicTx


def pd_probe(hw, radio, result, captures):
    configure_checked(hw, radio, 2450000000)
    hw.source.configure('noise', rate=3840000)
    hw.lcd.set_bus_phase(2)
    hw.lcd.enable()
    hw.source.start()
    tx = AdiCyclicTx(hw.checked.registers('axi_ad9361_dac_dma'))
    words = cw_words(peak=1023)
    owner = allocate_owned(words.nbytes+128)
    owner[:] = 0xa5
    buf = owner[64:-64]
    buf.view('<i2')[:] = words.reshape(-1)
    owner.flush()
    points = result.setdefault('pd_points', [])
    try:
        tx.start(buf)
        for attenuation in attenuation_steps():
            radio.set_attenuation(attenuation)
        # Fixed amplitude grid, report measured bin contrast; no assumed SNR map.
        for amplitude in (0, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65535):
            hw.src_regs.write(0x20, amplitude)
            if hw.src_regs.read(0x20) != amplitude:
                raise RuntimeError('Noise amplitude readback mismatch')
            time.sleep(.04)
            snapshots, contrasts, powers = [], [], []
            for _ in range(30):
                health = radio.health()
                power = hw.read_capture(hw.arm_capture(), timeout=.6)
                radio.health()
                snap = hw.cfar.snapshot(retries=12)
                if hw.channel_health():
                    raise RuntimeError('Processing error')
                # Same power frame local contrast; CFAR snapshot is asynchronous.
                reference = np.r_[power[1100:1128], power[1177:1205]].astype(float)
                noise = max(float(np.mean(reference)), 1)
                peak = max(float(power[1150:1155].max())-noise, 1e-9)
                contrasts.append(float(10*np.log10(peak/noise)))
                snapshots.append(dict(sequence=snap.sequence, hits=snap.hit_count,
                    detected=any(t.start <= 1154 and t.stop >= 1150 for t in snap.targets),
                    rssi_dbm=health['rssi_dbm'], tx_atten_db=health['tx_atten_db']))
                powers.append(power)
            points.append(dict(noise_amplitude=amplitude, observations=snapshots,
                median_peak_excess_to_local_bin_noise_db=float(np.median(contrasts)),
                detection_fraction=float(np.mean([x['detected'] for x in snapshots])),
                unique_snapshot_sequences=len({x['sequence'] for x in snapshots})))
            captures['pd_power_'+str(amplitude)] = np.stack(powers)
            print('F3_PD', points[-1], flush=True)
        result['pd_scope'] = ('PL target-list CW overlap +/-2 bins, 30 periodic snapshots/noise amplitude; '
            'power captures and CFAR snapshots are asynchronous; measured averaged-bin contrast is '
            'NOT calibrated input single-bin SNR. Cannot certify Pd@10dB from this grid.')
        result['pd_10db_certified'] = False
    finally:
        try:
            radio.mute()
        finally:
            try:
                tx.stop(timeout_s=.6)
            finally:
                hw.src_regs.write(0, 0)
                result['capture_tx_quarantined'] = bool(tx.inflight)
                if tx.inflight:
                    result['_retained_tx'] = tx
                    result['_retained_owner'] = owner
                else:
                    result['tx_dma_guards_ok'] = bool(np.all(owner[:64] == 0xa5) and np.all(owner[-64:] == 0xa5))
                    del buf
                    owner.freebuffer()
