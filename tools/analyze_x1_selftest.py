"""Reuse the independent N4 raw archive verifier for the X1 artifact pair."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
from zoneinfo import ZoneInfo

from analyze_v1_selftest import verify

ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt',type=int,choices=(1,2,3),required=True)
    args=parser.parse_args()
    result_path=ROOT/('board/measurements/x1_selftest_r%d.json'%args.attempt)
    output=result_path.with_name(result_path.stem+'_acceptance.json')
    if output.exists() or Path(str(output)+'.sha256').exists():
        parser.error('Preserve prior evidence')
    result=verify(result_path,ROOT/'data/reference/spectrum',ROOT/'board/overlay/sentinel_v1b/sentinel_v1b.bit')
    result.update(scope='X1 finite tone/replay verification only; RF metrics and visual acceptance separate',
                  recorded_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat())
    output.write_text(json.dumps(result,indent=2)+chr(10),encoding='utf-8')
    Path(str(output)+'.sha256').write_text(hashlib.sha256(output.read_bytes()).hexdigest()+'  '+output.name+chr(10),encoding='ascii')
    print('X1_FINITE_ARCHIVE_ACCEPTANCE_PASS')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
