"""Bounded RX1 snapshots, separate from the disabled PL processing source.

No hardware access on import. Each tile has a separate settling/discard period;
this is explicitly not a continuous recording or a calibrated power measurement.
"""
import ctypes as ct
import base64
import hashlib
import json
from pathlib import Path
import time

import numpy as np

from .panorama import SAMPLE_RATE_HZ, tile_centers, welch_psd, stitch


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def seal(path):
    path = Path(path)
    Path(str(path)+'.sha256').write_text(digest(path)+'  '+path.name+'\n')


def write_json(path, data):
    path = Path(path)
    temp = path.with_suffix(path.suffix+'.tmp')
    temp.write_text(json.dumps(data, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    temp.replace(path)
    seal(path)


def validate_request(group, confirmed, limit=None, profile='legacy'):
    if not confirmed:
        raise PermissionError('Confirm the actual A/D receive antenna before scanning')
    if profile not in ('legacy', 'fast'):
        raise ValueError('Unknown scan profile')
    centers = tile_centers(group, 9000000 if profile == 'fast' else 8000000)
    if limit is not None:
        if type(limit) is not int or not 1 <= limit <= len(centers):
            raise ValueError('Invalid bounded tile count')
        centers = centers[:limit]
    return centers


def radio_state(radio):
    mode = ct.c_uint32()
    radio._check(radio.lib.z20_get_ensm_mode(ct.byref(mode)), 'ENSM')
    gain = ct.c_int32()
    radio._check(radio.lib.z20_get_rx_gain(0, ct.byref(gain)), 'RX1 gain')
    state = dict(lo_hz=radio.rx_lo, rate_hz=radio.rate,
                 attenuation_db=list(radio.tx_atten), ensm_mode=mode.value,
                 rssi_dbm=radio.rssi(0), rx1_gain_db=gain.value)
    if state['attenuation_db'] != [89.75, 89.75] or mode.value != 1:
        raise RuntimeError('Receive-only/max attenuation readback required')
    if state['rssi_dbm'] > -30:
        raise RuntimeError('RX1 RSSI exceeds -30 dBm; abort snapshot')
    return state


class GuardedSnapshots:
    """One owned guarded allocation per finite DMAC transaction."""
    def __init__(self, registers):
        from .dma import AdiDmac
        self.owners = []
        self.dma = AdiDmac(registers, 'rx', allocator=self.allocate)

    def allocate(self, n):
        from .cma import allocate_owned
        owner = allocate_owned(n+128)
        self.owners.append(owner)
        owner[:] = 0xa5
        owner[64:64+n] = 0xcc
        owner.flush()
        return owner[64:64+n]

    def capture(self, samples=131072):
        before = time.monotonic()
        received = self.dma.recv(samples*8, timeout_s=3)
        owner = self.owners[-1]
        try:
            owner.invalidate()
            if not (np.all(owner[:64] == 0xa5) and np.all(owner[-64:] == 0xa5)):
                raise RuntimeError('DMA allocation guard changed')
            words = np.asarray(received).view('<i2').reshape(samples, 4).copy()
            if words.min() < -2048 or words.max() > 2047:
                raise RuntimeError('ADC format is not signed 12-bit')
            return words, dict(samples=samples, bytes=samples*8, guards_ok=True,
                               elapsed_s=time.monotonic()-before,
                               minimum=int(words.min()), maximum=int(words.max()))
        finally:
            # recv completed before this block. On timeout it never reaches here.
            del received
            owner.freebuffer()
            self.owners = [item for item in self.owners if item is not owner]

    def stop(self):
        self.dma.mmio.write(self.dma.CTRL, 0)
        return bool(self.dma.inflight)


def scan_session(session, output, group, centers, snapshots, profile='legacy', keep_iq=False,
                 progress=None, cancelled=None, restore_lo_hz=96050000,
                 restore_bandwidth_hz=1500000, settle_s=.15):
    """Run inside an already exclusive, baseline-rate Session. No source.start."""
    output = Path(output)
    if not .05 <= settle_s <= .5:
        raise ValueError('Settling time must be 0.05..0.5 seconds')
    plan = validate_request(group, True, profile=profile)
    if not centers or centers != plan[:len(centers)]:
        raise ValueError('Scan must follow the validated bounded plan')
    samples = 65536 if profile == 'fast' else 131072
    keep_iq = bool(keep_iq or profile == 'legacy')
    radio, hw = session.radio, session.hw
    records, tiles = [], []
    result = dict(schema=1, status='RUNNING', group=group, source='RX1A_ANTENNA',
                  scope='FINITE_DISCONTINUOUS_RAW_DMA_SNAPSHOTS',
                  rf_transmission_requested=False, sample_rate_hz=SAMPLE_RATE_HZ,
                  bandwidth_requested_hz=24000000, usable_tile_hz=20000000,
                  power_units='FS^2/Hz', calibrated_dbm=False, tiles=records,
                  pl_source_enabled=False, continuous_integrity_certified=False)
    result.update(profile=profile, samples_per_tile=samples, raw_iq_saved=keep_iq,
                  step_hz=9000000 if profile == 'fast' else 8000000,
                  settle_s=settle_s)
    adc = hw.checked.registers('axi_ad9361')
    try:
        for index, lo in enumerate(centers):
            if cancelled is not None and cancelled():
                raise InterruptedError('Scan stopped by owner')
            tile_started = time.monotonic()
            timing = {}
            if lo not in plan:
                raise ValueError('LO outside the selected antenna scan plan')
            if hw.src_regs.read(0) & 1:
                raise RuntimeError('PL processing source must remain disabled')
            mark = time.monotonic()
            radio.configure(lo, SAMPLE_RATE_HZ, 24000000)
            timing['combined_rate_lo_bandwidth_configure_s'] = time.monotonic()-mark
            mark = time.monotonic()
            time.sleep(settle_s)
            timing['agc_wait_s'] = time.monotonic()-mark
            mark = time.monotonic()
            before = radio_state(radio)
            if abs(before['lo_hz']-lo) > 3 or before['rate_hz'] != SAMPLE_RATE_HZ:
                raise RuntimeError('LO/sample-rate readback mismatch')
            # Discard one bounded transaction after retuning; do not claim
            # continuity across retunes or clear in-session errors as "zero gaps".
            timing['initial_state_readback_s'] = time.monotonic()-mark
            mark = time.monotonic()
            _, discard = snapshots.capture(samples=samples) if profile == 'fast' else snapshots.capture()
            timing['discard_dma_s'] = time.monotonic()-mark
            mark = time.monotonic()
            words, capture = snapshots.capture(samples=samples) if profile == 'fast' else snapshots.capture()
            timing['retained_dma_s'] = time.monotonic()-mark
            mark = time.monotonic()
            after = radio_state(radio)
            if after['lo_hz'] != before['lo_hz'] or after['rate_hz'] != SAMPLE_RATE_HZ:
                raise RuntimeError('RF configuration changed during snapshot')
            timing['final_state_readback_s'] = time.monotonic()-mark
            mark = time.monotonic()
            path = output/('tile_%03d.npz' % index)
            iq = words[:, 0].astype(float)+1j*words[:, 1].astype(float)
            frequency, power = welch_psd(iq)
            timing['welch_s'] = time.monotonic()-mark
            mark = time.monotonic()
            values = dict(baseband_hz=frequency, psd_fs2_per_hz=power,
                          actual_lo_hz=before['lo_hz'], rate_hz=SAMPLE_RATE_HZ)
            if keep_iq:
                values['rx1_iq_counts'] = words[:, :2]
            # PSD-only tiles are small; compression costs more CPU than it saves.
            (np.savez_compressed if profile == 'legacy' else np.savez)(path, **values)
            seal(path)
            timing['npz_compression_write_and_hash_s'] = time.monotonic()-mark
            records.append(dict(index=index, requested_lo_hz=lo, before=before,
                                after=after, file=path.name, sha256=digest(path),
                                capture=capture, settling_discard=discard,
                                clipped_fraction=float(np.mean((words[:, :2] <= -2048) |
                                                               (words[:, :2] >= 2047))),
                                adc_status=adc.read(0x5c),
                                pl_perf_status_unqualified=hw.perf.snapshot().status))
            timing['unattributed_s'] = max(0., time.monotonic()-tile_started-sum(timing.values()))
            timing['tile_total_before_progress_write_s'] = time.monotonic()-tile_started
            records[-1]['timing'] = timing
            tiles.append((before['lo_hz'], frequency, power))
            write_json(output/'result.json', result)
            print(json.dumps(dict(type='pano_tile', schema=1, group=group,
                index=index, total=len(centers), lo_hz=before['lo_hz'],
                sample_rate_hz=SAMPLE_RATE_HZ, nfft=len(frequency),
                psd_f32_base64=base64.b64encode(np.asarray(power, dtype='<f4').tobytes()).decode('ascii'),
                provisional=True)), flush=True)
            print('F4_TILE %d/%d LO=%d' % (index+1, len(centers), before['lo_hz']), flush=True)
            if progress is not None:
                progress(index, len(centers), before['lo_hz'], frequency, power)
        frequency, power, count = stitch(tiles, group)
        path = output/'panorama.npz'
        np.savez_compressed(path, frequency_hz=frequency, psd_fs2_per_hz=power, count=count)
        seal(path)
        result.update(status='PASS_SNAPSHOT_SCAN', panorama=path.name,
                      panorama_sha256=digest(path),
                      full_group=len(centers) == len(plan),
                      missing_bins=int(np.count_nonzero(count == 0)),
                      covered_bins=int(np.count_nonzero(count)),
                      notes='Uncalibrated AGC/antenna response. Gaps between finite captures; '
                            'PL FIFO sticky flags are not a continuous-DMA acceptance metric.')
    except InterruptedError as error:
        result.update(status='CANCELLED', error=str(error))
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
    finally:
        result['buffers_quarantined'] = snapshots.stop()
        try:
            if result['buffers_quarantined']:
                raise RuntimeError('In-flight DMA quarantined; no automatic RF retune')
            radio.configure(restore_lo_hz, 3840000, restore_bandwidth_hz)
            state = radio_state(radio)
            if state['rate_hz'] != 3840000 or abs(state['lo_hz']-restore_lo_hz) > 3:
                raise RuntimeError('Baseline restoration readback failed')
            result['baseline_restore'] = state
            result['receive_startup_restored'] = hw.prepare_receive()
        except BaseException as error:
            result.update(status='FAIL', restoration_error=repr(error))
        write_json(output/'result.json', result)
    return result
