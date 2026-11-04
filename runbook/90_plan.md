# 90 后续执行策划案（2026-11-03 起，取代 80_next.md 中 N5–N9）

> **代理阅读顺序**：`AGENTS.md` → `runbook/review_20261103.md` → **本文件** → `docs/antenna_sd_guide.md` → 需要细节时再查 `80_next.md` 和 `30–70` 分册。
> **冲突规则**：本文件 > 80_next.md > 30–70 分册。
> **前提（不可更改）**：没有衰减器（C1 维持 SKIPPED）；不用喇叭；不做红外遥控；耳机插 P1（LINE_OUT）；屏幕为 J22 SSD1963（800×480）；J7/J8 = 2.5V。
> **步骤编号**：X0–X9。每步都写明：运行环境 / 天线 / 前置条件 / 操作 / 产出 / **量化指标** / 验收 / 失败处理 / 提交。
> **通用规则**：长任务放后台，日志写到 `logs/X*.log`；每个子项最多 3 轮；👤 步骤给出操作说明后停下等用户；每步验收通过后 `git commit -m "[Xn] ..."`；不改 `third_party/`、`vendor/atk/`。

---

## 0. 路线图

| 步骤 | 名称 | 里程碑 | 预计 | 板端 | 天线（详见 antenna_sd_guide） |
|---|---|---|---|---|---|
| X0 | 收尾提交、SD 卡备份、默认参数修正 | — | 0.5 天 | 是 | A（RX1A 接 20–512 MHz 粗长天线，TX 空） |
| X1 | CFAR 列表质量优化 | M-A | 1 天 | 是 | A |
| X2 | 全带宽流水化（目标 30.72 MSPS） | M-A | 1–2 天 | 是 | A |
| X3 | E1 / E10 / 带宽对比，G1 归档 | **M-A 完成** | 0.5 天 | 是 | A |
| X4 | 分层调制识别 v2（P2.9b） | M-B | 1–2 天 | 否（PC） | — |
| X5 | 信道化提取 + 捕获 + 识别上屏 | M-B | 2 天 | 是 | A |
| X6 | 实时 FM 耳机监听 | M-B | 1–1.5 天 | 是 | A + 耳机 |
| X7 | 空口闭环 + 数字注噪评测 | M-C | 1 天 | 是 | B（2.4 GHz 双天线）或 C（433 MHz 双天线） |
| X8 | 扫频、稳定性、时延等附加指标 | M-C | 1 天 | 是 | A → D（宽带胶棒） |
| X9 | 对比实验、技能包、报告、复现、发布 | M-C | 2 天 | 否 | — |

**时间不够时的裁剪顺序**：X8 扫频 → X6 降级为"PS 解调 + 实时播放" → X5 中的 HOC 改由 PS 计算 → X2 降级为"测出最高零溢出档位"。**X0、X3、X7、X9 不可裁剪。**

---

## 1. 运行环境

| 项目 | 值 |
|---|---|
| PC | Windows + PowerShell 7（`pwsh`），在仓库根目录执行 `. ./tools/env.ps1`。仓库根目录就是**当前工作目录**，不要写死盘符 |
| 工具 | Vivado/Vitis 2025.2；Python 使用 `.venv`；ADI 工程在 `build/work/adi_hdl/` 中构建 |
| 板端 | 地址以 `docs/board_info.md` 为准（直连时为 192.168.2.99），PYNQ 2.7；`board.ps1 push/run/pull` |
| 当前位流 | `board/overlay/sentinel_v1/`（N4 已验收，3.84 MSPS，BUS_PHASE = 3） |
| 板端管理入口 | `/usr/local/sbin/zss-n4-admin`（需要显式传入 `--phase 3`） |

---

## X0 收尾提交、SD 卡备份与默认参数修正

**运行环境**：PC + 板端 + 👤
**天线**：配置 A（不变）
**操作**：
1. 核对工作区中 13 个已修改文件和 7 个未跟踪的 `board/measurements/n4_*` 文件：
   - 运行 `.\.venv\Scripts\python -m pytest src/ps/tests -q`，必须全部通过；
   - 确认这些改动与 N4 板端验收时使用的版本一致（对比 `n4_acceptance_summary.json` 中记录的 SHA256）；
   - 一致的话一并提交：`[N4] commit board acceptance code and measurements`。
2. **默认参数**：`monitor.py`、`bench_lcd.py`、`zss-n4-admin` 的 `--phase` 默认值改为 3；RTL 复位值保持 25，作为安全上电值，由软件在初始化时写入 3。
3. **温度显示**：`telemetry.read_temperature_c()` 改为读取 XADC，路径为 `/sys/bus/iio/devices/iio:device*/in_temp0_raw` 加 `_offset` 和 `_scale`，在状态栏显示。
4. 👤 **SD 卡整卡备份**（操作见 `docs/antenna_sd_guide.md` §3.3）：用户关机、拔卡，用 Win32DiskImager 读出整卡镜像，代理负责计算镜像的 SHA256 并记录。
5. 把 `report/HANDOFF_20261102_N4.md` 和 `NEXT_AGENT_PROMPT.md` 中写死的路径改为"仓库根目录"。

**指标**：PC 测试 100% 通过；`git status` 干净；SD 镜像 SHA256 已记录到 `docs/sd_backup.md`；状态栏能显示温度（数值在 30–85 °C 之间）。
**提交**：`[X0] commit N4 artifacts, default phase 3, XADC temperature, SD backup record`

---

## X1 CFAR 目标列表质量优化

**运行环境**：PC（仿真）→ 板端
**天线**：配置 A；中心频率 98 MHz（FM 频段）
**操作**：
1. 黄金模型 `sim/golden/cfar.py` 增加以下内容：
   - `min_width_bins`（默认 2）：宽度小于这个值的段丢弃；
   - `merge_gap_bins`（可配置，默认从 2 改为 6）：间隙不超过这个值的相邻段合并；
   - `mask_table`：最多 16 个屏蔽区间，用于 DC 附近和已知梳状杂散；
   - 排序：只保留峰值功率最高的 32 个目标（原来是从左到右截断）。
2. RTL `cfar_core` 同步修改：
   - 新增寄存器 `MIN_WIDTH`、`MERGE_GAP`、`MASK[0..15]`；
   - 新增 `STATUS_LATCH`：状态和目标列表在同一帧锁存；
   - top-32 排序用插入排序的移位寄存器实现（32 级，每个周期插入 1 个）；资源不够时退化为"超过 32 个时丢弃功率最小的"。
3. 仿真逐位比对（扩展 N3 的 testbench），然后重新构建 `sentinel_v1b`。
4. 板端实测：98 MHz，3.84 MSPS，120 秒，与 N4 的结果对比。

**指标**：

| 指标 | N4 基线 | X1 目标 |
|---|---|---|
| 容量告警率 | 40% | **< 5%** |
| 95.8 MHz 电台检出率（±25 kHz 内） | 41/106 = 39% | **≥ 80%** |
| 每帧目标数中位数 | — | 记录 |
| 时序 | WNS +0.086 | WNS ≥ 0，WHS ≥ 0 |

**验收**：逐位一致；板端指标达标；👤 用户确认屏幕列表中的电台频率与本地实际电台一致。
**失败处理**：告警率降不下来时，提高 Welch 平均（`AVG_SHIFT` 加 1）或提高 Pfa 门限，并记录对检出率的影响。不得通过"隐藏告警"来达标。
**提交**：`[X1] CFAR min-width/merge/mask and top-32 targets`

---

## X2 全带宽流水化（目标 30.72 MSPS）

**运行环境**：PC → 板端
**天线**：配置 A
**原因**：N4 在仿真中的吞吐上限约为 29.889 MSPS，瓶颈是 CFAR 按帧串行处理并反压 `spec_front`。
**操作**：
1. `cfar_core` 改为乒乓双缓冲：A 缓冲接收第 k 帧时，处理逻辑处理第 k−1 帧；处理来不及时**丢弃整帧并计数**（`FRAME_DROP`），**绝不反压上游**。
2. `spec_front` 的 Welch 平均部分：确认在 150 MHz、每周期 1 个样本时没有气泡（bubble）。
3. `adc_tap` 的 FIFO 溢出改为粘滞标志加计数（`SAMPLE_DROP`）。
4. 仿真：以 30.72 MSPS 连续输入 64 帧，`SAMPLE_DROP` 必须为 0（`FRAME_DROP` 允许不为 0，但要记录）。
5. 重新构建 `sentinel_v1c`，在板上按档位逐档测试：

| 采样率 | RF 带宽 | 测试时长 | 记录 |
|---|---|---|---|
| 7.68 MSPS | 6 MHz | 10 min | SAMPLE_DROP、FRAME_DROP、fps |
| 15.36 MSPS | 12 MHz | 10 min | 同上 |
| 24.576 MSPS | 20 MHz | 10 min | 同上 |
| 30.72 MSPS | 25 MHz | 10 min | 同上 |

**指标**：在**最高档**做到 `SAMPLE_DROP = 0`（这是"实时处理带宽"的定义）；目标 30.72 MSPS，最低要求 24.576 MSPS。98 MHz 中心频率时，30.72 MSPS 能覆盖 85.7–110.3 MHz，**整个 FM 广播频段一屏可见**。
**验收**：👤 用户确认 30.72 MSPS 下屏幕上能同时看到整个 88–108 MHz 范围内的电台。
**失败处理**：如果 30.72 MSPS 下有丢样，报告"零丢样的最高档位"，并给出瓶颈分析（周期预算表）。
**提交**：`[X2] pipelined CFAR, zero sample drop up to <rate>`

---

## X3 M-A 收口：对比实验与 G1

**运行环境**：板端 + PC
**天线**：配置 A
**操作**：
1. **E1（频谱 + CFAR）**：

| 指标 | CPU 基线（`p5_cpu_baseline.json`） | PL（`perf_mon` 实测） |
|---|---|---|
| 2048 点 FFT 帧率 | 1483 帧/s | 约 15 000 帧/s（30.72 MSPS 时） |
| CFAR 单帧耗时 | 11.95 ms | 实测（约 2048 个周期 ≈ 14 µs） |
| 加速比 | — | 计算得出 |

2. **E10（显示）**：

| 方案 | fps | BRAM | CPU 占用 |
|---|---|---|---|
| CPU 渲染 + 256 KiB 双页帧缓存（P5.4） | 1.67 | 68 | 实测 |
| PL 直驱，按 BUS_PHASE 档位（N4） | 7.19 → 69.33（档位 25 → 2） | 49（整机） | 实测 |

3. **带宽表**：X2 的 4 个档位。
4. **PL 检测时延**：`perf_mon` 标记样本到列表就绪中断的周期数，测 1000 次，给出中位数和最大值。
5. 生成 `report/opt_tables.md` 中的 E1、E10、带宽、时延各节，以及 `report/figures/e1_*.png` 等图。
6. 把 G1 标为 DONE（引用 N4 的测试源和回放自检结果）。

**指标**：E1 加速比 ≥ 10 倍；PL 检测时延 < 200 µs（不含 Welch 平均窗口的等待时间）；所有数字都能追溯到对应的 JSON。
**提交**：`[X3] milestone A: E1/E10/bandwidth/latency tables, G1 done`

> **M-A 完成后作品即具备提交条件。**

---

## X4 分层调制识别 v2（P2.9b，PC 端）

**运行环境**：PC（`.venv`，CPU 版 torch）
**天线**：不需要
**操作**：按 `80_next.md` N6 执行，补充以下要求：
1. 捕获长度 4096 点；有效采样率与 X5 的信道化输出保持一致：3.84 MSPS ÷ 抽取 → 480 kSPS（AM/FM 用）；数字调制 4–16 点/符号。**训练和板端使用的采样率必须相同**，写入 `params.py` 中的 `AMC_FS`。
2. 第一层 CNN 输出 8 类：BPSK、PSK-高阶、QAM、2FSK、GFSK、OOK、AM、FM；第二层用盲同步加统计特征区分 QPSK/8PSK 和 16QAM/64QAM。
3. 评估脚本输出：10 类混淆矩阵、准确率–SNR 曲线、8 个大类的准确率–SNR 曲线，并与 v1 画在同一张图中（实验 E7）。
4. INT8 导出和纯 NumPy 推理，并在板端测量单次推理耗时。

**指标**：

| 指标 | 目标 | v1 基线 |
|---|---|---|
| 10 类准确率 @ SNR = 10 dB | **≥ 88%** | 77% |
| 8 个大类准确率 @ SNR = 10 dB | ≥ 95% | — |
| QPSK/8PSK 召回率 @ SNR = 10 dB | ≥ 80% | 37% / 32% |
| INT8 相对 FP32 的下降 | ≤ 1% | — |
| 板端单次推理耗时（4096 点，含第二层） | ≤ 100 ms | — |

**失败处理**：最多 3 轮。仍未达标时如实写入报告（大类准确率单独列出），然后**继续执行 X5**。
**提交**：`[X4] hierarchical AMC v2`

---

## X5 信道化提取 + 识别上屏

**运行环境**：PC → 板端
**天线**：配置 A
**操作**：
1. `pfb_os2` 和 `nco_capture`：按 30_rtl_ip P3.4/P3.5 执行，先与黄金模型逐位比对；
2. 捕获帧（4096 点）通过 DMA 送到 PS → 计算 HOC（PS 端 NumPy；时间充裕时做 HLS 版本并对比，作为 E4）→ X4 的识别器；
3. 调度：按 CFAR 目标轮询，新目标优先；每个目标保留最近 5 次识别结果做投票；
4. UI：
   - 列表中增加调制类型和置信度；
   - 右侧显示所选目标的星座图（200×200）；
   - 底部状态栏显示"识别时延"。

**指标**：PFB 和 NCO 逐位一致；端到端识别时延（从目标出现到列表中显示调制类型）中位数 < 500 ms；在 98 MHz 下，FM 电台识别为 FM 的比例 ≥ 80%；整机时序通过；LUT ≤ 75%，BRAM ≤ 110。
**验收**：👤 用户确认屏幕上 FM 电台标注为"FM"，星座图区域在变化。
**提交**：`[X5] channelizer capture and on-screen AMC`

---

## X6 实时 FM 耳机监听

**运行环境**：PC → 板端 + 👤
**天线**：配置 A；**耳机插 P1（LINE_OUT）**
**操作**：
1. `demod_audio`（PL）：在 X5 的信道输出上做 CORDIC 鉴频 → 75 µs 去加重 → 抽取到 48 kHz → I2S（MCLK 12.288 MHz）。引脚：U9（MCLK）、AA11（BCLK）、U6（LRCK）、AB11（DACDAT）。
2. ES8388 初始化：通过 AXI IIC，SCL = A18、SDA = A19，器件地址 0x10。只打开 OUT1（耳机），音量从低开始。
3. `monitor.py --listen <Hz>`：选中电台后自动调谐信道和 NCO。
4. **降级方案**（PL 来不及完成时）：用 PS 解调，通过 I2S 的 FIFO 推流输出。这时 PL 只需要实现一个简单的 I2S 发送器。

**指标**：连续播放 5 分钟没有卡顿或断音（I2S FIFO 下溢计数 = 0）；导频突出度 ≥ 25 dB（与 `fm_antenna_comparison.json` 对比）；👤 主观评价"能清楚听到人声，只有轻微底噪"。
**提交**：`[X6] real-time FM audio to LINE_OUT`

---

## X7 空口闭环 + 数字注噪评测（无衰减器）

**运行环境**：板端 + 👤
**天线**：**配置 B（首选）或配置 C**，见 `docs/antenna_sd_guide.md`
**操作**：按 `80_next.md` N8 和 `60_board.md` G3.1b/G3.2/G3.2b 执行：
1. `calibrate`：TX 衰减从 89 dB 起每步减小 3 dB，直到 SNR ≥ 25 dB 或到达 30 dB 下限；RSSI > −30 dBm 时立即中止；
2. `sweep`：在 src_mux MODE = 3 下注入噪声，SNR 取 −4 到 20 dB（步长 2 dB），10 类调制 × 13 个 SNR 点 × 200 段；
3. 用采到的 `air_v1` 数据微调识别模型（E9）；
4. 在空闲频段测 Pfa；用注噪测 Pd 曲线。

**指标**：

| 指标 | 目标 |
|---|---|
| 空口实测识别率 @ 注噪 SNR = 10 dB | ≥ 85%（与仿真曲线的差距 ≤ 5 个百分点） |
| E9：微调后准确率提升 | > 0，如实记录 |
| 实测 Pfa / 设定 Pfa | 0.5–2 |
| Pd @ 单 bin SNR = 10 dB（Pfa = 1e-3） | ≥ 90% |
| 全程 TX 衰减 | ≥ 30 dB（记录中的最小值） |

**提交**：`[X7] OTA loopback with digital noise injection`

---

## X8 扫频、稳定性与附加指标

**运行环境**：板端
**天线**：先用配置 A 扫 70–512 MHz，再换配置 D 扫 512 MHz–3 GHz
**操作**：
1. `sweep.py`：每段 20 MHz（30.72 MSPS 下去掉两侧边缘），快速锁定 LO 后采集 8 帧，拼接出全景频谱和占用度；
2. 1 小时稳定性测试（monitor 模式，30.72 MSPS 或 X2 的最高档）；
3. 功耗：用 12V 适配器加功率计或万用表电流档测量（👤 可选）。

**指标**：

| 指标 | 目标 |
|---|---|
| 扫频速度 | 记录（GHz/s） |
| 1 小时稳定性 | SAMPLE_DROP = 0，进程不崩溃，内存增长 < 10 MB |
| 温度 | 记录最高值，< 85 °C |
| 功耗 | 记录（W） |

**提交**：`[X8] sweep, 1h stability, power`

---

## X9 交付

按 `70_deliver.md` 和 `80_next.md` N9 执行，补充要求：
- E1–E12 中没做的实验，在表里写明"未做及原因"；
- 技能包：S7 为 `pynq_lcd8080_kit`；另外新增 **S13 `sd_card_safety`**（PYNQ 板的安全断电、整卡备份和恢复、写入原子化），这些内容来自 N1 的实际故障；
- 报告中必须写明的判断依据：2.5V 与 HR Bank 的关系、数字注噪方法、分层识别的理由、PL 直驱显示的计算、CFAR 乒乓流水的吞吐计算；
- 最终交付包：`python tools/make_handoff_zip.py`；代码开源（👤 用户提供 GitHub 地址）。

**指标**：设计报告 7 个章节齐全；README 的"无需射频板复现路径"由用户或同学实际走通一遍；所有目录名和文件名为纯英文小写。
**提交**：`[X9] final deliverables`
