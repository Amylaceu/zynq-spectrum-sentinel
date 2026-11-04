# P4 系统集成、时序收敛与一键构建

> 目标：在 P1 的基础工程中加入 P3 的全部 IP、显示通路和音频，得到 `sentinel_z20` 完整位流，并提供一条命令就能从零重建的脚本。
> 采用增量集成：P0 功能集 → 收敛 → 逐个加入 P1 功能 → 每加一个都检查一次资源和时序。

---

## P4.1 新建集成工程覆盖层 `src/hw/sentinel_z20/`

**做法**：复制 `src/hw/fmcomms2_z20/` 到 `src/hw/sentinel_z20/`，再新增 `sentinel_bd.tcl`，在 `system_bd.tcl` 末尾 `source` 它。

修改 `system_project.tcl`：
- 工程名改为 `sentinel_z20`；
- 在 `adi_project` 之后、`adi_project_run` 之前执行：
```tcl
set_property ip_repo_paths [concat [get_property ip_repo_paths [current_project]] \
   [file normalize $::env(REPO)/src/ip_repo] [file normalize $::env(REPO)/vendor/atk/pynq_ref/ip_repo]] [current_project]
update_ip_catalog
```
> 需要确认：`adi_project` 内部在什么时刻创建 BD 并 `source system_bd.tcl`。如果 IP 仓库必须在创建 BD 之前设置，就把上面两行放到 `system_bd.tcl` 的最开头。

同步时加参数：`.\tools\sync_hw.ps1 -Proj sentinel_z20`，脚本会自动同步到 `projects/fmcomms2/sentinel_z20`。另外要把 P1.7 生成的 `build_libs.tcl` 复制一份到 `src/hw/sentinel_z20/`，`build_all.ps1` 会用到它。

---

## P4.2 `sentinel_bd.tcl` 连线规格

### 时钟
```tcl
ad_ip_parameter sys_ps7 CONFIG.PCW_EN_CLK2_PORT 1
ad_ip_parameter sys_ps7 CONFIG.PCW_FPGA2_PERIPHERAL_FREQMHZ 150
ad_ip_parameter sys_ps7 CONFIG.PCW_EN_RST2_PORT 1
ad_ip_parameter sys_ps7 CONFIG.PCW_USE_S_AXI_HP0 1
ad_ip_parameter sys_ps7 CONFIG.PCW_USE_S_AXI_HP3 1
ad_ip_instance proc_sys_reset dsp_rstgen
ad_connect sys_ps7/FCLK_CLK2 dsp_rstgen/slowest_sync_clk
ad_connect sys_ps7/FCLK_RESET2_N dsp_rstgen/ext_reset_in
```

### 数据通路
```
util_ad9361_adc_pack/packed_fifo_wr （ADI 原有，接到 RX DMA，保留用于原始 IQ 录制）
axi_ad9361 adc_data_i0/q0 + adc_valid_i0 ──▶ [adc_tap：l_clk 域，打包成 32 位 AXIS]
   ──▶ axis_data_fifo（异步 FIFO，l_clk → dsp_clk，深度 4096，带 overflow 输出）
   ──▶ src_mux.s0
axi_dma_replay.M_AXIS_MM2S ──▶ replay_pacer ──▶ src_mux.s1
test_src ──▶ src_mux.s2
src_mux.m ──▶ axis_broadcaster(2) ──┬▶ spec_front ──┬▶ axis_broadcaster ──┬▶ cfar_core ──▶ axi_dma_list.S2MM
                                    │               │                     └▶ dpx_hist
                                    │               └▶ disp_engine（频谱行）
                                    └▶ pfb_os2 ──▶ nco_capture ──┬▶ axi_dma_cap.S2MM
                                                                 ├▶ hoc_moments ──▶ （HOC 结果写入 cap 帧尾，或经 AXI-Lite 读取）
                                                                 └▶ demod_audio ──▶ I2S 引脚
disp_engine.m_axi_wf ──▶ HP3（瀑布图环形缓冲）
axi_vdma（UI 图层，MM2S）──▶ disp_engine.s_axis_ui
disp_engine ──▶ v_axi4s_vid_out ──▶ rgb2lcd ──▶ LCD 引脚
v_tc ──▶ v_axi4s_vid_out
axi_dynclk ──▶ pix_clk
```
`adc_tap` 是一个很小的自研模块（放在 `src/rtl/adc_tap/`）：从 `axi_ad9361` 的 ADC 输出中取出 I0/Q0，打包成 `{Q,I}`，再输出为带 `tvalid` 的 AXIS 流。
> **数据格式**：`axi_ad9361` 默认输出的是 12 位**符号扩展**到 16 位的数据（不是左对齐）。`adc_tap` 内部要把它左移 4 位（`{adc[11:0],4'b0}`），才符合 README 3.3 节的统一格式。这样回放数据和测试源数据的满幅定义就与 AD9361 实时数据一致。实际格式以 `axi_ad9361` 的 `ADC_DATAFORMAT` 相关寄存器为准，代理需要查阅 `library/axi_ad9361` 的文档确认。

### 地址分配（AXI-Lite，GP0）

| 模块 | 基地址 | 大小 |
|---|---|---|
| axi_ad9361 | 0x79020000 | 64K（ADI 原有） |
| axi_ad9361_adc_dma | 0x7C400000 | 4K（ADI 原有） |
| axi_ad9361_dac_dma | 0x7C420000 | 4K（ADI 原有） |
| axi_ad9361_spi | 0x41E00000 | 64K |
| axi_ad9361_gpio | 0x41200000 | 64K |
| src_mux / test_src | 0x43C00000 | 64K |
| spec_front | 0x43C10000 | 64K |
| cfar_core（含 occupancy/alarm） | 0x43C20000 | 64K |
| nco_capture | 0x43C30000 | 64K |
| hoc_moments | 0x43C40000 | 64K |
| demod_audio | 0x43C50000 | 64K |
| disp_engine（含 dpx） | 0x43C60000 | 64K |
| perf_mon | 0x43C70000 | 64K |
| axi_dma_replay | 0x40400000 | 64K |
| axi_dma_list | 0x40410000 | 64K |
| axi_dma_cap | 0x40420000 | 64K |
| axi_vdma_ui | 0x43000000 | 64K |
| v_tc | 0x43C80000 | 64K |
| axi_dynclk | 0x43C90000 | 64K |
| axi_iic_touch | 0x41610000 | 64K |
| axi_gpio_touch_lcd（触摸 INT/RST、LCD BL/RST、LED） | 0x41210000 | 64K |
| axi_iic_audio（ES8388，与 EEPROM、RTC 共用 I2C 总线） | 0x41620000 | 64K |

> 所有 Xilinx `axi_dma` 都设为 Simple 模式（关闭 SG），`c_sg_length_width = 23`（单次最多传 8 MB），避免默认 14 位长度只能传 16 KB 的问题（这一点写进技能包 S2 的踩坑清单）。

### 中断（`sys_concat_intc`，ps-N 编号）
| 编号 | 来源 |
|---|---|
| ps-13 / ps-12 | ADI adc_dma / dac_dma（原有） |
| ps-11 | axi_iic_fmc（原有） |
| ps-10 | axi_ad9361_spi |
| ps-9 | cfar_core 列表就绪 |
| ps-8 | nco_capture 捕获完成 |
| ps-7 | axi_dma_cap |
| ps-6 | axi_dma_list |
| ps-5 | axi_dma_replay |
| ps-4 | cfar 告警 |
| ps-3 | axi_iic_touch |
| ps-2 | axi_vdma_ui |
| ps-1 | perf_mon 溢出 |

> PYNQ 通过 `axi_intc` 管理中断。如果 PYNQ 2.7 镜像要求中断经过 `axi_intc`（正点原子 base 工程就是这样做的），就把上表中所有自研模块的中断先接到一个 `axi_intc`（地址 0x41800000），再把它的输出接到 `IRQ_F2P[0]`。**代理需要先查看 `vendor/atk/pynq_ref/base/ready_to_test/base.tcl` 中的中断结构，与其保持一致。**

---

## P4.3 板级约束 `src/hw/sentinel_z20/z20_periph.xdc`

管脚均取自正点原子 `Z20 ZYNQ_IO.xdc`，并核对过 IO 分配表：
```tcl
## RGB LCD (Bank13, 3.3V)
set_property -dict {PACKAGE_PIN R6  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[0]}]
set_property -dict {PACKAGE_PIN T6  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[1]}]
set_property -dict {PACKAGE_PIN U4  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[2]}]
set_property -dict {PACKAGE_PIN T4  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[3]}]
set_property -dict {PACKAGE_PIN V8  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[4]}]
set_property -dict {PACKAGE_PIN W8  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[5]}]
set_property -dict {PACKAGE_PIN W11 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[6]}]
set_property -dict {PACKAGE_PIN W10 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[7]}]
set_property -dict {PACKAGE_PIN AA9 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[8]}]
set_property -dict {PACKAGE_PIN AA8 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[9]}]
set_property -dict {PACKAGE_PIN AB2 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[10]}]
set_property -dict {PACKAGE_PIN AB1 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[11]}]
set_property -dict {PACKAGE_PIN W6  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[12]}]
set_property -dict {PACKAGE_PIN W5  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[13]}]
set_property -dict {PACKAGE_PIN U12 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[14]}]
set_property -dict {PACKAGE_PIN U11 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[15]}]
set_property -dict {PACKAGE_PIN AB7 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[16]}]
set_property -dict {PACKAGE_PIN AB6 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[17]}]
set_property -dict {PACKAGE_PIN AB5 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[18]}]
set_property -dict {PACKAGE_PIN AB4 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[19]}]
set_property -dict {PACKAGE_PIN Y11 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[20]}]
set_property -dict {PACKAGE_PIN Y10 IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[21]}]
set_property -dict {PACKAGE_PIN Y9  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[22]}]
set_property -dict {PACKAGE_PIN Y8  IOSTANDARD LVCMOS33} [get_ports {lcd_rgb[23]}]
set_property -dict {PACKAGE_PIN V4  IOSTANDARD LVCMOS33} [get_ports lcd_hs]
set_property -dict {PACKAGE_PIN V10 IOSTANDARD LVCMOS33} [get_ports lcd_vs]
set_property -dict {PACKAGE_PIN V5  IOSTANDARD LVCMOS33} [get_ports lcd_de]
set_property -dict {PACKAGE_PIN AA6 IOSTANDARD LVCMOS33} [get_ports lcd_bl]
set_property -dict {PACKAGE_PIN V9  IOSTANDARD LVCMOS33} [get_ports lcd_clk]
set_property -dict {PACKAGE_PIN AB9 IOSTANDARD LVCMOS33} [get_ports lcd_rst]
## Touch GT9147
set_property -dict {PACKAGE_PIN Y4  IOSTANDARD LVCMOS33 PULLUP true} [get_ports touch_scl]
set_property -dict {PACKAGE_PIN AA7 IOSTANDARD LVCMOS33 PULLUP true} [get_ports touch_sda]
set_property -dict {PACKAGE_PIN AA4 IOSTANDARD LVCMOS33 PULLUP true} [get_ports touch_int]
set_property -dict {PACKAGE_PIN W7  IOSTANDARD LVCMOS33 PULLUP true} [get_ports touch_rst_n]
## ES8388 audio (I2S on Bank13; I2C A18/A19 on Bank35, shared with EEPROM/RTC)
set_property -dict {PACKAGE_PIN U9   IOSTANDARD LVCMOS33} [get_ports aud_mclk]
set_property -dict {PACKAGE_PIN AA11 IOSTANDARD LVCMOS33} [get_ports aud_bclk]
set_property -dict {PACKAGE_PIN U6   IOSTANDARD LVCMOS33} [get_ports aud_lrc]
set_property -dict {PACKAGE_PIN AB11 IOSTANDARD LVCMOS33} [get_ports aud_dacdat]
set_property -dict {PACKAGE_PIN U5   IOSTANDARD LVCMOS33} [get_ports aud_adcdat]
set_property -dict {PACKAGE_PIN A18  IOSTANDARD LVCMOS33 PULLUP true} [get_ports aud_scl]
set_property -dict {PACKAGE_PIN A19  IOSTANDARD LVCMOS33 PULLUP true} [get_ports aud_sda]
## PL LEDs (Bank35)
set_property -dict {PACKAGE_PIN H17 IOSTANDARD LVCMOS33} [get_ports {pl_led[0]}]
set_property -dict {PACKAGE_PIN H18 IOSTANDARD LVCMOS33} [get_ports {pl_led[1]}]
## HDMI out (P2, optional) — Bank35 TMDS_33
# set_property -dict {PACKAGE_PIN B19 IOSTANDARD TMDS_33} [get_ports hdmi_clk_p]
# set_property -dict {PACKAGE_PIN H19 IOSTANDARD TMDS_33} [get_ports {hdmi_d_p[0]}]
# set_property -dict {PACKAGE_PIN B16 IOSTANDARD TMDS_33} [get_ports {hdmi_d_p[1]}]
# set_property -dict {PACKAGE_PIN C18 IOSTANDARD TMDS_33} [get_ports {hdmi_d_p[2]}]
```
> **冲突检查**：AB7、AB6 等引脚在正点原子的设计中同时用于 HDMI 输入（`video_rgb_in`）和 LCD，本设计不使用 HDMI 输入，所以没有冲突。A18/A19 只能被一个 I2C 控制器驱动。

时序约束 `src/hw/sentinel_z20/timing.xdc`：
```tcl
set_clock_groups -asynchronous \
  -group [get_clocks -of_objects [get_pins i_system_wrapper/system_i/sys_ps7/inst/PS7_i/FCLKCLK[0]]] \
  -group [get_clocks -of_objects [get_pins i_system_wrapper/system_i/sys_ps7/inst/PS7_i/FCLKCLK[2]]] \
  -group [get_clocks rx_clk -include_generated_clocks] \
  -group [get_clocks -of_objects [get_pins -hier -filter {NAME =~ *axi_dynclk*/PXL_CLK_O}]]
set_output_delay -clock [get_clocks -of_objects [get_ports lcd_clk]] -max 2 [get_ports {lcd_rgb[*] lcd_hs lcd_vs lcd_de}]
set_output_delay -clock [get_clocks -of_objects [get_ports lcd_clk]] -min -1 [get_ports {lcd_rgb[*] lcd_hs lcd_vs lcd_de}]
```
> 层次路径以实际综合结果为准。第一次构建后用 `get_clocks` 列出所有时钟名，再回填到这里。用 `report_clock_interaction` 确认异步时钟组的设置正确。

---

## P4.4 增量集成顺序（每一步都要构建并记录资源和时序）

| 子步骤 | 加入内容 | 构建标签 | 预期 LUT 占用 |
|---|---|---|---|
| P4.4.1 | `adc_tap` + 异步 FIFO + `src_mux` + `test_src` + 回放 DMA + `perf_mon` | `int1` | ~30% |
| P4.4.2 | `spec_front` + `cfar_core` + 列表 DMA | `int2` | ~42% |
| P4.4.3 | 显示通路：VDMA + `disp_engine` + `v_tc` + `rgb2lcd` + `axi_dynclk` + 触摸 IIC/GPIO | `int3` | ~55% |
| P4.4.4 | `pfb_os2` + `nco_capture` + 捕获 DMA + `hoc_moments` | `int4` | ~65% |
| P4.4.5 | `demod_audio` + 音频 IIC + `dpx_hist`（P1 功能） | `int5` | ~75% |

**每个子步骤的命令**：
```powershell
.\tools\sync_hw.ps1 -Proj sentinel_z20
Set-Location third_party/hdl/projects/fmcomms2/sentinel_z20
$env:SENTINEL_STAGE = "int2"          # sentinel_bd.tcl 根据这个变量决定加入哪些模块
vivado -mode batch -nojournal -source system_project.tcl *> $env:REPO\logs\P4.4_int2.log
Set-Location $env:REPO
.\tools\collect_hw.ps1 -Tag int2 -Proj sentinel_z20
python tools/vivado_report_digest.py build/reports/int2 --append build/reports/integration_progress.md --tag int2
```
`sentinel_bd.tcl` 中按阶段分支：
```tcl
set stage [expr {[info exists ::env(SENTINEL_STAGE)] ? $::env(SENTINEL_STAGE) : "int5"}]
set stages {int1 int2 int3 int4 int5}
proc stage_ge {s} { upvar stages st stage cur; expr {[lsearch $st $cur] >= [lsearch $st $s]} }
if {[stage_ge int1]} { ... }
if {[stage_ge int2]} { ... }
```

**每个子步骤的验收**：WNS ≥ 0、WHS ≥ 0，`report_cdc` 中没有 Critical 级别的问题，新增模块的资源与 P3 单模块综合的结果偏差在 20% 以内。

**时序不收敛时的处理顺序**：
1. 检查关键路径是否跨时钟域，如果是，补充异步约束；
2. 在关键路径上加一级寄存器，把 DSP48 的 AREG/BREG/MREG/PREG 全部打开；
3. 把 `dsp_clk` 从 150 MHz 降到 122.88 MHz。此时 30.72 MSPS 下每个样本仍有 4 个周期，吞吐率满足要求；
4. 改用 `Performance_ExplorePostRoutePhysOpt` 实现策略；
5. 资源不够时，按总方案第 9 节的压缩手段处理：FFT 改为 Radix-2 Lite，或者暂时去掉 `dpx_hist`。

---

## P4.5 一键构建脚本 `build/build_all.ps1`

```powershell
<#
 用法：  .\build\build_all.ps1 [-Stage int5] [-SkipLibs] [-SkipHls]
 作用：  从零构建：HLS IP → 自研 RTL IP 打包 → ADI 库 → Vivado 工程 → 位流 → 收集产物 → 生成报告
#>
param([string]$Stage = "int5", [switch]$SkipLibs, [switch]$SkipHls)
$ErrorActionPreference = "Stop"
. $env:REPO\tools\env.ps1
$t0 = Get-Date
python tools/gen_params_vh.py sim/golden/params.py src/rtl/common/sentinel_params.vh
Get-ChildItem src/regs/*.yaml | ForEach-Object { python tools/regmap_codegen.py $_.FullName --verilog src/rtl/regs --c src/ps/include --py src/ps/sentinel/drivers/regs }
if (-not $SkipHls) {
  vitis-run --mode hls --tcl src/hls/hoc_moments/run_hls.tcl *> logs/build_hls.log
  Expand-Archive src/ip_repo/hoc_moments.zip -DestinationPath src/ip_repo/hoc_moments -Force
}
foreach ($ip in (Get-Content build/scripts/rtl_ips.txt)) {
  $n, $d = $ip -split "\s+"
  vivado -mode batch -nojournal -source build/scripts/package_ip.tcl -tclargs $n $d src/ip_repo *> "logs/build_pkg_$n.log"
}
.\tools\sync_hw.ps1 -Proj sentinel_z20
Push-Location third_party/hdl/projects/fmcomms2/sentinel_z20
if (-not $SkipLibs) { vivado -mode batch -nojournal -source build_libs.tcl *> $env:REPO\logs\build_libs.log }
$env:SENTINEL_STAGE = $Stage
vivado -mode batch -nojournal -source system_project.tcl *> $env:REPO\logs\build_vivado.log
Pop-Location
.\tools\collect_hw.ps1 -Tag sentinel -Proj sentinel_z20
python tools/vivado_report_digest.py build/reports/sentinel --out build/reports/sentinel/SUMMARY.md
"build done in $([int]((Get-Date)-$t0).TotalMinutes) min" | Tee-Object -Append logs/build_all.log
```
`build/scripts/rtl_ips.txt` 每行写一个 IP：`<ip 名> <源目录>`。

**复现性验收**（P7 阶段要在另一个干净目录中再做一次）：
```powershell
git clone --recursive <repo> $env:TEMP\zs_clean; Set-Location $env:TEMP\zs_clean
.\build\build_all.ps1
# 比对两次构建的资源报告：允许有 ±1% 的随机波动，功能部分必须一致
```

---

## P4.6 阶段产出与提交
- `board/overlay/sentinel/sentinel.bit`、`sentinel.hwh`
- `build/reports/sentinel/SUMMARY.md`（资源、时序、功耗）
- `build/reports/integration_progress.md`（int1 到 int5 的资源和时序演变，可直接作为优化过程的证据）
```powershell
git add src/hw/sentinel_z20 build board/overlay/sentinel tools runbook/STATUS.md
git commit -m "[P4] full system integration (sentinel_z20)"
```
