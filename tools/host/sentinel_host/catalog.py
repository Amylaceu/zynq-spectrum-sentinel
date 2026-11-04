"""J v4 product inventory. Sub-items remain independently addressable.

This is a routing catalogue, not a claim that a planned hardware command exists.
Only the five already implemented resident scenes may be sent by this UI.
"""
from dataclasses import dataclass
from pathlib import Path
import sys

PAGES = ('系统与硬件', '频谱全景', '监测识别', '广播收听', '精度与验证',
         '空口与鲁棒性', '性能与优化', '回放中心', '自动演示', '开发历程')
LIVE_SCENES = frozenset(('check', 'fm', 'listen', 'perf', 'idle'))


def repository():
    if getattr(sys, 'frozen', False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Feature:
    key: str
    page: int
    title: str
    action: str
    sources: tuple
    scene: str = ''


def f(key, page, title, action, *sources, scene=''):
    return Feature(str(key), page-1, title, action, sources, scene)


FEATURES = (
    f(1, 1, '一键自检', '运行自检', 'board/measurements/i1_r3*/**/result.json', 'docs/i1_resident_service.md', scene='check'),
    f(2, 1, 'RX BIST 数字回环', '查看 RX 回环实测', 'docs/rx_bist_dma_acceptance.md', 'report/figures/rx_bist_capture.png'),
    f(3, 1, 'TX → RX 数字回环', '查看 TX 回环实测', 'board/measurements/tx_loopback_acceptance.json', 'report/figures/tx_loopback.png'),
    f(4, 1, 'LVDS 接口时序窗口', '查看时序窗口', 'docs/rx_timing_margin.md', 'report/figures/rx_timing_margin.png'),
    f(5, 1, '温度与接收功率', '查看遥测', 'docs/i1_resident_service.md'),
    f(6, 1, '硬件连接与引脚', '查看连接与引脚', 'docs/hw_base_summary.md', 'docs/board_info.md'),
    f(7, 1, '发射安全与历次检查', '查看安全记录', 'board/measurements/i0_s1_ota_r1_preflight.json', 'board/measurements/i0_s1_ota_r1_postflight.json'),
    f(8, 1, 'SD 镜像与工程快照', '查看备份记录', 'docs/snapshots.md', 'docs/sd_backup.md'),
    f(9, 2, '70 MHz–2.7 GHz 参考全景', '显示已测参考全景', 'board/measurements/h1_a_scan_r2/raw/result.json', 'board/measurements/h1_d_scan_r1/raw/result.json'),
    f(10, 2, '全景扫描逐段回放', '查看扫描记录', 'board/measurements/h1_a_scan_r2/raw/result.json', 'board/measurements/h1_d_scan_r1/raw/result.json'),
    f(11, 2, '扫描提速与耗时分解', '查看扫描提速', 'board/measurements/h1_fast_comparison_r1.json'),
    f(12, 2, 'FM 搜台候选', '查看搜台实测', 'board/measurements/fm_scan_candidates.json', 'board/measurements/fm_scan_round1.json'),
    f(13, 2, '全景定点分析', '转到监测页（不启动）', 'docs/f4_panorama_progress.md'),
    f(14, 3, '实时频谱 / 瀑布 / 峰值', '开始监测', 'docs/g4plus_host_v2.md', scene='fm'),
    f(15, 3, 'CFAR / Top-32 / 目标事件', '查看目标与事件', 'docs/x3_acceptance_summary.md'),
    f(16, 3, '窗函数 / 平均 / CFAR 参数演示', '查看参数接口资料', 'src/regs/*.yaml', 'src/ps/sentinel/drivers/regs/spec_ctrl.py', 'src/ps/sentinel/drivers/regs/cfar_ctrl.py'),
    f(17, 3, 'PFB 16 通道与 NCO 提取', '查看信道化证据', 'docs/x5*.md', 'src/ps/sentinel/capture_x5.py'),
    f(18, 3, '十类识别 / Top-5 / 五票', '识别所选信号', 'docs/amc_attempts.md'),
    f(19, 3, '星座 / 瞬频 / 瞬幅 / HOC', '查看识别特征', 'src/ps/sentinel/amc/features.py'),
    f(20, 3, '识别时延与统计口径', '查看识别时延', 'docs/y2*.md', 'docs/x3_acceptance_summary.md'),
    f(21, 3, '占用度与告警', '查看占用告警规则', 'tools/host/alarms.yaml', 'tools/host/sentinel_host/alarms.py'),
    f(22, 3, 'IQ / CSV / PNG 导出', '导出当前 IQ 快照', 'docs/g4plus_host_v2.md'),
    f(23, 3, 'LCD 孪生与点击同步', '查看同步记录', 'docs/g4c*.md', 'docs/g4plus_host_v2.md'),
    f(24, 4, '指定电台收听', '开始收听 95.8 MHz', 'docs/y3_noise_diagnosis.md', scene='listen'),
    f(25, 4, '质量门控与自动选台', '查看选台依据', 'src/ps/sentinel/release_support.py', 'board/release/config.yaml'),
    f(26, 4, '弱信号自动静音 / 恢复', '查看门控实测', 'docs/y3_noise_diagnosis.md', 'src/ps/sentinel/fm_quality.py'),
    f(27, 4, '喇叭计数 / 下溢 / 音量保护', '查看音量验收', 'docs/i1_resident_service.md', 'board/release/config.yaml'),
    f(28, 4, '六段历史 FM 录音', '打开历史录音库', 'report/results/fm_*.wav'),
    f(29, 4, 'FM 噪声诊断', '查看噪声诊断', 'docs/y3_noise_diagnosis.md', 'report/figures/fm_*demod.png'),
    f(30, 4, '天线对比与选型', '查看天线对比', 'docs/antenna_comparison.md', 'report/figures/fm_band_antenna.png', 'board/measurements/i0_fm_comparison_r1.json'),
    f(31, 5, '测试源三音精度', '查看三音实测', 'docs/n4_acceptance_summary.md', 'report/figures/n4_trace_simulation.png'),
    f(32, 5, '8192 字回放源比对', '查看回放源比对', 'sim/results/z10_clock_r2/source_compare.json', 'docs/n4_acceptance_summary.md'),
    f(33, 5, '真实录波送入 FPGA', '查看 PL 回放路径', 'src/ps/sentinel/drivers/regs/src_ctrl.py', 'data/captured/fm_diagnostic/*.sigmf-meta'),
    f(34, 5, 'PC 黄金模型逐位比对', '查看黄金模型验收', 'sim/results/*/source_compare.json', 'tools/golden_compare.py'),
    f(35, 5, '自动测试与仿真波形', '查看回归与波形', 'board/measurements/j0_regression.json', 'report/figures/n4_trace_simulation.png'),
    f(36, 6, '十类真实空口采集与混淆矩阵', '查看 F3 空口实测', 'board/measurements/f3_evaluation_r1/result.json', 'board/measurements/f3_evaluation_r1/confusion_10db.png'),
    f(37, 6, 'SNR 与注噪鲁棒性', '查看注噪准确率曲线', 'board/measurements/f3_evaluation_r1/accuracy.png', 'board/measurements/f3_evaluation_r1/ota_curve.json'),
    f(38, 6, 'PL MODE3 数字注噪', '查看 PL 注噪实测', 'docs/f3*.md', 'src/ps/sentinel/drivers/regs/src_ctrl.py'),
    f(39, 6, '仿真 / 空口 / 八大类对比', '查看仿真空口对比', 'board/measurements/f3_evaluation_r1/result.json', 'board/measurements/f3_evaluation_r1/accuracy.png'),
    f(40, 6, '模型迭代与失败尝试', '查看三轮迭代', 'docs/amc_attempts.md', 'report/figures/e7_x4_*.png', 'report/figures/amc_attempts_failed.png'),
    f(41, 6, 'Pd / Pfa 观测', '查看检测观测结果', 'board/measurements/f3_pd_r1/result.json', 'board/measurements/f3_pfa_r1/result.json'),
    f(42, 6, '2.4 GHz 环境能量观测', '查看热点对照（INCONCLUSIVE）', 'board/measurements/i0_s*_hotspot_comparison_r1/*.json', 'board/measurements/i0_antenna_s.json'),
    f(43, 7, '帧率 / 吞吐 / 温度 / PS 负载', '刷新实时性能', 'docs/i1_resident_service.md', scene='perf'),
    f(44, 7, '同帧 FPGA 与 CPU 对比', '查看同帧计时实测', 'docs/x3_acceptance_summary.md', 'report/figures/e1_x3_throughput.png', 'board/measurements/x3_perf_r3.json'),
    f(45, 7, 'NumPy / 缓存 / C 推理对比', '查看推理引擎实测', 'report/opt_tables.md', 'board/measurements/x4_*board*.json'),
    f(46, 7, '显示提速与字体演进', '查看显示演进', 'report/figures/e10_x3_display.png', 'report/figures/lcd_*preview.png', 'report/figures/ui_v3/*.png'),
    f(47, 7, '资源时序与 150 → 100 MHz', '查看冻结构建报告', 'board/overlay/sentinel_v2_100m/acceptance.json', 'docs/timing_closure*.md'),
    f(48, 7, '各阶段对比实验表', '查看对比实验表', 'report/opt_tables.md'),
    f('49a', 8, '会话回放 / 暂停 / 倍速 / 定位', '打开 ZSR 会话', 'board/measurements/g4*/*.zsr/manifest.json', 'board/measurements/g5*/*.zsr/manifest.json'),
    f('49b', 8, 'IQ 录波与离线 FM 解调', '查看 SigMF 录波库', 'data/captured/fm_diagnostic/*.sigmf-meta', 'data/captured/samples/rx_bist_verified.sigmf-meta'),
    f('49c', 8, '历史音频 / 波形 / 语谱', '打开全部录音', 'report/results/*.wav'),
    f('49d', 8, 'A / D 全景扫描回放', '查看全景回放资料', 'board/measurements/h1_a_scan_r2/raw/result.json', 'board/measurements/h1_d_scan_r1/raw/result.json'),
    f('49e', 8, 'F3 空口逐类回放', '查看空口采集记录', 'board/measurements/f3_capture_r1/raw/result.json', 'board/measurements/f3_evaluation_r1/result.json'),
    f('49f', 8, '录波送入板端回放源', '查看板端回放路径', 'docs/n4_acceptance_summary.md', 'data/captured/fm_diagnostic/*.sigmf-meta'),
    f('49g', 8, '新会话 / PNG / CSV / IQ / HTML', '录制与导出', 'docs/g4plus_host_v2.md'),
    f(50, 9, 'A 组：自检 → 监测 → 广播 → 三音', '查看 A 组演示记录', 'docs/g5_progress.md', 'board/measurements/g5_a_board_r2/acceptance.json'),
    f(51, 9, 'B 组：环境 → 空口回放 → 注噪 → 性能', '查看 B 组演示记录（不发射）', 'docs/f3*.md', 'board/measurements/f3_evaluation_r1/result.json'),
    f('52a', 10, '全部成果按键索引', '打开成果索引', 'report/host_coverage.md'),
    f('52b', 10, '全部阶段时间线', '查看阶段时间线', 'runbook/STATUS.md'),
    f('52c', 10, '未达标项与原因', '查看未达标记录', 'report/feature_list.md', 'docs/g4d_progress.md', 'docs/x3_acceptance_summary.md'),
    f('52d', 10, '大模型协作记录', '打开协作记录库', 'report/llm_logs/*.md'),
    f('52e', 10, '关键图库（可放大）', '打开完整图库', 'report/figures/**/*.png'),
    f('52f', 10, '方案 / 执行手册 / 技能包', '打开工程文档库', 'report/design_plan.md', 'runbook/*.md', 'skill/**/*.md'),
)
BY_KEY = {item.key: item for item in FEATURES}


def sources_for(feature, root=None):
    root = (root or repository()).resolve()
    paths = set()
    for pattern in feature.sources:
        for path in root.glob(pattern):
            if path.is_file() and not path.is_symlink() and root in path.resolve().parents:
                paths.add(path)
    return sorted(paths)
