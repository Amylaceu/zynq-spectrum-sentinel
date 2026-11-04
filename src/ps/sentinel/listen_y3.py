"""Continuous PL FM listening alongside capture/AMC, without owning RF.

Enter after the channelizer reset, before starting the RF source. Call
wait_ready after starting that source. Exit before releasing the RF session.
Injected codec/clock objects allow lifecycle tests without PYNQ or MMIO.
"""
import math
import time

from .audio_y3 import CodecOutputs, PynqIicBus, shutdown_audio_outputs
from .capture_x5 import select_channel


def validate_listen(image, station_hz, lo_hz, volume_db):
    if station_hz is None:
        return
    if image != 'sentinel_v2_100m':
        raise ValueError('Integrated listening requires sentinel_v2_100m')
    if not math.isfinite(station_hz) or not 87500000 <= station_hz <= 108000000:
        raise ValueError('Listening station must be in the FM broadcast band')
    select_channel(station_hz - lo_hz)
    CodecOutputs.volume_code(volume_db)


def evaluate_listening(result, seconds):
    """Independent digital checks; never substitute for the hearing report."""
    audio = result.get('audio') or {}
    samples = audio.get('samples') or []
    telemetry = result.get('telemetry') or []
    final = audio.get('audio_before_stop') or {}
    def number(value, low, high):
        return (type(value) in (int, float) and math.isfinite(value)
                and low <= value <= high)
    def clean(state):
        return (state.get('playing') is True and state.get('underflows') == 0
                and state.get('iq_overflow') is False and state.get('pcm_full') is False
                and number(state.get('fifo_level'), 128, 8192))
    return dict(
        completed=result.get('status') == 'completed' and not result.get('stopped_by_signal')
                  and number(result.get('elapsed_total_s'), seconds, seconds+10),
        audio_stopped=audio.get('status') == 'stopped_awaiting_human'
                      and audio.get('safe_stop_errors') == [],
        samples_present=len(samples) >= max(1, int(seconds/3)-1),
        counters=bool(samples) and all(
            number(s.get('interval_s'), .5, 3)
            and number(s.get('audio_frame_rate_hz'), 47000, 49000)
            and number(s.get('pcm_sample_rate_hz'), 47000, 49000)
            and clean(s.get('audio') or {}) for s in samples),
        final_interval=clean(final) and audio.get('channel_health_before_stop') == 0
                       and type(audio.get('pfb_capture_status_before_stop')) is int
                       and not audio['pfb_capture_status_before_stop'] & 0x1f0,
        display=bool(telemetry) and all(number(t.get('display_fps'), 30, 120) for t in telemetry),
        temperature=bool(telemetry) and all(number(t.get('temperature_c'), 30, 85) for t in telemetry),
        rf=bool(telemetry) and all(number(t.get('rx_rssi_dbm'), -200, -30)
                                  and t.get('tx_atten_mdb') == [89750, 89750] for t in telemetry),
    )


class FMListener:
    def __init__(self, hw, station_hz, lo_hz, evidence, volume_db=-21,
                 codec=None, clock=time.monotonic, sleep=time.sleep):
        select_channel(station_hz - lo_hz)
        CodecOutputs.volume_code(volume_db)
        self.hw, self.audio = hw, hw.audio
        self.codec = codec if codec is not None else CodecOutputs(PynqIicBus(hw.audio_iic))
        self.station, self.lo, self.volume = station_hz, lo_hz, volume_db
        self.evidence, self.clock, self.sleep = evidence, clock, sleep
        self.playing = False
        self.last = None
        self.evidence.update(status='preparing', station_hz=station_hz,
                             analog_volume_db=volume_db,
                             output='ES8388 ROUT2 -> MD8002A -> J36',
                             human_listening='PENDING', samples=[])

    def __enter__(self):
        try:
            self.audio.disable(release_pins=True)
            self.codec.initialize(volume_db=self.volume)
            selection = self.audio.configure(self.station, self.lo, self.codec)
            self.evidence.update(channel=selection.channel, fcw=selection.fcw)
            self.audio.start()
            self.sleep(.001)  # clear FIFO reset-busy before source start
            self.evidence['status'] = 'armed_muted'
            return self
        except BaseException:
            self.evidence['status'] = 'failed_initialization'
            self.evidence['safe_stop_errors'] = shutdown_audio_outputs(self.codec, self.audio)
            raise

    def _snapshot(self, require_playing=False):
        state = self.audio.snapshot()
        # Retain fault evidence before disable clears the sticky latches.
        self.evidence['last_observed_audio'] = state
        if state['iq_overflow'] or state['pcm_full'] or state['underflows']:
            raise RuntimeError('Audio FIFO continuity error: ' + str(state))
        if require_playing and (not state['playing'] or state['fifo_level'] < 128):
            raise RuntimeError('Audio playback stopped or FIFO below low-water threshold')
        return state

    def wait_ready(self, safety_check):
        deadline = self.clock() + 8
        while self.clock() < deadline:
            safety_check()
            state = self._snapshot()
            if state['playing'] and state['fifo_level'] >= 3072:
                self.codec.unmute()
                self.playing = True
                self.last = (self.clock(), state)
                self.evidence.update(status='playing', audio_start=state)
                return
            self.sleep(.05)
        raise TimeoutError('Audio FIFO did not prefill; codec remains muted')

    def sample(self):
        if not self.playing:
            raise RuntimeError('Audio must be ready before sampling')
        state, now = self._snapshot(require_playing=True), self.clock()
        before, previous = self.last
        elapsed = now - before
        if elapsed <= 0:
            raise RuntimeError('Audio sample interval must be positive')
        sample = dict(audio=state, interval_s=elapsed,
                      audio_frame_rate_hz=(state['frames'] - previous['frames']) / elapsed,
                      pcm_sample_rate_hz=(state['pcm_samples'] - previous['pcm_samples']) / elapsed)
        self.evidence['samples'].append(sample)
        self.last = (now, state)
        if any(not 47000 <= sample[key] <= 49000
               for key in ('audio_frame_rate_hz', 'pcm_sample_rate_hz')):
            raise RuntimeError('Audio or PCM counter stopped/drifted: ' + str(sample))
        return sample

    def __exit__(self, exc_type, exc, tb):
        final_error = None
        try:
            if self.playing:
                self.evidence['audio_before_stop'] = self._snapshot(require_playing=True)
                health = int(self.hw.channel_health())
                capture = int(self.hw.x5_status.read(0))
                self.evidence.update(channel_health_before_stop=health,
                                     pfb_capture_status_before_stop=capture)
                if health or capture & 0x1f0:
                    raise RuntimeError('Processing continuity error before audio stop')
        except Exception as error:
            final_error = error
            self.evidence['final_check_error'] = repr(error)
        finally:
            errors = shutdown_audio_outputs(self.codec, self.audio)
            self.evidence['safe_stop_errors'] = errors
            self.evidence['status'] = ('failed' if exc_type or final_error or errors
                                       else 'stopped_awaiting_human')
        if exc_type is None:
            if final_error is not None:
                raise final_error
            if errors:
                raise RuntimeError('Audio safe stop failed: ' + str(errors))
        return False
