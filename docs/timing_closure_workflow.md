# 后续功能的时序与流水线执行准则（Vivado 2025.2）

本文件是后续功能的工程门禁；现以 95_final.md 的 Z10 为先。用户已要求中止 Y3 第三轮构建并先执行 Z10；冻结输入、日志和在途源文件保持原状，中断不算时序 FAIL。没有通过整机时序、CDC、引脚审计的新位流不得上板。

## 已核实的基线与判断

| 来源 | 实测 | 对应决策 |
|---|---|---|
| `report/results/timing_v1d_baseline.rpt`（从 `build/reports/sentinel_v1d/final_timing.rpt` 原样归档；哈希见测量 JSON） | 整机 WNS +0.092 ns、WHS +0.037 ns；LUT 35,568 / 66.86%（`board/overlay/sentinel_v1d/acceptance.json`） | 保留已验收 v1d 位流；新功能优先复用现有 PS/PL 接口。新增硬件以 LUT 75% 作为内部转 PS 预警线，不把预警当正式验收。 |
| 同一时序报告，100 MHz AXI 控制域 | 最差 setup +0.217 ns，PS7→`x5_ctrl_axi_cdc`，逻辑 0 级、布线占 88.1% | 不向 CDC 协议内部随意插数据寄存器；先检查布局、扇出、互连资源及合法的物理优化。 |
| 同一时序报告，150 MHz DSP 域 | 最差 setup +0.098 ns，CFAR `search_index`→FSM CE，10 级逻辑、布线占 68.1% | 若此路径在新版本中成为负 slack，才以一级“比较/决策”分段作为首个 RTL 候选；先独立仿真，再整机集成。 |
| 同一时序报告，AD9361 `rx_clk` 域 | 全局最差 +0.092 ns 是 ADI TX 通路异步复位的 recovery 检查，布线占 85.7%、扇出约 660 | 数据流水线不能修复 recovery；不修改 `third_party/`。核对复位约束与释放方式，必要时只在自有覆盖层/接口上改动并重新做 CDC 与板测。 |

当前 `fm_phase_y3.v` 是逐迭代 CORDIC；`fm_audio_filter_y3.v` 已把 RAM 读取、乘法、累加、去加重减法/乘法/更新分成状态。是否再加一级，以 Y3 整机**实际**关键路径为依据。组件综合通过、或者看到单一路径 slack 为正，均不等于完整音频链可用。

## 后续功能的硬件预算

1. **Y3**：第三轮按用户新要求中止，作为中断构建保留日志。先完成 Z10 的 100 MHz 基线，再重新评估 Y3-S；1 kHz/3 秒出声和连续 5 分钟都需要独立验证。
2. **Y4**：优先使用当前位流已有的 TX DMA、TxGuard、注噪/测试源能力。先核查功能存在，再决定是否真的需要改 PL；射频操作仍须按配置 B/C 获得用户确认。
3. **Z1/Z3/Z4/Y5–Y7**：一键演示、占用度告警、Web 监看、PS 扫频和报告优先在 PS 端落地。Z2 UI 优先使用既有 J22 显示数据接口；仅当现有接口无法表达必需画面时，提交最小 PL 修改和新增时序预算。
4. 固定 3.84 MSPS 基线；当前阶段不引入 30.72 MSPS 整条 PL 链、第二屏或新时钟域。每次变更只引入一项新硬件接口，并记录 LUT/FF/BRAM/DSP 与每个时钟域的 WNS/WHS 差值。

本机约 23.8 GB RAM、20 个逻辑处理器。Z10 的独立 v2 工程默认 OOC/实现并行 6、maxThreads 8；先监控可用内存与峰值，出现链接崩溃/内存不足时在下一轮降到 4。旧 Y3 脚本和冻结输入不改。同一项目目录不同时运行两个 Vivado 实例。并行度仅影响等待时间，不等于时序修复。

## 四道门禁：早发现、少跑完整布线

| 门禁 | 操作 | 继续条件 |
|---|---|---|
| G0 功能 | 黄金向量/自检/背压/复位仿真；对流式通路比较数据与每个 beat 的 `tvalid/tready/tlast/tuser` | 零丢样、零重复、输出次序与约定延迟一致；失败不启动 Vivado 整机实现。 |
| G1 模块 | 对变更模块进行 OOC 综合和局部时序、资源审计；检查 DSP/BRAM 推断 | 核心功能等价且无明显新增关键长组合路径。OOC 结果仅作筛选，不是整机验收。 |
| G2 整机早期 | 综合后查看 `report_timing_summary`、`report_methodology`、`report_cdc`；布局后查看最差路径、逻辑/布线比例、`report_qor_suggestions` | 逐条解释负 slack 和新警告；综合/布局 slack 是估计值，不以任意固定阈值自动判死刑，由路径性质决定是否继续。 |
| G3 整机签核 | 完整布线后检查 setup/hold WNS、WHS ≥ 0；另查 CDC、DRC、约束、音频/射频/LCD 引脚，原有板测回归 | 只有全部通过才生成可部署位流；JSON + SHA256 归档。 |

已有最终报告的快速分诊（只读输入；输出是新的证据文件）：

```powershell
python tools/timing_triage.py report/results/timing_v1d_baseline.rpt --stage route --output board/measurements/timing_v1d_baseline.json
```

上面是首次生成命令，已有文件时会拒绝覆盖。交接设备只需校验 `board/measurements/timing_v1d_baseline.json.sha256`，并核对 JSON 内的报告哈希。对未来综合或布局报告传 `--stage synth` / `--stage placed`，工具仅输出诊断，不作最终签核；`--stage route` 才给出基础 WNS/WHS 门禁。不要把这份结果当作 CDC/管脚/板测收据。

## 什么时候以及怎样加寄存器

- **先看路径类型。** 逻辑级数多、运算链长且 setup 失败时，优先分割最长组合链；布线占比高时先检查扇出、布局和拥塞；异步 reset recovery/hold/CDC 路径不能靠给数据流加流水线解决。不能靠放宽时钟或随意 `set_false_path` 制造“通过”。
- **先加一级，不预设“插几级”。** 对 CFAR `SEARCH` 候选，可把读表/比较与位置更新/FSM 转换分成相邻状态，候选值、索引和决策在同一时钟锁存。控制状态与数据一起延后一拍，并核对吞吐率、最多 32 项排序的比较结果和 AXI 背压。只有一级的局部/整机证据表明仍不足时才评估第二级。
- **流式接口完整对齐。** 数据、`tvalid`、`tlast`、`tuser`、样本序号及配置快照应处于同一流水级；`tready` 必须由合法的弹性缓冲/skid FIFO 协议处理，不可只对它打一拍。对帧边界、复位、连续有效及随时反压做逐拍断言/黄金比较。增加流水后更新 PS 侧“首次结果时延”定义，不改变射频样本时间戳的语义。
- **反馈环须证明速率。** CFAR 排序 FSM 或 FM 递归去加重属于反馈路径；增加状态会改变每个样本的处理周期。验证持续 3.84 MSPS 上游、480 kSPS 分信道输入和 48 kHz 音频输出下不溢出、不掉帧。跨时钟边界继续使用已有 CDC/FIFO，不将普通寄存器当同步器。

若 v2 报告显示新的负 slack，先记录首条失败路径的起点、终点、Path Type、逻辑级数、布线占比和所属时钟域，再改对应的自有 RTL。每次只做一个可对比的版本，保留旧位流和证据。增量实现只对小幅改动、相同工具版本和高复用的已签核 checkpoint 尝试；不能直接把 150 MHz v1d DCP 当作 100 MHz 的已验证参考。降低 DSP 时钟不会改善独立的 AD9361 RX_CLK/复位 recovery 路径，+1.0 ns 全局 WNS 必须实测，不能由频率差推算。

参考：[AMD Vivado UG906：Report Timing Summary](https://docs.amd.com/r/2025.2-English/ug906-vivado-design-analysis/Report-Timing-Summary)、[AMD UG949：设计方法](https://docs.amd.com/r/2025.2-English/ug949-vivado-design-methodology)、[AMD UG986：增量实现](https://docs.amd.com/r/2025.2-English/ug986-vivado-tutorial-implementation/Step-3-Turning-on-Incremental-Implementation)；具体工具命令以本机 2025.2 `-help` 为准。
