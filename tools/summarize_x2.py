"""Summarize independently accepted fast-path runs; never upgrade a screen."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from analyze_x2 import evaluate
from run_x2_board import accepted_dependency
from x2_transport import ROOT, sha, verified, write_evidence

RATES = (7680000, 15360000, 24576000, 30720000)


def accepted_run(stem, deployment_digest, *, screening):
    execution_path, execution = accepted_dependency(
        stem, deployment_digest, screening=screening)
    prefix = execution_path.name.removesuffix('_execution.json')
    measurement_path = execution_path.with_name(prefix+'.json')
    acceptance_path = execution_path.with_name(prefix+'_acceptance.json')
    measurement = verified(measurement_path)
    metrics = evaluate(measurement, screening=screening)
    if bool(execution.get('screening', False)) != screening:
        raise ValueError('Execution scope mismatch: '+stem)
    if verified(acceptance_path)['metrics'] != metrics:
        raise ValueError('Recomputed metrics differ: '+stem)
    return dict(metrics=metrics, boot_id=measurement['boot_id'],
                measurement=measurement_path.relative_to(ROOT).as_posix(),
                measurement_sha256=sha(measurement_path),
                execution_sha256=sha(execution_path),
                acceptance_sha256=sha(acceptance_path))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--deployment-attempt', type=int, choices=(1, 2, 3), required=True)
    parser.add_argument('--rate', type=int, choices=RATES, required=True,
                        help='Highest sustained-qualified rate')
    parser.add_argument('--visual', type=Path, required=True,
                        help='Separate hashed human confirmation tied to the sustained run')
    args = parser.parse_args()
    if args.rate < 24576000:
        raise ValueError('Below X2 minimum target; record FAIL separately')
    output = ROOT/'board/measurements/x2_acceptance_summary.json'
    markdown = ROOT/'docs/x2_acceptance_summary.md'
    if output.exists() or markdown.exists():
        raise FileExistsError('Preserve existing X2 summary')
    deployment_path = ROOT/('board/measurements/x2_deployment_r%d.json' % args.deployment_attempt)
    deployment = verified(deployment_path)
    if deployment['status'] != 'PASS_DEPLOYMENT':
        raise ValueError('Accepted deployment required')
    digest = sha(deployment_path)
    implementation_path = ROOT/'board/overlay/sentinel_v1c/acceptance.json'
    implementation = verified(implementation_path)
    if (implementation['status'] != 'PASS'
            or deployment['implementation_acceptance_sha256'] != sha(implementation_path)):
        raise ValueError('Implementation/deployment mismatch')
    screens = [accepted_run('x2_screen_'+str(rate), digest, screening=True)
               for rate in RATES if rate <= args.rate]
    sustained = accepted_run('x2_monitor_'+str(args.rate), digest, screening=False)
    accepted_dependency('x2_selftest', digest)
    visual_path = args.visual.resolve()
    visual = verified(visual_path)
    if (visual['status'] != 'PASS_HUMAN_VISUAL'
            or visual['measurement_sha256'] != sustained['measurement_sha256']
            or visual['rate_hz'] != args.rate or visual['boot_id'] != sustained['boot_id']):
        raise ValueError('Human confirmation does not match sustained run')
    limits = [
        'Lower rates were screened for 60 seconds, not sustained-qualified for 600 seconds.',
        'User requested shorter tests; agent selected four screens plus highest-rate sustained test.',
        'FRAME_DROP is intentional detector frame decimation, distinct from SAMPLE_DROP.',
        'Configured RF bandwidth is not a calibrated analog passband measurement.',
        'X1 remains FAIL; X2 throughput does not establish all-station detection accuracy.',
        'This finite test does not establish full-temperature or long-term stability.',
    ]
    result = dict(status='PASS_FAST_PATH', recorded_at_pc=datetime.now(timezone.utc).isoformat(),
        highest_sustained_rate_hz=args.rate, original_four_rate_600s_plan_complete=False,
        deployment_sha256=digest, implementation_sha256=sha(implementation_path),
        simulation_sha256=sha(ROOT/'sim/results/x2_simulation_acceptance.json'),
        implementation_timing=implementation['final_timing'],
        implementation_resources=implementation['resources'],
        screens=screens, sustained=sustained, visual_sha256=sha(visual_path),
        limitations=limits, summarizer_sha256=sha(Path(__file__)))
    lines = ['# X2 快速路径验收汇总', '',
             '状态：PASS_FAST_PATH。低档为60秒筛选，最高通过档为600秒持续验收；原四档各600秒未全部执行。', '',
             '| 采样率 MSPS | 时长 s | 范围 | SAMPLE_DROP | FRAME_DROP | 中位 fps |',
             '|---:|---:|---|---:|---:|---:|']
    for run in screens+[sustained]:
        m = run['metrics']
        lines.append('| %.3f | %.3f | %s | %d | %d | %.3f |' % (
            m['rate_hz']/1e6, m['elapsed_s'], m['qualification'],
            m['sample_drop'], m['frame_drop'], m['median_display_fps']))
    lines += ['', '整机时序：`'+json.dumps(implementation['final_timing'])+'`。', '',
              '资源：`'+json.dumps(implementation['resources'])+'`。', '',
              '各测量JSON、独立验收和SHA256关联见 `board/measurements/x2_acceptance_summary.json`。', '',
              '限制：', '']+['- '+limit for limit in limits]
    write_evidence(output, result)
    markdown.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    print('X2_FAST_PATH_SUMMARY_PASS')


if __name__ == '__main__':
    main()
