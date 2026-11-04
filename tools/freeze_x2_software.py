"""Freeze tested X2 board/host software separately from the active HDL build."""
import argparse
import ast
import re
from datetime import datetime, timezone

from deploy_x2 import NEW
from x2_transport import ROOT, sha, write_evidence

TOOLS = ('tools/deploy_x2.py', 'tools/run_x2_board.py', 'tools/x2_transport.py',
         'tools/analyze_x2.py', 'tools/accept_x2_selftest.py', 'tools/freeze_x2_software.py')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--test-log', required=True)
    args = parser.parse_args()
    testlog = ROOT/args.test_log
    test_text = testlog.read_text()
    counts = re.findall(r'\b(\d+) passed\b', test_text)
    if not counts or int(counts[-1]) < 228 or re.search(r'\b(failed|error|errors)\b', test_text.lower()):
        raise ValueError('Expected complete regression log, at least 228 passing tests and no errors')
    files = set(NEW+TOOLS)
    files |= {p.relative_to(ROOT).as_posix() for directory in
              ('src/ps/tests', 'tools/tests') for p in (ROOT/directory).glob('*x2*.py')}
    board_python = [ROOT/n for n in NEW if n.endswith('.py')]
    for path in board_python:
        ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path), feature_version=(3, 8))
    output = ROOT/('docs/x2_software_predeployment_r%d.json' % args.attempt)
    write_evidence(output, dict(status='READY_FOR_DEPLOYMENT',
        recorded_at_pc=datetime.now(timezone.utc).isoformat(), attempt=args.attempt,
        scope='PC regression and board Python 3.8 syntax; no X2 hardware acceptance',
        regression_log=args.test_log, regression_log_sha256=sha(testlog),
        board_python_syntax='3.8',
        source_sha256={n: sha(ROOT/n) for n in sorted(files)}))
    print('X2_SOFTWARE_FROZEN files='+str(len(files)))


if __name__ == '__main__':
    main()
