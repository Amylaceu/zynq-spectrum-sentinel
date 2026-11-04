# 当前主上位机功能覆盖：J-v7

固定100MHz位流；不发射。源码入口为tools/host/product.py；旧exe不含本轮修改。

| 卡片 | 当前板测状态 | 证据/边界 |
|---|---|---|
| F0 | DONE | PN状态检查，不是实际逐位错误计数 |
| F1 | READY | 启动及停止恢复已验证 |
| F2 | READY | 约40–41fps；0bin，8192字无不一致 |
| F4 | READY | 启动及停止恢复已验证 |
| F5 | READY | 启动及停止恢复已验证 |
| F6 | READY | 启动及停止恢复已验证 |
| F7 | READY | 启动及停止恢复已验证 |
| F10 | READY | 启动及停止恢复已验证 |
| F8 | DONE | 搜台换台可用；同步录音三轮失败，已隐藏入口 |
| F11 | DONE | 约34秒，15秒时限未达 |
| F12 | NOT_QUALIFIED | FM4/10，未达9/10，不显示可靠标签 |
| F13 | DONE | 实测录波输入，本轮板端推理，500条逐项一致 |
| F14 | PASS（有限快照流程） | 本轮9条网络记录/27个有效信标；恢复、锁定和人工换线解锁通过 |

逐卡截图索引：[本轮截图](../board/measurements/j7_acceptance_summary.md)。完整结果、SHA256和限制见[集成说明](../docs/j7_features.md)。所有网络默认统一样式，不自动突出某个热点。

以下为历史v4覆盖记录，不代表当前主界面。
# 上位机成果覆盖核对（J 修订 v4）

52 项主成果含 49a–g、52a–f，共 63 个独立入口。十页候选源码已接入入口；入口可点击不代表实时功能已经验收。当前仅完成离线布局和命令门禁开发，尚未发布正式 v3。

候选入口：`.venv/Scripts/python.exe tools/host/product.py`。旧版默认入口和 exe 保留。

来源摘要清单：`board/measurements/j_v4_sources.json`（附 SHA256）。有原始摘要的文件核对原始摘要；无原始摘要的文件只建立当前快照，不宣称补做原测量校验。原测量日期缺失时不使用文件复制时间替代。

离线截图：`report/figures/host_j_v4_r3/`。全部为合成界面预览，不是新真板验收。

| 编号 | 页面 | 操作按键 | 当前展示方式 | 来源模式 | 验证 / 后续条件 |
|---|---|---|---|---|---|
| 1 | 系统与硬件 | 运行自检 | 实时常驻 check（候选 UI 待板测） | `board/measurements/i1_r3*/**/result.json`<br>`docs/i1_resident_service.md` | 已复用现有场景；本轮真板 3 次就绪/P90 未测 |
| 2 | 系统与硬件 | 查看 RX 回环实测 | 实测资料 / 工程资料浏览 | `docs/rx_bist_dma_acceptance.md`<br>`report/figures/rx_bist_capture.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 3 | 系统与硬件 | 查看 TX 回环实测 | 实测资料 / 工程资料浏览 | `board/measurements/tx_loopback_acceptance.json`<br>`report/figures/tx_loopback.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 4 | 系统与硬件 | 查看时序窗口 | 实测资料 / 工程资料浏览 | `docs/rx_timing_margin.md`<br>`report/figures/rx_timing_margin.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 5 | 系统与硬件 | 查看遥测 | 实测资料 / 工程资料浏览 | `docs/i1_resident_service.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 6 | 系统与硬件 | 查看连接与引脚 | 实测资料 / 工程资料浏览 | `docs/hw_base_summary.md`<br>`docs/board_info.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 7 | 系统与硬件 | 查看安全记录 | 实测资料 / 工程资料浏览 | `board/measurements/i0_s1_ota_r1_preflight.json`<br>`board/measurements/i0_s1_ota_r1_postflight.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 8 | 系统与硬件 | 查看备份记录 | 实测资料 / 工程资料浏览 | `docs/snapshots.md`<br>`docs/sd_backup.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 9 | 频谱全景 | 显示已测参考全景 | 实测全景 / SHA256 载入 | `board/measurements/h1_a_scan_r2/raw/result.json`<br>`board/measurements/h1_d_scan_r1/raw/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 10 | 频谱全景 | 查看扫描记录 | 实测资料 / 工程资料浏览 | `board/measurements/h1_a_scan_r2/raw/result.json`<br>`board/measurements/h1_d_scan_r1/raw/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 11 | 频谱全景 | 查看扫描提速 | 实测资料 / 工程资料浏览 | `board/measurements/h1_fast_comparison_r1.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 12 | 频谱全景 | 查看搜台实测 | 实测资料 / 工程资料浏览 | `board/measurements/fm_scan_candidates.json`<br>`board/measurements/fm_scan_round1.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 13 | 频谱全景 | 转到监测页（不启动） | 本地导航（不启动射频） | `docs/f4_panorama_progress.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 14 | 监测识别 | 开始监测 | 实时常驻 fm（候选 UI 待板测） | `docs/g4plus_host_v2.md` | 已复用现有场景；本轮真板 3 次就绪/P90 未测 |
| 15 | 监测识别 | 查看目标与事件 | 实测资料 / 工程资料浏览 | `docs/x3_acceptance_summary.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 16 | 监测识别 | 查看参数接口资料 | 实测资料 / 工程资料浏览 | `src/regs/*.yaml`<br>`src/ps/sentinel/drivers/regs/spec_ctrl.py`<br>`src/ps/sentinel/drivers/regs/cfar_ctrl.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 17 | 监测识别 | 查看信道化证据 | 实测资料 / 工程资料浏览 | `docs/x5*.md`<br>`src/ps/sentinel/capture_x5.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 18 | 监测识别 | 识别所选信号 | 实时目标选择（待真板） | `docs/amc_attempts.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 19 | 监测识别 | 查看识别特征 | 实测资料 / 工程资料浏览 | `src/ps/sentinel/amc/features.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 20 | 监测识别 | 查看识别时延 | 实测资料 / 工程资料浏览 | `docs/y2*.md`<br>`docs/x3_acceptance_summary.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 21 | 监测识别 | 查看占用告警规则 | 实测资料 / 工程资料浏览 | `tools/host/alarms.yaml`<br>`tools/host/sentinel_host/alarms.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 22 | 监测识别 | 导出当前 IQ 快照 | 本地 IQ 导出（待数据验收） | `docs/g4plus_host_v2.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 23 | 监测识别 | 查看同步记录 | 实测资料 / 工程资料浏览 | `docs/g4c*.md`<br>`docs/g4plus_host_v2.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 24 | 广播收听 | 开始收听 95.8 MHz | 实时常驻 listen（候选 UI 待板测） | `docs/y3_noise_diagnosis.md` | 已复用现有场景；本轮真板 3 次就绪/P90 未测 |
| 25 | 广播收听 | 查看选台依据 | 实测资料 / 工程资料浏览 | `src/ps/sentinel/release_support.py`<br>`board/release/config.yaml` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 26 | 广播收听 | 查看门控实测 | 实测资料 / 工程资料浏览 | `docs/y3_noise_diagnosis.md`<br>`src/ps/sentinel/fm_quality.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 27 | 广播收听 | 查看音量验收 | 实测资料 / 工程资料浏览 | `docs/i1_resident_service.md`<br>`board/release/config.yaml` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 28 | 广播收听 | 打开历史录音库 | WAV 回放 / 波形 / PC 播放 | `report/results/fm_*.wav` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 29 | 广播收听 | 查看噪声诊断 | 实测资料 / 工程资料浏览 | `docs/y3_noise_diagnosis.md`<br>`report/figures/fm_*demod.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 30 | 广播收听 | 查看天线对比 | 实测资料 / 工程资料浏览 | `docs/antenna_comparison.md`<br>`report/figures/fm_band_antenna.png`<br>`board/measurements/i0_fm_comparison_r1.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 31 | 精度与验证 | 查看三音实测 | 实测资料 / 工程资料浏览 | `docs/n4_acceptance_summary.md`<br>`report/figures/n4_trace_simulation.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 32 | 精度与验证 | 查看回放源比对 | 实测资料 / 工程资料浏览 | `sim/results/z10_clock_r2/source_compare.json`<br>`docs/n4_acceptance_summary.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 33 | 精度与验证 | 查看 PL 回放路径 | 实测资料 / 工程资料浏览 | `src/ps/sentinel/drivers/regs/src_ctrl.py`<br>`data/captured/fm_diagnostic/*.sigmf-meta` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 34 | 精度与验证 | 查看黄金模型验收 | 实测资料 / 工程资料浏览 | `sim/results/*/source_compare.json`<br>`tools/golden_compare.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 35 | 精度与验证 | 查看回归与波形 | 实测资料 / 工程资料浏览 | `board/measurements/j0_regression.json`<br>`report/figures/n4_trace_simulation.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 36 | 空口与鲁棒性 | 查看 F3 空口实测 | 实测资料 / 工程资料浏览 | `board/measurements/f3_evaluation_r1/result.json`<br>`board/measurements/f3_evaluation_r1/confusion_10db.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 37 | 空口与鲁棒性 | 查看注噪准确率曲线 | 实测资料 / 工程资料浏览 | `board/measurements/f3_evaluation_r1/accuracy.png`<br>`board/measurements/f3_evaluation_r1/ota_curve.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 38 | 空口与鲁棒性 | 查看 PL 注噪实测 | 实测资料 / 工程资料浏览 | `docs/f3*.md`<br>`src/ps/sentinel/drivers/regs/src_ctrl.py` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 39 | 空口与鲁棒性 | 查看仿真空口对比 | 实测资料 / 工程资料浏览 | `board/measurements/f3_evaluation_r1/result.json`<br>`board/measurements/f3_evaluation_r1/accuracy.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 40 | 空口与鲁棒性 | 查看三轮迭代 | 实测资料 / 工程资料浏览 | `docs/amc_attempts.md`<br>`report/figures/e7_x4_*.png`<br>`report/figures/amc_attempts_failed.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 41 | 空口与鲁棒性 | 查看检测观测结果 | 实测资料 / 工程资料浏览 | `board/measurements/f3_pd_r1/result.json`<br>`board/measurements/f3_pfa_r1/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 42 | 空口与鲁棒性 | 查看热点对照（INCONCLUSIVE） | 实测资料 / 工程资料浏览 | `board/measurements/i0_s*_hotspot_comparison_r1/*.json`<br>`board/measurements/i0_antenna_s.json` | INCONCLUSIVE；不能识别热点；保留原始对照结论 |
| 43 | 性能与优化 | 刷新实时性能 | 实时常驻 perf（候选 UI 待板测） | `docs/i1_resident_service.md` | 已复用现有场景；本轮真板 3 次就绪/P90 未测 |
| 44 | 性能与优化 | 查看同帧计时实测 | 实测资料 / 工程资料浏览 | `docs/x3_acceptance_summary.md`<br>`report/figures/e1_x3_throughput.png`<br>`board/measurements/x3_perf_r3.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 45 | 性能与优化 | 查看推理引擎实测 | 实测资料 / 工程资料浏览 | `report/opt_tables.md`<br>`board/measurements/x4_*board*.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 46 | 性能与优化 | 查看显示演进 | 实测资料 / 工程资料浏览 | `report/figures/e10_x3_display.png`<br>`report/figures/lcd_*preview.png`<br>`report/figures/ui_v3/*.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 47 | 性能与优化 | 查看冻结构建报告 | 实测资料 / 工程资料浏览 | `board/overlay/sentinel_v2_100m/acceptance.json`<br>`docs/timing_closure*.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 48 | 性能与优化 | 查看对比实验表 | 实测资料 / 工程资料浏览 | `report/opt_tables.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49a | 回放中心 | 打开 ZSR 会话 | ZSR 回放 / 暂停 / 0.5/1/2倍速；定位待接入 | `board/measurements/g4*/*.zsr/manifest.json`<br>`board/measurements/g5*/*.zsr/manifest.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49b | 回放中心 | 查看 SigMF 录波库 | 实测资料 / 工程资料浏览 | `data/captured/fm_diagnostic/*.sigmf-meta`<br>`data/captured/samples/rx_bist_verified.sigmf-meta` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49c | 回放中心 | 打开全部录音 | WAV 回放 / 波形 / PC 播放 | `report/results/*.wav` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49d | 回放中心 | 查看全景回放资料 | 实测资料 / 工程资料浏览 | `board/measurements/h1_a_scan_r2/raw/result.json`<br>`board/measurements/h1_d_scan_r1/raw/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49e | 回放中心 | 查看空口采集记录 | 实测资料 / 工程资料浏览 | `board/measurements/f3_capture_r1/raw/result.json`<br>`board/measurements/f3_evaluation_r1/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49f | 回放中心 | 查看板端回放路径 | 实测资料 / 工程资料浏览 | `docs/n4_acceptance_summary.md`<br>`data/captured/fm_diagnostic/*.sigmf-meta` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 49g | 回放中心 | 录制与导出 | 本地会话录制与导出 | `docs/g4plus_host_v2.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 50 | 自动演示 | 查看 A 组演示记录 | 实测资料 / 工程资料浏览 | `docs/g5_progress.md`<br>`board/measurements/g5_a_board_r2/acceptance.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 51 | 自动演示 | 查看 B 组演示记录（不发射） | 实测资料 / 工程资料浏览 | `docs/f3*.md`<br>`board/measurements/f3_evaluation_r1/result.json` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52a | 开发历程 | 打开成果索引 | 成果索引跳转（不启动射频） | `report/host_coverage.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52b | 开发历程 | 查看阶段时间线 | 实测资料 / 工程资料浏览 | `runbook/STATUS.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52c | 开发历程 | 查看未达标记录 | 实测资料 / 工程资料浏览 | `report/feature_list.md`<br>`docs/g4d_progress.md`<br>`docs/x3_acceptance_summary.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52d | 开发历程 | 打开协作记录库 | 实测资料 / 工程资料浏览 | `report/llm_logs/*.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52e | 开发历程 | 打开完整图库 | 实测资料 / 工程资料浏览 | `report/figures/**/*.png` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |
| 52f | 开发历程 | 打开工程文档库 | 实测资料 / 工程资料浏览 | `report/design_plan.md`<br>`runbook/*.md`<br>`skill/**/*.md` | 入口路由已有离线自动测试；来源摘要见 JSON；对应动态验收待测 |

## 仍需执行的验收与接入

- J1：正式 v3、可配置 7200 秒、一键入口及完整发布校验尚待完成；v2 不覆盖。
- J2：本轮十页预览须用户确认后才新布局连真板；十页逐项操作、30 分钟循环和冷启动未测。
- J3/J4：三音、F3 原始 IQ 回放和推理、参考全景补扫及恢复读回尚待集成。
- 其余新常驻场景：RX BIST、选台、质量门控演示、参数演示、PL 回放/注噪、CPU/推理计时、自动 A/B 未接入；不发送未实现的命令。
- 回放中心：SigMF 黄金模型复算/FM 解调、ZSR 拖动定位、全景逐段动画、F3 逐类回放及语谱图尚待接入。
- 各页专用 ZSR 兜底待 J5 录制；当前只提供明确标注的通用 FM 监测历史会话，不将其冒充本页内容。
- 没有进行新射频操作，未发射、未加载新位流、未训练或重评历史指标；所有历史 FAIL 保留。
