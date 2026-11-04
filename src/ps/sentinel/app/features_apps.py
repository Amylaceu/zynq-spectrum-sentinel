"""Application cards on the J6 single RF owner; no synthesis, training or TX.

Long operations service stop/ping between finite transactions. They never run a
second Session or a background hardware thread. Every result has JSON + SHA256.
"""
from collections import Counter, deque
from datetime import datetime, timezone
import json
from pathlib import Path
import time
import uuid

import numpy as np

from .features_j6 import FeatureBackend
from ..release_support import select_demo_station, write_result, sha


APPLICATIONS = ('F0', 'F8', 'F11', 'F12', 'F13', 'F14')


def qualified(trials):
    return (len(trials) == 10 and all(t['quality_pass'] for t in trials)
            and sum(t['label'] == 'FM' and t['confidence'] >= .5 for t in trials) >= 9)


def voted(predictions):
    if len(predictions) < 5:
        return dict(label='?', confidence=0., votes=len(predictions), top5=[])
    counts = Counter(p['label'] for p in predictions)
    winners = {k for k, n in counts.items() if n == max(counts.values())}
    label = next(p['label'] for p in reversed(predictions) if p['label'] in winners)
    confidence = float(np.mean([p['confidence'] for p in predictions if p['label'] == label]))
    labels = {v['label'] for p in predictions for v in p['top5']}
    top5 = sorted([dict(label=k, score=sum(next((v['score'] for v in p['top5']
                    if v['label'] == k), 0.) for p in predictions)/5) for k in labels],
                  key=lambda v: -v['score'])[:5]
    return dict(label=label if confidence >= .5 and counts[label] >= 3 else '?',
                confidence=confidence, votes=5, majority=counts[label], top5=top5,
                top5_scope='mean_of_five_coarse8_softmax_top5; omitted probabilities treated as zero')


def strongest_points(frequency, power, count, band=None, limit=5):
    """Select measured, separated peaks; never rank gaps or nonfinite bins."""
    valid = (count > 0) & np.isfinite(power) & (power > 0)
    if band is not None:
        valid &= (frequency >= band[0]) & (frequency <= band[1])
    points = []
    for index in np.argsort(np.where(valid, power, -np.inf))[::-1]:
        if not valid[index] or len(points) == limit:
            break
        if all(abs(frequency[index]-p['frequency_hz']) >= 200000 for p in points):
            points.append(dict(frequency_hz=float(frequency[index]),
                               power_db=float(10*np.log10(power[index]))))
    return points


class ApplicationBackend(FeatureBackend):
    def start(self):
        self.job = None
        self.cancel_requests = []
        self.app_results = []
        self.qualified_stations = []
        self.quarantined = None
        self.fatal_error = None
        self.record_stop = False
        self.recording = False
        super().start()
        self.baseline_config = dict(self.config)

    def feature(self, identity, action='start', mode='CA', alpha=1974):
        if identity == 'F2' and action == 'start':
            comparison = super().feature('F9')
            if comparison['status'] != 'READY':
                comparison = dict(comparison, id='F2')
                return comparison
            value = super().feature(identity, action, mode, alpha)
            value['metrics'].update(comparison['metrics'])
            value['elapsed_s'] += comparison['elapsed_s']
            value['within_target'] = value['elapsed_s'] <= 3
            value['comparison_source'] = 'Four live PL golden frames, followed by continuous three-tone display'
            self.last_feature = value
            self._present(force=True)
            write_result(self.output/('merged_f2_%d.json' % time.monotonic_ns()), value)
            return value
        return super().feature(identity, action, mode, alpha)

    def restore(self):
        if self.quarantined is not None or self.fatal_error:
            raise RuntimeError('DMA quarantined; automatic restoration forbidden')
        self.mute()
        self.hw.source.stop()
        if hasattr(self, 'baseline_config'):
            self.config = dict(self.baseline_config)
            if abs(self.radio.rx_lo-self.config['lo_hz']) > 3 or self.radio.rate != 3840000:
                self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
        self.tracker.tracks.clear()
        self.last_audio = None
        return super().restore()

    def _start_receive(self):
        super()._start_receive()
        if self.link: self.link.lo = self.config['lo_hz']

    def emit(self, stage, **data):
        data.update(id=self.application_id, run_id=self.run_id, stage=stage)
        self.application_display(stage, data)
        self.link.service.publish('file', json.dumps(data, allow_nan=False).encode('utf-8'),
                                  application_data=True)

    def application_display(self, stage, data):
        """Use existing PS-region rendering without touching RF/DMA ownership."""
        if self.recording:
            return  # Do not add UI/MMIO work to a finite DMA recording deadline.
        self.lcd_identity = self.application_id
        detail = stage.upper()
        if 'completed' in data and data.get('total'):
            detail = '%d/%d (%.0f%%)' % (data['completed'], data['total'],
                                      100*data['completed']/data['total'])
        if stage == 'confusion': detail += ' ACC %.1f%%' % (100*data['accuracy_10'])
        if stage == 'bist':
            detail = 'ERR '+str(sum(bool(v & 6) for v in data['channel_status']))
        if stage == 'vote':
            detail = '%s %.0f%% / %d VOTES' % (data['vote']['label'],
                100*data['vote']['confidence'], data['vote']['votes'])
        if stage == 'qualification': detail = '%d QUALIFIED' % len(data['eligible'])
        if stage == 'found_stations': detail = '%d STATIONS' % len(data['stations'])
        if stage == 'finished':
            result = data['result']
            if self.application_id == 'F8' and not result.get('restored'):
                detail = '%.3f MHz' % (self.config['station_hz']/1e6)
            elif self.application_id == 'F13' and 'scores' in result:
                detail = 'ACC %.1f%%' % (100*result['scores']['accuracy_10'])
            else: detail = '%s %.1fs' % (result['status'], result['elapsed_s'])
        self.lcd_progress = detail
        if self.quarantined is None and not self.fatal_error and (
                stage in ('finished', 'bist', 'qualification', 'vote') or
                time.monotonic()-self.last_ui >= .5):
            self._present(force=True)

    def checkpoint(self):
        if self.stop_requested():
            raise InterruptedError('Service stopping')
        while True:
            request = self.link.service.poll()
            if request is None:
                break
            _, _, name, args = request
            if name == 'stop' or name in ('application', 'feature') and args.get('action') == 'stop':
                self.cancel_requests.append(request)
            elif name == 'ping':
                self.link.service.reply(request, board_mono=time.monotonic())
            elif name == 'application' and args.get('action') == 'record_stop' and self.recording:
                self.record_stop = True
                self.link.service.reply(request, recording_stop_requested=True)
            else:
                self.link.service.reply(request, ok=False, error='Application busy; stop first')
        if self.cancel_requests:
            raise InterruptedError('Application stop requested')

    def application_request(self, request, args):
        identity = args['id']
        if args['action'] == 'record_stop':
            self.link.service.reply(request, recording_stop_requested=False)
            return
        if args['action'] == 'stop':
            value = self.feature('F1', 'stop')
            value['id'] = identity
            self.link.service.reply(request, feature=value)
            return
        if args['action'] == 'record':
            if self.active != 'F8' or not self.audible:
                raise RuntimeError('Start a quality-approved audible broadcast before recording')
        else:
            self.restore()
        self.application_id, self.run_id = identity, uuid.uuid4().hex
        self.job_output = self.output/('application_'+self.run_id)
        self.job_output.mkdir()
        self.app_started = time.monotonic()
        self.cancel_requests = []
        self.job = dict(args)
        self.active = identity
        self.lcd_identity, self.lcd_progress = identity, '0%'
        self._present(force=True)
        self.link.service.reply(request, feature=dict(id=identity, status='READY',
            elapsed_s=time.monotonic()-self.app_started, metrics={}, within_target=True,
            application_pending=True, run_id=self.run_id))

    def tick(self):
        if self.job is not None:
            args, self.job = self.job, None
            result = dict(id=args['id'], run_id=self.run_id, status='RUNNING', tx_requested=False)
            try:
                suffix = '_'+args['action'] if args['action'] in ('search', 'record') else ''
                result.update(getattr(self, 'run_'+args['id'].lower()+suffix)(args))
                result.setdefault('status', 'DONE')
                if result['status'] == 'RUNNING': result['status'] = 'DONE'
            except InterruptedError as error:
                result.update(status='CANCELLED', error=str(error))
            except Exception as error:
                result.update(status='FAILED', error=repr(error))
            finally:
                result['elapsed_s'] = time.monotonic()-self.app_started
                keep_live = result['status'] == 'DONE' and args['id'] in ('F8', 'F12') and args['action'] == 'start'
                if not keep_live and self.quarantined is None and not self.fatal_error:
                    try:
                        result['readback'] = self.restore()
                        result['restored'] = True
                    except Exception as error:
                        result.update(status='FAILED', restored=False, restoration_error=repr(error))
                        self.fatal_error = 'Baseline restoration failed; further RF commands disabled'
                write_result(self.job_output/'result.json', result)
                self.app_results.append(result)
                self.emit('finished', result=result)
                for req in self.cancel_requests:
                    self.link.service.reply(req, ok=bool(result.get('restored')), feature=dict(id=args['id'],
                        status='STOPPED' if result.get('restored') else 'FAILED',
                        restored=bool(result.get('restored')), readback=result.get('readback')))
                self.cancel_requests = []
                if self.quarantined is not None:
                    raise RuntimeError('DMA quarantine requires controlled recovery; no reset performed')
                if self.fatal_error:
                    raise RuntimeError(self.fatal_error)
            return
        if self.active == 'F12':
            self.safety()
            self.f12_sample()
            return
        super().tick()

    def run_f8(self, args):
        requested = args['station_hz']
        if not requested and getattr(self, 'found_stations', []):
            requested = self.found_stations[0]['frequency_hz']
        if requested:
            # User requested tuning, not a claim of a known station identity.
            candidate = next((s for s in getattr(self, 'found_stations', []) if s['frequency_hz'] == requested), None)
            self.config['lo_hz'] = candidate['lo_hz'] if candidate else requested+250000
            self.config['station_hz'] = requested
            self.config['stations'] = [dict(frequency_hz=requested, lo_hz=self.config['lo_hz'], confirmed_stereo=True)]
        self._prepare_capture_dma()
        self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
        self._start_receive()
        choice = select_demo_station(self.hw, self.radio, self.config, self.job_output)
        write_result(self.job_output/'selection.json', choice)
        self.emit('stations', selection=choice)
        eligible = [v['station'] for v in choice['candidates'] if v['trusted']]
        station = next((v for v in eligible if v['frequency_hz'] == requested), None) if requested else choice['selected']
        if station is None:
            raise RuntimeError('No trusted stereo station passed quality; remain muted')
        self.config['station_hz'] = station['frequency_hz']
        tuned_config = dict(self.config)
        # Base feature restores defaults before activation; apply the temporary
        # selected station only inside its startup hook.
        self.tuned_start_config = tuned_config
        value = self.feature('F8')
        value['elapsed_s'] = time.monotonic()-self.app_started
        value['within_target'] = value['elapsed_s'] <= 3
        if value['status'] != 'READY': raise RuntimeError(value.get('error'))
        self.emit('audio_ready', feature=value)
        return dict(status='DONE', feature=value, selection=choice)

    def before_feature_start(self, identity):
        if identity == 'F8' and hasattr(self, 'tuned_start_config'):
            self.config = self.tuned_start_config
            del self.tuned_start_config

    def _quality(self):
        if not self.recording:
            return super()._quality()
        # The existing quality algorithm is unchanged. Defer its compressed SD
        # evidence writes until the raw RX queue has drained; synchronous npz
        # writes compete with the finite DMA refill deadline on Cortex-A9.
        from ..capture_x5 import select_channel
        from ..fm_quality import stereo_quality
        capture = self.hw.channel_capture.acquire(
            select_channel(self.config['station_hz']-self.config['lo_hz']), source=0)
        quality = stereo_quality(capture['iq'])
        entry = dict(quality, scene=self.scene, observed_mono=time.monotonic(),
                     timestamp_cycles=capture['timestamp_cycles'])
        self.record_quality.append((capture, entry))
        self.quality_samples.append(entry)
        self.quality, self.last_quality = quality, time.monotonic()
        return quality

    def run_f0(self, args):
        self.radio.check_rssi()
        duration_ms = 500
        try:
            statuses = self.radio.bist_prbs(duration_ms)
        except Exception:
            self.fatal_error = 'PN check failed; C driver holds RF reset. Stop service; do not continue RX.'
            raise
        # C adapter restores PN selection/BIST and ends in ALERT, never TX.
        # Re-enter the same RX configuration only after the finite check ends.
        self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
        values = dict(channel_status=statuses, error_channels=sum(bool(s & 6) for s in statuses),
            duration_ms=duration_ms, nominal_samples_per_channel=round(3840000*duration_ms/1000),
            actual_compared_word_counter_available=False,
            scope='RX-injected PN9 status flags; nominal sample count, not measured bit-error count')
        self.emit('bist', **values)
        return dict(status='DONE' if not any(s & 6 for s in statuses) else 'FAILED', bist=values)

    def run_f8_search(self, args):
        from ..capture_x5 import select_channel
        from ..fm_quality import stereo_quality
        self._prepare_capture_dma()
        candidates, trials = [], []
        # Existing quality measurement, a finite receive-only 100 kHz grid.
        # No station identity is inferred from a spectral peak or model label.
        for start in range(87500000, 108000001, 1000000):
            self.checkpoint()
            self.hw.source.stop()
            self.config['lo_hz'] = start+550000
            self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
            self._start_receive()
            time.sleep(.08)
            for hz in range(start, min(start+1000000, 108100000), 100000):
                self.checkpoint(); self.radio.check_rssi()
                capture = self.hw.channel_capture.acquire(select_channel(hz-self.config['lo_hz']), source=0)
                q = stereo_quality(capture['iq'])
                trial = dict(frequency_hz=hz, lo_hz=self.config['lo_hz'], quality=q)
                trials.append(trial)
                if q['good'] and q['pilot_prominence_db'] >= 20: candidates.append(trial)
            self.emit('fm_search', completed=min(start+900000, 108000000)-87500000,
                total=20500000, candidates=len(candidates))
        selected = []
        for v in sorted(candidates, key=lambda v: -v['quality']['pilot_prominence_db']):
            if all(abs(v['frequency_hz']-s['frequency_hz']) >= 200000 for s in selected):
                selected.append(dict(frequency_hz=v['frequency_hz'], lo_hz=v['lo_hz'], confirmed_stereo=True))
            if len(selected) == 8: break
        validated = []
        for station in selected:
            self.checkpoint()
            self.hw.source.stop()
            self.config['lo_hz'] = station['lo_hz']
            self.config['stations'] = [station]
            self.radio.configure(station['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
            self._start_receive()
            choice = select_demo_station(self.hw, self.radio, self.config, self.job_output)
            if choice['selected']: validated.append(station)
        self.found_stations = validated
        write_result(self.job_output/'search_trials.json', dict(trials=trials))
        self.emit('found_stations', stations=validated)
        return dict(status='DONE', stations=validated, trial_count=len(trials),
                    trials_file='search_trials.json', trials_sha256=sha(self.job_output/'search_trials.json'),
                    scope='100 kHz receive grid; stereo pilot quality, not broadcaster identity')

    def run_f8_record(self, args):
        import math
        from ..rx_queue import QueuedRx
        from ..panorama_capture import seal
        # A 16 MiB descriptor gives the foreground quality/safety checks twice
        # the previous refill budget. Capture whole descriptors, then trim the
        # verified tail to exactly three seconds (never pad or stitch gaps).
        block_bytes = 16777216
        requested_samples = 3*3840000
        blocks = math.ceil(requested_samples/(block_bytes//8))
        recording = np.empty(blocks*block_bytes, dtype=np.uint8)
        recording.fill(0)  # Fault in destination pages before DMA begins.
        raw = self.job_output/'raw'; raw.mkdir()
        queue = QueuedRx(self.hw.checked.registers('axi_ad9361_adc_dma'), nbytes=block_bytes)
        adc = self.hw.checked.registers('axi_ad9361')
        self.record_stop = False; self.recording = True
        self.record_quality = []
        records = []
        capture_error = None
        try:
            queue.start()
            warmup = time.monotonic()+1
            while time.monotonic() < warmup:
                queue.consume(lambda _: None)
            adc.write(0x88, 4)
            if adc.read(0x88) & 4: raise RuntimeError('FIFO overflow after warmup')
            # Drop all descriptors that could predate the cleared epoch. A
            # fault from this point is measured and is never cleared again.
            for _ in range(len(queue.buffers)):
                queue.consume(lambda _: None)
                if adc.read(0x88) & 4: raise RuntimeError('FIFO overflow during clean priming')
            epoch = time.monotonic()
            for index in range(blocks):
                loop_start = time.monotonic()
                self.checkpoint()
                if self.record_stop and records: break
                if time.monotonic()-epoch > 15: raise TimeoutError('Finite recording deadline')
                copy_seconds = []
                def copy(buffer):
                    view = np.asarray(buffer).view(np.uint8).reshape(-1)
                    if view.nbytes != block_bytes: raise ValueError('Recording DMA length differs')
                    mark = time.monotonic()
                    np.copyto(recording[index*block_bytes:(index+1)*block_bytes], view)
                    copy_seconds.append(time.monotonic()-mark)
                identifier = queue.consume(copy)
                records.append(dict(index=index, descriptor_id=identifier, copy_s=copy_seconds[-1],
                    fifo_status=int(adc.read(0x88)), audio=self.hw.audio.snapshot()))
                if records[-1]['fifo_status'] & 4: raise RuntimeError('ADC overflow; recording rejected')
                check_start = time.monotonic()
                self._audio_quality()
                quality_end = time.monotonic()
                self.safety()
                records[-1].update(quality_s=quality_end-check_start,
                    safety_s=time.monotonic()-quality_end)
                if not self.audible: raise RuntimeError('Broadcast quality failed while recording')
                self.emit('recording', completed=index+1, total=blocks,
                    sampled_s=min((index+1)*(block_bytes//8), requested_samples)/3840000,
                    limit_s=3)
                records[-1].update(loop_s=time.monotonic()-loop_start,
                    completed_offset_s=time.monotonic()-epoch)
                if adc.read(0x88) & 4: raise RuntimeError('ADC overflow after service checks; recording rejected')
        except BaseException as error:
            capture_error = repr(error)
            raise
        finally:
            try:
                queue.close()
            finally:
                self.recording = False
                if queue.failed: self.quarantined = queue
                if not queue.failed:
                    from .monitor_x5 import save_capture
                    for capture, entry in self.record_quality:
                        filename, digest = save_capture(self.job_output, self.capture_index, capture)
                        self.capture_index += 1
                        entry.update(capture_filename=filename, capture_sha256=digest)
                write_result(raw/'acquisition_diagnostics.json', dict(blocks=records,
                    error=capture_error, buffers_quarantined=bool(queue.failed),
                    quality=[entry for _, entry in self.record_quality],
                    sd_evidence_deferred_until_dma_drained=True))
                self.record_quality = []
        if not records: raise RuntimeError('No recorded blocks')
        self.mute()
        samples = min(requested_samples, len(records)*(block_bytes//8))
        if recording[:len(records)*block_bytes].view('<i2').min() < -2048 or recording[:len(records)*block_bytes].view('<i2').max() > 2047:
            raise ValueError('Invalid signed 12-bit ADC format')
        path = raw/'current_adc_iq.i16'
        with path.open('xb') as stream: recording[:samples*8].tofile(stream)
        seal(path)
        station, lo = self.config['station_hz'], self.config['lo_hz']
        stopped = self.restore()
        value = dict(status='PASS_FINITE_RECORDING', session_id=self.run_id, station_hz=station,
            sample_rate_hz=3840000, lo_hz=lo, file=path.name, file_sha256=sha(path),
            recorded_samples=samples, duration_s=samples/3840000, blocks=records,
            requested_duration_s=3, acquired_samples=len(records)*(block_bytes//8),
            discarded_tail_samples=len(records)*(block_bytes//8)-samples,
            user_stopped=self.record_stop,
            synthetic=False, observed_overflow_epochs=0, buffers_quarantined=False,
            speaker_pcm_readback=False, listen_during_recording=True, owner_stopped=stopped,
            before=dict(lo_hz=lo), sampled_duration_s=samples/3840000,
            source='CURRENT_RX1A_FM_IQ',
            continuity='No FIFO overflow observed; no embedded ADC sequence counter')
        write_result(raw/'result.json', value)
        self.emit('recorded', remote_raw=str(raw), capture=value, capture_sha256=sha(raw/'result.json'))
        return dict(status='DONE', recording=value, restored=True)

    def run_f11(self, args):
        from ..panorama_capture import GuardedSnapshots, scan_session
        from ..panorama import tile_centers
        snapshots = GuardedSnapshots(self.hw.checked.registers('axi_ad9361_adc_dma'))
        first = []
        def progress(index, total, lo, frequency, power):
            if not first: first.append(time.monotonic()-self.app_started)
            # Display at most 512 actual bins per tile; full resolution is
            # retained in the signed NPZ evidence, not sent through HostLink.
            valid = np.flatnonzero((abs(frequency) <= 10000000) & (abs(frequency) >= 150000))[::8]
            self.emit('scan_tile', completed=index+1, total=total,
                elapsed_s=time.monotonic()-self.app_started, lo_hz=lo,
                frequency_hz=(frequency[valid]+lo).tolist(),
                power_db=(10*np.log10(np.maximum(power[valid], 1e-30))).tolist())
        def cancelled():
            self.checkpoint()
            return False
        scan_output = self.job_output/'scan'
        scan_output.mkdir()
        value = scan_session(self.session, scan_output, 'A', tile_centers('A', 9000000),
            snapshots, profile='fast', progress=progress, cancelled=cancelled,
            restore_lo_hz=self.config['lo_hz'], restore_bandwidth_hz=self.config['rf_bandwidth_hz'],
            settle_s=self.config.get('panorama_settle_s', .15))
        if value.get('buffers_quarantined'):
            self.quarantined = snapshots
            raise RuntimeError('Panorama DMA quarantined; retaining owners')
        strongest, fm_strongest = [], []
        if value.get('panorama'):
            with np.load(scan_output/value['panorama'], allow_pickle=False) as data:
                f, p, count = data['frequency_hz'], data['psd_fs2_per_hz'], data['count']
                strongest = strongest_points(f, p, count)
                fm_strongest = strongest_points(f, p, count, (88000000, 108000000))
        return dict(status='DONE' if value['status'] == 'PASS_SNAPSHOT_SCAN' else value['status'],
            first_tile_s=first[0] if first else None, within_target=time.monotonic()-self.app_started <= 15,
            scan_status=value['status'], scan_file='scan/result.json',
            scan_sha256=sha(scan_output/'result.json'), strongest=strongest,
            fm_strongest=fm_strongest, tiles=len(value['tiles']),
            missing_bins=value.get('missing_bins'), covered_bins=value.get('covered_bins'),
            settle_s=value.get('settle_s'),
            spur_assessment='UNDETERMINED: no same-frequency F1 corroboration')

    def run_f12(self, args):
        from ..capture_x5 import select_channel
        from ..fm_quality import stereo_quality
        from .monitor_x5 import save_capture
        if not hasattr(self, 'found_stations'):
            self.run_f8_search(args)
        self._prepare_capture_dma()
        self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
        self._start_receive()
        qualification = []
        stations = self.found_stations
        for station in stations:
            self.hw.source.stop()
            self.config['lo_hz'] = station['lo_hz']
            self.radio.configure(station['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
            self._start_receive()
            trials = []
            for index in range(10):
                self.checkpoint(); self.safety()
                capture = self.hw.channel_capture.acquire(select_channel(station['frequency_hz']-self.config['lo_hz']), source=0)
                filename, digest = save_capture(self.job_output, len(qualification)*10+index, capture)
                quality = stereo_quality(capture['iq'])
                prediction = self.predictor.predict(capture['iq'], fs=480000)[0]
                trials.append(dict(label=prediction['label'], confidence=prediction['confidence'],
                    quality_pass=bool(quality['good'] and quality['pilot_prominence_db'] >= 20),
                    quality=quality, capture_filename=filename, capture_sha256=digest))
                self.emit('qualifying', frequency_hz=station['frequency_hz'], completed=index+1, total=10)
            qualification.append(dict(station=station, trials=trials, qualified=qualified(trials)))
        self.qualified_stations = [v['station']['frequency_hz'] for v in qualification if v['qualified']]
        write_result(self.job_output/'qualification.json', dict(stations=qualification))
        self.emit('qualification', stations=qualification, eligible=self.qualified_stations)
        frequency = args['station_hz'] or self.config['station_hz']
        if frequency not in self.qualified_stations and self.qualified_stations:
            frequency = self.qualified_stations[0]
        if frequency not in self.qualified_stations:
            return dict(status='NOT_QUALIFIED', qualification=qualification,
                        reason='No selected candidate meets quality and FM >=9/10; no label displayed')
        self.f12_frequency = frequency
        chosen = next(s for s in stations if s['frequency_hz'] == frequency)
        self.hw.source.stop()
        self.config['lo_hz'] = chosen['lo_hz']
        self.radio.configure(chosen['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
        self._start_receive()
        self.f12_votes = deque(maxlen=5)
        self.f12_last = 0.
        self.f12_index = 100
        self.active, self.scene = 'F12', 'perf'
        self.hw.lcd.enable()
        for _ in range(5):
            self.checkpoint(); self.f12_sample(force=True)
        return dict(status='DONE', qualification=qualification, vote=voted(self.f12_votes),
                    first_vote_s=time.monotonic()-self.app_started,
                    within_target=time.monotonic()-self.app_started <= 5)

    def f12_sample(self, force=False):
        if not force and time.monotonic()-self.f12_last < .4: return
        from ..capture_x5 import select_channel
        from ..fm_quality import stereo_quality
        from .monitor_x5 import save_capture
        start = time.monotonic()
        capture = self.hw.channel_capture.acquire(select_channel(self.f12_frequency-self.config['lo_hz']), source=0)
        filename, digest = save_capture(self.job_output, self.f12_index, capture)
        self.f12_index += 1
        quality = stereo_quality(capture['iq'])
        if quality['good'] and quality['pilot_prominence_db'] >= 20:
            self.f12_votes.append(self.predictor.predict(capture['iq'], fs=480000)[0])
        else:
            self.f12_votes.clear()
        vote = voted(self.f12_votes)
        self.emit('vote', frequency_hz=self.f12_frequency, vote=vote, quality=quality,
            capture_filename=filename, capture_sha256=digest,
            latency_ms=(time.monotonic()-start)*1000)
        self.link.service.publish('iq', np.asarray(capture['iq'][:512], dtype='<c8').tobytes(),
                                  target_key=0, sample_rate_hz=480000)
        self.capture(); self._present(force=True)
        self.f12_last = time.monotonic()

    def run_f13(self, args):
        from ..amc.contract import CLASSES
        from ..capture_x5 import decode_packet, select_channel
        from ..f3_evaluate import add_noise, scores
        directory = self.root/'data/f3_measured'
        manifest = json.loads((directory/'result.json').read_text())
        reference = json.loads((directory/'evaluation.json').read_text())
        if sha(directory/'result.json') != reference['capture_result_sha256'] or sha(self.model) != reference['model_sha256']:
            raise ValueError('F3 capture/model provenance mismatch')
        signals = []
        for index, item in enumerate(manifest['modulation_captures']):
            self.checkpoint()
            path = directory/item['filename']
            if item['index'] != index or item['label'] != CLASSES[index] or sha(path) != item['sha256']:
                raise ValueError('F3 class provenance differs')
            with np.load(path, allow_pickle=False) as data:
                if data['words'].shape != (50, 4104) or int(data['fs_hz']) != 480000:
                    raise ValueError('F3 packet dimensions differ')
                signals.extend(decode_packet(w, select_channel(240000), 3)['iq'] for w in data['words'])
        x = add_noise(np.stack(signals), 10, np.random.default_rng(431014))
        truth = np.repeat(np.arange(10, dtype=np.int16), 50)
        predicted = []
        for index in range(10):
            class_start = time.monotonic()
            for begin in range(index*50, (index+1)*50, 5):
                self.checkpoint()
                predictions = self.predictor.predict(x[begin:begin+5], fs=480000)
                predicted.extend(p['class_index'] for p in predictions)
                values = scores(truth[:len(predicted)], np.asarray(predicted, dtype=np.int16))
                self.emit('confusion', label=CLASSES[index], completed=len(predicted), total=500,
                    labels=list(CLASSES), **values)
            while time.monotonic()-class_start < 3:
                self.checkpoint(); time.sleep(.05)
        with np.load(directory/'predictions.npz', allow_pickle=False) as expected:
            if sha(directory/'predictions.npz') != reference['predictions_sha256']:
                raise ValueError('Reference prediction digest differs')
            exact = bool(np.array_equal(expected['ota_10'], predicted))
        target = next(v for v in reference['curves']['ota'] if v['injected_reference_db'] == 10)
        matrix_equal = values['confusion_10'] == target['confusion_10'] and values['confusion_8'] == target['confusion_8']
        return dict(status='DONE' if exact and matrix_equal else 'MISMATCH', scores=values,
            predictions=predicted, exact_predictions=exact, exact_confusion=matrix_equal,
            reference_capture_sha256=sha(directory/'result.json'), model_sha256=sha(self.model),
            input_source='F3 measured over-air IQ; board inference now; no transmission',
            added_noise_reference_db=10, seed=431014)

    def run_f14(self, args):
        if not args['antenna_2g4']: raise PermissionError('Confirm RX1A 2.4 GHz antenna')
        from ..panorama_capture import GuardedSnapshots, radio_state, write_json
        from ..wifi_capture import capture_channels
        raw = self.job_output/'raw'; raw.mkdir()
        snapshots = GuardedSnapshots(self.hw.checked.registers('axi_ad9361_adc_dma'))
        result = dict(schema=1, status='STARTED', session_id=self.run_id, source='AD9361_RX1A',
            antenna='RX1A_2G4', tx_requested=False, bitstream_download=False,
            pl_source_enabled=False, sample_rate_hz=30720000, bandwidth_requested_hz=24000000,
            samples_per_capture=1048576, captures_per_channel=4, continuous_recording=False,
            channels=[], boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip())
        try:
            capture_channels(self.session, snapshots, raw, result, list(range(1, 14)),
                checkpoint=self.checkpoint, progress=lambda p: self.emit('wifi_capture', **p))
        except BaseException as error:
            result.update(status='FAIL', error=repr(error))
        finally:
            quarantined = snapshots.stop()
            result['buffers_quarantined'] = quarantined
            if quarantined:
                # Match GuardedSnapshots policy: never reset or retune owned DMA.
                write_json(raw/'result.json', result)
                self.quarantined = snapshots
                raise RuntimeError('DMA quarantine: service must stop, no automatic retune')
            self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
            result['restored'] = radio_state(self.radio)
            result['receive_startup_restored'] = self.hw.prepare_receive()
            result['capture_ended_utc'] = datetime.now(timezone.utc).isoformat()
            write_json(raw/'result.json', result)
        if result['status'] != 'PASS_FINITE_RX_CAPTURE':
            raise RuntimeError(result.get('error', result['status']))
        self.emit('wifi_captured', remote_raw=str(raw), capture=result, capture_sha256=sha(raw/'result.json'))
        return dict(status='DONE', capture=result, remote_raw=str(raw))
