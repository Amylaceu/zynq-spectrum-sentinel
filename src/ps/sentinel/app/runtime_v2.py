"""One-process demo resources with the original per-segment RF ownership.

GPIO=0 resets the transceiver. Consequently RF and codec initialization are
deliberately repeated after safe shutdown; only overlay/DMA objects and the
frozen predictor are cached. Failed DMA objects are never reused or freed here.
No hardware is accessed on import or while warming the classifier.
"""
from contextlib import redirect_stdout, redirect_stderr
import importlib.util
import importlib
from pathlib import Path
import signal
import time
import traceback

from .runtime_v1 import Session
from ..release_support import sha


class SentinelRuntime:
    def __init__(self, root, *, hw_factory=None, session_factory=Session,
                 predictor_factory=None, clock=time.monotonic, sleep=time.sleep):
        self.root = Path(root).resolve()
        self.bit = self.root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
        self.hw_factory, self.session_factory = hw_factory, session_factory
        self.predictor_factory = predictor_factory
        self.clock, self.sleep = clock, sleep
        self.hw = self.active = self.codec = None
        self.predictors, self.modules = {}, {}
        self.stop_requested = False
        self.hostlink_service = None
        self.hostlink_address = None
        self.poisoned = False
        self.evidence = dict(overlay_loads=0, rf_initializations=0,
            model_loads=0, model_warmups=0, segments=[],
            rf_reinitialization_reason='GPIO=0 asserts AD9361 reset at every stop',
            pcm_recording='UNSUPPORTED_NO_PLAYBACK_PCM_READBACK')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def _hardware(self, bit, download=False):
        if Path(bit).resolve() != self.bit:
            raise ValueError('Runtime only owns the frozen v2_100m image')
        if self.poisoned:
            raise RuntimeError('Runtime failed; full audited recovery required')
        if self.hw is None:
            factory = self.hw_factory
            if factory is None:
                from ..v2 import V2
                factory = V2
            self.hw = factory(str(self.bit), download=True)
            self.evidence['overlay_loads'] += 1
        if not self.hw.overlay.is_loaded():
            raise RuntimeError('Cached overlay is no longer loaded')
        if getattr(self.hw.channel_capture, 'failed', False):
            self.poisoned = True
            raise RuntimeError('DMA failure requires full PL recovery, not cached reuse')
        return self.hw

    def session(self, bit, source='test', load=False, lo=98000000,
                rate=3840000, hw_factory=None):
        if source not in ('rf', 'test') or rate != 3840000:
            raise ValueError('Receive/internal-test modes at 3.84 MSPS only')
        if Path(bit).resolve() != self.bit:
            raise ValueError('Mismatched segment bitstream')
        return _Segment(self, str(self.bit), source, lo, rate)

    def predictor(self, model, precision='int8'):
        from .monitor_x5 import MODEL_SHA256
        path = Path(model).resolve()
        key = (str(path), precision)
        if key not in self.predictors:
            if sha(path) != MODEL_SHA256:
                raise ValueError('Runtime requires frozen model')
            factory = self.predictor_factory
            if factory is None:
                from ..amc.infer_np import Predictor
                factory = Predictor
            predictor = factory(str(path), precision=precision)
            # Explicitly synthetic, never counted as an RF prediction.
            import numpy as np
            iq = np.exp(2j*np.pi*np.arange(4096)/31).astype(np.complex64)
            predictor.predict(iq, fs=480000)
            self.predictors[key] = predictor
            self.evidence['model_loads'] += 1
            self.evidence['model_warmups'] += 1
            self.evidence['warmup_source'] = 'synthetic complex tone; excluded from measured results'
        return self.predictors[key]

    def get_codec(self, hw):
        if self.codec is None:
            from ..audio_y3 import CodecOutputs, PynqIicBus
            self.codec = CodecOutputs(PynqIicBus(hw.audio_iic))
        return self.codec

    def mark_content_started(self):
        if self.active is not None:
            self.active.record['content_started_monotonic_s'] = self.clock()
            self.active.record['startup_seconds'] = (
                self.clock()-self.active.record['started_monotonic_s'])

    def wait_frames(self, hw, timeout=2):
        """Require two complete display frames before starting segment content."""
        from ..drivers.regs import lcd_ctrl as L
        before, start = int(hw.lcd.registers.read(L.FRAME_COUNT)), self.clock()
        while self.clock()-start < timeout:
            if self.stop_requested:
                raise KeyboardInterrupt('Demo stop requested')
            current = int(hw.lcd.registers.read(L.FRAME_COUNT))
            if ((current-before) & 0xffffffff) >= 2:
                if self.active is not None:
                    self.active.record['ready_monotonic_s'] = self.clock()
                    self.active.record['ready_frame'] = current
                return current
            if self.active and self.active.radio:
                self.active.radio.check_rssi()
            self.sleep(.01)
        raise TimeoutError('LCD frame counter did not advance by two')

    def stopped_readback(self):
        """Read under exclusive lock after Session releases C-driver ownership."""
        import fcntl
        if self.hw is None or self.active is not None:
            raise RuntimeError('No stopped runtime hardware')
        with open('/run/lock/zss_ad9361.lock', 'a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if not self.hw.overlay.is_loaded():
                raise RuntimeError('Overlay changed before stop verification')
            record = dict(gpio_data=int(self.hw.checked.registers('axi_ad9361_gpio').read(0)),
                source_ctrl=int(self.hw.src_regs.read(0)),
                audio_control=int(self.hw.audio.control.read(0)))
            record['status'] = 'FAIL' if any(record.values()) else 'PASS'
            if record['status'] != 'PASS':
                self.poisoned = True
                raise RuntimeError('Segment stop readback failed: '+str(record))
            return record

    def run_script(self, name, argv, log_path):
        """Explicit runtime injection; no monkeypatching Session or sys.argv."""
        if name not in self.modules:
            if name == 'run_x5_monitor.py':
                module = importlib.import_module('sentinel.app.monitor_x5')
            else:
                path = self.root/'scripts'/name
                spec = importlib.util.spec_from_file_location('_sentinel_demo_'+path.stem, str(path))
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
            self.modules[name] = module
        handlers = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        try:
            with Path(log_path).open('w') as log, redirect_stdout(log), redirect_stderr(log):
                try:
                    return self.modules[name].main(argv, runtime=self) or 0
                except BaseException:
                    traceback.print_exc()
                    raise
        except BaseException:
            self.poisoned = True
            raise
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)

    def close(self):
        if self.active is not None:
            self.active.close()
        if self.hostlink_service is not None:
            self.hostlink_service.close()


class _Segment:
    def __init__(self, runtime, bit, source, lo, rate):
        self.runtime, self.hw, self.radio = runtime, None, None
        self.rf_gpio = None
        self.inner = runtime.session_factory(bit, source, True, lo, rate,
                                             hw_factory=runtime._hardware)
        self.record = dict(source=source, lo_hz=lo, started_monotonic_s=runtime.clock())
        self.closed = False

    def __enter__(self):
        if self.runtime.active is not None or self.runtime.stop_requested or self.runtime.poisoned:
            raise RuntimeError('Runtime not available for new segment')
        try:
            self.inner.__enter__()
        except BaseException:
            self.runtime.poisoned = True
            raise
        self.hw, self.radio, self.rf_gpio = self.inner.hw, self.inner.radio, self.inner.rf_gpio
        self.receive_startup = getattr(self.inner, 'receive_startup', None)
        self.runtime.active = self
        if self.radio is not None:
            self.runtime.evidence['rf_initializations'] += 1
        self.runtime.evidence['segments'].append(self.record)
        return self

    def close(self):
        if self.closed:
            return
        # Do not touch PL when initialization never acquired ownership.
        if self.runtime.active is not self:
            return
        errors = []
        try:
            if self.radio is not None:
                try:
                    self.record['tx_attenuation_before_reset_db'] = list(self.radio.tx_atten)
                    if tuple(self.record['tx_attenuation_before_reset_db']) != (89.75, 89.75):
                        errors.append('Receive-only TX attenuation changed')
                except BaseException as error:
                    errors.append('TX readback: '+repr(error))
            from ..audio_y3 import shutdown_audio_outputs
            codec = self.runtime.codec
            errors.extend(shutdown_audio_outputs(
                codec if codec is not None and codec.initialized else None, self.hw.audio))
            try:
                self.hw.source.stop()
                self.hw.src_regs.write(0, 0)
            except BaseException as error:
                errors.append('Source stop: '+repr(error))
        finally:
            try:
                self.inner.close()
            except BaseException as error:
                errors.append('Session cleanup: '+repr(error))
            self.closed = True
            self.runtime.active = None
            try:
                self.record['stop_readback'] = self.runtime.stopped_readback()
            except BaseException as error:
                errors.append('Stopped readback: '+repr(error))
            self.record.update(finished_monotonic_s=self.runtime.clock(), cleanup_errors=errors)
        if errors:
            self.runtime.poisoned = True
            raise RuntimeError('Persistent segment safe stop failed: '+'; '.join(errors))

    def __exit__(self, *args):
        if args[0] is not None:
            self.runtime.poisoned = True
        self.close()
