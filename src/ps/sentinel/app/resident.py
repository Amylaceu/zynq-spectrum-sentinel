"""Receive-only presentation owner. One RF session, codec and predictor per serve.

Only the owner thread touches RF, IQ DMA or codec. Scene requests never release
the Session or reset its GPIO. Unavailable extensions fail before any hardware
operation; no transmit implementation or implicit replay is provided here.
"""
from contextlib import nullcontext
import time


SCENES = ('check', 'pano', 'fm', 'listen', 'wifi', 'ota', 'noise', 'perf', 'idle')
LIMITS = dict(check=5., fm=2., listen=3., perf=1., idle=1.)
UNAVAILABLE = dict(pano='I5 quick scan not installed', wifi='I4 reception not installed',
                   ota='REPLAY_REQUIRED: S1 selection; live transmission disabled',
                   noise='REPLAY_REQUIRED: S1 selection; live transmission disabled')


class SceneUnavailable(ValueError):
    pass


def validate_request(request):
    """Small exact schema: no arbitrary frequency, waveform, gain or TX controls."""
    if not isinstance(request, dict) or request.get('command') not in ('scene', 'status', 'stop'):
        raise ValueError('Unknown resident command')
    command = request['command']
    expected = {'command', 'id'} if command == 'scene' else {'command'}
    if set(request) != expected:
        raise ValueError('Unexpected resident command fields')
    if command == 'scene' and request['id'] not in SCENES:
        raise ValueError('Unknown scene')
    return command


class ResidentController:
    """Injectable lifecycle and readiness policy, independent of PYNQ imports."""
    def __init__(self, backend, clock=time.monotonic, sleep=time.sleep):
        self.backend, self.clock, self.sleep = backend, clock, sleep
        self.scene = 'idle'
        self.stopping = False
        self.closed = False
        self.transitions = []

    def switch(self, scene):
        if scene not in SCENES:
            raise ValueError('Unknown scene')
        if scene in UNAVAILABLE:
            raise SceneUnavailable(UNAVAILABLE[scene])
        if self.closed or self.stopping:
            raise RuntimeError('Resident is stopping')
        begin = self.clock()
        record = dict(scene=scene, previous=self.scene, started_mono=begin)
        self.transitions.append(record)
        try:
            # Mute before any reconfiguration. The RF lock/GPIO stay owned.
            with self.backend.paused():
                self.backend.mute()
                self.backend.readback()
                self.backend.enter_scene(scene)
                self.scene = scene
            deadline = begin+LIMITS[scene]
            while True:
                if self.stopping:
                    raise InterruptedError('Stop requested during scene readiness')
                self.backend.safety()
                readiness = self.backend.ready(scene)
                if readiness['ready']:
                    break
                if self.clock() >= deadline:
                    raise TimeoutError('Scene did not become ready: '+scene)
                self.sleep(.01)
            record.update(status='READY', readiness=readiness,
                          readback=self.backend.readback(), ready_mono=self.clock())
            record['ready_s'] = record['ready_mono']-begin
            record['within_target'] = record['ready_s'] <= LIMITS[scene]
            return dict(record)
        except (TimeoutError, InterruptedError) as error:
            # Weak RF is a failed scene, not permission to unmute or fake data.
            with self.backend.paused():
                self.backend.mute()
                self.backend.enter_scene('idle')
                self.scene = 'idle'
            record.update(status='NOT_READY', error=str(error), elapsed_s=self.clock()-begin,
                          readback=self.backend.readback())
            return dict(record)
        except BaseException as error:
            record.update(status='FAILED', error=repr(error), elapsed_s=self.clock()-begin)
            self.close()
            raise

    def dispatch(self, request):
        command = validate_request(request)
        if command == 'scene':
            return self.switch(request['id'])
        if command == 'stop':
            self.stopping = True
            return dict(status='STOP_REQUESTED')
        return dict(status='RUNNING', scene=self.scene, readback=self.backend.readback(),
                    unavailable=dict(UNAVAILABLE), arm_ota=False)

    def close(self):
        if not self.closed:
            self.closed = True
            self.stopping = True
            self.backend.close()


class ReceiveBackend:
    """Frozen v2 hardware adapter; unrelated demo runtime is left intact."""
    def __init__(self, root, output, *, hostlink_bind=None, stop_requested=lambda: False):
        from pathlib import Path
        self.root, self.output = Path(root), Path(output)
        self.hostlink_bind, self.stop_requested = hostlink_bind, stop_requested
        self.runtime = self.session = self.codec = self.link = None
        self.hw = self.radio = self.presenter = None
        self.closed = False
        self.scene = 'idle'
        self.quality = None
        self.audible = False
        self.capture_index = 0
        self.last_quality = self.last_ui = self.last_classify = 0.
        self.last_telemetry = 0.
        self.fps = 0.
        self.last_audio = None
        self.last_audio_time = None
        self.quality_samples = []
        self.records, self.samples, self.telemetry = [], [], None

    def start(self):
        from .runtime_v2 import SentinelRuntime
        from .monitor_x5 import checked_inputs
        from ..release_support import load_config
        from ..tracker_x5 import TargetTracker
        from ..ui_v3.presenter import Presenter
        from ..drivers.regs import lcd_ctrl as L
        self.config = load_config(self.root/'config.yaml')
        self.bit = self.root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
        self.model = self.root/'ps/models/weights/amc_v2/round_3/model.npz'
        acceptance = checked_inputs(self.bit, self.model, 'sentinel_v2_100m')
        self.accepted_bit = acceptance['artifacts_sha256'][self.bit.name]
        self.runtime = SentinelRuntime(self.root)
        try:
            self.predictor = self.runtime.predictor(self.model)
            self.session = self.runtime.session(str(self.bit), 'rf', True,
                self.config['lo_hz'], 3840000).__enter__()
            self.hw, self.radio = self.session.hw, self.session.radio
            self.hw.audio.disable(release_pins=True)
            self.codec = self.runtime.get_codec(self.hw)
            self.codec.initialize(volume_db=self.config['volume_db'],
                speaker_volume_db=self.config.get('speaker_volume_db'))
            self.runtime.evidence['codec_initializations'] = 1
            self.runtime.evidence['rf_reinitialization_reason'] = 'Only final stop resets GPIO; scenes keep one RF session'
            self.runtime.evidence['lifecycle'] = 'resident_receive_only'
            self.tracker = TargetTracker()
            self.hw.lcd.set_bus_phase(self.config['bus_phase'])
            self.hw.lcd.enable()
            self.presenter = Presenter(self.hw.lcd, 'v3')
            self._start_receive()
            self.last_frame = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
            self.last_telemetry = time.monotonic()
            if self.hostlink_bind:
                from .hostlink_runtime import RuntimeLink
                self.link = RuntimeLink(self.hw, self.bit, self.output,
                    self.config['lo_hz'], mode='resident', address=self.hostlink_bind,
                    runtime=self.runtime).__enter__()
                self.link.bind_presenter(self.presenter)
                self.link.service.mode = 'resident'
            self.enter_scene('idle')
        except BaseException:
            self.close()
            raise

    def paused(self):
        return self.link.paused() if self.link else nullcontext()

    def _start_receive(self):
        from .monitor_x1_guard8 import configure_checked
        self.hw.source.stop()
        configure_checked(self.hw, self.radio, self.config['lo_hz'])
        self.hw.reset_channelizer()
        self.hw.perf.arm()
        self.hw.source.configure('rf', rate=3840000)
        self.hw.source.start()

    def mute(self):
        if self.codec is not None and self.codec.initialized:
            self.codec.checked(0x19, self.codec.MUTE)
        self.audible = False
        if self.hw is not None:
            # Keep codec initialized; stop only the audio stream, never RF GPIO.
            self.hw.audio.disable(release_pins=False)

    def readback(self):
        tx = list(self.radio.tx_atten)
        src = int(self.hw.src_regs.read(0))
        gpio = int(self.hw.checked.registers('axi_ad9361_gpio').read(0))
        if tx != [89.75, 89.75] or not src & 1 or gpio == 0:
            raise RuntimeError('Resident RX readback failed: '+str((tx, src, gpio)))
        return dict(tx_attenuation_db=tx, source_ctrl=src, gpio_data=gpio,
                    lo_hz=self.radio.rx_lo, rate_hz=self.radio.rate,
                    audio_control=int(self.hw.audio.control.read(0)),
                    codec_muted=self.codec.read(0x19) == self.codec.MUTE)

    def safety(self):
        from .monitor_x1_guard8 import check_safety
        from ..telemetry import read_temperature_c
        self.radio.check_rssi()
        self.temperature = read_temperature_c()
        check_safety(dict(tx_atten_mdb=[round(x*1000) for x in self.radio.tx_atten],
                          rx_rssi_dbm=self.radio.rssi(0), temperature_c=self.temperature))
        if (self.hw.channel_health() or self.hw.x5_status.read(0) & 0x1f0
                or getattr(self.hw.channel_capture, 'failed', False)):
            raise RuntimeError('Resident processing/DMA continuity fault')
        if self.scene == 'listen':
            audio = self.hw.audio.snapshot()
            if audio['iq_overflow'] or audio['pcm_full'] or audio['underflows']:
                raise RuntimeError('Resident audio FIFO fault: '+str(audio))
        if not self.hw.overlay.is_loaded():
            raise RuntimeError('Frozen overlay ownership changed')

    def enter_scene(self, scene):
        from ..drivers.regs import lcd_ctrl as L
        from ..fm_quality import StereoQualityGate
        self.scene = scene
        self.epoch = time.monotonic()
        self.begin_frame = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
        self.last_quality = 0.
        self.quality = None
        self.gate = StereoQualityGate()
        self.audio_before = self.hw.audio.snapshot()
        self.last_audio = self.last_audio_time = None
        self.tracker.tracks.clear()
        if scene == 'listen':
            # Running PFB data during the audio FIFO reset-busy window latches
            # iq_overflow. Pause upstream, never reset AD9361 or reopen its lock.
            self.hw.source.stop()
            try:
                self.selection = self.hw.audio.configure(
                    self.config['station_hz'], self.config['lo_hz'], self.codec)
                self.hw.audio.start()
                time.sleep(.001)
            finally:
                self.hw.source.start()
            self.audio_before = self.hw.audio.snapshot()
        self.cached_check = None
        if self.link:
            self.link.selected = None
            self.link.page = 'STAT' if scene in ('perf', 'check') else 'SIG'
            self.link.ui_state.view = self.link.page
            self.link.ui_state.selected = None
            self.link.ui_state.listening = scene == 'listen'
            self.link.ui_state.change('scene:'+scene)
        self._present(force=True)

    def _quality(self):
        from ..capture_x5 import select_channel
        from ..fm_quality import stereo_quality
        from .monitor_x5 import save_capture
        station, lo = self.config['station_hz'], self.config['lo_hz']
        capture = self.hw.channel_capture.acquire(select_channel(station-lo), source=0)
        filename, digest = save_capture(self.output, self.capture_index, capture)
        self.capture_index += 1
        quality = stereo_quality(capture['iq'])
        self.quality_samples.append(dict(quality, capture_filename=filename,
            capture_sha256=digest, scene=self.scene, observed_mono=time.monotonic(),
            timestamp_cycles=capture['timestamp_cycles']))
        self.quality = quality
        self.last_quality = time.monotonic()
        return quality

    def _targets(self):
        try:
            snapshot = self.hw.cfar.snapshot(retries=8)
        except RuntimeError as error:
            if 'changed during read' not in str(error):
                raise
            return self.tracker.visible(time.monotonic())
        if snapshot.status_latch & 0x0c:
            raise RuntimeError('Latched CFAR fault')
        self.tracker.update(snapshot.targets, self.config['lo_hz'], 3840000, time.monotonic())
        return self.tracker.visible(time.monotonic())

    def _audio_quality(self):
        if time.monotonic()-self.last_quality < .25:
            return
        quality = self._quality()
        should_play = self.gate.update(quality) and quality['pilot_prominence_db'] >= 20
        audio = self.hw.audio.snapshot()
        if should_play and not self.audible:
            if not audio['playing'] or audio['fifo_level'] < 3072:
                return
            self.codec.unmute()
            self.audible = True
        elif not should_play and self.audible:
            self.codec.checked(0x19, self.codec.MUTE)
            self.audible = False

    def ready(self, scene):
        from ..drivers.regs import lcd_ctrl as L
        if scene == 'fm':
            targets = self._targets()
            delta = (int(self.hw.lcd.registers.read(L.FRAME_COUNT))-self.begin_frame) & 0xffffffff
            return dict(ready=delta >= 2 and bool(targets), frame_delta=delta, targets=len(targets))
        if scene == 'listen':
            self._audio_quality()
            audio = self.hw.audio.snapshot()
            delta = (audio['pcm_samples']-self.audio_before['pcm_samples']) & 0xffffffff
            return dict(ready=self.audible and audio['playing'] and delta > 0,
                audio=audio, sample_delta=delta, pilot=self.quality, codec_unmuted=self.audible,
                scope='Digital playback readiness; human listening separately required')
        if scene == 'check':
            if self.cached_check is None:
                from ..release_support import sha
                self.cached_check = dict(bit_sha256=sha(self.bit),
                    product_id=self.radio.lib.z20_read_register(0x037),
                    temperature_c=self.temperature, quality=self._quality(),
                    arm_ota=False, ota='REPLAY_REQUIRED',
                    network_rtt='CLIENT_MEASUREMENT_REQUIRED')
                self.cached_check['passed'] = (self.cached_check['bit_sha256'] == self.accepted_bit and
                    self.cached_check['product_id'] >= 0 and
                    self.cached_check['product_id'] & 0xf8 == 0x08 and
                    self.cached_check['quality']['good'] and
                    self.cached_check['quality']['pilot_prominence_db'] >= 20)
            return dict(ready=self.cached_check['passed'], checks=self.cached_check)
        return dict(ready=True)

    def _present(self, force=False, iq=None, symbols=None, selected=None):
        from ..drivers.regs import lcd_ctrl as L
        if self.presenter is None:
            return
        tracks = self.tracker.visible(time.monotonic())
        label = ('LISTEN %.3fM' % (self.config['station_hz']/1e6) if self.audible
                 else 'WEAK FM: MUTED' if self.scene == 'listen' else 'X4 EXP / TX OFF')
        options = dict(lo_hz=self.config['lo_hz'], frame=int(self.hw.lcd.registers.read(L.FRAME_COUNT)),
            fps=self.fps, temperature_c=getattr(self, 'temperature', None),
            demo_mode=self.scene.upper(), demo_title='SCENE '+self.scene.upper(), model_status=label,
            pc_connected=self.link.service.connected if self.link else False)
        if self.link and self.link.page:
            options['view'] = self.link.page
        if iq is not None:
            options.update(iq=iq, symbols=symbols, selected=selected)
        options.update(getattr(self, 'feature_ui_options', {}))
        self.presenter.present(tracks, force=force, **options)
        self.last_ui = time.monotonic()

    def tick(self):
        from ..drivers.regs import lcd_ctrl as L
        from .monitor_x5 import classify_one
        now = time.monotonic()
        self.safety()
        if self.scene == 'listen':
            self._audio_quality()
        if self.scene in ('fm', 'listen'):
            tracks = self._targets()
            track = self.tracker.next(now)
            if self.link and self.link.selected is not None:
                track = next((t for t in tracks if t.key == self.link.selected), track)
            # In listen mode quality captures have priority over experimental AMC.
            if track and now-self.last_classify >= (1. if self.scene == 'listen' else .35):
                record, iq, symbols = classify_one(self.hw, self.predictor, self.tracker,
                    track, self.output, self.capture_index, self.config['lo_hz'])
                self.capture_index += 1
                self.last_classify = time.monotonic()
                self.records.append(record)
                self.presenter.classification(record['prediction'])
                if self.link:
                    self.link.classification(record, iq)
                self._present(iq=iq, symbols=symbols, selected=track.key)
        # All blocking IQ/inference/UI calls precede counter-rate timestamps.
        now = time.monotonic()
        if now-self.last_telemetry >= 1:
            current = int(self.hw.lcd.registers.read(L.FRAME_COUNT))
            elapsed = now-self.last_telemetry
            self.fps = ((current-self.last_frame) & 0xffffffff)/elapsed
            audio = self.hw.audio.snapshot()
            if self.scene == 'listen' and self.last_audio is not None:
                seconds = now-self.last_audio_time
                for key in ('frames', 'pcm_samples'):
                    rate = ((audio[key]-self.last_audio[key]) & 0xffffffff)/seconds
                    if not 47000 <= rate <= 49000:
                        raise RuntimeError('Resident audio sample clock integrity failed')
            self.last_audio, self.last_audio_time = audio, now
            self.telemetry = dict(scene=self.scene, display_frames=current, display_fps=self.fps,
                temperature_c=self.temperature, rx_rssi_dbm=self.radio.rssi(0),
                tx_attenuation_db=list(self.radio.tx_atten), tx_on=False,
                audio=dict(audio, output_unmuted=self.audible, station_hz=self.config['station_hz']),
                pilot=self.quality)
            self.samples.append(self.telemetry)
            self.last_frame, self.last_telemetry = current, now
        if now-self.last_ui >= .2:
            self._present()
        if self.link:
            self.link.update(self.tracker.visible(time.monotonic()),
                telemetry=self.telemetry, events=self.presenter.events.latest())

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        try:
            if self.link is not None:
                try:
                    self.link.__exit__(None, None, None)
                except BaseException as error:
                    errors.append(repr(error))
        finally:
            if self.runtime is not None:
                try:
                    self.runtime.close()
                except BaseException as error:
                    errors.append(repr(error))
        self.cleanup_errors = errors
        if errors:
            raise RuntimeError('Resident final cleanup failed: '+str(errors))

