"""Bounded, receive-only F2 demonstration group A supervisor."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

from ..release_support import load_config, verify_release, write_result, sha


SEGMENTS = (
    (1, 'SELFTEST', 10),
    (2, 'FM MONITOR / AMC', 40),
    (3, 'FM SPEAKER', 30),
    (4, 'THREE-TONE TEST', 15),
)


def stopped_readback(root):
    command = [sys.executable, '-I', str(root/'scripts/y3_postflight.py'),
               '--bit', str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit')]
    response = subprocess.run(command, capture_output=True, text=True, timeout=30)
    if response.returncode:
        raise RuntimeError('Segment stop verification failed: '+response.stderr[-1000:])
    value = json.loads(response.stdout)
    if value.get('status') != 'PASS' or any(type(value.get(k)) is not int or value[k] != 0
            for k in ('gpio_data', 'source_ctrl', 'audio_control')):
        raise RuntimeError('Segment controls did not stop: '+str(value))
    return value


def checked_result(directory):
    path = directory/'result.json'
    if sha(path) != Path(str(path)+'.sha256').read_text().split()[0]:
        raise RuntimeError('Segment result hash mismatch')
    result = json.loads(path.read_text())
    if result.get('status') not in ('PASS', 'completed'):
        raise RuntimeError('Segment incomplete: '+str(result.get('status')))
    if result.get('safe_stop_errors'):
        raise RuntimeError('Segment cleanup errors')
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    parser.add_argument('--hostlink', action='store_true')
    parser.add_argument('--hostlink-bind')
    parser.add_argument('--group', choices=('A',), default='A')
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--station-hz', type=int, required=True)
    parser.add_argument('--lo-hz', type=int, required=True)
    parser.add_argument('--volume', type=float, required=True)
    parser.add_argument('--segment', type=int, choices=(1, 2, 3, 4))
    parser.add_argument('--isolated', action='store_true', help='Use original per-segment subprocess/download path')
    parser.add_argument('--record-audio', type=Path, help='Requested playback WAV; unsupported on frozen image (reported explicitly)')
    parser.add_argument('--loop', action='store_true')
    parser.add_argument('--cycles', type=int, choices=range(1, 4),
                        help='Bounded repeat count for acceptance (default one; --loop is indefinite)')
    args = parser.parse_args(argv)
    root, output = args.root.resolve(), args.output.resolve()
    if os.geteuid() != 0:
        parser.error('Run from sentinel.sh with sudo')
    if output.exists():
        parser.error('Preserve existing demo evidence')
    if not (root/'manifest.json').is_file():
        parser.error('Release root is incomplete')
    verify_release(root)
    config = load_config(root/'config.yaml')
    if (args.station_hz != config['station_hz'] or args.lo_hz != config['lo_hz']
            or args.volume != config['volume_db']):
        parser.error('Use the checked release configuration')
    if args.loop and args.cycles is not None:
        parser.error('--loop and --cycles are mutually exclusive')
    output.mkdir(parents=True)
    logs = output/'logs'
    logs.mkdir()
    stop = [False]
    child = [None]
    runtime = None
    if not args.isolated:
        from .runtime_v2 import SentinelRuntime
        runtime = SentinelRuntime(root)
        if args.hostlink:
            runtime.hostlink_address = args.hostlink_bind or config.get('hostlink_bind')
            if not runtime.hostlink_address:
                parser.error('Explicit hostlink LAN address required')
    elif args.hostlink:
        parser.error('hostlink requires persistent demo runtime')

    def request_stop(*_):
        stop[0] = True
        if runtime is not None:
            runtime.stop_requested = True
        if child[0] is not None and child[0].poll() is None:
            child[0].send_signal(signal.SIGTERM)

    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, request_stop)

    selected = [item for item in SEGMENTS if args.segment is None or item[0] == args.segment]
    result = dict(status='STARTED', group='A', image='sentinel_v2_100m',
                  runtime_mode='isolated' if args.isolated else 'persistent',
                  wav_recording=dict(status='UNSUPPORTED_NO_PLAYBACK_PCM_READBACK',
                      requested_path=str(args.record_audio) if args.record_audio else None,
                      file_created=False),
                  cycles_timing=[], RF_TX_requested=False, tx1a='disconnected', rx_port='RX1A',
                  station_hz=args.station_hz, lo_hz=args.lo_hz, volume_db=args.volume,
                  loop=args.loop, segment_filter=args.segment, segments=[],
                  started_utc=datetime.now(timezone.utc).isoformat())
    receipt = output/'demo.json'

    def save():
        if runtime is not None:
            result['runtime'] = runtime.evidence
        write_result(receipt, result)

    def execute(command, log_path, seconds):
        if runtime is not None:
            if stop[0]:
                return None
            code = runtime.run_script(Path(command[2]).name, command[3:], log_path)
            if runtime.stop_requested:
                stop[0] = True
            return code
        with log_path.open('wb') as log:
            if stop[0]:
                return None
            child[0] = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                        start_new_session=True)
            if stop[0]:
                child[0].terminate()
            try:
                return child[0].wait(timeout=seconds+90)
            except subprocess.TimeoutExpired:
                child[0].terminate()
                # Never start another worker or reset hardware while cleanup
                # is pending; retain ownership until the child has exited.
                child[0].wait()
                raise RuntimeError('Segment exceeded bounded runtime; terminated gracefully')
            finally:
                if child[0].poll() is not None:
                    child[0] = None

    try:
        save()
        cycle = 0
        while not stop[0]:
            cycle += 1
            cycle_started = time.monotonic()
            station = None
            for number, title, seconds in selected:
                if stop[0]:
                    break
                tag = 'segment_%02d_%s' % (number, uuid.uuid4().hex[:8])
                segment_dir = output/tag
                if number == 3 and station is None:
                    probe = output/('selection_'+uuid.uuid4().hex[:8])
                    code = execute([sys.executable, '-I', str(root/'scripts/release_selftest.py'),
                        '--out', str(probe), '--select-station', '--ui', args.ui], logs/(probe.name+'.log'), 10)
                    if stop[0]:
                        break
                    if code != 0:
                        raise RuntimeError('Station selection failed; no speaker playback')
                    station = checked_result(probe)['station_selection']['selected']
                    result.setdefault('selection_checks', []).append(dict(
                        directory=probe.name, stop_readback=(runtime.stopped_readback() if runtime is not None else stopped_readback(root))))
                if number == 1:
                    command = [sys.executable, '-I', str(root/'scripts/release_selftest.py'),
                               '--out', str(segment_dir), '--seconds', str(seconds),
                               '--demo-title', '%d/4 %s' % (number, title), '--select-station']
                elif number == 2:
                    command = [sys.executable, '-I', str(root/'scripts/run_x5_monitor.py'),
                               '--bit', str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'),
                               '--image', 'sentinel_v2_100m', '--out', str(segment_dir),
                               '--seconds', str(seconds), '--bus-phase', '2', '--lo', str(args.lo_hz),
                               '--model', str(root/'ps/models/weights/amc_v2/round_3/model.npz'),
                               '--quality-station-hz', str(args.station_hz),
                               '--noise-events', str(root/'measurements/noise_events'),
                               '--demo-title', '%d/4 %s' % (number, title)]
                elif number == 3:
                    command = [sys.executable, '-I', str(root/'scripts/run_y3_audio.py'),
                               '--bit', str(root/'overlay/sentinel_v2_100m/sentinel_v2_100m.bit'),
                               '--image', 'sentinel_v2_100m', '--out', str(segment_dir),
                               '--seconds', str(seconds), '--bus-phase', '2', '--load',
                               '--station-hz', str(station['frequency_hz']), '--lo-hz', str(station['lo_hz']),
                               '--volume', str(args.volume), '--stereo-quality-gate',
                               '--noise-events', str(root/'measurements/noise_events'),
                               '--demo-title', '%d/4 %s' % (number, title)]
                    if 'speaker_volume_db' in config:
                        command += ['--speaker-volume', str(config['speaker_volume_db'])]
                else:
                    command = [sys.executable, '-I', str(root/'scripts/run_test_display.py'),
                               '--root', str(root), '--out', str(segment_dir),
                               '--seconds', str(seconds), '--lo-hz', str(args.lo_hz),
                               '--title', '%d/4 %s' % (number, title)]
                command += ['--ui', args.ui]
                log_path = logs/(tag+'.log')
                started = time.monotonic()
                code = execute(command, log_path, seconds)
                segment = dict(number=number, cycle=cycle, title=title, duration_requested_s=seconds,
                               duration_wall_s=time.monotonic()-started, exit_code=code,
                               evidence_dir=tag, log=str(log_path.relative_to(output)))
                result['segments'].append(segment)
                save()
                segment['stop_readback'] = (runtime.stopped_readback() if runtime is not None else stopped_readback(root))
                if stop[0]:
                    break
                if code != 0:
                    raise RuntimeError('Demo segment %d failed with exit %d; see %s' %
                                       (number, code, log_path))
                record = checked_result(segment_dir)
                segment['result_sha256'] = sha(segment_dir/'result.json')
                if number == 1:
                    station = record['station_selection']['selected']
                    if station is None:
                        raise RuntimeError('No trusted station; abort demo before speaker playback')
                if number == 3:
                    segment['audible_seconds'] = record['audible_seconds']
                    if record['audible_seconds'] <= 0:
                        raise RuntimeError('Speaker stayed muted; not successful FM playback')
                save()
            result['cycles_timing'].append(dict(cycle=cycle, wall_seconds=time.monotonic()-cycle_started))
            result['completed_cycles'] = cycle if not stop[0] else cycle-1
            if (not args.loop and cycle >= (args.cycles or 1)) or stop[0]:
                break
        result['status'] = 'STOPPED' if stop[0] else 'PASS'
    except BaseException as error:
        result.update(status='FAIL', error=repr(error))
        raise
    finally:
        if child[0] is not None and child[0].poll() is None:
            child[0].send_signal(signal.SIGTERM)
            child[0].wait()
        if runtime is not None:
            try:
                runtime.close()
                result['final_stop_readback'] = runtime.stopped_readback()
            except BaseException as error:
                result.update(status='FAIL', safe_stop_error=repr(error))
        result['finished_utc'] = datetime.now(timezone.utc).isoformat()
        save()
    return 0 if result['status'] in ('PASS', 'STOPPED') else 1


if __name__ == '__main__':
    raise SystemExit(main())
