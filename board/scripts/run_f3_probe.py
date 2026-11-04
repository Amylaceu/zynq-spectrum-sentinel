"""Bounded F3 preflight/calibration using frozen PL, isolated RF library."""
import argparse
import ctypes as ct
import fcntl
import hashlib
import os
from pathlib import Path
import signal
import sys
import time

os.environ['XILINX_XRT'] = '/usr'
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ps'))
import numpy as np
from sentinel.v2 import V2
from sentinel.rf.f3 import F3Radio, attenuation_steps
from sentinel.f3_signal import cw_words, tone_metrics
from sentinel.dma import AdiDmac, AdiCyclicTx
from sentinel.cma import allocate_owned
from sentinel.artifacts import atomic_json, atomic_write
from sentinel.capture_x5 import select_channel
from sentinel.app.monitor_x1_guard8 import configure_checked


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('preflight', 'watchdog', 'calibrate', 'capture', 'pd'))
    p.add_argument('--bit', required=True)
    p.add_argument('--library', required=True)
    p.add_argument('--library-sha256', required=True)
    p.add_argument('--out', required=True)
    antennas = p.add_mutually_exclusive_group(required=True)
    antennas.add_argument('--antenna-b-direct-confirmed', action='store_true')
    antennas.add_argument('--presentation-antenna-confirmed', choices=('S1', 'S2'),
                          help='Explicit I0 user confirmation; same fixed RF protections')
    args = p.parse_args()
    output = Path(args.out)
    if output.exists():
        raise FileExistsError(output)
    if hashlib.sha256(Path(args.library).read_bytes()).hexdigest() != args.library_sha256:
        raise ValueError('F3 library digest mismatch')
    def stop(*_):
        raise KeyboardInterrupt('Requested graceful stop')
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, stop)
    antenna = ('Presentation '+args.presentation_antenna_confirmed+', user confirmed'
               if args.presentation_antenna_confirmed else 'B-direct, user confirmed 2-3cm')
    result = dict(status='STARTED', mode=args.mode, antenna=antenna,
                  library_sha256=args.library_sha256, samples=[], rf_lo_hz=2450000000,
                  boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
    radio = None
    hw = None
    tx = rx = None
    owners = []
    captures = {}
    start = time.monotonic()
    with open('/run/lock/zss_release_v2.lock', 'a') as release_lock:
        fcntl.flock(release_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with open('/run/lock/zss_ad9361.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            hw = V2(args.bit, download=False)
            if not hw.overlay.is_loaded():
                raise RuntimeError('Frozen overlay is not loaded')
            gpio = hw.checked.registers('axi_ad9361_gpio')
            if gpio.read(0) or hw.src_regs.read(0) or hw.audio.control.read(0):
                raise RuntimeError('Existing hardware is not stopped')
        try:
            radio = F3Radio(args.library).open(gain=30)
            adc = hw.checked.registers('axi_ad9361')
            for ch in range(4):
                adc.write(0x400+ch*64, 0x51)
                adc.write(0x418+ch*64, 0)
                adc.write(0x4414+ch*64, 0)
                adc.write(0x4418+ch*64, 2)  # DMA source, initially disabled
            adc.write(0x4044, 1)
            result['prepared_attenuation_db'] = radio.tx_atten
            result['rejected_unsafe_attenuation'] = radio.lib.z20_set_tx_attenuation(39750)
            if result['rejected_unsafe_attenuation'] >= 0:
                raise RuntimeError('C attenuation boundary failed')
            # MODE3 uses live RF + noise, not replay + noise.
            hw.source.configure('noise', rate=3840000)
            result['mode3_ctrl_readback'] = hw.src_regs.read(0)
            hw.src_regs.write(0, 0)
            if result['mode3_ctrl_readback'] != 6:
                raise RuntimeError('MODE3 control readback failed')
            result['mode3_scope'] = 'Control readback only; RF injection selftest pending'
            result['start_health'] = radio.start()
            if args.mode == 'watchdog':
                # No waveform, maximum attenuation; deliberately stop heartbeat.
                time.sleep(2.3)
                result['watchdog_status'] = radio.lib.z20_f3_watchdog_status()
                result['watchdog_gpio'] = gpio.read(0)
                if result['watchdog_status'] != -110 or result['watchdog_gpio'] != 0:
                    raise RuntimeError('Watchdog reset failed')
            else:
                hw.prepare_receive()
                radio.health()
                if args.mode == 'calibrate':
                    tx = AdiCyclicTx(hw.checked.registers('axi_ad9361_dac_dma'))
                    rx = AdiDmac(hw.checked.registers('axi_ad9361_adc_dma'), 'rx')
                    words = cw_words(peak=1023)
                    txowner = allocate_owned(words.nbytes+128)
                    rxowner = allocate_owned(32768*8+128)
                    owners.extend((txowner, rxowner))
                    for o in owners:
                        o[:] = 0xa5
                    txbuf, rxbuf = txowner[64:-64], rxowner[64:-64]
                    txbuf.view('<i2')[:] = words.reshape(-1)
                    for o in owners:
                        o.flush()
                    rx.allocator = lambda _: rxbuf
                    radio.health()
                    rx.recv(rxbuf.nbytes, timeout_s=.6)
                    captures['tx_off_native'] = np.asarray(rxbuf).view('<i2').reshape(-1, 4).copy()
                    radio.health()
                    tx.start(txbuf)
                    for attenuation in attenuation_steps():
                        if time.monotonic()-start > 75:
                            raise TimeoutError('Bounded calibration deadline')
                        radio.set_attenuation(attenuation)
                        time.sleep(.05)
                        health = radio.health()
                        rx.recv(rxbuf.nbytes, timeout_s=.6)
                        radio.health()
                        native = np.asarray(rxbuf).view('<i2').reshape(-1, 4).copy()
                        iq = native[:, 0].astype(float)+1j*native[:, 1].astype(float)
                        metric = tone_metrics(iq)
                        result['samples'].append(dict(health, **metric))
                        captures['att_'+str(int(attenuation))+'_native'] = native
                        print('F3_SAMPLE', result['samples'][-1], flush=True)
                        if metric['max_component'] >= 2000:
                            raise RuntimeError('ADC near clipping; stop instead of increasing power')
                        if metric['cw_ratio_db'] >= 25:
                            break
                    radio.mute()
                    tx.stop(timeout_s=.6)
                    rx.mmio.write(rx.CTRL, 0)
                    result['broadband_25db_pass'] = bool(result['samples'][-1]['cw_ratio_db'] >= 25)
                    # Keep gain and waveform fixed; independently inspect PL PFB.
                    radio.health()
                    configure_checked(hw, radio, 2450000000)
                    hw.reset_channelizer()
                    hw.source.configure('noise', rate=3840000)
                    hw.lcd.set_bus_phase(2)
                    hw.lcd.enable()
                    hw.source.start()
                    radio.health()
                    tx.start(txbuf)
                    selected_attenuation = result['samples'][-1]['tx_atten_db']
                    for attenuation in attenuation_steps(selected_attenuation):
                        radio.set_attenuation(attenuation)
                        time.sleep(.02)
                    result['pfb_noise_probe'] = []
                    for noise_amp in (0, 0, 8192):
                        hw.src_regs.write(0x20, noise_amp)
                        if hw.src_regs.read(0x20) != noise_amp:
                            raise RuntimeError('Noise amplitude readback mismatch')
                        time.sleep(.02)
                        radio.health()
                        packet = hw.channel_capture.acquire(select_channel(240000), source=3, timeout_s=.6)
                        radio.health()
                        y = packet['iq'].astype(np.complex128)
                        signal_power = float(abs(y.mean())**2)
                        residual_power = float(np.mean(abs(y-y.mean())**2))
                        probe = dict(noise_amp=noise_amp, signal_power=signal_power,
                                     residual_power=residual_power,
                                     coherent_cw_ratio_db=float(10*np.log10(max(signal_power,1e-30)/max(residual_power,1e-30))),
                                     channel_rate_hz=480000,
                                     metric='DC coherent CW / all residual PL PFB output power; not occupied-band AMC SNR')
                        result['pfb_noise_probe'].append(probe)
                        captures['pfb_words_'+str(len(result['pfb_noise_probe']))] = packet['raw_words']
                    result['mode3_injection_observed'] = bool(result['pfb_noise_probe'][-1]['residual_power'] >
                        2*max(x['residual_power'] for x in result['pfb_noise_probe'][:2]))
                    result['mode3_scope'] = 'Actual RF+noise through PL PFB capture; not replay+noise'
                    hw.source.stop()
                    hw.src_regs.write(0x20, 0)
                    radio.mute()
                    tx.stop(timeout_s=.6)
                    result['guards_ok'] = all(bool(np.all(o[:64] == 0xa5) and np.all(o[-64:] == 0xa5)) for o in owners)
                    if not result['guards_ok']:
                        raise RuntimeError('DMA guard altered')
                elif args.mode == 'capture':
                    from sentinel.f3_capture import collect
                    collect(hw, radio, ROOT/'data/f3_ota', output, result)
                elif args.mode == 'pd':
                    from sentinel.f3_detection import pd_probe
                    pd_probe(hw, radio, result, captures)
                else:
                    for _ in range(5):
                        time.sleep(.1)
                        result['samples'].append(radio.health())
                radio.mute()
                radio.stop()
                mode = ct.c_uint32()
                radio._check(radio.lib.z20_get_ensm_mode(ct.byref(mode)), 'ENSM')
                result['stop_ensm'] = mode.value
                result['stop_attenuation_db'] = radio.tx_atten
                if mode.value != 2 or radio.tx_atten != (89.75, 89.75):
                    raise RuntimeError('Stop RF readback mismatch')
            result['status'] = 'PASS'
        except BaseException as error:
            result.update(status='FAIL', error=repr(error))
        finally:
            if radio is not None:
                try:
                    radio.mute()
                except Exception as error:
                    result['mute_cleanup_error'] = repr(error)
            if tx is not None:
                try:
                    tx.stop(timeout_s=.6)
                except Exception as error:
                    result.update(status='FAIL', tx_cleanup_error=repr(error))
            if rx is not None:
                rx.mmio.write(rx.CTRL, 0)
            hw.src_regs.write(0, 0)
            if radio is not None:
                radio.close()
            result['gpio_after_close'] = gpio.read(0)
            result['source_after_close'] = hw.src_regs.read(0)
            result['quarantined'] = bool((tx and tx.inflight) or (rx and rx.inflight))
            result['quarantined'] |= bool(hw.channel_capture.engine.inflight)
            result['quarantined'] |= bool(result.get('capture_tx_quarantined'))
            result['elapsed_s'] = time.monotonic()-start
            if result['gpio_after_close'] or result['source_after_close'] or result['quarantined']:
                result['status'] = 'FAIL'
            if captures:
                archive = output.with_suffix('.npz')
                atomic_write(archive, lambda stream: np.savez_compressed(stream, **captures))
                result['capture_sha256'] = hashlib.sha256(archive.read_bytes()).hexdigest()
            retained = {k: result.pop(k) for k in list(result) if k.startswith('_retained')}
            atomic_json(output, result)
            print(result, flush=True)
            if result['quarantined']:
                # Buffer lifetime cannot end before documented PL reset recovery.
                while True:
                    time.sleep(1)
            if owners:
                del txbuf, rxbuf
                for o in owners:
                    o.freebuffer()
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
