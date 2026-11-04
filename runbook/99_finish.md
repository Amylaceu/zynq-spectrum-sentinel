# 99 收尾执行方案（2026-11-03 起，取代 95_final.md 中尚未完成的部分）

> 阅读顺序：`AGENTS.md` → `runbook/CONTEXT.md` → **本文件** → `docs/antenna_sd_guide.md`。冲突时以本文件为准。
> 基线：`board/overlay/sentinel_v2_100m/`（100 MHz，WNS +0.210 / WHS +0.030 ns，3.84 MSPS）。**不再重新综合或布线**，除非 F 步骤明确要求。
> 原则：**所有 FAIL 如实保留，不再调参、不再训练、不再追时序**。剩余时间全部用于：①把成果固化，避免丢失；②完成空口闭环；③一键演示；④报告与交付。

---

## 0. 对进度报告（20261103）的评审

### 做得好的
- 100 MHz 基线已经上板回归：单音、三音、8192 字回放全部通过；接口时序窗口恢复正常；191 份捕获校验通过。
- 喇叭出声，FM 广播能清楚收听：300 秒数字链路零下溢；新增 FM 质量门控（导频突出度、相位跳变），信号质量差时自动静音。
- 噪声问题的诊断很扎实：用原始 IQ 证明噪声来自射频输入端，与 LCD 无关，也没有把恢复归功于代码。

### 不足（按严重程度）
| 编号 | 问题 | 风险 | 处理步骤 |
|---|---|---|---|
| **F1** | **33 个已修改文件和 208 个未跟踪条目没有提交**，其中包括 100 MHz 工程、位流、驱动和测量成果。现有备份早于这些改动 | **最高**：一旦硬盘出问题、误删或换电脑，当前唯一可运行的版本就会丢失 | F0 |
| F2 | 板端运行目录是每轮测试的隔离副本，没有正式的一键启动版本 | 演示和复现都依赖临时目录 | F1 |
| F3 | 识别模式下的显示帧率为 28.99 fps，略低于 30 fps | 小，属于指标问题 | 不处理，如实报告 |
| F4 | 间歇性射频噪声的来源没有找到 | 演示当天可能出现噪声 | F1 中加入启动自检，F4 演示前检查 |
| F5 | 严格"连续 300 秒不静音"差 0.95 秒（这是开头的静音保护造成的） | 指标定义问题 | 改为"质量放行后连续 300 秒"计时，如实写明 |
| F6 | 空口闭环（Y4/G3）、一键演示（Z1）、UI 整合（Z2）、报告和交付都还没做 | 作品不完整 | F2–F6 |
| F7 | 报告中出现了"Codex 执行代理"的字样，以及大量内部术语（r1/r2、FAIL 回执等） | 正式材料不能这样写 | F5 中改写 |

---

## 1. 步骤总表

| 步骤 | 内容 | 天线配置 | 必需？ | 预计 |
|---|---|---|---|---|
| **F0** | 全部成果提交并打快照 | A | **必需，最先做** | 1 h |
| **F1** | 板端正式发布版和一键启动 | A | **必需** | 0.5 天 |
| **F2** | 一键演示 A 组（接收类功能） | A | **必需** | 0.5–1 天 |
| **F3** | 空口闭环与数字注噪评测（G3），以及演示 B 组 | **B** | **必需** | 1 天 |
| F4 | 宽频扫描与 1 小时稳定性 | A → D | 建议 | 0.5 天 |
| **F5** | 对比实验汇总、技能包、设计报告 | — | **必需** | 1.5 天 |
| **F6** | 复现验证、录制清单、最终交付包 | A → B | **必需** | 0.5 天 |

---

## F0 全部成果提交并打快照（必需，最先做）

**操作**：
1. `git status` 列出所有已修改和未跟踪的条目，分成三类：
   - **必须提交**：`src/`、`board/scripts/`、`board/overlay/sentinel_v2_100m/`、`tools/`、`sim/golden/`、`sim/tb/`、`sim/scripts/`、`runbook/`、`docs/`、`report/`（不含大文件）、`board/measurements/*.json` 和 `*.sha256`、`build/scripts/`、`build/reports/**/SUMMARY.md` 和 `*.json`；
   - **不提交，但放进快照**：`board/measurements/` 中大于 5 MB 的 NPZ/IQ 文件、`report/results/*.zip`、`build/reports/**/*.rpt`；
   - **忽略**：`build/work/`、`logs/`、`.venv/`、`*.dcp`、Vivado 缓存目录。
2. 更新 `.gitignore`，然后分 3–5 个提交（按主题分：100 MHz 工程、驱动和脚本、测量证据、文档），每个提交都要能通过 `pytest src/ps/tests -q`。
3. 生成完整快照：`python tools/make_handoff_zip.py dist/zss_snapshot_20261103.zip`，要包括 vendor/atk、未入库的测量大文件和 sentinel_v2_100m 位流包。计算 SHA256，写入 `docs/snapshots.md`。
4. 👤 提醒用户把快照另外拷贝一份到 U 盘或网盘。

**验收**：`git status` 只剩被忽略的条目；快照能在另一个目录解压，且 `pytest` 通过。
**提交**：`[F0] commit all 100MHz work and create full snapshot`

---

## F1 板端正式发布版与一键启动（必需）

**天线**：A
**操作**：
1. 在板端新建正式目录 `/home/xilinx/sentinel/release/v2/`，放入 `ps/`、`scripts/`、`overlay/sentinel_v2_100m/`、`config.yaml`。由 `tools/release_board.ps1` 推送，并在推送后校验 SHA256。
2. 统一入口 `scripts/sentinel.sh`：
   - `sentinel.sh monitor`：频谱、检测、识别、上屏；
   - `sentinel.sh listen 95.8`：FM 监听，输出到喇叭；
   - `sentinel.sh demo A` / `sentinel.sh demo B`：一键演示；
   - `sentinel.sh stop`：先静音，再关闭射频，GPIO/SRC/音频全部归 0；
   - `sentinel.sh selftest`：位流哈希、AD9361 ID、TX 衰减 89.75 dB、温度、导频质量（如果在 FM 频段）。
3. `config.yaml` 集中保存默认参数：BUS_PHASE = 2、采样率 3.84 MSPS、RF 带宽、音量（默认 −12 dB，上限 −6 dB，需同步修改音量保护范围并测试）、电台列表（95.8 MHz 及其 LO）。
4. 启动时自检：如果导频突出度 < 20 dB，在屏幕上显示"RF NOISY – check antenna/power"，并把当时的 IQ、增益、RSSI 保存到 `measurements/noise_events/`（对应 F4 问题，用于演示当天排查）。
5. **不设开机自启**（避免演示前误启动射频）。

**指标**：`sentinel.sh selftest` 全部通过；`stop` 后读回 GPIO/SRC/音频均为 0；用户只需一条命令就能启动和停止。
**提交**：`[F1] board release v2 with single entry script`

---

## F2 一键演示 A 组（必需）

**天线**：A（RX1A 接 20–512 MHz，TX1A 空）
**操作**：实现 `sentinel.app.demo --group A`（95_final Z1 中 A 组的 1–4 段），并补上 Z2 中**软件层面**的 UI：
- 段 1 自检（10 s）→ 段 2 FM 频段监测，包括识别和星座图（40 s）→ 段 3 自动锁定最强的可信电台并用喇叭播放（30 s）→ 段 4 测试源三音（15 s）；
- 屏幕顶部显示段标题和倒计时；状态栏显示模式、LO、帧率、温度、TX OFF（绿色）；
- **UI 只修改 PS 绘制的部分**（事件区、按调制类型配色），**不重新构建位流**（Z2 的硬件改动放弃，原因写进报告）；
- 支持 `--segment N` 单独重录某一段、`--loop` 循环播放，并把音频另存为 WAV。

**指标**：A 组完整运行约 1.5 分钟，连续 3 次无崩溃；段 3 喇叭出声；👤 用户目视确认。
**提交**：`[F2] demo group A`

---

## F3 空口闭环与数字注噪评测（G3）及演示 B 组（必需）

**天线**：**配置 B-直插**：TX1A 和 RX1A 各直接拧一根 2.4 GHz 折叠胶棒天线，折成竖直、同一方向；FMCOMMS3 用铜柱撑住。👤 用户确认后才能发射。**直插时 TX 衰减下限为 40 dB**（`--att-floor 40`；TxGuard 的 30 dB 硬下限保持不变），起始 89 dB，每步减小 3 dB。
**前置条件**：先确认 `sentinel_v2_100m` 中 src_mux 的 MODE = 3（注噪）可用（读寄存器并做一次回放注噪自检）；不可用时，在 PS 端对捕获数据加噪声，并在报告中说明。
**操作**：
1. 发射前自检：TxGuard 设为空口模式（下限 30 dB）；读回 TX 衰减；RSSI 中止门限 −30 dBm。
2. `loopback_eval calibrate --att-floor 40`：LO 2.45 GHz，TX 衰减从 89 dB 起每步减小 3 dB，直到 SNR ≥ 25 dB 或到达 40 dB 下限；直插耦合强，预计在 50–70 dB 就能达到目标 SNR。
3. `loopback_eval sweep`：10 类调制 × 注噪 SNR（−4 到 20 dB，步长 2 dB）× 每点 100 段（时间不够时减为 50 段）。
4. 同时得到：混淆矩阵、准确率–SNR 曲线（与仿真曲线叠加）、8 个大类的准确率曲线。
5. Pfa：TX 关闭，在 2.30–2.39 GHz 空闲频段测试；Pd：发单音，扫注噪 SNR（−6 到 16 dB）。
6. 实现 `demo --group B`（95_final Z1 中的段 7 → 5 → 6 → 8），启动时要求输入 `yes` 确认天线配置。
7. 全部结束后：TX 衰减恢复 89.75 dB，ENSM 回到 ALERT；👤 提醒用户拆掉 TX1A 上的天线，恢复配置 A。

**指标**：

| 指标 | 目标 |
|---|---|
| 空口 10 类准确率 @ 注噪 SNR = 10 dB | ≥ 80%（达不到时如实报告） |
| 空口 8 大类准确率 @ 10 dB | ≥ 90% |
| 实测 Pfa / 设定 Pfa | 0.5–2 |
| Pd @ 单 bin SNR = 10 dB | ≥ 90% |
| 全程 TX 衰减最小值 | ≥ 40 dB（直插） |
| B 组演示 | 约 2 分钟，连续 3 次无崩溃 |

**提交**：`[F3] G3 OTA loopback evaluation and demo group B`

---

## F4 宽频扫描与 1 小时稳定性（建议）

**天线**：先用 A 扫 70–512 MHz；再换 **D**（RX1A 接宽带胶棒天线）扫 512 MHz–2.7 GHz。
**操作**：
1. 扫频用 PS 快照方式：30.72 MSPS 只做快照，不经过 PL 处理链；每段 20 MHz；拼接出全景图，并标注 FM、对讲、GSM、LTE、WiFi 等频段。完成后恢复 3.84 MSPS 的正常配置。
2. 1 小时稳定性：配置 A，`sentinel.sh monitor`（含识别）运行 3600 秒。记录采样溢出、帧率、温度、内存、噪声事件次数。

**指标**：全景图完成；1 小时内采样溢出 = 0、无崩溃、内存增长 < 10 MB、温度 < 85 °C。
**提交**：`[F4] panoramic sweep and 1h stability`

---

## F5 对比实验、技能包与设计报告（必需）

**操作**：
1. `report/opt_tables.md` 补齐以下各项：
   - E1 FFT + CFAR，CPU 与 PL 对比（22.75 倍）；
   - E10 显示：1.67 → 49.4 fps；
   - 150 MHz 与 100 MHz 的时序和资源对比（Z10 的历程）；
   - E7 识别各轮对比；E9 仿真与空口对比（来自 F3）；
   - X1、X2、X3 的失败分析作为"优化过程"的真实记录。
   - 没做的实验写明"未做及原因"。
2. 技能包 `skill/`（至少 6 项，每项都要有 README 和最小示例）：
   - S1 `pynq_overlay_check`、S2 `pynq_dma_kit`、S5 `golden_compare`、S6 `vivado_report_digest`；
   - S7 `pynq_lcd8080_kit`；
   - S13 `sd_card_safety`；
   - **新增 S14 `timing_closure_playbook`**：150 MHz → 100 MHz 的判断方法、并行构建、只重跑实现、"禁止用 false_path 掩盖违例"的原则，以及 Z10/T5 的真实数据。
3. `report/design_report.md`（再导出为 PDF），按竞赛 3.3.5.3 的 7 个章节编写：
   - **用正式的工程语言**，不出现"Codex/agent 回执/r1 r2"等内部用语；
   - 第 4 章"优化过程"使用真实的失败和改进数据；
   - 第 8 章"实测指标"中设一节"未达标项与原因"：X1 检出率、X2 带宽、X3 时延定义、X4 准确率、识别模式帧率 28.99 fps、连续播放的计时口径；
   - 第 5 章"大模型协作"引用 `report/llm_logs/`，并写明如何用 runbook 协议约束 AI 代理（这本身就是一个亮点）。
4. 根目录 `README.md`：硬件清单、上电检查清单、无需射频板的复现路径（`--source test/replay`）、`sentinel.sh` 的用法。

**提交**：`[F5] experiments, skills, design report`

---

## F6 复现验证、录制清单与交付（必需）

**操作**：
1. 复现验证：在另一个干净目录中解压 F0 的快照，按 README 执行"无需射频板"的路径（`pytest` 和回放模式自检），结果写入 `report/reproduce_check.md`。
2. 录制清单 `report/video_shotlist.md`（按 95_final Z6）：v01 硬件 → v02 demo A（配置 A）→ 换天线 → v04 demo B（配置 B）→ v05 PC 录屏 → 结尾。每段写明对应命令、时长和旁白提示。
3. 最终交付包：`dist/zss_final.zip`，附 SHA256；👤 用户提供 GitHub 地址后再推送。
4. 👤 提醒用户在最终交付前再做一次 SD 卡整卡备份。

**提交**：`[F6] reproduce check, shot list, final package`

---

## 不再做的事（明确冻结）
- 不重新训练识别模型；不再调 CFAR 参数；不再追 30.72 MSPS 宽带；不再追 WNS ≥ +1 ns；不做 Z2 的硬件 UI 改动；不做第二块屏、触摸、红外、双通道。
- 例外：只有当 F1–F3 的功能**因为 PL 缺陷无法运行**时，才允许重新构建，并且必须先征得用户同意。
