"""Run one bounded receive-only, fail-closed Y3 FM onboard-speaker check."""
import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import signal
import sys
import time

import numpy as np


def write_receipt(path, result):
    data = json.dumps(result, indent=2, sort_keys=True)+'\n'
    temporary = path.with_suffix('.tmp')
    temporary.write_text(data)
    temporary.replace(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    path.with_name(path.name+'.sha256').write_text(digest+'  '+path.name+'\n')


def main(argv=None, runtime=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit', type=Path, required=True)
    parser.add_argument('--image', choices=('sentinel_y3', 'sentinel_v2_100m'),
                        default='sentinel_y3')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--load', action='store_true',
                        help='Explicitly download the separately audited Y3 image')
    parser.add_argument('--station-hz', type=int, default=95800000)
    parser.add_argument('--lo-hz', type=int, default=96400000)
    parser.add_argument('--seconds', type=float, default=300)
    parser.add_argument('--volume', '--min-audio-db', dest='volume_db', type=float,
                        default=-21, help='OUT1/OUT2 analog dB, -45..-6 in 1.5dB steps; release defaults -12')
    parser.add_argument('--bus-phase', type=int, choices=(2, 3), default=3,
                        help='SSD1963 write-bus phase; 3 retains the prior default')
    parser.add_argument('--speaker-volume', type=float, choices=(-6, -3, 0),
                        help='Explicit ROUT2-only gain; OUT1 retains the -6 dB ceiling')
    parser.add_argument('--stereo-quality-gate', action='store_true',
                        help='Known stereo FM only: keep noisy/uncertain input muted')
    parser.add_argument('--noise-events', type=Path,
                        help='F1: save IQ/gain/RSSI when known-stereo pilot is below 20 dB')
    parser.add_argument('--demo-title', help='F2 PS-only segment heading/countdown')
    parser.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    parser.add_argument('--hostlink', action='store_true')
    parser.add_argument('--hostlink-bind')
    args = parser.parse_args(argv)
    if not 70000000 <= args.lo_hz <= 512000000 or abs(args.station_hz-args.lo_hz) >= 1920000:
        parser.error('FM station must be within the 3.84MSPS receive span')
    if not 1 <= args.seconds <= 300:
        parser.error('Bounded Y3 test: 1..300 seconds')
    if args.out.exists():
        parser.error('Choose a new output directory; evidence is immutable')
    # Board scripts are installed beside the isolated PS package.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'ps'))
    import os
    if os.geteuid() != 0:
        raise SystemExit('Run with sudo using the PYNQ Python interpreter')
    os.environ['XILINX_XRT'] = '/usr'
    from sentinel.app.runtime_v1 import Session
    from sentinel.v_y3 import VY3
    from sentinel.v2 import V2
    from sentinel.params import clock_hz_for_image
    from sentinel.audio_y3 import CodecOutputs, PynqIicBus, shutdown_audio_outputs
    from sentinel.capture_x5 import select_channel
    from sentinel.fm_quality import StereoQualityGate, stereo_quality
    from sentinel.release_support import NoiseRecorder
    from sentinel.telemetry import read_temperature_c
    from sentinel.drivers.regs import lcd_ctrl as L
    from sentinel.drivers.regs import src_ctrl as S
    from sentinel.ui_v3.presenter import Presenter
    from sentinel.app.monitor_x1_guard8 import configure_checked
    from sentinel.app.hostlink_runtime import RuntimeLink
    CodecOutputs.volume_code(args.volume_db)  # no bus access on invalid input
    if args.speaker_volume is not None:
        CodecOutputs.speaker_volume_code(args.speaker_volume)

    args.out.mkdir(parents=True, exist_ok=False)
    result_path = args.out/'result.json'
    result = dict(status='started', image=args.image, source='rf', RF_TX_requested=False,
        dsp_clock_hz=clock_hz_for_image(args.image),
        tx_attenuation_db=[89.75, 89.75], station_hz=args.station_hz, lo_hz=args.lo_hz,
        sample_rate_hz=3840000, channel_rate_hz=480000, bandwidth_hz=1500000,
        duration_requested_s=args.seconds, initial_digital_volume_db=CodecOutputs.DIGITAL_VOLUME_DB,
        initial_analog_volume_db=args.volume_db, bus_phase_requested=args.bus_phase,
        wav_recording=('not_supported_playback_only_path' if args.demo_title else None),
        fcw=None, pfb_channel=None,
        boot_id=Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        tx1a='disconnected', rx_port='RX1A', samples=[], codec_registers_before_unmute=None)
    stop = [False]
    def request_stop(*_):
        stop[0] = True
        if runtime is not None:
            runtime.stop_requested = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    codec = None
    session = None
    presenter = None
    link = None
    network_cleanup = ExitStack()
    try:
        write_receipt(result_path, result)
        factory = V2 if args.image == 'sentinel_v2_100m' else VY3
        session_factory = runtime.session if runtime is not None else Session
        session = session_factory(str(args.bit), 'rf', args.load, args.lo_hz, 3840000, hw_factory=factory)
        session.__enter__()
        hw, radio = session.hw, session.radio
        if radio.tx_atten != (89.75, 89.75):
            raise RuntimeError('TX attenuation safety readback failed')
        if abs(radio.rx_lo-args.lo_hz) > 5 or radio.rate != 3840000:
            raise RuntimeError('AD9361 LO/rate readback failed')
        if radio.rssi(0) > -30:
            raise RuntimeError('RX RSSI exceeds -30dBm; stop before audio')
        hw.audio.disable(release_pins=True)
        bus = PynqIicBus(hw.audio_iic)
        codec = runtime.get_codec(hw) if runtime is not None else CodecOutputs(bus)
        codec.initialize(volume_db=args.volume_db, speaker_volume_db=args.speaker_volume)
        result['speaker_analog_volume_db'] = codec.speaker_volume_db
        selection = select_channel(args.station_hz-args.lo_hz)
        result.update(codec_address_7bit=codec.ADDRESS, codec_slave=True,
            codec_out1_enabled=True, codec_out2_enabled=True,
            output_route='ROUT2->MD8002A->J36', codec_muted_before_play=True,
            codec_registers_before_unmute={hex(reg): codec.read(reg) for reg in
                (0x04, 0x08, 0x17, 0x18, 0x19, 0x1a, 0x1b, 0x27, 0x2a, 0x2e, 0x2f, 0x30, 0x31)},
            fcw=selection.fcw, pfb_channel=selection.channel, residual_hz=selection.residual_hz,
            configuration_readback={'lo_hz': radio.rx_lo, 'rate_hz': radio.rate,
                                     'tx_attenuation_db': list(radio.tx_atten)})
        hw.source.stop()
        hw.reset_channelizer()
        result['dsp_configuration_readback'] = configure_checked(hw, radio, args.lo_hz)
        hw.lcd.set_bus_phase(args.bus_phase)
        hw.lcd.enable()
        presenter = Presenter(hw.lcd, args.ui)
        hw.perf.clear()
        hw.perf.arm()
        configured_rate = hw.source.configure('rf', rate=3840000)
        rate_divider = hw.source.mmio.read(S.RATE_DIV)
        hw.audio.configure(args.station_hz, args.lo_hz, codec)
        hw.audio.start()
        time.sleep(.001)  # let FIFO reset-busy clear before accepting RF IQ
        hw.source.start()
        if runtime is not None:
            runtime.wait_frames(hw)
        deadline = time.monotonic()+8
        while time.monotonic() < deadline:
            state = hw.audio.snapshot()
            if state['iq_overflow'] or state['pcm_full'] or state['underflows']:
                raise RuntimeError('Audio FIFO error before playback: '+str(state))
            if state['playing'] and state['fifo_level'] >= 3072:
                break
            time.sleep(.1)
        else:
            raise TimeoutError('Audio FIFO did not prefill to its playback threshold')
        quality_gate = StereoQualityGate() if args.stereo_quality_gate else None
        if args.noise_events is not None and quality_gate is None:
            raise ValueError('Noise-event monitoring requires stereo quality gate')
        recorder = NoiseRecorder(args.noise_events) if args.noise_events is not None else None
        rf_noisy = False
        audible = False
        if quality_gate is None:
            codec.unmute()
            audible = True
        result['stereo_quality_gate'] = bool(quality_gate)
        result['quality_samples'] = []
        result['audible_intervals_s'] = []
        result.update(status='playing', started_utc=datetime.now(timezone.utc).isoformat(),
            source_rate_divider_readback=rate_divider,
            configured_rate_hz=configured_rate, actual_rate_hz=radio.rate,
            bus_phase=args.bus_phase, initial_audio_output_enabled=audible)
        start = last = time.monotonic()
        if args.hostlink or getattr(runtime, 'hostlink_address', None):
            link = network_cleanup.enter_context(RuntimeLink(hw, args.bit, args.out, args.lo_hz,
                mode='listen', address=args.hostlink_bind or getattr(runtime, 'hostlink_address', None),
                runtime=runtime))
        if runtime is not None:
            runtime.mark_content_started()
        last_frames = int(hw.lcd.registers.read(L.FRAME_COUNT))
        last_audio = hw.audio.snapshot()
        audible_start = 0.0 if audible else None
        last_quality = start
        def remote_station(station_hz):
            nonlocal selection, audible, audible_start, last_audio, last_quality, last, last_frames
            if args.demo_title:
                raise ValueError('Demo listening is controlled locally')
            if quality_gate is None:
                raise ValueError('Remote listen requires stereo quality gate')
            from sentinel.release_support import load_config
            cfg = load_config(Path(args.bit).resolve().parents[2]/'config.yaml')
            if round(station_hz) not in {s['frequency_hz'] for s in cfg['stations']}:
                raise ValueError('Station is not in confirmed stereo list')
            if abs(station_hz-args.lo_hz) >= 1920000:
                raise ValueError('Restart local listen with station LO before remote selection')
            selection = select_channel(station_hz-args.lo_hz)
            codec.checked(0x19, codec.MUTE)
            if audible_start is not None:
                result['audible_intervals_s'].append([audible_start, time.monotonic()-start])
            audible, audible_start = False, None
            hw.audio.disable(release_pins=True)
            hw.audio.configure(station_hz, args.lo_hz, codec)
            hw.audio.start()
            args.station_hz = int(round(station_hz))
            last_audio = hw.audio.snapshot()
            last_quality = time.monotonic()
            last = last_quality
            last_frames = int(hw.lcd.registers.read(L.FRAME_COUNT))
            result.setdefault('remote_stations_hz', []).append(args.station_hz)
            if quality_gate is not None:
                quality_gate.__init__()
        while not stop[0] and time.monotonic()-start < args.seconds:
            time.sleep(min(.25, max(.01, args.seconds-(time.monotonic()-start))))
            radio.check_rssi()
            if link is not None:
                link.commands([], request_stop, on_listen=remote_station)
            now = time.monotonic()
            if quality_gate is not None and now-last_quality >= .25:
                capture = hw.channel_capture.acquire(selection, source=0)
                quality = stereo_quality(capture['iq'])
                if recorder is not None:
                    rf_noisy = quality['pilot_prominence_db'] < 20
                    event = recorder.observe(capture, quality, radio, args.station_hz, args.lo_hz)
                    if event is not None:
                        result.setdefault('noise_events', []).append(event)
                should_play = quality_gate.update(quality)
                # The existing gate still applies; F1 additionally holds mute
                # below its explicit 20 dB known-stereo pilot requirement.
                if recorder is not None and rf_noisy:
                    should_play = False
                elapsed_quality = time.monotonic()-start
                quality.update(elapsed_s=elapsed_quality, gate_open=should_play,
                               timestamp_cycles=capture['timestamp_cycles'])
                result['quality_samples'].append(quality)
                if should_play != audible:
                    if should_play:
                        codec.unmute()
                        audible_start = elapsed_quality
                    else:
                        codec.checked(0x19, codec.MUTE)
                        result['audible_intervals_s'].append([audible_start, elapsed_quality])
                        audible_start = None
                    audible = should_play
                last_quality = time.monotonic()
            # Capture and codec IIC calls are blocking. Counter rates must use
            # a timestamp after those calls, not the pre-capture polling time.
            now = time.monotonic()
            if now-last < 1:
                if result['samples']:
                    previous_ui = result['samples'][-1]
                    presenter.present([], lo_hz=radio.rx_lo, rate_hz=radio.rate,
                        frame=previous_ui['display_frames'], fps=previous_ui['display_fps'],
                        temperature_c=previous_ui['temperature_c'], view='SIG', demo_mode='LISTEN',
                        demo_title=args.demo_title,
                        demo_remaining_s=max(0, args.seconds-(now-start)) if args.demo_title else None)
                continue
            audio = hw.audio.snapshot()
            frame_count = int(hw.lcd.registers.read(L.FRAME_COUNT))
            elapsed = now-last
            fps = ((frame_count-last_frames) & 0xffffffff)/elapsed
            temperature = read_temperature_c()
            entry = dict(elapsed_s=now-start, audio=audio, display_frames=frame_count,
                display_fps=fps, temperature_c=temperature, rx_rssi_dbm=radio.rssi(0),
                tx_attenuation_db=list(radio.tx_atten),
                audio_frame_rate_hz=(audio['frames']-last_audio['frames'])/elapsed,
                pcm_sample_rate_hz=(audio['pcm_samples']-last_audio['pcm_samples'])/elapsed,
                channel_health=int(hw.channel_health()),
                pfb_capture_status=int(hw.x5_status.read(0)))
            if audio['iq_overflow'] or audio['pcm_full'] or audio['underflows']:
                raise RuntimeError('Audio continuity/FIFO error: '+str(entry))
            if not audio['playing'] or audio['fifo_level'] < 128:
                raise RuntimeError('Audio FIFO below protective low-water threshold')
            if (entry['channel_health'] or entry['pfb_capture_status'] & 0x1f0
                    or not 47000 <= entry['audio_frame_rate_hz'] <= 49000
                    or not 47000 <= entry['pcm_sample_rate_hz'] <= 49000):
                raise RuntimeError('Continuous sample/clock integrity failed: '+str(entry))
            if fps < 30 or temperature is None or not 30 <= temperature <= 85:
                raise RuntimeError('LCD performance/temperature gate failed: '+str(entry))
            if entry['rx_rssi_dbm'] > -30 or entry['tx_attenuation_db'] != [89.75, 89.75]:
                raise RuntimeError('RF safety readback failed: '+str(entry))
            result['samples'].append(entry)
            if link is not None:
                link.update(telemetry=entry, events=presenter.events.latest())
                if args.demo_title:
                    link.service.publish('demo', group='A', segment=3, title=args.demo_title,
                        remaining_s=max(0, args.seconds-(now-start)))
            result['last_codec_status'] = ('unmuted' if audible else 'quality-muted')
            presenter.present(
                [], lo_hz=radio.rx_lo, rate_hz=radio.rate, frame=frame_count,
                fps=fps, temperature_c=temperature,
                demo_title=args.demo_title,
                demo_mode='LISTEN', view='SIG',
                demo_remaining_s=(max(0, args.seconds-(now-start)) if args.demo_title else None),
                model_status=('RF NOISY - check antenna/power' if rf_noisy else '%s %.3f MHz / TX OFF' %
                    ('LISTENING' if audible else 'WEAK FM: MUTED', args.station_hz/1e6)))
            result['ui'] = presenter.summary()
            write_receipt(result_path, result)
            print(json.dumps(entry, sort_keys=True), flush=True)
            last, last_frames, last_audio = now, frame_count, audio
        result['elapsed_total_s'] = time.monotonic()-start
        if audible_start is not None:
            result['audible_intervals_s'].append([audible_start, result['elapsed_total_s']])
        result['audible_seconds'] = sum(b-a for a,b in result['audible_intervals_s'])
        # The last one-second telemetry sample may precede the end of playback.
        # Capture sticky errors before disable resets the FIFO fault latches.
        result['audio_before_stop'] = hw.audio.snapshot()
        result['channel_health_before_stop'] = int(hw.channel_health())
        result['pfb_capture_status_before_stop'] = int(hw.x5_status.read(0))
        end_audio = result['audio_before_stop']
        if (end_audio['iq_overflow'] or end_audio['pcm_full']
                or end_audio['underflows'] or not end_audio['playing']
                or result['channel_health_before_stop']
                or result['pfb_capture_status_before_stop'] & 0x1f0):
            raise RuntimeError('Continuity error in final playback interval: '+str(end_audio))
        result['status'] = 'completed' if not stop[0] and result['elapsed_total_s'] >= args.seconds else 'stopped_early'
    except BaseException as error:
        result.update(status='failed', error=repr(error))
        raise
    finally:
        try:
            network_cleanup.close()
        except Exception as error:
            result['hostlink_cleanup_error'] = repr(error)
            result['status'] = 'failed'
        if link is not None:
            result['hostlink'] = link.summary()
        if presenter is not None:
            result['ui'] = presenter.summary()
        result['stopped_utc'] = datetime.now(timezone.utc).isoformat()
        audio = session.hw.audio if session is not None and session.hw is not None else None
        result['safe_stop_errors'] = shutdown_audio_outputs(codec, audio)
        if audio is not None:
            try:
                result['final_audio'] = audio.snapshot()
            except Exception as error:
                result['safe_stop_errors'].append('PL audio final snapshot: '+repr(error))
        if codec is not None:
            result['final_codec_muted'] = not codec.initialized and not result['safe_stop_errors']
        if session is not None:
            try:
                session.close()
            except Exception as error:
                result['safe_stop_errors'].append('RF stop/cleanup: '+repr(error))
        result['status'] = 'failed_safe_stop_error' if result['safe_stop_errors'] else result['status']
        result['final_elapsed_s'] = time.monotonic()-start if 'start' in locals() else 0
        write_receipt(result_path, result)
    if result['status'] == 'failed_safe_stop_error':
        raise RuntimeError('Audio cleanup failed; see result.json')


if __name__ == '__main__':
    main()
