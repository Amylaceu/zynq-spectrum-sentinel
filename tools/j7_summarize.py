"""Summarize immutable J7 evidence without treating partial checks as full acceptance."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT/'tools'), str(ROOT/'src/ps')]
from x2_transport import verified
from sentinel.release_support import sha, write_result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    base = ROOT/'board/measurements'
    checks = base/'j7_checks_r3_retry/result.json'
    recording = base/'j7_final_record_checks/result.json'
    source = verified(checks); failed = verified(recording)
    cards = []
    for entry in source['tests']:
        result, stopped = entry['result'], entry['stop']
        image = checks.parent/entry['screenshot']['file']
        if sha(image) != entry['screenshot']['sha256']:
            raise ValueError('Screenshot differs: '+str(image))
        cards.append(dict(id=entry['id'], status=result['status'],
            elapsed_s=result.get('elapsed_s'), restored=stopped.get('restored'),
            screenshot=image.relative_to(ROOT).as_posix(), sha256=sha(image),
            fps_samples=entry.get('fps_samples'), fps_pass=entry.get('fps_pass')))
    wifi_path = base/'j7_wifi_main_r1/result.json'
    wifi = verified(wifi_path) if wifi_path.is_file() else None
    result = dict(schema='j7_acceptance/1', status='PARTIAL_WITH_RECORDED_FAILURES',
        source='CURRENT_BOARD_CHECKS', cards=cards,
        inputs=[dict(file=p.relative_to(ROOT).as_posix(), sha256=sha(p)) for p in (checks, recording)],
        recording=dict(status='FAIL', controls_visible=False,
            error=failed['rejected_commands'][-1]['result']['error'],
            final_stop_restored=failed['final_stop']['restored'],
            explanation='Three integrated trials overflowed; no completed current recording or listening acceptance.'),
        wifi=dict(status=wifi['status'] if wifi else 'PENDING_ANTENNA_AND_MAIN_UI_ACCEPTANCE',
            historical_standalone_result_is_not_this_acceptance=True,
            result_file=wifi_path.relative_to(ROOT).as_posix() if wifi else None,
            result_sha256=sha(wifi_path) if wifi else None,
            network_records=len(wifi.get('decode', {}).get('result', {}).get('networks', [])) if wifi else None),
        limitations=[
            'F8 single start 3.13 s exceeds 3 s; P90 not established.',
            'F11 full scan about 34 s exceeds 15 s; first tile about 1 s.',
            'F12 FM 4/10 fails 9/10; no reliable live label displayed.',
            'F13 measured recording input, new on-board inference; not new live RF reception.',
            'F0 reports PN status bits and nominal samples, not an actual bit-error counter.'],
        frozen_bit_sha256=sha(ROOT/'board/overlay/sentinel_v2_100m/sentinel_v2_100m.bit'))
    write_result(args.output, result)
    index = args.output.with_suffix('.md')
    lines = ['# 本轮逐卡截图索引', '', '截图来自真实板测；状态及限制以 JSON 汇总为准。', '',
             '| 卡片 | 板端状态 | 停止恢复 | 截图 |', '|---|---|---|---|']
    for card in cards:
        relative = Path(card['screenshot']).relative_to('board/measurements').as_posix()
        lines.append('| %s | %s | %s | [%s](%s) |' %
                     (card['id'], card['status'], card['restored'], card['id'], relative))
    if wifi:
        image = wifi_path.parent/wifi['screenshot']['file']
        if sha(image) != wifi['screenshot']['sha256']:
            raise ValueError('Wi-Fi screenshot differs')
        lines.append('| F14 | %s | %s | [F14](%s) |' %
                     (wifi['status'], wifi.get('stop', {}).get('restored'),
                      image.relative_to(base).as_posix()))
    lines += ['', 'F8 同步录音：FAIL，入口已隐藏。F14 全流程状态以 JSON 为准。',
              'F14_neutral_layout.png 为同轮结果的显示回归，不是新增射频采集；已取消自动热点高亮。', '']
    index.write_text('\n'.join(lines), encoding='utf-8')
    Path(str(index)+'.sha256').write_text(sha(index)+'  '+index.name+'\n', encoding='ascii')
    print('J7_SUMMARY_WRITTEN', len(cards))


if __name__ == '__main__':
    main()
