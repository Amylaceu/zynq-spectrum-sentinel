"""Render reproducible X3 tables/plots from the hash-checked PC analysis."""
import json
from pathlib import Path
import sys

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from analyze_x3 import ROOT, checked, sha, save


def main():
    source = ROOT/'board/measurements/x3_analysis.json'
    data = checked(source)
    for name, digest in data['inputs_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Analysis input changed: '+name)
    d, rx, display = data['digital'], data['receive'], data['display']
    raw = checked(ROOT/'board/measurements/x3_perf_r3.json')
    figures = ROOT/'report/figures'
    figures.mkdir(exist_ok=True)
    outputs = {}
    def figure(name):
        path = figures/name
        plt.savefig(path, dpi=160, bbox_inches='tight')
        plt.close()
        outputs[path.relative_to(ROOT).as_posix()] = sha(path)
    cpu = d['cpu_kernel_median_s']
    fps = d['post_welch_frames_per_s_avg0']
    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(['CPU FFT only', 'CPU FFT + CA kernels', 'PL FFT + X1 CFAR'],
                 [1/cpu['fft2048'], 1/(cpu['fft2048']+cpu['cfar2048']), fps], color=['#718da5','#ac7948','#278c91'])
    ax.bar_label(bars, fmt='%.1f')
    ax.set(ylabel='Frames / second', title='E1: measured throughput at 3.84 MSPS, AVG_SHIFT=0', ylim=(0, 2200))
    fig.text(.5, -.02, 'CPU CA excludes clustering/top-32. Throughput ratios are not per-frame latency speedups.', ha='center', fontsize=9)
    figure('e1_x3_throughput.png')
    fig, ax = plt.subplots(figsize=(8, 4))
    latency = np.array([r['after']['latency_cycles'] for r in raw['latency']['samples']])/150
    ax.plot(np.arange(1000), latency, linewidth=.6)
    ax.axhline(200, color='#b44a4a', linestyle='--', label='Original target <200 us')
    ax.set(xlabel='Finite frame index', ylabel='First IQ sample to list-ready (us)',
           title='1000 hardware markers; includes ~533 us frame acquisition', ylim=(150, 680))
    ax.legend(loc='center right')
    figure('e1_x3_latency.png')
    fig, ax = plt.subplots(figsize=(9, 4))
    labels = ['CPU full chain']+['PL phase '+str(r['bus_phase']) for r in display['phases']]+['PL RX + text']
    values = [display['cpu_fullchain_fps']]+[r['fps'] for r in display['phases']]+[rx['display_median_fps']]
    bars = ax.bar(labels, values, color=['#ac7948']+['#718da5']*7+['#278c91'])
    ax.bar_label(bars, fmt='%.2f', fontsize=8)
    ax.set(ylabel='LCD frames / second', title='E10: distinct display measurement scopes', ylim=(0, 79))
    ax.tick_params(axis='x', labelrotation=32)
    fig.subplots_adjust(bottom=.30)
    fig.text(.5, .01, 'Phase sweep: no PS text updates. RX: 1 Hz text/list, 30 s window. CPU: gapped IQ snapshots.', ha='center', fontsize=9)
    figure('e10_x3_display.png')
    table = f'''# X3 对比实验与原指标核对

数据：`board/measurements/x3_analysis.json`（带 SHA256）。由 `tools/analyze_x3.py` 独立重算，图表由 `tools/render_x3_report.py` 生成。

## E1 频谱与检测吞吐

| 指标 | 历史 CPU P5 | 本轮 CPU | PL v1b（3.84 MSPS） |
|---|---:|---:|---:|
| 2048 点 FFT 中位耗时 | 0.67431 ms | {cpu['fft2048']*1000:.5f} ms | 不单独测 FFT 延迟 |
| CA 门限/hit 中位耗时 | 11.95167 ms | {cpu['cfar2048']*1000:.5f} ms | 不单独测 CFAR 延迟 |
| FFT 吞吐 | 1483.00 帧/s | {1/cpu['fft2048']:.2f} 帧/s | {fps:.2f} 帧/s（连续功率帧） |
| FFT + CA 内核组合吞吐 | {1/(data['historical_cpu']['fft2048_median_s']+data['historical_cpu']['cfar2048_median_s']):.2f} 帧/s | {1/(cpu['fft2048']+cpu['cfar2048']):.2f} 帧/s | {fps:.2f} 帧/s |
| FFT 单项吞吐比 | — | — | 对历史 {d['fft_only_speedup_historical']:.2f} 倍 / 本轮 {d['fft_only_speedup_current']:.2f} 倍 |
| FFT+CA 组合吞吐比 | — | — | 对历史 {d['fft_ca_kernel_throughput_ratio_historical']:.2f} 倍 / 本轮 {d['fft_ca_kernel_throughput_ratio_current']:.2f} 倍 |

本轮 CPU 的 2048 点 CA 门限/hit 与独立黄金模型逐字一致。CPU 基准不含 X1 聚类与 top-32；PL 包含，因此组合值是注明范围的吞吐对比。独立连续测试 {d['throughput_window_s']:.6f} s，计数器实测 {d['actual_iq_samples_per_s']:.2f} IQ/s。AVG_SHIFT=0，不能用 RF AVG_SHIFT=3 的后 Welch 事件当原始 FFT 帧率。未用 30.72 MSPS 的理论 15000 帧/s 替代板测。

## 1000 次检测时延

| 指标 | 实测 |
|---|---:|
| 中位数 | {d['latency_median_us']:.5f} µs |
| 最大值 | {d['latency_max_us']:.5f} µs |
| 最小值 | {d['latency_min_us']:.5f} µs |
| 原定 <200 µs | **FAIL** |

ARM 后首个接受 IQ 到列表就绪，包含 2048 点采集；AVG_SHIFT=0，无 Welch 平均等待。3.84 MSPS 下首末样本间隔约 {d['acquisition_first_to_last_us']:.5f} µs，本身已超过 200 µs。扣除采集后的差值约 {d['derived_median_remainder_us']:.5f} µs 仅为推算剩余流水开销，不能冒充独立 CFAR 实测，也不能用于把失败改为通过。

## E10 显示

| 方案 | fps | 整机 BRAM | CPU 占用与范围 |
|---|---:|---:|---|
| 历史 CPU 快照、绘制、帧缓存传输 | {display['cpu_fullchain_fps']:.5f} | 68 | NOT_MEASURED；400×240 RGB332 倍显，256 KiB 双页 |
| N4 PL，phase=25 | 7.19272 | 49 | 无 PS 文字刷新基准，CPU NOT_MEASURED |
| N4 PL，phase=3 | 50.44897 | 49 | 无 PS 文字刷新基准，CPU NOT_MEASURED |
| N4 PL，phase=2 | 69.33003 | 49 | 无 PS 文字刷新基准，CPU NOT_MEASURED |
| 本轮 PL v1b，phase=3，真实接收 | {rx['display_median_fps']:.5f} | {display['current_v1b_bram']} | 进程占单核 {rx['cpu_window']['process_one_core_percent']:.2f}%；全机双核平均忙碌 {rx['cpu_window']['system_busy_all_cores_percent']:.2f}% |

本轮 30 秒接收窗口，26 条遥测，文字/列表约 1 Hz；频谱与瀑布约 49 fps。对历史 CPU 显示帧率约 {display['pl_to_cpu_display_ratio']:.2f} 倍，显示架构/采集连续性不同，属于系统效果对比。本轮温度最高 {rx['max_temperature_c']:.2f}°C，采样溢出 0。Pillow 纯绘图 {cpu['pillow800x480_render_only']*1000:.3f} ms 不等于 CPU 整机显示帧率。其余各档与原始窗口见 JSON；没有补造历史 CPU 占用。

## X2 带宽

| 采样率 MSPS | RF 带宽 MHz | 板测 |
|---:|---:|---|
| 7.68 | 6 | NOT_TESTED |
| 15.36 | 12 | NOT_TESTED |
| 24.576 | 20 | NOT_TESTED |
| 30.72 | 25 | NOT_TESTED |

X2 路由时序失败，按用户要求延期，失败位流从未加载。本轮仅 3.84 MSPS，模拟 RF 带宽配置 1.5 MHz；数字 ±1.92 MHz 频谱范围不代表模拟平坦通带。

## G1 与 M-A 范围

重新独立核验 N4 NPZ 对仓库参考向量：8192 个功率字零错、单音 1088 bin、三音 724/1088/1324。`x3_g1_acceptance.json` 与 SHA256 可追溯，G1 可标 DONE。

X3 归档工作完成，原时延指标 FAIL；X1 检出率、X2 宽带时序仍 FAIL。M-A 为保留未达标项的阶段检查点，不能写成 X0–X3 全部验收通过或全部竞赛功能已完成。
'''
    target = ROOT/'report/opt_tables.md'
    target.write_text(table, encoding='utf-8')
    outputs[target.relative_to(ROOT).as_posix()] = sha(target)
    manifest = ROOT/'board/measurements/x3_report_manifest.json'
    payload = {'analysis_sha256':sha(source), 'generator_sha256':sha(Path(__file__)), 'outputs_sha256':outputs}
    # These are regenerable presentation outputs, never raw acquisitions.
    if manifest.exists():
        if checked(manifest)['analysis_sha256'] != sha(source):
            raise ValueError('Preserve report from a different analysis')
        manifest.write_text(json.dumps(payload, indent=2)+'\n', encoding='utf-8')
        Path(str(manifest)+'.sha256').write_text(sha(manifest)+'  '+manifest.name+'\n', encoding='ascii')
    else:
        save(manifest, payload)
    print(json.dumps(outputs, indent=2))


if __name__ == '__main__':
    main()
