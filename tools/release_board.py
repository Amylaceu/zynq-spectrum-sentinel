"""Build F1 release locally by default; --deploy explicitly transfers/installs it.

No synthesis, training, RF start, audio playback or boot-service installation.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src/ps'))
from sentinel.release_support import load_config, verify_release, write_result, IMAGE, sha
from sentinel.v_y3 import checked_y3_bundle


def payload_files():
    bundle = ROOT/'board/overlay'/IMAGE
    accepted = checked_y3_bundle(bundle/(IMAGE+'.bit'), image=IMAGE)
    from run_y3_board import verify_v2_inputs
    verify_v2_inputs(accepted)
    files = {}
    for p in sorted((ROOT/'src/ps/sentinel').rglob('*.py')):
        ast.parse(p.read_text(encoding='utf-8'), feature_version=(3, 8))
        files[p.relative_to(ROOT/'src').as_posix()] = p
    for name in ('sentinel.sh', 'release_entry.py', 'release_selftest.py',
                 'install_release.py', 'run_x5_monitor.py', 'run_y3_audio.py',
                 'run_test_display.py', 'demo_a.py', 'demo_b.py', 'y3_postflight.py',
                 'run_f4_panorama.py', 'serve_resident.py', 'serve_features_j6.py'):
        p = ROOT/'board/scripts'/name
        if p.suffix == '.py':
            ast.parse(p.read_text(encoding='utf-8'), feature_version=(3, 8))
        files['scripts/'+name] = p
    files['scripts/j6_golden_cfar.py'] = ROOT/'sim/golden/cfar.py'
    for name in ('in_axis32.hex', 'exp_power_shifted.hex', 'spec_window_bh4.hex'):
        files['data/reference/spectrum/'+name] = ROOT/'data/reference/spectrum'/name
    for name in ('result.json',)+tuple('class_%02d.npz' % i for i in range(10)):
        files['data/f3_measured/'+name] = ROOT/'board/measurements/f3_capture_r1'/name
    for name, target in (('result.json', 'evaluation.json'), ('predictions.npz', 'predictions.npz')):
        files['data/f3_measured/'+target] = ROOT/'board/measurements/f3_evaluation_r1'/name
    model = ROOT/'src/ps/models/weights/amc_v2/round_3/model.npz'
    if sha(model) != '5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935':
        raise ValueError('Frozen model changed')
    files['ps/models/weights/amc_v2/round_3/model.npz'] = model
    f3 = ROOT/'build/f3_library/libad9361_f3.so'
    if f3.is_file():
        from x2_transport import verified
        library = verified(ROOT/'board/measurements/f3_library_r1.json')
        if sha(f3) != library['library_sha256']:
            raise ValueError('F3 library digest mismatch')
        files['ps/libad9361_pynq/libad9361_f3.so'] = f3
        for p in sorted((ROOT/'data/reference/f3_ota').iterdir()):
            files['data/f3_ota/'+p.name] = p
    else:
        raise FileNotFoundError('Retrieve accepted F3 library into build/f3_library before packaging')
    for p in sorted(bundle.iterdir()):
        if p.is_file():
            if p.suffix in ('.bit', '.hwh', '.xsa') and sha(p) != accepted['artifacts_sha256'][p.name]:
                raise ValueError('Frozen artifact changed: '+p.name)
            files['overlay/'+IMAGE+'/'+p.name] = p
    files['config.yaml'] = ROOT/'board/release/config.yaml'
    load_config(files['config.yaml'])
    return files


def build(output):
    import shutil
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    stage = output/'v2'
    files = payload_files()
    hashes = {}
    for name, source in files.items():
        target = stage/name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        hashes[name] = sha(target)
    manifest = dict(schema=1, image=IMAGE, files=hashes,
                    library_source='existing accepted board library; copied and hashed at install',
                    hardware_started=False, historical_failures_preserved=True)
    write_result(stage/'manifest.json', manifest)
    verify_release(stage, require_library=False)
    archive = output/'release_v2.tar.gz'
    with tarfile.open(archive, 'x:gz') as tar:
        for p in sorted(stage.rglob('*')):
            if p.is_file():
                tar.add(p, arcname=p.relative_to(stage).as_posix(), recursive=False)
    write_result(output/'package.json', dict(status='LOCAL_PACKAGE_PASS_BOARD_PENDING',
                 created_utc=datetime.now(timezone.utc).isoformat(), archive=archive.name,
                 archive_sha256=sha(archive), files=len(files), manifest_sha256=sha(stage/'manifest.json')))
    return archive


def deploy(archive, replace=False, password=None, candidate=None):
    from x2_transport import Transport, REMOTE, PYTHON
    transport = Transport(password=password) if password is not None else Transport()
    digest = sha(archive)
    remote_archive = REMOTE+'/setup/f1_'+digest+'.tar.gz'
    installer = REMOTE+'/setup/f1_install_'+digest+'.py'
    transport.copy(archive, transport.target+':'+remote_archive)
    transport.copy(ROOT/'board/scripts/install_release.py', transport.target+':'+installer)
    # Verify the separately transferred installer as well as the payload archive.
    if transport.ssh(['sha256sum', installer]).split()[0] != sha(ROOT/'board/scripts/install_release.py'):
        raise ValueError('Remote installer checksum mismatch')
    command = [PYTHON, '-I', installer, '--archive', remote_archive, '--sha256', digest]
    if replace:
        command.append('--replace')
    if candidate:
        if candidate not in ('i1_r1', 'i1_r2', 'i1_r3', 'audio_volume_r1', 'i2_r1', 'i2_r2', 'i2_r3', 'j6_r1', 'j6_r2', 'j6_r3', 'j6_dma_r1', 'j6_audio_r1', 'j6_audio_r2', 'j6_audio_r3', 'j7_r1', 'j7_r2', 'j7_r3', 'j7_final', 'j7_rec3_r1', 'j8_r1', 'j8_r2', 'j8_r3', 'j8_final'):
            raise ValueError('Invalid isolated candidate name')
        command += ['--candidate', candidate]
    result = json.loads(transport.ssh(command, privileged=True, timeout=120))
    if result.get('archive_sha256') != digest or result.get('status') != 'INSTALLED_HASH_VERIFIED':
        raise ValueError('Installer did not confirm exact payload')
    write_result(archive.parent/'deployment.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True, help='New local package directory')
    parser.add_argument('--deploy', action='store_true')
    parser.add_argument('--replace', action='store_true')
    parser.add_argument('--sudo-stdin', action='store_true',
                        help='Read one sudo password line from stdin; never write it to evidence')
    args = parser.parse_args()
    if args.replace and not args.deploy:
        parser.error('--replace requires --deploy')
    if args.sudo_stdin and not args.deploy:
        parser.error('--sudo-stdin requires --deploy')
    password = sys.stdin.readline().rstrip('\r\n') if args.sudo_stdin else None
    if args.sudo_stdin and not password:
        parser.error('Missing sudo credential on stdin')
    archive = build(args.output)
    print(str(archive), flush=True)
    if args.deploy:
        print(json.dumps(deploy(archive, args.replace, password=password), indent=2), flush=True)


if __name__ == '__main__':
    main()
