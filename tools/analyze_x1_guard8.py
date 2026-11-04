"""Audit both immutable guard=8 windows using unchanged X1 acceptance metrics."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from run_x1_board import ROOT, sha, write_evidence
from run_x1_guard8 import verified, FILES, FROZEN
from analyze_x1_board import summarize
from analyze_x1_frozen_replay import frequency_summary


def main():
    frozen = verified(FROZEN)
    for name, digest in frozen['source_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Frozen code changed: '+name)
    deployment = verified(ROOT/'board/measurements/x1_guard8_deploy_execution.json')
    if deployment['status'] != 'PASS_DEPLOYMENT':
        raise ValueError('Deployment did not pass')
    records, results, evidence, supplement = {}, {}, {}, {}
    for mode, lo in (('capacity', 98000000), ('station', 96400000)):
        path = ROOT/'board/measurements'/('x1_guard8_'+mode+'.json')
        receipt_path = path.with_name(path.stem+'_execution.json')
        data, receipt = verified(path), verified(receipt_path)
        if (receipt['status'] != 'PASS_EXECUTION' or receipt['result_sha256'] != sha(path)
                or receipt['source_sha256'] != deployment['source_sha256']
                or receipt['preflight']['status'] != 'PASS' or receipt['postflight']['status'] != 'PASS'
                or data['boot_id'] != receipt['boot_id_before']
                or data['boot_id'] != receipt['postflight']['boot_id']
                or sha(ROOT/receipt['log']) != receipt['log_sha256']):
            raise ValueError('Execution/evidence association failed: '+mode)
        for name, digest in receipt['source_sha256'].items():
            if sha(ROOT/name) != digest:
                raise ValueError('Trial source changed: '+name)
        if data['configuration']['guard'] != 8 or data['configuration_readback']['0x8'] != 8:
            raise ValueError('Guard8 was not applied/read back')
        records[mode] = data
        results[mode] = summarize(data, lo)
        supplement[mode] = frequency_summary(data['samples'], data['actual_lo_hz'],
                                              data['actual_rate_hz'], 95450000)
        evidence[mode] = dict(path=path.relative_to(ROOT).as_posix(), sha256=sha(path),
                              receipt_sha256=sha(receipt_path), log_sha256=receipt['log_sha256'])
    if (records['capacity']['configuration'] != records['station']['configuration']
            or records['capacity']['boot_id'] != records['station']['boot_id']
            or records['capacity']['artifacts_sha256'] != records['station']['artifacts_sha256']):
        raise ValueError('Windows must share configuration, boot and artifacts')
    acceptance = verified(ROOT/'board/overlay/sentinel_v1b/acceptance.json')
    if acceptance['status'] != 'PASS' or records['station']['artifacts_sha256'] != acceptance['artifacts_sha256']:
        raise ValueError('Hardware acceptance association failed')
    for name, digest in acceptance['artifacts_sha256'].items():
        if sha(ROOT/'board/overlay/sentinel_v1b'/name) != digest:
            raise ValueError('Hardware artifact changed')
    passed = (results['capacity']['capacity_alarm_rate_upper_bound_all_attempts'] < .05
              and results['station']['station_detection_rate_all_attempts'] >= .8)
    result = dict(status='PASS_METRICS' if passed else 'FAIL_METRICS',
                  recorded_at_pc=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                  scope='One user-authorized additional trial; human visual acceptance separate',
                  original_three_rounds_preserved=True, original_frequency_hz=95800000,
                  x1=results, supplementary_9545=supplement, evidence=evidence,
                  source_sha256={name: sha(ROOT/name) for name in (
                      *FILES, 'tools/run_x1_guard8.py', 'tools/analyze_x1_guard8.py',
                      'tools/analyze_x1_board.py', 'tools/analyze_x1_frozen_replay.py')})
    write_evidence(ROOT/'board/measurements/x1_guard8_metrics.json', result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
