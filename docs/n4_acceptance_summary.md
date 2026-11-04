> 本文为2026-11-02的N4验收历史。2026-11-03已恢复工作，当前以runbook/90_plan.md和STATUS.md为准；原始验收JSON不修改。

# N4 验收汇总与暂停交接

记录时间（PC）：2026-11-02T23:33:31.667006+08:00

**状态：N4 DONE（限定为已测3.84MSPS仅接收功能，保留以下限制）。按用户要求暂停，N5未开始，M-A尚未完成。**

## 已通过的验收

- sentinel_v1整机实现与独立审计：WNS +0.086ns、WHS +0.046ns、脉宽裕量 +0.264ns；26,625 LUT、35,103 FF、49 BRAM、64 DSP。
- 板端自检与PC独立复核：单音频点误差0bin，三音3目标，四帧8192个功率字逐位零错。
- LCD全部七档经用户确认计数增加且画面正常；最小已验证档2，加一档余量选3。
- 用户确认真实接收“有动态频谱/瀑布，列表有条目，画面正常”。PL生成频谱/瀑布，PS约每秒刷新文字/列表。
- 两次120秒RF测试自然结束，双路TX衰减所有记录均89.75dB；最终独占锁下只读GPIO数据为0，无monitor/bench活动进程。
- 最终PS测试58项通过，日志logs/N4_final_ps_tests.log。

## LCD基准（前10秒不刷新文字UI）

| BUS_PHASE | 无UI基准fps | 动态UI更新次数 | 目视结果 |
|---:|---:|---:|---|
| 25 | 7.1927 | 131 | 通过 |
| 12 | 14.5853 | 102 | 通过 |
| 8 | 21.3914 | 179 | 通过 |
| 6 | 27.7720 | 117 | 通过 |
| 4 | 39.5600 | 118 | 通过 |
| 3 | 50.4490 | 120 | 通过 |
| 2 | 69.3300 | 109 | 通过 |

原始测量中的human_visual_acceptance=pending保留；人工结果另存n4_phase*_ui_acceptance.json，使用SHA256关联，不回写原始测量。

## RF显示数据

| 请求LO | 实际LO | 记录数 | fps最小/中位/最大 | FIFO溢出记录 | 目标列表容量告警 |
|---|---|---:|---|---:|---:|
| 98 MHz | 97999998 Hz | 105 | 48.626 / 49.453 / 50.188 | 0 | 42 |
| 96.4 MHz（覆盖95.8 MHz） | 96399998 Hz | 106 | 48.462 / 49.418 / 50.195 | 0 | 43 |

两次均为3.84MSPS、BUS_PHASE=3、仅RX，接收滤波带宽配置1.5MHz。完整显示帧率约49.4fps不代表PS列表同速更新。95.8MHz附近补测有41/106条记录包含±25kHz范围的峰值，关联既有FM导频/听音证据；检测窄峰的宽度不是整个FM信道带宽。此次补测没有另行获得用户对95.8MHz条目的专门目视确认，已取得的目视反馈来自98MHz测试。

## 限制与后续改进

- 仅验收3.84MSPS接收，RF滤波带宽配置1.5MHz；未证明30.72MSPS连续无溢出。
- 32目标列表容量告警：98MHz测试42/105条、96.4MHz测试43/106条；不等于采样FIFO溢出，也不等于所有谱帧的溢出率。状态寄存器与目标快照可能不同帧。
- 95.8MHz对应频点在补测106条记录中检出41次（峰值距中心不超过25kHz），结合此前FM导频/听音证据支持频点对应；不宣称每条目标都是电台、不宣称完整占用带宽或调制自动识别通过。
- LCD 2档69.33fps为无UI基准；运行默认3档，完整RF+UI约49.4fps。逐档目视不等于全温或长期稳定性。
- ADI内部仍有Critical CDC分类及IO约束告警；整机时序PASS不代表所有CDC/IO风险已消除。
- 每次RF测试120秒，不替代N8一小时稳定性；本轮未进行空口发射、PFB信道化、AMC或耳机实时监听。
- PL频谱刷新约49.4fps；PS文字和列表约每秒刷新，不能称整套文字UI每秒刷新49次。
- 板端墙上时钟不可信；关联依据为PC记录时间、boot_id、单调计时和文件哈希。
- 已安装管理员入口默认phase仍25；使用时明确传--phase 3。RTL复位/初始化默认仍25。

建议后续优先改善：列表容量告警显示、同帧读取容量标志、抑制梳状干扰候选并核验FM聚类带宽；这些尚未实现。不要用增大门限或忽略告警的方式冒称已全部通过。

## 证据与文件

- 汇总JSON：board/measurements/n4_acceptance_summary.json。
- 自检：board/measurements/n4_selftest_round2.json、.npz及_acceptance.json。
- LCD：board/measurements/n4_bench_phase*_ui_r*.json及n4_phase*_ui_acceptance.json。
- RF：board/measurements/n4_monitor_rf_phase3_r1.json、n4_monitor_rf_958_phase3_r1.json。
- 用户反馈：board/measurements/n4_rf_phase3_visual_acceptance.json。
- 退出复位：board/measurements/n4_final_rf_gpio.json；进程检查logs/N4_final_board_processes.log。
- 位流与硬件交付：board/overlay/sentinel_v1/；build/reports/sentinel_v1/SUMMARY.md。
- 历史FM证据：docs/fm_antenna_acceptance.md、board/measurements/fm_antenna_comparison.json及runbook/STATUS.md中的听音回报。

## 恢复工作入口

唯一工作仓库为经Git核实的当前仓库根目录；不得回写其他旧规划目录。下一步为runbook/80_next.md的N5，须等用户恢复任务。N5再完成E1/E10对比和G1登记，本轮不提前更改G1状态。不配置Git身份，不commit/push。

已装管理入口仍默认25档；若之后需要手动复现，确认无RF进程后使用唯一tag：

```sh
sudo -n /usr/local/sbin/zss-n4-admin monitor --source rf --lo 96400000 --rate 3840000 --phase 3 --seconds 120 --tag <新的唯一标签>
```

本轮已停止监测。LCD可能保留最后一帧，暂停后不继续滚动属于程序结束后的状态；未新增开机自启。
