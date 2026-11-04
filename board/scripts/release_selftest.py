"""F1 receive-only startup check; no audio playback or transmit request."""
import argparse
from contextlib import ExitStack
import os
from pathlib import Path
import signal
import sys


def main(argv=None, runtime=None):
    root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(root/'ps'))
    from sentinel.release_support import load_config, verify_release, write_result, startup_quality, select_demo_station
    from sentinel.app.runtime_v1 import Session
    from sentinel.app.monitor_x1_guard8 import configure_checked, check_safety
    from sentinel.v2 import V2
    from sentinel.telemetry import read_temperature_c
    from sentinel.ui_v3.presenter import Presenter
    from sentinel.app.hostlink_runtime import RuntimeLink
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=0,
                        help='F2 hold the selftest display, seconds after initialization')
    parser.add_argument('--demo-title')
    parser.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    parser.add_argument('--select-station', action='store_true')
    args = parser.parse_args(argv)
    if not 0 <= args.seconds <= 10:
        parser.error('Selftest display duration must be 0..10 seconds')
    if os.geteuid() != 0:
        parser.error('Run with sudo using the PYNQ Python interpreter')
    verify_release(root)
    config = load_config(root/'config.yaml')
    if args.out.exists():
        parser.error('Preserve existing measurements')
    args.out.mkdir(parents=True)
    result = dict(status='STARTED', RF_TX_requested=False, audio_playback=False)
    def stop(*_):
        if runtime is not None:
            runtime.stop_requested = True
        raise KeyboardInterrupt('Selftest stop requested')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, stop)
    bit = root/'overlay'/config['image']/(config['image']+'.bit')
    presenter = None
    try:
        session_factory = runtime.session if runtime is not None else Session
        with session_factory(str(bit), 'rf', True, config['lo_hz'], config['sample_rate_hz'], hw_factory=V2) as session, ExitStack() as cleanup:
            hw, radio = session.hw, session.radio
            hw.audio.disable(release_pins=True)
            product = radio.lib.z20_read_register(0x037)
            if product < 0 or product & 0xf8 != 0x08:
                raise RuntimeError('Unexpected AD9361 product ID')
            state = dict(temperature_c=read_temperature_c(), rx_rssi_dbm=radio.rssi(0),
                         tx_atten_mdb=[round(v*1000) for v in radio.tx_atten])
            check_safety(state)
            configure_checked(hw, radio, config['lo_hz'])
            hw.reset_channelizer()
            hw.lcd.set_bus_phase(config['bus_phase'])
            hw.lcd.enable()
            presenter = Presenter(hw.lcd, args.ui)
            hw.source.configure('rf', rate=config['sample_rate_hz'])
            hw.source.start()
            if runtime is not None:
                runtime.wait_frames(hw)
            quality = startup_quality(hw, radio, config['station_hz'], config['lo_hz'],
                                      root/'measurements/noise_events')
            if args.select_station:
                result['station_selection'] = select_demo_station(
                    hw, radio, config, root/'measurements/noise_events')
                if result['station_selection']['selected'] is None:
                    raise RuntimeError('No trusted confirmed FM station; speaker remains muted')
            link = None
            if getattr(runtime, 'hostlink_address', None):
                link = cleanup.enter_context(RuntimeLink(hw, bit, args.out, radio.rx_lo,
                    mode='selftest', address=runtime.hostlink_address, runtime=runtime))
            message = 'SELFTEST PASS / TX OFF' if quality['quality_pass'] else 'RF NOISY - check antenna/power'
            checks = [('AD9361 ID', True), ('BITSTREAM', True),
                      ('TX 89.75dB', state['tx_atten_mdb'] == [89750, 89750]),
                      ('TEMP', state['temperature_c'] is not None and 30 <= state['temperature_c'] <= 85)]
            presenter.present([], force=True, lo_hz=radio.rx_lo,
                temperature_c=state['temperature_c'], model_status=message,
                selftest_checks=[(name, None if args.seconds else passed) for name, passed in checks],
                view='SIG', demo_mode='SELFTEST')
            if args.seconds:
                import time
                from sentinel.drivers.regs import lcd_ctrl as L
                start = last = time.monotonic()
                if runtime is not None:
                    runtime.mark_content_started()
                previous = hw.lcd.registers.read(L.FRAME_COUNT)
                while time.monotonic()-start < args.seconds:
                    radio.check_rssi()
                    now = time.monotonic()
                    frames = hw.lcd.registers.read(L.FRAME_COUNT)
                    fps = ((frames-previous) & 0xffffffff)/max(now-last, .001)
                    state['temperature_c'] = read_temperature_c()
                    state['rx_rssi_dbm'] = radio.rssi(0)
                    state['tx_atten_mdb'] = [round(v*1000) for v in radio.tx_atten]
                    check_safety(state)
                    if link is not None:
                        link.commands([], stop)
                        link.update(telemetry=dict(state, display_fps=fps))
                        link.service.publish('demo', group='A', segment=1, title='SELFTEST',
                            remaining_s=max(0, args.seconds-(now-start)))
                    revealed = min(4, int((now-start)/.5))
                    presenter.present([], lo_hz=radio.rx_lo,
                        frame=frames, fps=fps, temperature_c=state['temperature_c'],
                        model_status=message, demo_title=args.demo_title,
                        demo_mode='SELFTEST', demo_remaining_s=args.seconds-(now-start),
                        selftest_checks=[(name, passed if i < revealed else None)
                                         for i, (name, passed) in enumerate(checks)])
                    previous, last = frames, now
                    time.sleep(min(.2, max(0, args.seconds-(time.monotonic()-start))))
            result.update(status='PASS' if quality['quality_pass'] else 'FAIL_RF_QUALITY',
                          product_id=product, startup_quality=quality, telemetry=state)
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if presenter is not None:
            result['ui'] = presenter.summary()
        write_result(args.out/'result.json', result)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
