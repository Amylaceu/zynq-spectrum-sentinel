# P1 基础工程基线（只追加，不覆盖）

## 2026-11-02 / base_z20

器件 `xc7z020clg484-2`，Vivado 2025.2；ADI HDL 固定提交
`b62abeff22d613d08e1aeb7f94850ab6a6576a74`。这是电脑端构建结果，尚未下载或上板验收。

| 项目 | 基线 |
|---|---:|
| Slice LUTs | 10,386 / 53,200（19.52%） |
| Slice Registers | 16,192 / 106,400（15.22%） |
| Block RAM Tile | 4 / 140（2.86%） |
| DSP48E1 | 28 / 220（12.73%） |
| Bonded IOB | 55 / 200（27.50%） |
| Routed WNS / TNS | +0.524 ns / 0 ns |
| Routed WHS / THS | +0.008 ns / 0 ns |
| Pulse width slack | +0.264 ns |
| 无时钟寄存器 / 未约束内部端点 | 0 / 0 |
| ADC_INIT_DELAY | 23（仅初值，G2 必须做接口校准） |

资源来源：`build/reports/base_z20/system_top_utilization_placed.rpt`（布局后）；
时序来源：`build/reports/base_z20/system_top_timing_summary_routed.rpt`（布线后）。
`logs/P1.8_build.log` 无实际 ERROR，构建退出码 0。

### 接口与实现范围

- PS：Z20 DDR/外设预设，FCLK0=100 MHz，FCLK1=200 MHz。
- AD9361 LVDS 接口、RX/TX DMA（关闭 SG）、Quad SPI、双通道 GPIO、FMC IIC。
- SPI 基址 `0x41E00000`，GPIO `0x41200000`，AD9361 `0x79020000`，RX DMA `0x7C400000`，TX DMA `0x7C420000`。
- 默认控制 GPIO 为 0，RESETB 保持低；未运行驱动、未启用 TX。
- FMC Bank33/34 使用 2.5 V 约束；IIC Bank35 为 3.3 V。SCL=G21，SDA=G20。
- 实际显示硬件为 J22 SSD1963 8080 并口 800×480，本基础工程未集成显示，也未实现 FFT/CFAR/PFB/AMC。

### 尚需处理的警告与验证范围

- ADI 分支期望 Vivado 2025.1，实际为 2025.2，按 runbook 开启版本检查豁免；已用实际构建验证，不能称为版本完全匹配。
- Place 30-73：Quad SPI 的 IO0_I_REG 带 IOB=TRUE，但该方向未接外部输入。当前为四线单向 SPI，构建通过；在 P4 集成时复核该未用输入寄存器与 IP 自动约束。
- 方法学报告保留 TIMING-54（7 条 scoped 时钟例外）、未知 CDC/同步器属性和缺外部 I/O delay 提示。内部端点均受约束且当前 STA 通过，但不能将这些警告解释为所有外部协议时序均已验证。
- 18 个输入、22 个输出缺 delay；需在接口校准和系统集成时逐类核对 ADI 的时钟域及异步控制约束，不通过随意添加 false_path 消除提示。
- P0.8 镜像启动、G0 原工程确认、G1/G2/G3 均未完成；本阶段没有连接 JTAG、写 SD 卡或操作射频。

### 可复现产物

`board/overlay/base_z20/`：`base_z20.bit`、`base_z20.hwh`、`base_z20.xsa`，SHA256 见同目录 `sha256.txt`。
构建在 `build/work/adi_hdl/` 独立 checkout 中进行；覆盖层保存在 `src/hw/fmcomms2_z20/`，原始 `third_party/` 与 `vendor/atk/` 未改动。

### 2026-11-02 板端补充验证

经已确认的2.5V硬件状态，base_z20在PYNQ2.7上实际加载成功。AXI SYSID=0x10161、AD9361接口IP版本=0x0A0300、GPIO=0、SPI状态=0x25；下载后SSH保持可用。见board/measurements/base_runtime_probe.jsonl。此记录不代表AD9361产品ID、射频初始化或原始IQ DMA已通过。
