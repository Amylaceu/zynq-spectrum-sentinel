# 80 后续执行方案（2026-11-02 起，取代 runbook 中与之冲突的部分）

> **执行代理必读顺序**：`AGENTS.md` → `runbook/review_20261102.md`（评审结论）→ **本文件** → 需要细节时再查 `runbook/20–70` 原分册。
> **冲突规则**：本文件 > 原分册。特别是显示相关内容：原分册中的 J26 / RGB / VDMA / v_tc / rgb2lcd / GT9147 **一律作废**，以本文件第 2 节为准。
> **前提**：没有衰减器（C1 维持 SKIPPED）；红外遥控器部分不做；喇叭不用，耳机插 P1（LINE_OUT）。
> **步骤编号**：N0–N9。每步都标明**运行环境、前置条件、操作、产出文件、验收、排错、提交信息**。执行协议与 `AGENTS.md` §4 相同（日志写入 `logs/N*.log`，最多 3 轮，👤 步骤停下等人工）。

---

## 0. 优先级与里程碑

| 里程碑 | 包含步骤 | 达成后作品具备的能力 | 优先级 |
|---|---|---|---|
| **M-A 最小可提交作品** | N0, N1, N2, N3, N4, N5 | PL 实时 FFT + CFAR，硬件加速显示（≥ 15 fps），信号列表，E1/E10 对比数据 | **必须** |
| **M-B 完整功能** | N6, N7 | 信道化提取、HOC、分层调制识别、实时 FM 耳机监听 | 强烈建议 |
| **M-C 闭环与交付** | N8, N9 | 空口闭环 + 注噪 SNR 曲线、对比实验全集、技能包、报告、开源 | 必须（N9）；N8 强烈建议 |

**时间紧张时的裁剪顺序**（从最先裁剪开始）：余辉图 DPX → 全景扫频 → 告警 → 远程推流 → 教学 notebook 只保留 L1–L3 → HOC 改由 PS 计算（不做 HLS）。**M-A 和 N9 不可裁剪。**

---

## 1. 运行环境（所有 N 步骤共用）

| 项目 | 值 |
|---|---|
| PC | Windows，PowerShell 7（`pwsh`）；在仓库根目录执行 `. .\tools\env.ps1` |
| Vivado / Vitis | 2025.2（`$env:XILINX_ROOT`）；HLS 使用 `vitis-run --mode hls` |
| ADI 工程构建目录 | `build/work/adi_hdl/`（独立 checkout，**不得**改动 `third_party/hdl`） |
| 板端 | `xilinx@192.168.2.99`（以 `docs/board_info.md` 为准），PYNQ 2.7，Python 使用 `board_python`，代码目录 `/home/xilinx/sentinel` |
| 板端命令 | `.\tools\board.ps1 push / run "<cmd>" [-AsRoot] / pull board/measurements/...` |
| 已验证的位流 | `board/overlay/live_z20_lcd/`（AD9361 + J22 LCD 双页帧缓存），作为新工程的起点 |
| 当前天线 | RX1A 接 20–512 MHz 磁吸天线（FM）。TX 口在 N8 之前不接天线 |

---

## 2. 显示架构修订（替代原 P3.6 / P4.3 / P4.4.3）

**实际硬件**：ATK-MD0700 V2.4，SSD1963 控制器，8080 16 位并口，800×480，接 J22（引脚见 `src/hw/fmcomms2_z20_lcd_live/lcd_j22.xdc`）。SSD1963 自带帧存储，不需要 FPGA 持续扫描输出。

**新架构 `lcd8080_engine`**（替代 `lcd_j22_framebuffer.v`）：
```
                ┌─────────────────────────── lcd8080_engine ───────────────────────────┐
PS(AXI-Lite)──▶ │ 命令队列 FIFO（PS 写入：区域窗口 0x2A/0x2B、滚动 0x33/0x37、填充等）    │
PS(AXI BRAM)──▶ │ UI 层：文字/列表区，RGB332，按"脏矩形"局部刷新                        │──▶ 8080 总线 ──▶ SSD1963
PL spec_front ─▶│ 频谱区：直接由 dB 行 BRAM 生成像素（曲线/门限/目标框），无需帧缓存     │
PL spec_front ─▶│ 瀑布区：每帧只写一行（调色板 LUT），用 SSD1963 硬件垂直滚动              │
                └────────────────────────────────────────────────────────────────────────┘
```
- **8080 写周期**：`BUS_PHASE_CYCLES` 做成寄存器，可在运行时修改，默认 25（与当前已验证的值一致），逐档下调到稳定的最小值（N4 中实测）。
- **区域划分（800×480）**：频谱区 (0,0)–(560,160)；瀑布区 (0,160)–(560,400)；右侧 UI 区 (560,0)–(800,400)；底部状态栏 (0,400)–(800,480)。
- **刷新策略**：每帧依次写频谱区全部像素（560×160 = 89 600 像素）和瀑布区的 1 行（560 像素），UI 区只在内容变化时局部刷新。
- **帧率估算**（每像素约 3×P + 3 个周期，P = `BUS_PHASE_CYCLES`，50 MHz 时钟，每帧只写频谱区 89 600 像素加瀑布 1 行）：P = 25 时约 7 fps，P = 8 时约 20 fps，P = 4 时约 37 fps。对比现状：整屏 384 000 像素、P = 25 时只有 1.7 fps。**仅靠"局部刷新"一项，在不改总线时序的情况下就能提升约 4 倍**；再把 P 降到 8 就能达到 15 fps 以上的目标。在 N4 中实测确定，并把结果写进 E10。
- **触摸**：暂不实现（屏上触摸芯片型号未核实，`AGENTS.md` 规定不得猜测）。所有交互通过 SSH 命令或 Jupyter 完成。
- **引脚冲突检查结论**：J22 显示占用 C20…F21（摄像头排针 P3）、AA12、AB12、U10、Y4、AA4、Y5；与音频（U9/AA11/U6/AB11/U5，I2C A18/A19）、FMC（Bank33/34）、PL LED（H17/H18）**都不冲突**。

---

## N0 收尾与对齐（约 0.5 小时）

**运行环境**：PC
**操作**：
1. 在 `STATUS.md` 中把 G0 标为 DONE，备注写明：屏幕为 ATK-MD0700 SSD1963 J22 800×480；J7/J8 = 2.5V（已测）；RX1A 接 20–512 MHz 天线。
2. 更新 `AGENTS.md` §2"显示"一行为：`ATK-MD0700 V2.4（SSD1963，8080 16 位，800×480）接 J22；触摸暂不使用`。同步修改 `docs/hardware_bom.md` 的 A4 项。
3. `src/ps/models/weights/`：只提交 `*_metrics.json` 和 `*_history.json`，在 `.gitignore` 中加入 `src/ps/models/weights/*.pt`。
4. `STATUS.md` 末尾追加 N0–N9 的状态行（初始为 TODO）。
5. 在 `runbook/README.md` 的文件索引中加入 `review_20261102.md` 和 `80_next.md`，并注明"80 优先于 30–60 中与之冲突的内容"。

**验收**：`git status` 干净；`Select-String AGENTS.md -Pattern "SSD1963"` 有结果。
**提交**：`[N0] align docs with actual J22 SSD1963 display and review`

---

## N1 完成 G2：TX-DMA → BIST 数字回环逐位比对 + 统一 RF 封装（约 0.5–1 天）

**运行环境**：PC + 板端（使用 `live_z20_lcd` 位流，不需要重新构建）。**不经过射频，TX 天线口保持空置。**
**前置条件**：G2 现有的各项检查已通过（STATUS 中有记录）。

**操作**：
1. **统一封装** `src/ps/sentinel/rf/`：
   - `ad9361.py`：把 `board/scripts/*.py` 中重复的 ctypes 声明收敛到一个 `AD9361` 类，提供 `open()`、`close()`、`rx_lo`、`rate`、`rx_gain_mode`、`rssi()`、`tx_atten`、`bist_loopback(on)`、`bist_prbs()`；
   - `safety.py`：按 runbook P5.3 实现 `TxGuard`（air 模式下限 30 dB，cable 模式需要 `confirm_attenuator=True` 才能切换，下限 10 dB）；`AD9361.tx_atten` 的 setter **必须**经过 `TxGuard.check()`；
   - 在 `__exit__` 和 `atexit` 中：TX 衰减恢复为 89.75 dB，ENSM 回到 ALERT，RF 复位 GPIO 置 0；
   - 单元测试 `src/ps/tests/test_safety.py`：覆盖拒绝 29.75 dB、未确认时拒绝切换到 cable 模式、异常退出后 TX 关闭。
2. **TX-DMA 回环** `board/scripts/check_tx_loopback.py`：
   - 打开 AD9361 的数字回环：`ad9361_bist_loopback(phy, 1)`，即 TX 数据在 AD9361 数字接口内部直接回到 RX，**不经过射频，天线口不发射**；
   - TX DMA（ADI dac_dma，地址 0x7C420000，cyclic 模式）发送已知序列：先发计数器 ramp，再发 PN 序列，各 64 KiB；
   - RX DMA 接收 256 KiB，自动搜索对齐位置后逐样本比对，要求 I/Q 两路 **100% 一致**；
   - 运行期间持续读 TX 衰减，必须保持 89.75 dB；结束后关闭回环、复位 GPIO。
3. 生成 `board/measurements/tx_loopback.json` 和 `report/figures/tx_loopback.png`。

**命令**：
```powershell
. .\tools\env.ps1
.\.venv\Scripts\python -m pytest src/ps/tests -q *> logs/N1_pc_tests.log
.\tools\board.ps1 push
.\tools\board.ps1 run "python3 scripts/check_tx_loopback.py --rate 30.72e6 --out measurements/tx_loopback.json" -AsRoot *> logs/N1_tx_loopback.log
.\tools\board.ps1 pull board/measurements
```
**验收**：两种序列逐位一致；`tx_atten_mdb` 始终为 [89750, 89750]；PC 测试全部通过。通过后把 G2 标为 DONE（FM 实时耳机监听移到 N7，不再作为 G2 的条件）。
**排错**：
- 回环数据全零：确认 DAC 数据源选择寄存器（`axi_ad9361` DAC 通道的 `DATA_SEL`）设为 DMA，而不是内部 DDS；
- 数据有固定偏移：属于正常的流水延迟，用互相关对齐；
- 个别位错误：在 `scan_rx_timing.py` 的基础上增加 TX 方向的延迟扫描（寄存器 0x006/0x007 的 TX 部分）。

**提交**：`[N1] TX DMA digital loopback bit-exact and unified RF wrapper with TxGuard`

---

## N2 P3 基础设施 + `spec_front`（约 1–2 天）

**运行环境**：PC（Vivado xsim、Python）。不需要开发板。
**前置条件**：P2.2 / P2.3 / P2.8 已完成（参考数据在 `data/reference/spectrum`、`data/reference/cfar`）。

**操作**：
1. 按 `runbook/30_rtl_ip.md` P3.0 建立：`sim/scripts/run_xsim.ps1`、`tools/golden_compare.py`、`tools/regmap_codegen.py`、`build/scripts/package_ip.tcl`、`build/scripts/synth_module.tcl`。路径全部用 `$env:REPO` / `$::env(REPO)`。
2. `src/regs/spec_ctrl.yaml`：寄存器包括 `CTRL`（EN、WIN_SEL）、`AVG_SHIFT`、`DISP_DECIM`、`FRAME_CNT`（只读）、`VERSION` = 0x53500001。
3. `src/rtl/spectrum/`：
   - `spec_window.v`：窗函数 ROM（`.coe` 由 `sim/golden/spectrum.window_coefs` 导出），支持 BH4、Hann、矩形三种；
   - Xilinx `xfft` IP：2048 点，Pipelined Streaming，scaled，自然序输出。缩放方案必须与 `docs/spectrum_numeric.md` 的约定完全一致；
   - `spec_power.v`：计算 I² + Q² 并截位；
   - `spec_welch.v`：BRAM 帧缓存实现指数平均；
   - `spec_db.v`：dB 转换（Q8.8，前导零加查表）；
   - `spec_front.v`：顶层。输入 32 位 IQ 的 AXIS 流；输出 (a) `m_axis_pwr`（uint32 线性功率，送 CFAR），(b) `m_axis_db`（Q8.8，送显示）。fftshift 在输出端做，dB 结果抽取到 560 个点送显示（取每段最大值）。
4. testbench `sim/tb/tb_spec_front.sv`：输入 `data/reference/spectrum/in_*.hex`，比对：FFT 输出与 C 模型逐位一致；功率、Welch、dB 也逐位一致；随机拉低 `tready` 测试背压。
5. 单模块综合：150 MHz 约束下 WNS ≥ 0，记录资源用量。

**命令**：
```powershell
.\sim\scripts\run_xsim.ps1 -Top tb_spec_front -Srcs (Get-Content sim/tb/tb_spec_front.files) *> logs/N2_sim.log
python tools/golden_compare.py --exp data/reference/spectrum/exp_db.hex --got sim/results/spec_front_db.hex --mode exact *> logs/N2_cmp.log
vivado -mode batch -source build/scripts/synth_module.tcl -tclargs spec_front src/rtl/spectrum 150 *> logs/N2_synth.log
```
**验收**：PASS，一致率 100%，单模块 WNS ≥ 0；结果写入 `sim/results/SUMMARY.md`。
**提交**：`[N2] spec_front bit-exact against golden model`

---

## N3 `cfar_core` + 聚类 + 占用度（约 1 天）

**运行环境**：PC。
**操作**：按 `runbook/30_rtl_ip.md` 中 P3.3.a–e 的要求执行（规格写在 `src/rtl/cfar/README.md`；CA/GO/SO 三种模式，wrap 边界，40 位窗口和，一个 DSP 做门限乘法，聚类状态机，双缓冲目标列表，`irq_list_ready`）。另外增加：
- `m_axis_thr`：dB 形式的门限，送显示画门限线；
- 目标列表同时写入 AXI-Lite 可读的 32×16 B 窗口，PS 不用 DMA 也能读取（简化软件）。

**命令**：同 N2，模块名换成 `tb_cfar_core`、`cfar_core`。
**验收**：6 组（3 种模式 × 2 种边界）逐位一致，150 MHz 下 WNS ≥ 0。
**提交**：`[N3] cfar_core with clustering bit-exact`

---

## N4 集成 `sentinel_v1` 位流：PL 实时频谱 + CFAR + 新显示引擎（约 2 天）

**运行环境**：PC（Vivado 构建）+ 板端（上板验收）。
**前置条件**：N2、N3 完成。

**操作**：
1. 新建覆盖层 `src/hw/sentinel_v1/`，内容从 `src/hw/fmcomms2_z20_lcd_live/` 复制（保留已验证的 RF 约束、G22 FMC_PWRGD、J22 引脚）。
2. 新增 RTL：
   - `src/rtl/adc_tap/adc_tap.v`：从 `axi_ad9361` 取 I0/Q0，12 位数据左对齐到 16 位（**先确认 ADI 核的输出格式**，写入 `docs/adc_format.md`），经 `xpm_fifo_async` 跨到 `dsp_clk`（FCLK2 = 150 MHz），带 overflow 粘滞标志；
   - `src/rtl/src_mux/`：4 种模式（RF、回放、测试源、RF + 注噪），按 `runbook/30_rtl_ip.md` P3.1，包括 MODE = 3 的定点注噪；
   - `src/rtl/lcd/lcd8080_engine.v`：按本文第 2 节实现。复用 `lcd_j22_framebuffer.v` 中已验证的 SSD1963 初始化 ROM；`BUS_PHASE_CYCLES` 改为寄存器；增加区域窗口命令、频谱行渲染器、瀑布单行写入和硬件滚动；
   - `src/rtl/perf/perf_mon.v`：样本计数、FIFO 溢出、FFT 帧数、CFAR 命中数、检测时延（从测试源插入的标记样本到列表就绪中断）。
3. BD（`src/hw/sentinel_v1/sentinel_bd.tcl`）：
   - FCLK2 = 150 MHz；
   - `adc_tap → FIFO → src_mux → spec_front → (cfar_core, lcd8080_engine)`；
   - AXI-Lite 地址沿用 `runbook/40_integration.md` 的地址表，显示引擎用 0x43C60000；
   - UI 区使用 AXI BRAM 32 KiB（240×400 RGB332，96 KB 太大时改为 RGB111 或分块），**不再使用 256 KiB 双页帧缓存**；
   - 中断经过 `axi_intc`（参考 `vendor/atk/pynq_ref/base/ready_to_test/base.tcl` 的结构）。
4. 构建脚本 `tools/build_sentinel_v1.ps1`，参照 `tools/build_lcd_live.ps1` 编写，产物收集到 `board/overlay/sentinel_v1/`（bit / hwh / xsa / sha256 / provenance）。
5. 板端程序 `src/ps/sentinel/app/monitor.py`：
   - 加载 Overlay → `AD9361.open()` → 读取目标列表，在 UI 区显示信号列表（频率、带宽、峰值 dBFS）→ 在状态栏显示帧率、温度、overflow；
   - 支持 `--source rf|test|replay`，`--lo`，`--rate`，`--bus-phase N`。
6. **E10 实测**（`board/scripts/bench_lcd.py`）：对 `BUS_PHASE_CYCLES` = 25 / 12 / 8 / 6 / 4 / 3 / 2 每一档运行 10 秒，记录帧率；👤 用户逐档目视检查是否有错点或花屏。取"稳定档位再加 1 档余量"作为默认值。

**命令**：
```powershell
pwsh tools/build_sentinel_v1.ps1 -Attempt 1 *> logs/N4_build.log          # 后台运行，约 30–60 分钟
.\tools\board.ps1 push
.\tools\board.ps1 run "python3 -m sentinel.app.selftest_v1 --source test --out measurements/n4_selftest.json" -AsRoot
.\tools\board.ps1 run "python3 scripts/bench_lcd.py --phases 25,12,8,6,4,3,2 --out measurements/n4_lcd_bench.json" -AsRoot
.\tools\board.ps1 run "sh scripts/run_monitor.sh --source rf --lo 98e6" -AsRoot
.\tools\board.ps1 pull board/measurements
```
**验收**：
- 构建：WNS ≥ 0、WHS ≥ 0，BRAM ≤ 110/140，LUT ≤ 75%；
- `selftest_v1 --source test`：测试源单音的峰值频点误差 ≤ 1 bin；3 个单音得到 3 个目标；回放 `data/reference/spectrum` 时，PL 输出的功率谱与参考值逐位一致；overflow = 0；
- 👤 RF 模式下屏幕显示 FM 广播频谱（PL 计算），瀑布图平滑滚动，信号列表能列出电台，帧率 ≥ 15 fps（达不到时如实记录，并给出瓶颈分析）；
- 资源和时序写入 `build/reports/sentinel_v1/SUMMARY.md`。

**排错**：
- 屏幕花屏：把 `BUS_PHASE_CYCLES` 调回 25 确认显示逻辑正确，再逐档往下调；
- overflow 不为 0：检查 `dsp_clk` 是否为 150 MHz，以及 FIFO 深度；
- BRAM 超限：Welch 帧缓存改用 `ultra`/LUTRAM，或者 UI 改用 RGB111。

**提交**：`[N4] sentinel_v1: PL FFT/CFAR with direct SSD1963 rendering`

---

## N5 M-A 收口：E1 / E10 对比数据 + G1 验收（约 0.5 天）

**运行环境**：板端 + PC。
**操作**：
1. **E1**（频谱和 CFAR，CPU 与 PL 对比）：CPU 基线来自 `board/measurements/p5_cpu_baseline.json`，以及当前 `lcd_live` 的 1.67 fps；PL 数据来自 `perf_mon` 的帧计数和检测时延。表中要包括每秒处理的 FFT 帧数（PL 预期约 15 000 帧/s，CPU 约几十帧/s）。
2. **E10**（显示）：旧方案（CPU 渲染加 256 KiB 帧缓存，1.67 fps，68 个 BRAM）对比新方案（PL 直接渲染，N4 实测帧率和 BRAM 用量）。
3. 生成 `report/opt_tables.md` 中 E1 和 E10 两节，以及 `report/figures/e1_*.png`、`e10_*.png`。
4. 在 `STATUS.md` 中把 G1 标为 DONE（N4 的测试源和回放自检就是 G1）。

**验收**：两张对比表齐全，数据都能追溯到 `board/measurements/*.json`。
**提交**：`[N5] milestone A: PL acceleration and display benchmarks`

> **到 M-A 为止，作品已经可以提交**：真实射频接收 → PL 实时 FFT/CFAR → 硬件直接驱动显示 → 信号列表，并且有加速比、资源和时序证据。之后的步骤用于提高得分。

---

## N6 调制识别 v2：分层识别 + 盲同步（P2.9b，约 1–2 天）

**运行环境**：PC（训练）+ 板端（INT8 推理）。
**原因**：见 `review_20261102.md` R4。P2.9 的三轮尝试已经用完，本步骤作为新方法 P2.9b 重新计数，最多 3 轮，**阈值仍为 SNR = 10 dB 时总体准确率 ≥ 88%**，不得放宽。

**操作**：
1. **数据**：复用 `data/synthetic` 的生成器，捕获长度改为 **4096 点**（`CAPTURE_LEN` 在 `params.py` 中新增 `CAPTURE_LEN_AMC=4096`，原 1024 保留给 HOC 和 RTL）。
2. **第一层**（`src/ps/models/amc_l1.py`）：CNN + HOC，输出 7 个大类：`PSK | QAM | 2FSK | GFSK | OOK | AM | FM`。BPSK 单独作为第 8 类（它和 QPSK/8PSK 在 C40 上区别明显）。
3. **第二层**（`src/ps/sentinel/amc/fine.py`，纯 NumPy，不训练）：
   - 盲符号率估计：|x|² 的 FFT 中寻找循环谱线；
   - 频偏校正：PSK 用 M 次方法（M = 4 或 8），QAM 用四次方法；
   - Gardner 定时恢复，抽成 1 点/符号；
   - 判断阶数：
     - PSK 族：比较 |C40|/C21² 与 |C80|，QPSK 的 C40 约为 1，8PSK 约为 0，或者用相位直方图的 4 峰/8 峰判断；
     - QAM 族：幅度直方图的环数（16QAM 有 3 个环，64QAM 有 9 个环），或者用 C42 判断（理论值 −0.68 对 −0.619，区别较小，以环数为主）。
4. **评估** `python -m src.ps.models.amc_v2_eval`：在原测试集划分上输出总体准确率、10 类混淆矩阵、准确率–SNR 曲线；同时和 v1 画在同一张图里（实验 E7）。
5. 通过后导出第一层的 INT8 模型（`export_int8.py`，BN 融合，per-channel），并编写 `src/ps/sentinel/amc/infer_np.py`；校验 INT8 相对 FP32 的准确率下降 ≤ 1%。

**命令**：
```powershell
.\.venv\Scripts\python -m src.ps.models.make_dataset --capture-len 4096 --out data/synthetic/amc_v2 *> logs/N6_dataset.log
.\.venv\Scripts\python -m src.ps.models.amc_l1 --data data/synthetic/amc_v2 --epochs 30 --out src/ps/models/weights *> logs/N6_l1_train.log
.\.venv\Scripts\python -m src.ps.models.amc_v2_eval --data data/synthetic/amc_v2 --l1 src/ps/models/weights/amc_l1_fp32.pt --out report/results/amc_v2.json *> logs/N6_eval.log
```
**验收**：SNR = 10 dB 时总体准确率 ≥ 88%，INT8 准确率下降 ≤ 1%。三轮仍未达标时：如实记录到 `docs/amc_attempts.md`，并把**实际准确率**写进报告（7 个大类的准确率通常远高于 10 类，可以作为"大类识别"指标单独报告），标记 FAIL 后**继续执行 N7**，不要卡住。
**提交**：`[N6] hierarchical AMC with blind synchronization (P2.9b)`

---

## N7 信道化提取 + HOC + 实时 FM 耳机监听（约 2–3 天）

**运行环境**：PC + 板端。
**前置条件**：N4 完成。

**操作**（按顺序，每个模块都要经过黄金模型比对 → 仿真 → 集成）：
1. `pfb_os2`（P3.4）+ `nco_capture`（P3.5）：PS 根据 CFAR 目标列表选择信道号和 NCO 频率，PL 输出 4096 点捕获帧（DMA 送到 PS，这些 IQ 就是 N6 识别器的输入）。
2. `hoc_moments`（P3.7，HLS）：时间不够时降级为在 PS 中用 NumPy 计算（`sim/golden/hoc.py` 本身就是 NumPy 实现），并在报告中说明。
3. `demod_audio`（P3.8）：
   - 对选中信道做 FM 鉴相（CORDIC），去加重（75 µs），抽取到 48 kHz，经 I2S 输出到 ES8388；
   - 引脚：`aud_mclk` U9、`aud_bclk` AA11、`aud_lrc` U6、`aud_dacdat` AB11、`aud_adcdat` U5（输入，可以不接）；
   - ES8388 的 I2C（A18/A19，与 EEPROM/RTC 共用总线，器件地址 0x10）由 PS 通过 AXI IIC 配置，初始化序列参考 `vendor/atk/pynq_ref/ip_repo/audio_codec_ctrl_v1.0`；
   - 只打开 OUT1（耳机）；软件中保留 OUT2 开关，但默认关闭（喇叭暂不使用）。
4. 整合成 `sentinel_v2` 位流。`monitor.py` 增加：自动选择最强的目标 → 捕获 → 识别 → 在列表中显示调制类型和置信度；`--listen <freq>` 实时监听。
5. 👤 **验收**：耳机插 P1（LINE_OUT），`--listen 95.8e6`（或本地其他电台），能实时听到连续的广播，没有明显卡顿。

**命令**（构建和上板流程与 N4 相同，标签改为 `sentinel_v2`）：
```powershell
pwsh tools/build_sentinel_v2.ps1 -Attempt 1 *> logs/N7_build.log
.\tools\board.ps1 push
.\tools\board.ps1 run "sh scripts/run_monitor.sh --source rf --lo 98e6 --listen 95.8e6 --amc on" -AsRoot
```
**验收**：PFB 和 NCO 逐位一致；构建时序通过；👤 实时听到 FM 广播；屏幕上 FM 电台被识别为 FM。
**提交**：`[N7] channelizer capture, HOC and real-time FM audio`

---

## N8 G3：空口闭环 + 数字注噪 SNR 扫描（约 1 天，不需要衰减器）

**运行环境**：板端 + PC。
**前置条件**：N1（TxGuard、TX DMA）、N4（MODE = 3 注噪）、N6/N7（识别）。

### N8.1 👤 接线（硬件见本文附录 A）
- **方案 1（2.45 GHz，推荐）**：TX1A 和 RX1A 各接一根 **2.4 GHz 板状天线**，两根相距 ≥ 30 cm，摆成同一方向；
- **方案 2（433.92 MHz）**：TX1A 和 RX1A 各接一根 **20–512 MHz 磁吸天线**，相距 ≥ 50 cm，**不要吸在同一块金属板上**；
- 任何情况下都**禁止**用 SMA 线把 TX 和 RX 直接相连。

### N8.2 操作
按 `runbook/60_board.md` G3.1b、G3.2、G3.2b 执行。补充要求：
1. `loopback_eval calibrate`：TX 衰减从 89 dB 起，每步减小 3 dB，直到 RX 端 SNR ≥ 25 dB，或者到达 30 dB 的下限；RSSI > −30 dBm 时立即中止，并恢复 89.75 dB；
2. `loopback_eval sweep`：固定 TX 衰减，用 MODE = 3 注噪扫描 SNR（−4 到 20 dB，步长 2 dB），10 类调制 × 13 个 SNR 点 × 200 段，同时保存带标签的数据集 `data/captured/air_v1`；
3. 用 `air_v1` 微调识别模型（实验 E9：只用仿真数据 vs 加入实采数据）；
4. 在空闲频段测实测 Pfa；用注噪测 Pd 曲线；
5. **真实外部信号演示（可选）**：如果用户买到了 433.92 MHz 固定码遥控器（见附录 B），设 `--lo 433.92e6`，按下按键后，屏幕上应出现 OOK 突发信号并被识别为 OOK。保存截图和 `board/measurements/n8_ook_remote.json`。**这是纯接收，不涉及 TX**；
6. 1 小时稳定性测试（monitor 模式，overflow 必须为 0）；
7. `python tools/make_final_metrics.py --mode air` 生成 `report/final_metrics.md`。

**验收**：混淆矩阵、准确率–SNR 曲线（叠加仿真曲线）、Pd、Pfa、1 小时稳定性数据齐全。C1 保持 SKIPPED。
**提交**：`[N8] G3 over-the-air loopback with digital noise injection`

---

## N9 交付（P7，约 2 天）

按 `runbook/70_deliver.md` 执行。需要做的调整：
- **P7.1**：E1–E12 中，没做的实验在表中明确写"未做及原因"，不要留空。
- **P7.2 技能包**：S7 改为 **`pynq_lcd8080_kit`**，即 SSD1963/8080 并口屏在 PYNQ 下的驱动骨架（初始化 ROM、区域写、硬件滚动、`BUS_PHASE` 标定方法），可以迁移到任何 8080 接口屏；其余各项不变。
- **P7.4 报告**中必须写进去的"判断依据"：
  - 为什么接口用 2.5V（HR Bank 的 LVDS 限制）；
  - 为什么不用衰减器也能得到可信的 SNR 曲线（数字注噪方法）；
  - 为什么调制识别改成分层结构（v1 混淆矩阵的证据）；
  - 为什么显示改为 PL 直接驱动（1.67 fps 瓶颈的计算过程）。
- **P7.5 README**：硬件清单按附录 A 填写；"无需射频板的复现路径"使用 `--source test|replay`。
- **P7.6 复现**：在干净目录中执行 `build_sentinel_v2.ps1`，或在最终版本基础上提供 `build_all.ps1`。
- 最后执行 `python tools/make_handoff_zip.py` 生成交付包。

---

## 附录 A：最终硬件清单（按无衰减器、无喇叭、无红外遥控确定）

| 用途 | 器材 | 接口 |
|---|---|---|
| 主板 | 正点原子 Z20（xc7z020clg484-2），J7/J8 = 2.5V | — |
| 射频 | AD-FMCOMMS3-EBZ（加铜柱支撑） | J31 FMC |
| 显示 | ATK-MD0700 V2.4，SSD1963，800×480 | J22 / P3 |
| FM、VHF/UHF 接收（主力） | 20–512 MHz 磁吸天线（粗长那根） | RX1A |
| 433 MHz 空口闭环（可选） | 20–512 MHz 磁吸天线 ×2 | TX1A + RX1A，相距 ≥ 50 cm |
| 2.4 GHz 接收与空口闭环 | 2.4 GHz 板状天线 ×2（或宽带胶棒 ×2） | TX1A + RX1A，相距 ≥ 30 cm |
| 宽频扫频与演示 | 宽带胶棒天线 | RX1A |
| 监听 | 3.5 mm 有线耳机 | P1（LINE_OUT） |
| 外部 OOK 演示（可选） | 433.92 MHz 固定码对拷遥控器 | 无线发射，纯接收 |
| 不使用 | 衰减器、PE4302、喇叭、红外遥控器、OV5640 | — |

## 附录 B：外部遥控器的使用约束
- 只作为**被测信号源**（OOK/ASK），设备只接收，不发射。
- 选 **433.92 MHz** 版本（在 ISM 频段内，天线和闭环频点一致）；不选 315 MHz。
- 遥控器不需要"对拷"学习任何真实门禁的编码，用出厂默认码即可。不要拿它去学习或复制他人的门禁、车库遥控器。
