"""Build the J-v4 coverage ledger and pin source SHA256 without touching hardware.

UI access, offline validation and true-board acceptance are separate statuses.
This tool never upgrades a pending hardware feature to PASS.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT/'tools/host'), str(ROOT/'src/ps'), str(ROOT)]

from sentinel_host.catalog import FEATURES, PAGES, sources_for
from sentinel_host.evidence import record_file


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    Path(str(path)+'.sha256').write_text(hashlib.sha256(path.read_bytes()).hexdigest()+'  '+path.name+'\n')


def build(update_zip=None):
    if update_zip:
        # Compare only documented members. User edits and J0 records must survive.
        members = []
        with ZipFile(update_zip) as archive:
            for name in archive.namelist():
                if name.endswith('/'):
                    continue
                path = ROOT/name
                if Path(name).is_absolute() or '..' in Path(name).parts or ROOT not in path.resolve().parents:
                    raise ValueError('Unsafe update member')
                content = archive.read(name)
                same = path.is_file() and content == path.read_bytes()
                members.append(dict(path=name, bytes=len(content), matches_current=same,
                                    sha256=hashlib.sha256(content).hexdigest()))
        write_json(ROOT/'board/measurements/j_v4_update.json', dict(
            schema='j_v4_update/1', archive_sha256=hashlib.sha256(Path(update_zip).read_bytes()).hexdigest(),
            members=members, all_identical=all(m['matches_current'] for m in members),
            action='NO_OVERWRITE_REQUIRED', hardware_started=False))
    ledger = ROOT/'report/host_coverage.md'
    lines = ['# 上位机成果覆盖核对（J 修订 v4）', '',
             '52 项主成果含 49a–g、52a–f，共 63 个独立入口。十页候选源码已接入入口；'
             '入口可点击不代表实时功能已经验收。当前仅完成离线布局和命令门禁开发，尚未发布正式 v3。', '',
             '候选入口：`.venv/Scripts/python.exe tools/host/product.py`。旧版默认入口和 exe 保留。', '',
             '来源摘要清单：`board/measurements/j_v4_sources.json`（附 SHA256）。有原始摘要的文件核对原始摘要；'
             '无原始摘要的文件只建立当前快照，不宣称补做原测量校验。原测量日期缺失时不使用文件复制时间替代。', '',
             '离线截图：`report/figures/host_j_v4_r3/`。全部为合成界面预览，不是新真板验收。', '',
             '| 编号 | 页面 | 操作按键 | 当前展示方式 | 来源模式 | 验证 / 后续条件 |',
             '|---|---|---|---|---|---|']
    local = {'9': '实测全景 / SHA256 载入', '13': '本地导航（不启动射频）',
             '18': '实时目标选择（待真板）', '22': '本地 IQ 导出（待数据验收）',
             '28': 'WAV 回放 / 波形 / PC 播放', '49c': 'WAV 回放 / 波形 / PC 播放',
             '49a': 'ZSR 回放 / 暂停 / 0.5/1/2倍速；定位待接入',
             '49g': '本地会话录制与导出', '52a': '成果索引跳转（不启动射频）'}
    for feature in FEATURES:
        mode = ('实时常驻 '+feature.scene+'（候选 UI 待板测）') if feature.scene else local.get(feature.key, '实测资料 / 工程资料浏览')
        status = ('已复用现有场景；本轮真板 3 次就绪/P90 未测' if feature.scene else
                  '入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测')
        if feature.key == '42':
            status = 'INCONCLUSIVE；不能识别热点；保留原始对照结论'
        lines.append('| %s | %s | %s | %s | %s | %s |' % (
            feature.key, PAGES[feature.page], feature.action, mode,
            '<br>'.join('`'+s+'`' for s in feature.sources), status))
    lines += ['', '## 仍需执行的验收与接入', '',
              '- J1：正式 v3、可配置 7200 秒、一键入口及完整发布校验尚待完成；v2 不覆盖。',
              '- J2：本轮十页预览须用户确认后才新布局连真板；十页逐项操作、30 分钟循环和冷启动未测。',
              '- J3/J4：三音、F3 原始 IQ 回放和推理、参考全景补扫及恢复读回尚待集成。',
              '- 其余新常驻场景：RX BIST、选台、质量门控演示、参数演示、PL 回放/注噪、CPU/推理计时、自动 A/B 未接入；不发送未实现的命令。',
              '- 回放中心：SigMF 黄金模型复算/FM 解调、ZSR 拖动定位、全景逐段动画、F3 逐类回放及语谱图尚待接入。',
              '- 各页专用 ZSR 兜底待 J5 录制；当前只提供明确标注的通用 FM 监测历史会话，不将其冒充本页内容。',
              '- 没有进行新射频操作，未发射、未加载新位流、未训练或重评历史指标；所有历史 FAIL 保留。', '']
    ledger.write_text('\n'.join(lines), encoding='utf-8')
    rows = []
    records = {}
    for feature in FEATURES:
        files = sources_for(feature, ROOT)
        names = []
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            names.append(name)
            if name not in records:
                records[name] = record_file(path, ROOT)
        rows.append(dict(key=feature.key, page=feature.page+1, title=feature.title,
                         sources=names, has_source=bool(names), hardware_acceptance='PENDING'))
    value = dict(schema='j_v4_source_inventory/1', created_utc=datetime.now(timezone.utc).isoformat(),
                 page_count=10, main_feature_count=52, independent_entries=len(rows),
                 entries=rows, files=list(records.values()),
                 missing=[row['key'] for row in rows if not row['has_source']],
                 mismatches=[r['path'] for r in records.values() if r['integrity']=='HASH_MISMATCH'],
                 hardware_started=False, full_feature_acceptance='PENDING')
    write_json(ROOT/'board/measurements/j_v4_sources.json', value)
    print(json.dumps(dict(entries=len(rows), source_files=len(records), missing=value['missing'],
                          mismatches=value['mismatches']), ensure_ascii=False))
    return value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--update-zip', type=Path)
    build(parser.parse_args().update_zip)
