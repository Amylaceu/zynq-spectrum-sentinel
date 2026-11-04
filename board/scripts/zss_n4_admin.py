#!/usr/bin/python3 -I
"""Root-owned N4 command entry point; project Python remains trusted code.

Installed manually by the board owner. No shell expressions or arbitrary
Python commands are accepted. This is a development convenience, not a
security boundary against someone who can modify the project repository.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path('/home/xilinx/sentinel')
PYTHON = '/usr/local/share/pynq-venv/bin/python3'
BUNDLE = ROOT / 'overlay/sentinel_v1'


def checked_bundle():
    acceptance = json.loads((BUNDLE / 'acceptance.json').read_text())
    if acceptance.get('status') != 'PASS':
        raise RuntimeError('PC implementation acceptance has not passed')
    hashes = acceptance['artifacts_sha256']
    for suffix in ('bit', 'hwh', 'xsa'):
        path = BUNDLE / ('sentinel_v1.' + suffix)
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if hashes.get(path.name, '').lower() != actual:
            raise RuntimeError('Accepted artifact hash mismatch: ' + path.name)
    return acceptance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('health', 'selftest', 'monitor', 'bench'))
    parser.add_argument('--tag', default='manual')
    parser.add_argument('--source', choices=('test', 'replay', 'rf'), default='test')
    parser.add_argument('--load-overlay', action='store_true',
                        help='Explicitly load the accepted image for monitor after a reboot')
    parser.add_argument('--phase', type=int, choices=(25, 12, 8, 6, 4, 3, 2), default=3)
    parser.add_argument('--seconds', type=int, default=120)
    parser.add_argument('--lo', type=int, default=98000000)
    parser.add_argument('--rate', type=int, choices=(3840000, 24576000), default=3840000)
    args = parser.parse_args()
    if args.load_overlay and args.action != 'monitor':
        parser.error('--load-overlay is only supported by monitor; selftest already loads explicitly')
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,48}', args.tag):
        parser.error('Invalid output tag')
    if not 1 <= args.seconds <= 3600 or not 70000000 <= args.lo <= 6000000000:
        parser.error('Invalid duration or RX frequency')
    if os.geteuid() != 0:
        parser.error('Run through sudo /usr/local/sbin/zss-n4-admin')
    if args.action == 'health':
        print(json.dumps({'status': 'ready', 'uid': os.geteuid(),
                          'python_exists': Path(PYTHON).is_file(),
                          'root': str(ROOT), 'hardware_accessed': False}))
        return
    checked_bundle()
    output = 'measurements/n4_%s_%s.json' % (args.action, args.tag)
    if (ROOT / output).exists():
        parser.error('Preserve existing measurement; choose a new --tag')
    if args.action == 'selftest':
        command = [PYTHON, '-s', '-m', 'sentinel.app.selftest_v1',
                   '--source', 'test', '--load-overlay', '--out', output]
    elif args.action == 'monitor':
        command = [PYTHON, '-s', '-m', 'sentinel.app.monitor',
                   '--source', args.source, '--lo', str(args.lo),
                   '--rate', str(args.rate), '--bus-phase', str(args.phase),
                   '--seconds', str(args.seconds), '--out', output]
        if args.load_overlay:
            command.append('--load-overlay')
    else:
        command = [PYTHON, '-s', str(ROOT / 'scripts/bench_lcd.py'),
                   '--phase', str(args.phase), '--seconds', '10',
                   '--hold-seconds', '600', '--out', output]
    environment = {'HOME': '/root', 'USER': 'root', 'LOGNAME': 'root',
                   'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                   'PYTHONPATH': str(ROOT / 'ps') + ':' + str(ROOT),
                   'PYTHONNOUSERSITE': '1', 'XILINX_XRT': '/usr',
                   'LANG': 'C.UTF-8'}
    os.chdir(str(ROOT))
    os.execve(PYTHON, command, environment)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('N4_ADMIN_REFUSED: ' + str(error), file=sys.stderr)
        sys.exit(1)
