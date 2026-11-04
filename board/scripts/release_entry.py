"""Explicit F1 foreground supervisor with identity-checked graceful stop.

The worker owns the RF lock. Stop signals its supervisor, never kills arbitrary
Python processes, and verifies GPIO/SRC/audio after the worker's cleanup.
"""
import argparse
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'ps'))
from sentinel.release_support import load_config, verify_release, write_result

LOCK = '/run/lock/zss_release_v2.lock'
STATE = '/run/zss_release_v2.json'


def process_start(pid):
    # comm may contain spaces; field 22 is relative to the closing parenthesis.
    return (Path('/proc')/str(pid)/'stat').read_text().rsplit(')', 1)[1].split()[19]


def valid_supervisor(state, root):
    try:
        pid = state['pid']
        if type(pid) is not int or pid <= 1 or state['root'] != str(root):
            return False
        command = (Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
        return (str(root/'scripts/release_entry.py').encode() in command
                and process_start(pid) == state['start_ticks'])
    except (OSError, KeyError, IndexError):
        return False


def worker_command(root, config, args, out):
    if args.command == 'serve':
        if getattr(args, 'arm_ota', False):
            raise ValueError('S1 presentation uses labelled PC replay; live OTA arm is unavailable')
        seconds = args.seconds
        if not math.isfinite(seconds) or not 1 <= seconds <= 3600:
            raise ValueError('Serve duration must be 1..3600 seconds')
        command = [sys.executable, '-I', str(root/'scripts/serve_resident.py'),
                   '--out', str(out), '--seconds', str(seconds)]
        if args.hostlink:
            address = args.hostlink_bind or config.get('hostlink_bind')
            if not address:
                raise ValueError('Explicit hostlink LAN bind required')
            command += ['--hostlink-bind', address]
        return command
    show = args.command == 'show'
    if getattr(args, 'source', 'live') != 'live':
        raise ValueError('Board recorded-IQ replay is not installed. Use the verified PC .zsr replay; no RF started')
    if show and (getattr(args, 'ui', 'v3') != 'v3' or getattr(args, 'isolated', False)):
        raise ValueError('show requires persistent runtime and UI v3')
    bit = root/'overlay'/config['image']/(config['image']+'.bit')
    seconds = getattr(args, 'seconds', None)
    if seconds is not None and (args.command != 'monitor' or not math.isfinite(seconds)
                                or not 1 <= seconds <= 3600):
        raise ValueError('Monitor duration must be 1..3600 seconds')
    ui = ['--ui', getattr(args, 'ui', 'v3')]
    network = []
    if show or getattr(args, 'hostlink', False):
        address = getattr(args, 'hostlink_bind', None) or config.get('hostlink_bind')
        if not address:
            raise ValueError('Configure explicit hostlink LAN bind address')
        network = ['--hostlink', '--hostlink-bind', address]
    ui += network
    common = ui+['--bit', str(bit), '--image', config['image'], '--out', str(out),
              '--seconds', str(seconds if seconds is not None else config['run_seconds']),
              '--bus-phase', str(config['bus_phase'])]
    python = [sys.executable, '-I']
    noise = str(root/'measurements/noise_events')
    if args.command == 'selftest':
        return python+[str(root/'scripts/release_selftest.py'), '--out', str(out)]+ui
    if args.command == 'monitor':
        return python+[str(root/'scripts/run_x5_monitor.py')]+common+[
            '--model', str(root/'ps/models/weights/amc_v2/round_3/model.npz'),
            '--lo', str(config['lo_hz']), '--quality-station-hz', str(config['station_hz']),
            '--noise-events', noise]
    if args.command == 'listen':
        frequency = int(round(args.station_mhz*1e6))
        station = next((s for s in config['stations'] if s['frequency_hz'] == frequency), None)
        if station is None:
            raise ValueError('Use a station from the confirmed stereo station list')
        return python+[str(root/'scripts/run_y3_audio.py')]+common+[
            '--load', '--station-hz', str(frequency), '--lo-hz', str(station['lo_hz']),
            '--volume', str(config['volume_db']), '--stereo-quality-gate', '--noise-events', noise]+(
                ['--speaker-volume', str(config['speaker_volume_db'])]
                if 'speaker_volume_db' in config else [])
    if args.command in ('demo', 'show'):
        if getattr(args, 'group', 'A') != 'A':
            if getattr(args, 'record_audio', None):
                raise ValueError('Playback recording is only applicable to group A')
            if getattr(args, 'antenna_confirmed', None) != 'yes':
                raise ValueError('Demo B requires explicit B-direct antenna confirmation')
            command = python+[str(root/'scripts/demo_b.py'), '--root', str(root),
                '--output', str(out), '--antenna-confirmed', 'yes']
            if getattr(args, 'isolated', False):
                command.append('--isolated')
            if args.segment is not None:
                if args.segment not in (5, 6, 7, 8):
                    raise ValueError('B segments are 7,5,6,8')
                command += ['--segment', str(args.segment)]
            if args.loop:
                command.append('--loop')
            if args.cycles is not None:
                command += ['--cycles', str(args.cycles)]
            return command+ui
        if args.segment is not None and args.segment not in (1, 2, 3, 4):
            raise ValueError('A segments are 1,2,3,4')
        command = [sys.executable, '-I', str(root/'scripts/demo_a.py'),
                   '--root', str(root), '--output', str(out), '--station-hz', str(config['station_hz']),
                   '--lo-hz', str(config['lo_hz']), '--volume', str(config['volume_db'])]
        if getattr(args, 'isolated', False):
            command.append('--isolated')
        recording = getattr(args, 'record_audio', None)
        if show and recording is None:
            recording = out/'playback.wav'
        if recording is not None:
            command += ['--record-audio', str(recording)]
        if args.segment is not None:
            command += ['--segment', str(args.segment)]
        if args.loop:
            command.append('--loop')
        if getattr(args, 'cycles', None) is not None:
            command += ['--cycles', str(args.cycles)]
        return command+ui
    raise ValueError('Demo A/B is not installed yet; implemented in F2/F3, no hardware started')


def postflight(root, config):
    bit = root/'overlay'/config['image']/(config['image']+'.bit')
    result = subprocess.run([sys.executable, '-I', str(root/'scripts/y3_postflight.py'),
                             '--bit', str(bit)], capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError('Stop readback failed: '+result.stderr[-1500:])
    record = json.loads(result.stdout)
    controls = ('gpio_data', 'source_ctrl', 'audio_control')
    if (record.get('status') != 'PASS'
            or any(type(record.get(key)) is not int or record[key] != 0 for key in controls)):
        raise RuntimeError('Stop readback did not pass')
    return record


def stop_release(root, config):
    import fcntl
    state_path = Path(STATE)
    try:
        state = json.loads(state_path.read_text())
    except FileNotFoundError:
        state = None
    if state is not None:
        if not valid_supervisor(state, root):
            raise RuntimeError('Stale or unrelated PID; refusing to signal; inspect state manually')
        os.kill(state['pid'], signal.SIGTERM)
    deadline = time.monotonic()+45
    with open(LOCK, 'a') as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError('Graceful cleanup still pending; no forced kill or power cycle')
                time.sleep(.1)
        record = postflight(root, config)
        write_result(root/'measurements'/('stop_'+uuid.uuid4().hex+'.json'), record)
        print(json.dumps(record), flush=True)


def run_release(root, config, args):
    import fcntl
    tag = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:8]
    out = root/'measurements'/(args.command+'_'+tag)
    command = worker_command(root, config, args, out)  # validate before locks/PL
    (root/'measurements').mkdir(exist_ok=True)
    (root/'logs').mkdir(exist_ok=True)
    record = dict(status='STARTED', command=args.command, worker_args=command, output=str(out))
    child = [None]
    stopping = [False]
    def request_stop(*_):
        stopping[0] = True
        if child[0] is not None and child[0].poll() is None:
            child[0].terminate()
    with open(LOCK, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        state = dict(pid=os.getpid(), start_ticks=process_start(os.getpid()), root=str(root))
        for sig in (signal.SIGTERM, signal.SIGINT):
            signal.signal(sig, request_stop)
        Path(STATE).write_text(json.dumps(state))
        try:
            if stopping[0]:
                raise KeyboardInterrupt('Stopped before worker start')
            with (root/'logs'/(tag+'.log')).open('w') as log:
                # Separate process group ensures Ctrl+C reaches the supervisor,
                # then one graceful TERM reaches the worker's cleanup handler.
                child[0] = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT,
                                             start_new_session=True)
                if stopping[0]:
                    child[0].terminate()
                print('Running '+args.command+'; log '+str(root/'logs'/(tag+'.log')), flush=True)
                code = child[0].wait()
            record['worker_exit_code'] = code
            record['stop_readback'] = postflight(root, config)
            record['status'] = 'PASS' if code == 0 else 'FAIL_WORKER'
        except BaseException as error:
            record.update(status='FAIL', error=repr(error))
            raise
        finally:
            # Do not claim a stopped worker on exceptional supervisor exit.
            if child[0] is not None and child[0].poll() is None:
                child[0].terminate()
                child[0].wait()  # worker retains RF ownership until its finally block
            write_result(root/'measurements'/(tag+'_execution.json'), record)
            Path(STATE).unlink(missing_ok=True)
    return 0 if record['status'] == 'PASS' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    subs = parser.add_subparsers(dest='command', required=True)
    serve = subs.add_parser('serve')
    serve.add_argument('--seconds', type=float, default=3600)
    serve.add_argument('--hostlink', action='store_true')
    serve.add_argument('--hostlink-bind')
    serve.add_argument('--arm-ota', action='store_true', help='Unavailable with S1 replay selection')
    scene = subs.add_parser('scene')
    scene.add_argument('id', choices=('check', 'pano', 'fm', 'listen', 'wifi', 'ota', 'noise', 'perf', 'idle'))
    subs.add_parser('status')
    for name in ('monitor', 'stop', 'selftest', 'verify'):
        sub = subs.add_parser(name)
        if name in ('monitor', 'selftest'):
            sub.add_argument('--ui', choices=('v2', 'v3'), default='v3')
        if name == 'monitor':
            sub.add_argument('--seconds', type=float, help='Bounded monitor run, 1..3600 seconds')
            sub.add_argument('--hostlink', action='store_true')
            sub.add_argument('--hostlink-bind')
    listen = subs.add_parser('listen')
    listen.add_argument('station_mhz', type=float)
    listen.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    listen.add_argument('--hostlink', action='store_true')
    listen.add_argument('--hostlink-bind')
    demo = subs.add_parser('demo', aliases=['show'])
    demo.add_argument('--ui', choices=('v2', 'v3'), default='v3')
    demo.add_argument('--hostlink', action='store_true')
    demo.add_argument('--hostlink-bind')
    demo.add_argument('group', choices=('A', 'B'))
    demo.add_argument('--segment', type=int, choices=range(1, 9))
    demo.add_argument('--antenna-confirmed', choices=('yes',),
                      help='Explicit non-interactive B-direct confirmation')
    demo.add_argument('--isolated', action='store_true', help='Original subprocess/download fallback')
    demo.add_argument('--record-audio', type=Path, help='Explicit playback WAV request; availability reported in evidence')
    demo.add_argument('--loop', action='store_true')
    demo.add_argument('--cycles', type=int, choices=(1, 2, 3))
    demo.add_argument('--source', choices=('live', 'replay'), default='live',
                      help='show source; recorded-IQ board replay is unavailable and rejected before hardware access')
    args = parser.parse_args()
    config = load_config(ROOT/'config.yaml')
    verify_release(ROOT, require_library=args.command != 'verify')
    if args.command == 'verify':
        print('RELEASE_FILES_PASS (board RF library and hardware not checked)')
        return 0
    if args.command in ('demo', 'show') and args.group == 'B' and args.antenna_confirmed is None:
        if not sys.stdin.isatty():
            parser.error('Confirm B-direct antennas using --antenna-confirmed yes')
        confirmation = input('TX1A/RX1A 2.4GHz B-direct antennas ready? Type yes: ')
        if confirmation != 'yes':
            parser.error('Antenna confirmation declined; no RF started')
        args.antenna_confirmed = 'yes'
    if args.command in ('demo', 'show') and args.loop and args.cycles is not None:
        parser.error('--loop and --cycles are mutually exclusive')
    if os.geteuid() != 0:
        parser.error('Use sudo; no automatic privilege escalation')
    os.environ['XILINX_XRT'] = '/usr'
    os.environ['SENTINEL_RF_LIBRARY'] = str(ROOT/'ps/libad9361_pynq/libad9361_pynq.so')
    if args.command in ('scene', 'status'):
        from sentinel.app.resident_control import request
        message = dict(command=args.command)
        if args.command == 'scene':
            message['id'] = args.id
        response = request(message)
        print(json.dumps(response), flush=True)
        return 0 if response.get('ok') else 1
    if args.command == 'stop':
        stop_release(ROOT, config)
        return 0
    return run_release(ROOT, config, args)


if __name__ == '__main__':
    raise SystemExit(main())
