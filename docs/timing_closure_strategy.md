# 时序收敛策略（2026-11-03）

## 1. 现状诊断
| 现象 | 证据 | 判断 |
|---|---|---|
| 处理时钟 `dsp_clk` 为 150 MHz（外部 50 MHz 经 MMCM 生成） | `src/hw/sentinel_v1d/sentinel_bd.tcl` | **时钟远超需求**：系统只运行在 3.84 MSPS，150 MHz 下每个样本有 39 个周期，绝大部分时间在空等 |
| X2 r2 最差路径 −0.709 ns 位于 `cfar_core/detector/index_pipe` | `build/reports/sentinel_v1c/retry_r2_timing.rpt` | 逻辑深、扇出大，属于 150 MHz 下的结构问题 |
| −0.303 ns 位于 `adc_tap` 的 XPM FIFO 复位同步器 | 同上 | 复位跨时钟路径，约束或结构不当 |
| AXI-Lite CDC 路径中走线占 87.9% | 同上 | 布局分散、布线拥挤（LUT 已 58%），不是逻辑本身慢 |
| 构建使用 `ADI_MAX_OOC_JOBS=1`，主机有 20 线程、24 GB 内存 | `tools/build_sentinel_*.ps1` | **构建慢的主要原因之一**：几十个 OOC 子模块串行综合 |
| Z2 链接时两次崩溃（ACCESS_VIOLATION） | STATUS Y2 行 | 可能与内存或 Vivado 2025.2 和 ADI 2025.1 的版本差异有关 |

## 2. 解决方案（按收益从高到低）

### T1 把 `dsp_clk` 从 150 MHz 降到 100 MHz（收益最大，强烈建议）
- **为什么可行**：3.84 MSPS 下，100 MHz 每个样本仍有 26 个周期。FFT 按每周期 1 个样本流水；CFAR 的串行处理在 150 MHz 时上限约 29.9 MSPS，到 100 MHz 约 19.9 MSPS，仍是需求的 5 倍以上。PFB 的时分复用 MAC 同样有充足余量。
- **预期收益**：同一 DSP 时钟域内的单周期 setup 预算从约 6.67 ns 增至 10 ns。实际裕量还受重新布局、布线及抖动影响；CPU、AD9361 RX、LCD、音频域及复位 recovery/hold 不因此获得 3.33 ns。后续功能仍需逐项做仿真、资源和整机时序审计。
- **改动**：
  1. `sentinel_bd.tcl` 中 `CLKOUT1_REQUESTED_OUT_FREQ 150.000` 改为 `100.000`（50 MHz 整数倍频，MMCM 抖动更小）；
  2. 所有和处理时钟频率有关的**软件常量**改为从一个参数读取（`params.py` 中新增 `DSP_CLK_HZ = 100_000_000`），包括：`src_mux` 测试源和回放的节拍分频值（RATE_DIV）、`perf_mon` 周期到时间的换算、时延统计、帧率计算；
  3. T1 只调整时钟和参数，数值算法保持不变；实际执行还包含 T4 的复位与 CFAR 结构修改，因此必须另跑 ADC、CFAR 黄金比较与背压仿真，不能沿用旧结论；
  4. 已通过的 v1b/v1d 位流保留不动；新工程标签为 `sentinel_v2_100m`。
- **验收**：WNS ≥ +1.0 ns（目标 +2 ns 以上）；板端单音、三音、回放 8192 字零错；3.84 MSPS 实时显示的 SAMPLE_DROP = 0。

### T2 并行构建（构建时间预计缩短 50–70%）
- `ADI_MAX_OOC_JOBS` 从 1 改为 **6**（24 GB 内存，每个 OOC 进程约 1.5–2.5 GB，留出余量）；
- `launch_runs synth_1/impl_1 -jobs 6`；
- Vivado 全局线程：`set_param general.maxThreads 8`。
- 如果出现内存不足或链接崩溃，先核对内存及异常日志，再评估把 OOC_JOBS 降到 4；并行度不是时序修复。启动阶段工具错误与完整实现的时序轮次分开记录，不能将工具错误记成 WNS 不达标。

### T3 复用已经综合过的结果
- ADI IP 与自研 IP 使用 OOC 缓存。**不要在每轮构建前清空工程**；封装 IP 修改后重新打包对应模块。BD module reference 的外部 HDL 修改不一定使 `NEEDS_REFRESH` 变为真，必须核对输入哈希并显式重建变化模块；ADC 已提供 `-RefreshAdc` 入口。
- 只改约束或实现策略时：保留 `synth_1`，只重跑 `impl_1`（`reset_run impl_1; launch_runs impl_1`）。
- 启用增量实现：以上一次通过的 `*_routed.dcp` 作为参考（`set_property incremental_checkpoint <dcp> [get_runs impl_1]`）。改动越小，布线越快、越稳定。

### T4 修复两条已知的结构性违例
1. **`adc_tap` 的 FIFO 复位**：当前复位信号由 `adc_clk` 域的同步器产生，同时还被 `dsp_aresetn` 异步清零。应改为：
   - 用 `xpm_cdc_async_rst` 分别为两个时钟域生成复位；
   - XPM FIFO 的 `rst` 只接写时钟域的同步复位（XPM 内部会自己处理读侧）；
   - 不要对这条路径加 `set_false_path` 掩盖问题。
2. **`cfar_core` 检测器**：把 `index_pipe` 的比较和多路选择拆成两级流水，对高扇出的配置寄存器（MODE、ALPHA 等）复制一份或加一级寄存器（这些寄存器在帧边界才变化，可以多打一拍）。X2 的 `cfgpipe` 和 `maskpipe` 候选已经做过类似实验，可以直接复用。

### T5 降低布线拥挤
- 所有 AXI-Lite 寄存器块统一挂在 100 MHz 的 CPU 时钟域上，处理域通过少量同步信号读取配置。这样可以减少 AXI 时钟转换器的数量，每个转换器都带来一组跨时钟路径；
- 对 PFB、FFT、CFAR 这组处理核心加一个 Pblock，把它们约束在器件的同一区域，避免被拉散；
- 实现策略：先用 `Performance_ExplorePostRoutePhysOpt`；不收敛时再试 `Congestion_SpreadLogic_high`（ADI 原工程使用的策略）。

### T6 开发流程：先做模块级预检，再做整机构建
1. 模块改动后先以真实时钟约束做 OOC 综合/实现筛查。局部裕量只表明该模块的局部结果，不能当作整机或板测通过；耗时依据实际规模记录，不承诺几分钟；
2. 整机构建完成后自动运行 `report_qor_suggestions` 和 `report_design_analysis -congestion`，结果写入日志，下一轮据此改动，不要盲目重跑；
3. 每一轮只改一个因素，记录"改了什么 → WNS 和 WHS 如何变化"，这些记录可以直接作为报告中"优化过程"的素材。

## 3. 不建议的做法
- 加大量 `set_false_path` 或 `set_multicycle_path` 来"消除"违例（掩盖问题，答辩时会被问到）；
- 在 150 MHz 下继续换策略盲目重跑（X2 已经证明收益很小）；
- 每次都从零构建整个工程。

## 4. 预期效果
| 项目 | 现在 | 采用 T1–T3 后 |
|---|---|---|
| 最差裕量 | −0.709 ns ~ +0.09 ns（既有测量） | 目标 ≥ +1 ns，必须取整机实测值 |
| 单次整机构建 | 1–2 小时以上 | 记录本机实测耗时和缓存复用情况，不保证固定时长 |
| 后续加入 FM / I2S / UI | 每加一项都可能破坏时序 | 模块预检、缓存复用与 PS 优先；每次硬件变更仍须签核 |
| 对指标的影响 | — | 保持 3.84 MSPS 目标；时延、丢样和显示帧率必须重新验收；X2 全带宽继续延期 |
