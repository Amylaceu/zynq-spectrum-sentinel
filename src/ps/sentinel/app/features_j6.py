"""Receive-only J6 glue for frozen hardware; one thread owns every acquisition.

No new DSP algorithm. Digital tests use the existing finite_frame implementation;
CFAR threshold visualization calls the existing golden model, not MMIO readback.
"""
import importlib.util
import time

import numpy as np

from .resident import ReceiveBackend
from .hostlink_runtime import RuntimeLink, power_packet
from .monitor_x1_guard8 import configure_checked
from .selftest_v1 import finite_frame
from ..drivers.regs import spec_ctrl as F, src_ctrl as S, cfar_x1 as C, lcd_ctrl as L
from ..release_support import write_result, sha
from ..v1 import wait_until


IDS = tuple('F%d' % i for i in range(1, 11))


class FeatureLink(RuntimeLink):
    def _sample(self):
        # The foreground owner captures between commands; never two BRAM owners.
        return


def db(power):
    return 10*np.log10(np.maximum(np.asarray(power, dtype=float), 1))


class FeatureBackend(ReceiveBackend):
    def start(self):
        address = self.hostlink_bind
        self.hostlink_bind = None
        super().start()
        self.active = None
        self.results = []
        self.command_audit = []
        self.last_capture = 0.
        self.golden = None
        self.replay_reset_since_capture = False
        spec = importlib.util.spec_from_file_location('j6_golden', str(self.root/'scripts/j6_golden_cfar.py'))
        if spec is not None:
            self.golden = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(self.golden)
        self.link = FeatureLink(self.hw, self.bit, self.output, self.config['lo_hz'],
            mode='resident', address=address, runtime=self.runtime).__enter__()
        self.link.bind_presenter(self.presenter)
        self.defaults = self.restore()

    def readback(self):
        tx = list(self.radio.tx_atten)
        if tx != [89.75, 89.75] or self.radio.rate != 3840000:
            raise RuntimeError('J6 RF safety readback failed')
        return dict(tx_attenuation_db=tx, source_ctrl=int(self.hw.src_regs.read(S.CTRL)),
            spec_ctrl=int(self.hw.spec.read(F.CTRL)), average_shift=int(self.hw.spec.read(F.AVG_SHIFT)),
            noise_amplitude=int(self.hw.src_regs.read(S.NOISE_AMP)),
            cfar_ctrl=int(self.hw.cfar.mmio.read(C.CTRL)), alpha=int(self.hw.cfar.mmio.read(C.ALPHA)),
            audio_control=int(self.hw.audio.control.read(0)), codec_muted=self.codec.read(0x19) == self.codec.MUTE,
            lo_hz=self.radio.rx_lo, rate_hz=self.radio.rate,
            lcd_enabled=bool(self.hw.lcd.registers.read(L.CTRL) & 1))

    def restore(self):
        self.mute()
        self.hw.audio.disable(release_pins=True)
        self.hw.source.stop()
        time.sleep(.025)
        configure_checked(self.hw, self.radio, self.config['lo_hz'])
        self.hw.source.configure('rf', rate=3840000)
        self.hw.lcd.enable(False)
        self.active = None
        self.scene = 'idle'
        value = self.readback()
        expected = dict(source_ctrl=0, spec_ctrl=1, average_shift=3, noise_amplitude=0,
            cfar_ctrl=1, alpha=1974, audio_control=0, codec_muted=True, lcd_enabled=False)
        if any(value[k] != v for k, v in expected.items()):
            raise RuntimeError('Default readback mismatch: '+str(value))
        # configure_checked verifies all CFAR masks, widths, guard and count.
        value['full_cfar_defaults_checked'] = True
        value['source_defaults_checked'] = all(self.hw.src_regs.read(k) == v for k, v in (
            (S.RATE_DIV, round(100000000*65536/3840000)), (S.FRAME_LIMIT, 0),
            (S.FCW0, 64*2097152), (S.FCW1, 0), (S.FCW2, 0),
            (S.AMP0, 8192), (S.AMP1, 0), (S.AMP2, 0)))
        if not value['source_defaults_checked']:
            raise RuntimeError('Source default readback mismatch')
        return value

    def configure(self, mode='test', average=0, window=0, noise=0, cfar='CA', alpha=1974):
        self.hw.source.stop()
        time.sleep(.02)
        self.hw.enable_processing(average_shift=average, mode=cfar, n=16, guard=8,
            alpha=alpha, dc_mask=3, min_width_bins=2, merge_gap_bins=6)
        self.hw.spec.write(F.CTRL, 1 | (window << 1))
        self.hw.source.configure(mode, rate=3840000, bins=(-300, 64, 300), amplitudes=(4096,)*3)
        self.hw.src_regs.write(S.NOISE_AMP, noise)
        if (self.hw.spec.read(F.CTRL) != 1 | window << 1 or
                self.hw.spec.read(F.AVG_SHIFT) != average or
                self.hw.src_regs.read(S.NOISE_AMP) != noise or
                self.hw.cfar.mmio.read(C.ALPHA) != alpha or
                self.hw.cfar.mmio.read(C.CTRL) != 1 | ({'CA': 0, 'GO': 1, 'SO': 2}[cfar] << 1)):
            raise RuntimeError('Feature configuration readback failed')
        self.hw.source.start()

    def capture(self):
        token = self.hw.arm_capture()
        power = self.hw.read_capture(token, timeout=.6)
        targets = self.hw.cfar.snapshot(retries=20)
        self.link.latest_power = (power, time.monotonic(), 0, 0, self.config['lo_hz'])
        self.link.service.publish('spectrum', power_packet(power), lo_hz=self.config['lo_hz'],
            sample_rate_hz=3840000, frequency_start_hz=self.config['lo_hz']-1920000, bin_spacing_hz=3750)
        import zlib
        from ..display_twin import power_q88
        self.link.service.publish('pl_frame', zlib.compress(power_q88(power).tobytes(), 1),
            profile='x5_frozen', codec='zlib-i16le-q88', columns=560,
            lo_hz=self.config['lo_hz'], sample_rate_hz=3840000, frame_range=[0, 0],
            spectrum_source='sampled_power_snapshot', waterfall_source='sampled_trace_history',
            threshold_source='UNAVAILABLE_NO_MMIO_READBACK', peak_source='NOT_PRESENT_IN_FROZEN_LCD', lcd_frame_exact=False)
        return power, targets

    def _prepare_capture_dma(self):
        if self.replay_reset_since_capture:
            engine = self.hw.channel_capture.engine
            if self.hw.channel_capture.failed or engine.inflight:
                raise RuntimeError('Do not restart a failed or owned capture DMA')
            # finite_frame resets AXI DMA through MM2S, which also halts S2MM.
            # Re-start PYNQ's public channel only at this known reset boundary.
            if not engine.dma.recvchannel.running:
                engine.dma.recvchannel.start()
            self.replay_reset_since_capture = False

    def _quality(self):
        self._prepare_capture_dma()
        return super()._quality()

    def channel(self, frequency_hz):
        from ..capture_x5 import select_channel
        self._prepare_capture_dma()
        selection = select_channel(frequency_hz-self.config['lo_hz'])
        capture = self.hw.channel_capture.acquire(selection, source=0)
        iq = np.asarray(capture['iq'][:512], dtype='<c8')
        self.link.service.publish('iq', iq.tobytes(), target_key=0, sample_rate_hz=480000)
        self.channel_frequency = frequency_hz
        self.last_channel = time.monotonic()
        return dict(channel=selection.channel, fcw=selection.fcw,
            residual_hz=selection.residual_hz, sample_rate_hz=480000,
            frequency_hz=frequency_hz, timestamp_cycles=capture['timestamp_cycles'])

    def pair(self, before, after, unit=''):
        return dict(before=before, after=after, unit=unit)

    def _present(self, force=False, **kwargs):
        from .feature_display import display_options
        identity = getattr(self, 'lcd_identity', None)
        if identity:
            result = getattr(self, 'last_feature', {})
            if result.get('id') != identity: result = {}
            progress = getattr(self, 'lcd_progress', None)
            self.feature_ui_options = display_options(identity, result, progress,
                                                       self.config['station_hz'])
        # Finite jobs keep RF stopped. Enable only the display controller long
        # enough to commit a PS panel, then preserve the prior enable state.
        enabled = bool(self.hw.lcd.registers.read(L.CTRL) & 1)
        if not enabled: self.hw.lcd.enable()
        try:
            return super()._present(force=force, **kwargs)
        finally:
            if not enabled: self.hw.lcd.enable(False)

    def feature(self, identity, action='start', mode='CA', alpha=1974):
        if identity not in IDS or action not in ('start', 'stop'):
            raise ValueError('Unknown feature')
        started = time.monotonic()
        result = dict(id=identity, action=action, status='STARTED', tx_requested=False, metrics={})
        try:
            result['restored_before'] = self.restore()
            if action == 'start' and hasattr(self, 'before_feature_start'):
                self.before_feature_start(identity)
            if action == 'stop':
                result.update(status='STOPPED', restored=True, readback=self.readback())
            else:
                self.lcd_identity, self.lcd_progress = identity, None
                self.hw.lcd.enable()
                self.scene = 'perf'
                metrics = result['metrics']
                if identity in ('F1', 'F8', 'F7'):
                    if identity == 'F8':
                        # Follow the accepted standalone listener's startup:
                        # configure/reset while stopped, arm audio, then start
                        # RF once. Do not run/capture/stop RF before audio reset.
                        self.radio.configure(self.config['lo_hz'], 3840000, self.config['rf_bandwidth_hz'])
                        self.codec.initialize(volume_db=self.config['volume_db'],
                            speaker_volume_db=self.config.get('speaker_volume_db'))
                        configure_checked(self.hw, self.radio, self.config['lo_hz'])
                        self.hw.reset_channelizer()
                        self.hw.perf.clear()
                        self.hw.perf.arm()
                        self.hw.source.configure('rf', rate=3840000)
                    else:
                        self._start_receive()
                    first = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
                    t0 = time.monotonic()
                    if identity == 'F8':
                        self.enter_scene('listen')
                        # Retain <=3 s as a measured target, not permission to
                        # stop an otherwise healthy receiver during settling.
                        deadline = time.monotonic()+8
                        while time.monotonic() < deadline and not self.ready('listen')['ready']:
                            self.safety()
                            time.sleep(.02)
                        if not self.audible:
                            raise TimeoutError('FM quality gate not ready within 8 second settling window')
                        metrics['播放样本'] = self.pair(0, int(self.hw.audio.snapshot()['pcm_samples']), '样本')
                        metrics['下溢'] = self.pair(0, int(self.hw.audio.snapshot()['underflows']), '次')
                        metrics['输出'] = self.pair('静音', '板载喇叭 0 dB')
                    elif identity == 'F7':
                        power, targets = self.capture()
                        result['channel'] = self.channel(self.config['station_hz'])
                        metrics['提取通道'] = self.pair('宽带', result['channel']['channel'])
                        metrics['窄带采样率'] = self.pair(3840000, 480000, 'SPS')
                        metrics['NCO频率'] = self.pair('—', result['channel']['residual_hz'], 'Hz')
                    else:
                        power, targets = self.capture()
                        time.sleep(.12)
                        fps = ((int(self.hw.lcd.registers.read(L.FRAME_COUNT))-first)&0xffffffff)/(time.monotonic()-t0)
                        metrics['屏幕帧率'] = self.pair(0, round(fps, 2), 'fps')
                        metrics['目标数'] = self.pair(0, len(targets.targets))
                elif identity in ('F2', 'F3', 'F4', 'F5', 'F6'):
                    self.configure(mode='rf' if identity == 'F6' else 'test')
                    before, previous_targets = self.capture()
                    if identity == 'F3':
                        self.configure(window=2)
                    elif identity == 'F4':
                        self.configure(mode='noise', noise=2048, average=0)
                        before, _ = self.capture()
                        self.configure(mode='noise', noise=2048, average=5)
                        time.sleep(.15)
                    elif identity == 'F5':
                        self.configure(cfar=mode, alpha=alpha)
                    elif identity == 'F6':
                        self.configure(mode='noise', noise=8192)
                    power, targets = self.capture()
                    result['comparison_power_db'] = db(before).tolist()
                    peaks = sorted(int(t.peak_bin) for t in targets.targets)
                    if identity == 'F2':
                        errors = [min(abs(x-y) for y in peaks) if peaks else 2048 for x in (724, 1088, 1324)]
                        metrics['理论bin'] = self.pair('—', '724,1088,1324')
                        metrics['检出bin'] = self.pair('—', ','.join(map(str, peaks)))
                        metrics['最大误差'] = self.pair('—', max(errors), 'bin')
                        if len(peaks) != 3 or max(errors):
                            raise RuntimeError('Three-tone exact bin check failed: '+str(peaks))
                    elif identity == 'F3':
                        def width(p):
                            v = db(p); peak = 1088; lo = hi = peak
                            while lo > 1029 and v[lo-1] >= v[peak]-40: lo -= 1
                            while hi < 1200 and v[hi+1] >= v[peak]-40: hi += 1
                            return hi-lo+1
                        metrics['−40dB主瓣宽度'] = self.pair(width(before), width(power), 'bin')
                        metrics['窗选择'] = self.pair('BH4', '矩形')
                        result['scope'] = 'Integer-bin tones; rectangular window may have a narrower main lobe, not necessarily wider.'
                    elif identity == 'F4':
                        metrics['底噪空间标准差'] = self.pair(round(float(np.std(db(before)[100:600])), 3), round(float(np.std(db(power)[100:600])), 3), 'dB')
                        metrics['AVG_SHIFT'] = self.pair(0, 5)
                    elif identity == 'F5':
                        threshold, _ = self.golden.cfar(power, mode=mode, n=16, g=8, alpha_q88=alpha, dc_mask=3)
                        result['threshold_db'] = db(threshold).tolist()
                        result['threshold_source'] = 'SOFTWARE_RECONSTRUCTION_FROM_CURRENT_PL_POWER_NOT_REGISTER_READBACK'
                        metrics['CFAR类型'] = self.pair('CA', mode)
                        metrics['ALPHA Q8.8'] = self.pair(1974, alpha)
                        metrics['PL目标数'] = self.pair(len(previous_targets.targets), len(targets.targets))
                    elif identity == 'F6':
                        ratio = lambda p: round(float(np.max(db(p))-np.median(db(p))), 2)
                        metrics['峰值/中位底噪'] = self.pair(ratio(before), ratio(power), 'dB')
                        metrics['目标数'] = self.pair(len(previous_targets.targets), len(targets.targets))
                elif identity in ('F9', 'F10'):
                    refs = self.root/'data/reference/spectrum'
                    inputs = np.array([int(x, 16) for x in (refs/'in_axis32.hex').read_text().split()], dtype=np.uint32).reshape(4, 2048)
                    golden = np.array([int(x, 16) for x in (refs/'exp_power_shifted.hex').read_text().split()], dtype=np.uint32).reshape(4, 2048)
                    self.hw.enable_processing(average_shift=0, guard=8, min_width_bins=0)
                    mismatches = 0
                    for index in range(4 if identity == 'F9' else 1):
                        self.hw.perf.clear(); time.sleep(.005); self.hw.perf.arm()
                        power, targets, perf = finite_frame(self.hw, 'replay', replay=inputs[index], rate=3840000)
                        self.replay_reset_since_capture = True
                        mismatches += int(np.count_nonzero(power != golden[index]))
                    if identity == 'F9':
                        metrics['比对字数'] = self.pair(0, 8192, '字')
                        metrics['不一致'] = self.pair('—', mismatches, '字')
                        if mismatches: raise RuntimeError('Golden replay mismatch')
                    else:
                        packed = inputs[0]
                        iq = (packed & 65535).astype(np.uint16).view(np.int16).astype(float)+1j*(packed >> 16).astype(np.uint16).view(np.int16).astype(float)
                        # Reuse golden detector. CPU uses the same input IQ, floating FFT,
                        # and PL output scale; no bit-exact CPU equivalence is claimed.
                        window = np.loadtxt(str(self.root/'data/reference/spectrum/spec_window_bh4.hex'), dtype=str)
                        coefficients = np.array([int(v, 16) for v in window], dtype=float)/131072.
                        def cpu():
                            values = np.abs(np.fft.fftshift(np.fft.fft(iq*coefficients)))**2
                            values *= float(power.max())/max(float(values.max()), 1.)
                            return self.golden.cfar(np.minimum(values, 0xffffffff).astype(np.uint32), n=16, g=8)
                        cpu(); timings = []
                        for _ in range(5):
                            begin = time.perf_counter(); cpu(); timings.append(time.perf_counter()-begin)
                        cpu_ms = 1000*float(np.median(timings)); pl_ms = perf.latency_cycles/100000.
                        if not perf.markers_done or pl_ms <= 0: raise RuntimeError('No valid PL performance marker')
                        metrics['处理时间'] = self.pair(round(cpu_ms, 4), round(pl_ms, 4), 'ms (CPU→PL)')
                        metrics['CPU/PL比值'] = self.pair('—', round(cpu_ms/pl_ms, 3), '倍')
                        result['scope'] = 'Same replay IQ; CPU floating window/FFT+integer thresholds (no clustering); PL first-IQ to list includes serial input, fixed FFT and clustering. Not equivalent arithmetic or pure compute speedup.'
                        result['input_sha256'] = sha(refs/'in_axis32.hex')
                        result['timings_cpu_s'] = timings
                    self.configure()
                    self.capture()
                self.active = identity
                self.scene = 'listen' if identity == 'F8' else 'perf'
                result.update(status='READY', restored=False, readback=self.readback())
                result['targets'] = [dict(start=t.start, stop=t.stop, peak_bin=t.peak_bin) for t in self.hw.cfar.snapshot(retries=20).targets]
                self.last_feature = result
                self._present(force=True)
            result['elapsed_s'] = time.monotonic()-started
            result['within_target'] = result['elapsed_s'] <= (10 if identity == 'F10' else 3)
        except Exception as error:
            result.update(status='FAILED', error=repr(error), elapsed_s=time.monotonic()-started)
            result['readback'] = self.restore()
            result['restored'] = True
        self.results.append(result)
        write_result(self.output/('feature_%03d.json' % len(self.results)), result)
        self.last_feature = result
        return result

    def tick(self):
        self.safety()
        now = time.monotonic()
        if self.active == 'F8': self._audio_quality()
        if self.active == 'F7' and now-self.last_channel >= .6:
            self.channel(self.channel_frequency)
        if self.active and now-self.last_capture >= .15:
            self.capture(); self.last_capture = time.monotonic()
        if self.active and now-self.last_ui >= .25:
            self._targets(); self._present()
        if now-self.last_telemetry >= 1:
            now = time.monotonic()
            audio = self.hw.audio.snapshot()
            rates = None
            if self.active == 'F8' and self.last_audio is not None:
                seconds = now-self.last_audio_time
                rates = {key: ((audio[key]-self.last_audio[key]) & 0xffffffff)/seconds
                    for key in ('frames', 'pcm_samples')}
                if any(not 47000 <= value <= 49000 for value in rates.values()):
                    raise RuntimeError('J6 audio sample clock integrity failed')
            self.last_audio, self.last_audio_time = audio, now
            frame = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
            self.fps = ((frame-self.last_frame)&0xffffffff)/(now-self.last_telemetry) if self.active else 0.
            self.telemetry = dict(scene=self.active or 'idle', display_fps=self.fps, display_frames=frame,
                temperature_c=self.temperature, rx_rssi_dbm=self.radio.rssi(0), tx_on=False,
                tx_attenuation_db=list(self.radio.tx_atten), feature=getattr(self, 'last_feature', None),
                audio=dict(audio, output_unmuted=self.audible,
                    station_hz=self.config['station_hz']), pilot=self.quality, audio_rates_hz=rates)
            self.samples.append(self.telemetry)
            self.last_frame, self.last_telemetry = frame, now
        self.link.update(self.tracker.visible(now) if self.active else (), telemetry=self.telemetry)

    def commands(self):
        for _ in range(8):
            request = self.link.service.poll()
            if request is None: break
            _, _, name, args = request
            self.command_audit.append(dict(client=request[0], seq=request[1], command=name,
                args=dict(args), active_before=self.active, observed_mono=time.monotonic()))
            try:
                if name == 'feature':
                    value = self.feature(args['id'], args['action'], args['mode'], args['alpha'])
                    compact = {k: v for k, v in value.items() if k not in ('comparison_power_db', 'threshold_db')}
                    for key in ('comparison_power_db', 'threshold_db'):
                        if key in value:
                            self.link.service.publish('file', np.asarray(value[key], dtype='<f4').tobytes(),
                                feature_plot=key, request_seq=request[1], feature_id=args['id'])
                    self.last_feature = compact
                    self.link.service.reply(request, ok=value['status'] != 'FAILED', feature=compact)
                elif name == 'application' and hasattr(self, 'application_request'):
                    self.application_request(request, args)
                    break  # Execute/cancel this job before accepting another owner.
                elif name == 'get_status': self.link.service.reply(request, status=self.readback())
                elif name == 'ping': self.link.service.reply(request, board_mono=time.monotonic())
                elif name == 'stop':
                    self.restore(); self.link.service.reply(request, restored=True)
                elif name == 'set_page' and self.active:
                    self.link.page = args['page']; self._present(force=True)
                    self.link.service.reply(request, page=args['page'])
                elif name == 'select_target' and self.active == 'F7':
                    target = next((t for t in self.tracker.visible(time.monotonic()) if t.key == args['key']), None)
                    if target is None: raise ValueError('Target is no longer present')
                    value = dict(self.last_feature)
                    value['channel'] = self.channel(target.frequency_hz)
                    value['metrics'] = dict(value['metrics'])
                    value['metrics']['提取通道'] = self.pair('宽带', value['channel']['channel'])
                    value['metrics']['NCO频率'] = self.pair('—', value['channel']['residual_hz'], 'Hz')
                    self.last_feature = value
                    write_result(self.output/('channel_%d.json' % time.monotonic_ns()), value)
                    self.link.service.reply(request, feature=value)
                else: self.link.service.reply(request, ok=False, error='Use J6 bounded feature controls')
            except Exception as error:
                self.restore()
                self.link.service.reply(request, ok=False, error=repr(error))
