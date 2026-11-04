"""Run the frozen PL three-tone source with the live F2 display, TX disabled."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import signal
import sys
import time


def main(argv=None, runtime=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, required=True)
    parser.add_argument('--lo-hz', type=int, required=True)
    parser.add_argument('--title', required=True)
    parser.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    args = parser.parse_args(argv)
    if os.geteuid() != 0:
        parser.error('Requires the PYNQ Python interpreter with sudo')
    if not 1 <= args.seconds <= 15:
        parser.error('Test display duration must be 1..15 seconds')
    sys.path.insert(0, str(args.root/'ps'))
    from sentinel.app.runtime_v1 import Session
    from sentinel.app.monitor_x1_guard8 import CONFIGURATION
    from sentinel.v2 import V2
    from sentinel.telemetry import read_temperature_c
    from sentinel.ui_v3.presenter import Presenter
    from sentinel.app.hostlink_runtime import RuntimeLink
    from sentinel.drivers.regs import lcd_ctrl as L
    import json
    import hashlib

    args.out.mkdir(parents=True, exist_ok=False)
    bit = args.root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'
    result = dict(status='STARTED', source='PL three-tone', bins=[-300, 64, 300],
                  RF_TX_requested=False, duration_requested_s=args.seconds,
                  started_monotonic=time.monotonic())
    stop = [False]
    presenter = None
    def request_stop(*_):
        stop[0] = True
        if runtime is not None:
            runtime.stop_requested = True
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)
    try:
        session_factory = runtime.session if runtime is not None else Session
        with session_factory(str(bit), 'test', True, args.lo_hz, 3840000, hw_factory=V2) as session, ExitStack() as cleanup:
            hw = session.hw
            # Session(test) deliberately holds the AD9361 in reset. Do not
            # initialize it just to show internally generated PL signals.
            if session.rf_gpio.read(0) != 0:
                raise RuntimeError('RF GPIO must remain in reset')
            hw.audio.disable(release_pins=True)
            options = dict(CONFIGURATION)
            average = options.pop('average_shift')
            hw.enable_processing(average_shift=average, **options)
            hw.reset_channelizer()
            hw.lcd.set_bus_phase(2)
            hw.lcd.enable()
            presenter = Presenter(hw.lcd, args.ui)
            hw.perf.clear()
            hw.perf.arm()
            hw.source.configure('test', rate=3840000, bins=(-300, 64, 300),
                                amplitudes=(4096, 4096, 4096))
            hw.source.start()
            if runtime is not None:
                runtime.wait_frames(hw)
            link = None
            if getattr(runtime, 'hostlink_address', None):
                link = cleanup.enter_context(RuntimeLink(hw, bit, args.out, args.lo_hz,
                    mode='test_source', address=runtime.hostlink_address, runtime=runtime))
            start = last = time.monotonic()
            if runtime is not None:
                runtime.mark_content_started()
            frames_before = int(hw.lcd.registers.read(L.FRAME_COUNT))
            samples = []
            while not stop[0] and time.monotonic()-start < args.seconds:
                now = time.monotonic()
                frames = int(hw.lcd.registers.read(L.FRAME_COUNT))
                elapsed = max(now-last, .001)
                fps = ((frames-frames_before) & 0xffffffff)/elapsed
                state = dict(elapsed_s=now-start, frame_count=frames, fps=fps,
                             temperature_c=read_temperature_c(), rf_gpio=session.rf_gpio.read(0),
                             channel_health=int(hw.channel_health()))
                if state['rf_gpio'] != 0 or state['temperature_c'] is None or not 30 <= state['temperature_c'] <= 85:
                    raise RuntimeError('Reset/temperature safety gate failed')
                if state['channel_health']:
                    raise RuntimeError('Test source processing fault')
                if link is not None:
                    link.commands([], request_stop)
                    link.update(telemetry=state)
                    link.service.publish('demo', group='A', segment=4, title='THREE-TONE TEST',
                        remaining_s=max(0, args.seconds-(now-start)), source='PL test')
                presenter.present(
                    [], lo_hz=args.lo_hz, frame=frames, fps=fps,
                    temperature_c=state['temperature_c'], model_status='TEST SOURCE / TX OFF',
                    demo_title=args.title, demo_mode='TEST SOURCE',
                    demo_remaining_s=args.seconds-(now-start), view='SIG')
                samples.append(state)
                last, frames_before = now, frames
                time.sleep(min(.2, max(0, args.seconds-(time.monotonic()-start))))
            cleanup.close()  # release power BRAM owner before stopping its source
            hw.source.stop()
            hw.src_regs.write(0, 0)
            if hw.src_regs.read(0) != 0:
                raise RuntimeError('Source control did not return to zero')
            if not stop[0] and (len(samples) < 2 or samples[-1]['frame_count'] <= samples[0]['frame_count']):
                raise RuntimeError('Display frame counter did not advance')
            result.update(status='STOPPED' if stop[0] else 'PASS',
                          duration_actual_s=time.monotonic()-start, samples=samples,
                          final_frame_count=int(hw.lcd.registers.read(L.FRAME_COUNT)),
                          final_rf_gpio=session.rf_gpio.read(0))
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if presenter is not None:
            result['ui'] = presenter.summary()
        result['finished_monotonic'] = time.monotonic()
        path = args.out/'result.json'
        path.write_text(json.dumps(result, indent=2, sort_keys=True)+'\n')
        path.with_name('result.json.sha256').write_text(
            hashlib.sha256(path.read_bytes()).hexdigest()+'  result.json\n')
    return 0 if result['status'] in ('PASS', 'STOPPED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
