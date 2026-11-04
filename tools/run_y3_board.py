"""Isolated, bounded Y3 receive/audio deployment with immutable evidence.

No transmit operations. A routed PASS image and explicit configuration-A
authorization are mandatory. This runner never marks human listening as passed.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tarfile

from freeze_y3_build import verify
from run_x5_board import CHECK, INSTALL, LIB_SHA
from x2_transport import ROOT, REMOTE, PYTHON, OPTIONS, Transport, sha, verified, write_evidence
from x5_transfer import retrieve_files


def verify_v2_inputs(acceptance):
    """Bind deployment to the reviewed implementation inputs, before any SSH."""
    inputs = acceptance.get('build_input_sha256')
    if not isinstance(inputs, dict) or not inputs:
        raise ValueError('Missing audited v2 build input manifest')
    for name, digest in inputs.items():
        if (not isinstance(name, str) or not name or Path(name).is_absolute()
                or not isinstance(digest, str)
                or re.fullmatch(r'[0-9a-f]{64}', digest) is None):
            raise ValueError('Invalid v2 build input manifest entry')
        path = (ROOT/name).resolve()
        if (not path.is_relative_to(ROOT.resolve()) or not path.is_file()
                or sha(path) != digest):
            raise ValueError('v2 input changed after implementation: '+name)


def payload_files(attempt, image='sentinel_y3'):
    if image not in ('sentinel_y3', 'sentinel_v2_100m'):
        raise ValueError('Unsupported audio image')
    bundle = ROOT/'board/overlay'/image
    acceptance = verified(bundle/'acceptance.json')
    if acceptance.get('status') != 'PASS' or acceptance.get('image') != image:
        raise ValueError('Require audited Y3 audio image: '+image)
    if image == 'sentinel_y3':
        prebuild, _ = verify(attempt)
        if acceptance.get('prebuild_manifest_sha256') != sha(prebuild):
            raise ValueError('Require audited Y3 image matching unchanged prebuild inputs')
    else:
        sys.path.insert(0, str(ROOT/'src/ps'))
        from sentinel.v_y3 import checked_y3_bundle
        checked_y3_bundle(bundle/(image+'.bit'), image=image)
        verify_v2_inputs(acceptance)
    files = {}
    if acceptance.get('deployment_policy') == 'development_nonnegative_v1':
        for name in ('development_review.json', 'development_review.json.sha256'):
            files['overlay/'+image+'/'+name] = bundle/name
    for path in sorted((ROOT/'src/ps/sentinel').rglob('*.py')):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        files[path.relative_to(ROOT/'src').as_posix()] = path
    for name in ('run_y3_audio.py', 'y3_postflight.py'):
        path = ROOT/'board/scripts'/name
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 8))
        files['scripts/'+name] = path
    for suffix in ('bit', 'hwh', 'xsa'):
        path = bundle/(image+'.'+suffix)
        if sha(path) != acceptance['artifacts_sha256'].get(path.name):
            raise ValueError('Accepted image changed: '+path.name)
        files['overlay/'+image+'/'+path.name] = path
    for name in ('acceptance.json', 'acceptance.json.sha256', 'sha256.txt'):
        files['overlay/'+image+'/'+name] = bundle/name
    return files


def evaluate(result, seconds, preflight, postflight):
    samples = result.get('samples', [])
    end_audio = result.get('audio_before_stop', {})
    checks = dict(
        completed=result.get('status') == 'completed',
        duration=result.get('elapsed_total_s', 0) >= seconds,
        sample_count=len(samples) >= max(1, seconds-4),
        fifo_clean=bool(samples) and all(
            not s['audio']['iq_overflow'] and not s['audio']['pcm_full']
            and s['audio']['underflows'] == 0 and s['audio']['playing'] for s in samples),
        display=bool(samples) and min(s['display_fps'] for s in samples) >= 30,
        final_interval_clean=bool(end_audio)
            and end_audio.get('iq_overflow') is False
            and end_audio.get('pcm_full') is False
            and end_audio.get('underflows') == 0
            and end_audio.get('playing') is True
            and result.get('channel_health_before_stop') == 0
            and result.get('pfb_capture_status_before_stop', -1) & 0x1f0 == 0,
        temperature=bool(samples) and all(
            isinstance(s.get('temperature_c'), (int, float))
            and 30 <= s['temperature_c'] <= 85 for s in samples),
        clock_counts=bool(samples) and all(
            47000 <= s.get('audio_frame_rate_hz', 0) <= 49000
            and 47000 <= s.get('pcm_sample_rate_hz', 0) <= 49000
            and s.get('channel_health', -1) == 0
            and s.get('pfb_capture_status', -1) & 0x1f0 == 0 for s in samples),
        rf_muted=bool(samples) and all(s['tx_attenuation_db'] == [89.75, 89.75]
                                       and s['rx_rssi_dbm'] <= -30 for s in samples),
        codec_stopped=result.get('final_codec_muted') is True
                      and not result.get('safe_stop_errors'),
        source_stopped=postflight.get('status') == 'PASS'
                       and postflight.get('audio_control') == 0,
        same_boot=preflight.get('boot_id') == postflight.get('boot_id')
                  == result.get('boot_id'),
    )
    if result.get('stereo_quality_gate'):
        # IQ acquisition and IIC mute/unmute add variable blocking time. Bound
        # the actual observation gaps instead of assuming exactly 1Hz polling.
        times = [s.get('elapsed_s') for s in samples]
        duration = result.get('elapsed_total_s')
        finite_times = (bool(times) and all(type(t) in (int, float)
                        and math.isfinite(t) for t in times)
                        and type(duration) in (int, float) and math.isfinite(duration))
        gaps = ([times[0]]+[b-a for a,b in zip(times, times[1:])]
                +[duration-times[-1]]) if finite_times else []
        checks['sample_count'] = len(samples) >= max(1, int(seconds/2)-1)
        checks['telemetry_coverage'] = bool(gaps) and all(0 < gap <= 2 for gap in gaps)
        audible = result.get('audible_seconds')
        checks['audible_coverage'] = (type(audible) in (int, float)
                                      and math.isfinite(audible)
                                      and type(duration) in (int, float)
                                      and math.isfinite(duration)
                                      and .8*seconds <= audible <= duration)
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--image', choices=('sentinel_y3', 'sentinel_v2_100m'),
                        default='sentinel_y3')
    parser.add_argument('--implementation-attempt', type=int, choices=(1, 2, 3), default=1)
    parser.add_argument('--confirm-configuration-a', action='store_true', required=True)
    parser.add_argument('--sudo-stdin', action='store_true')
    parser.add_argument('--seconds', type=int, choices=(30, 300), default=300)
    parser.add_argument('--volume', type=float, default=-21)
    parser.add_argument('--stereo-quality-gate', action='store_true',
                        help='Separate diagnostic series; never overwrites the three original FM trials')
    parser.add_argument('--bus-phase', type=int, choices=(2, 3), default=3,
                        help='SSD1963 write-bus phase; 3 retains the prior default')
    parser.add_argument('--station-hz', type=int, default=95800000)
    parser.add_argument('--lo-hz', type=int,
                        help='Default station+480kHz places FM at PFB channel 14 center')
    parser.add_argument('--preflight-bit', required=True,
                        help='Exact path of the currently loaded, accepted v1d/Y3 image')
    args = parser.parse_args()
    lo_hz = args.station_hz + 480000 if args.lo_hz is None else args.lo_hz
    # Validate conservative analog level before deploying anything.
    sys.path.insert(0, str(ROOT/'src/ps'))
    from sentinel.audio_y3 import CodecOutputs
    CodecOutputs.volume_code(args.volume)
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential')
    tag = ('y3_audio_r%d' if args.image == 'sentinel_y3' else 'y3_v2_audio_r%d') % args.attempt
    if args.stereo_quality_gate:
        tag += '_quality'
    output = ROOT/'board/measurements'/tag
    start = output.with_name(tag+'_start.json')
    receipt = output.with_name(tag+'_execution.json')
    log = ROOT/'logs'/(tag+'_board.log')
    archive = ROOT/'build'/(tag+'_runtime.tar.gz')
    if any(p.exists() for p in (output, start, receipt, log, archive)):
        raise FileExistsError('Preserve prior Y3 attempt')
    files = payload_files(args.implementation_attempt, image=args.image)
    manifest = {name: sha(path) for name, path in files.items()}
    stage = REMOTE+'/setup/'+tag+'_runtime'
    with tarfile.open(archive, 'x:gz') as tar:
        for name, path in files.items():
            tar.add(path, arcname=name, recursive=False)
    transport = Transport(password)
    remote_archive = stage+'.tar.gz'
    transport.ssh(['test', '!', '-e', stage])
    transport.ssh(['test', '!', '-e', remote_archive])
    transport.copy(archive, transport.target+':'+remote_archive)
    transport.ssh([PYTHON, '-I', '-c', INSTALL], payload=json.dumps(dict(
        root=stage, archive=remote_archive, archive_sha256=sha(archive), files=manifest)))
    check = CHECK.replace('sentinel.app.monitor_x5', 'sentinel.v_y3')
    dependencies = json.loads(transport.ssh([PYTHON, '-I', '-c', check],
        payload=json.dumps(dict(root=stage, files=manifest))))

    def stopped(bit):
        return json.loads(transport.ssh(
            [PYTHON, '-I', stage+'/scripts/y3_postflight.py', '--bit', bit],
            privileged=True))

    preflight = stopped(args.preflight_bit)
    if preflight['status'] != 'PASS':
        raise ValueError('Prior receive/audio process has not stopped')
    library = REMOTE+'/ps/libad9361_pynq/libad9361_pynq.so'
    if transport.ssh(['sha256sum', library]).split()[0] != LIB_SHA:
        raise ValueError('RF library differs from audited baseline')
    bit = stage+'/overlay/'+args.image+'/'+args.image+'.bit'
    remote_output = stage+'/measurements/'+tag
    command = ['timeout', '--signal=TERM', '--kill-after=15s', str(args.seconds+60)+'s',
               PYTHON, '-I', stage+'/scripts/run_y3_audio.py', '--bit', bit,
               '--load', '--image', args.image, '--out', remote_output, '--station-hz', str(args.station_hz),
               '--lo-hz', str(lo_hz),
               '--seconds', str(args.seconds), '--volume', str(args.volume),
               '--bus-phase', str(args.bus_phase)]
    if args.stereo_quality_gate:
        command.append('--stereo-quality-gate')
    record = dict(status='STARTED', started_at_pc=datetime.now(timezone.utc).isoformat(),
                  configuration='A', image=args.image, RF_TX_requested=False, human_listening='PENDING',
                  station_hz=args.station_hz, lo_hz=lo_hz, bus_phase=args.bus_phase,
                  stereo_quality_gate=args.stereo_quality_gate,
                  tuning_note='Y3-only channel centering; does not alter prior Y2 measurements',
                  scope='Y3 bounded playback only; subjective audio remains a human gate',
                  remote_root=stage, command=command, preflight=preflight,
                  deployment_sha256=manifest, archive_sha256=sha(archive),
                  runner_sha256=sha(Path(__file__)), dependencies=dependencies)
    write_evidence(start, record)
    print('Y3_START '+tag+'; onboard speaker, OUT1 also enabled; keep headphones off', flush=True)
    try:
        with log.open('xb') as stream:
            process = subprocess.run(['ssh', *OPTIONS, transport.target,
                shlex.join(transport.privileged(command))],
                input=(password+'\n').encode() if password else b'',
                stdout=stream, stderr=subprocess.STDOUT, timeout=args.seconds+120)
        record['ssh_exit_code'] = process.returncode
    except Exception as error:
        record['execution_error'] = str(error)
    finally:
        record['status'] = 'FAIL_EXECUTION'
        try:
            record['postflight'] = stopped(bit)
        except Exception as error:
            record['postflight_error'] = str(error)
        try:
            output.mkdir(exist_ok=False)
            retrieve_files(transport.target, remote_output,
                           ['result.json', 'result.json.sha256'], output, OPTIONS)
            result = verified(output/'result.json')
            record['result_sha256'] = sha(output/'result.json')
            record['library_sha256_after'] = transport.ssh(['sha256sum', library]).split()[0]
            record['checks'] = evaluate(result, args.seconds, preflight, record.get('postflight', {}))
            transport.ssh([PYTHON, '-I', '-c', check],
                          payload=json.dumps(dict(root=stage, files=manifest)))
            if (record.get('ssh_exit_code') == 0 and all(record['checks'].values())
                    and record['library_sha256_after'] == LIB_SHA):
                record['status'] = ('PASS_QUANTITATIVE_AWAITING_HUMAN' if args.seconds == 300
                                    else 'PASS_SMOKE_NOT_5MIN')
        except Exception as error:
            record['retrieval_or_postflight_error'] = str(error)
        record['ended_at_pc'] = datetime.now(timezone.utc).isoformat()
        record['log_sha256'] = sha(log) if log.exists() else None
        write_evidence(receipt, record)
        print('Y3_ENDED '+record['status'], flush=True)
    return 0 if record['status'].startswith('PASS') else 1


if __name__ == '__main__':
    raise SystemExit(main())

