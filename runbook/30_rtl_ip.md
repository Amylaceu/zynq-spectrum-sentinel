# P3 自研 RTL / HLS IP 与逐模块仿真比对

> 目标：完成总方案第 6 节中所有自研模块。每个模块都要经过"规格 → RTL → testbench → 与 `data/reference/` 逐位比对 → 打包为 IP"五步。
> 语言：Verilog-2001 / SystemVerilog（仅 testbench 使用）；HLS 使用 Vitis HLS 2025.2。
> 仿真器：Vivado xsim（`xvlog` / `xelab` / `xsim`）。

---

## P3.0 公共基础设施

### P3.0.1 仿真脚本 `sim/scripts/run_xsim.ps1`
```powershell
param([Parameter(Mandatory)][string]$Top, [string[]]$Srcs, [string]$Ip = "")
# 用法：.\sim\scripts\run_xsim.ps1 -Top tb_cfar_core -Srcs src/rtl/cfar/*.v,sim/tb/tb_cfar_core.sv
. $env:REPO\tools\env.ps1
$work = "$env:REPO\build\work\xsim_$Top"; New-Item -ItemType Directory -Force $work | Out-Null
Push-Location $work
$files = $Srcs | ForEach-Object { (Resolve-Path "$env:REPO\$_").Path }
xvlog --sv -i $env:REPO\src\rtl\common $files *> xvlog.log; if ($LASTEXITCODE) { Get-Content xvlog.log -Tail 30; Pop-Location; exit 1 }
$libs = if ($Ip) { "-L $Ip" } else { "" }
xelab $Top -debug typical -L xpm -L unisims_ver -L secureip $libs -s "${Top}_snap" *> xelab.log; if ($LASTEXITCODE) { Get-Content xelab.log -Tail 30; Pop-Location; exit 1 }
xsim "${Top}_snap" -R *> xsim.log
$pass = Select-String xsim.log -Pattern "TB_RESULT: PASS" -Quiet
Copy-Item xsim.log "$env:REPO\sim\results\$Top.log" -Force
Pop-Location
if ($pass) { Write-Host "PASS $Top" -ForegroundColor Green; exit 0 } else { Write-Host "FAIL $Top" -ForegroundColor Red; exit 1 }
```

### P3.0.2 testbench 约定
- 每个 testbench 用 `$readmemh` 读取 `data/reference/<module>/in_*.hex`，把输出写入 `sim/results/<module>_out.hex`，并逐拍与 `exp_*.hex` 比对；
- 比对结束时打印 `TB_RESULT: PASS` 或 `TB_RESULT: FAIL mismatches=<n>`；
- 输入和输出都通过 AXI-Stream 握手；testbench 中随机拉低 `tready`（约 20% 的概率），检验背压处理是否正确。

### P3.0.3 Python 侧比对 `tools/golden_compare.py`（即技能包 S5 的原型）
```powershell
python tools/golden_compare.py --exp data/reference/cfar/exp_hit.hex --got sim/results/cfar_out.hex --mode exact
python tools/golden_compare.py --exp data/reference/spectrum/exp_fft.npy --got sim/results/spectrum_fft.hex --mode sqnr --min-sqnr 70
```
功能：自动搜索最佳延迟对齐，计算逐位一致率、最大误差和 SQNR，生成 `sim/results/<name>_compare.md` 和对比图。

### P3.0.4 寄存器契约与代码生成（技能包 S4）
- 契约文件：`src/regs/*.yaml`，每个 IP 一个，格式如下：
```yaml
name: cfar_ctrl
base: 0x43C10000
width: 32
regs:
  - {name: CTRL,   off: 0x00, fields: [{name: EN, bits: "0"}, {name: MODE, bits: "2:1"}, {name: EDGE, bits: "3"}]}
  - {name: PARAM,  off: 0x04, fields: [{name: N, bits: "5:0"}, {name: G, bits: "11:8"}, {name: GAP, bits: "19:16"}]}
  - {name: ALPHA,  off: 0x08, fields: [{name: Q88, bits: "15:0"}]}
  - {name: DCMASK, off: 0x0C, fields: [{name: BINS, bits: "7:0"}]}
  - {name: STATUS, off: 0x10, access: ro, fields: [{name: NTGT, bits: "5:0"}, {name: OVF, bits: "8"}]}
  - {name: VERSION,off: 0xFC, access: ro, reset: 0x53430001}
```
- 生成命令：
```powershell
python tools/regmap_codegen.py src/regs/cfar_ctrl.yaml --verilog src/rtl/regs --c src/ps/include --py src/ps/sentinel/drivers/regs --tb sim/tb/regs
```
- 每个寄存器块地址 0xFC 处固定放 `VERSION`（高 16 位为 IP 标识，低 16 位为版本号），供 Overlay 校验（技能包 S1）使用。

### P3.0.5 IP 打包脚本 `build/scripts/package_ip.tcl`
```tcl
# 用法：vivado -mode batch -source build/scripts/package_ip.tcl -tclargs <ip_name> <src_dir> <out_repo>
lassign $argv ip src out
create_project -in_memory -part xc7z020clg484-2
add_files [glob $src/*.v]
add_files -quiet [glob -nocomplain $::env(REPO)/src/rtl/common/*.v $::env(REPO)/src/rtl/regs/${ip}_regs.v]
set_property top $ip [current_fileset]
update_compile_order -fileset sources_1
ipx::package_project -root_dir $out/$ip -vendor sentinel.org -library user -taxonomy /Sentinel -import_files -set_current true
ipx::infer_bus_interfaces xilinx.com:interface:axis_rtl:1.0 [ipx::current_core]
ipx::infer_bus_interfaces xilinx.com:interface:aximm_rtl:1.0 [ipx::current_core]
set_property core_revision 1 [ipx::current_core]
ipx::create_xgui_files [ipx::current_core]
ipx::update_checksums [ipx::current_core]
ipx::save_core [ipx::current_core]
```

---

## 模块清单与执行顺序

| 步骤 | 模块 | 文件 | 参考数据 | 比对方式 | 优先级 |
|---|---|---|---|---|---|
| P3.1 | `src_mux`、`test_src`、`replay_pacer` | `src/rtl/src_mux/` | 自生成 | exact | P0 |
| P3.2 | `spec_front`：加窗 + FFT IP + 功率 + Welch + dB | `src/rtl/spectrum/` | `spectrum/` | sqnr ≥ 70 dB（FFT），exact（功率之后） | P0 |
| P3.3 | `cfar_core` + `cluster` + `occupancy` + `alarm` | `src/rtl/cfar/` | `cfar/` | exact | P0 |
| P3.4 | `pfb_os2` | `src/rtl/pfb/` | `pfb/` | exact | P0 |
| P3.5 | `nco_capture`：信道选择 + NCO + 抽取 + 捕获 | `src/rtl/nco_capture/` | `nco_capture/` | exact | P0 |
| P3.6 | `disp_engine`：渲染器 + 瀑布图读写 + 合成 + `lcd_id_probe` | `src/rtl/disp/` | `render/` | exact（逐像素） | P0 |
| P3.7 | `hoc_moments`（HLS） | `src/hls/hoc_moments/` | `hoc/` | exact | P0 |
| P3.8 | `demod_audio`：FM/AM 解调 + 重采样 + I2S | `src/rtl/demod/` | `demod/` | sqnr ≥ 60 dB | P1 |
| P3.9 | `dpx_hist`：余辉直方图 | `src/rtl/disp/` | `render/` | exact | P1 |
| P3.10 | `perf_mon` | `src/rtl/perf/` | 自生成 | exact | P0 |

**每个模块都按以下 5 个子步骤执行**（以 P3.3 为例，其余模块照此办理）：

### P3.3.a 规格
在 `src/rtl/cfar/README.md` 中写明以下内容：
- 端口：`s_axis_pwr`（tdata 32 位 + tlast 表示帧尾）、`m_axis_thr`、`m_axis_hit`、`m_axis_tgt`（每个目标 128 位）、AXI-Lite 接口；
- 时序：吞吐率 1 bin/周期，固定流水线延迟（写明具体周期数）；
- 算法：与 `sim/golden/cfar.py` 的"硬件一致性约定"逐条对应。

### P3.3.b RTL 实现要点
- 滑窗：深度为 2(N+G)+1 的移位寄存器。为了实现 wrap 边界，先把帧首的 N+G 个点缓存下来，帧尾时再补入（或者用 BRAM 环形缓冲预读）；
- 左右两个窗口和用增量方式更新：`L += p[k-g-1] - p[k-g-n-1]`，R 同理，40 位宽；
- 门限乘法使用一个 DSP48（25×18），输出饱和到 32 位；
- 聚类模块是一个状态机：IDLE → IN_SEG → GAP → EMIT；
- 目标列表写入双缓冲 BRAM，同时通过 AXIS 输出给 DMA；帧结束时产生 `irq_list_ready` 脉冲。

### P3.3.c testbench：`sim/tb/tb_cfar_core.sv`
覆盖 CA、GO、SO 三种模式 × 两种边界处理方式 × 随机背压，共 6 组数据。

### P3.3.d 运行与比对
```powershell
.\sim\scripts\run_xsim.ps1 -Top tb_cfar_core -Srcs "src/rtl/cfar/*.v","src/rtl/regs/cfar_ctrl_regs.v","sim/tb/tb_cfar_core.sv"
python tools/golden_compare.py --exp data/reference/cfar/exp_tgt_ca.hex --got sim/results/cfar_tgt_ca.hex --mode exact
```

### P3.3.e 单独综合（获取资源和 Fmax）+ 打包
```powershell
vivado -mode batch -source build/scripts/synth_module.tcl -tclargs cfar_core src/rtl/cfar 150 *> logs/P3.3_synth.log
vivado -mode batch -source build/scripts/package_ip.tcl  -tclargs cfar_core src/rtl/cfar src/ip_repo *> logs/P3.3_pkg.log
```
`build/scripts/synth_module.tcl` 的功能：在 150 MHz 约束下做 out-of-context 综合，输出 `build/reports/modules/<ip>_util.rpt` 和 `_timing.rpt`。

**验收**：xsim 结果 PASS；逐位一致率 100%；单模块综合 WNS ≥ 0（150 MHz）。

---

## 各模块的关键规格（代理实现时必须满足）

### P3.1 `src_mux` / `test_src` / `replay_pacer`
- 4 种模式（寄存器 `MODE`）：0 = RF、1 = 回放、2 = 测试源、**3 = RF + 注入噪声**。输出 32 位 IQ 的 AXIS 流（`tuser[1:0]` 标识模式），切换只在帧边界生效，避免毛刺；
- 模式 3 是无衰减器方案中实现"可控 SNR"的关键（见 `60_board.md` G3.1b）：`out = sat16(rf_iq + ((noise × NOISE_AMP) >>> 15))`，其中 noise 来自 `test_src` 的噪声发生器，I 路和 Q 路使用相互独立的 LFSR；黄金模型 `siggen.add_noise_fixed()` 必须实现完全相同的定点算法；
- `test_src`：两路 32 位相位累加 DDS（正弦和余弦查找表 1024×16）+ 32 位 Galois LFSR 噪声（取 12 个均匀随机数求和，近似高斯）；幅度可配置；
- `replay_pacer`：输入来自 AXI DMA MM2S；按 `RATE_DIV` 寄存器产生节拍（例如在 150 MHz 下设为 4.88，用小数累加器实现），模拟 30.72 MSPS 的输入速率。

### P3.2 `spec_front`
- FFT IP 配置：`xfft` 2048 点，Pipelined Streaming I/O，定点，输入 16 位，缩放模式（Scaled），自然序输出，`throttle_scheme realtime`；
- 窗系数 ROM：由 `spectrum.window_coefs` 导出为 `.coe` 文件，用 BRAM 实现；
- 输出两路：(a) dB 值（Q8.8）的 AXIS 流，送给显示和 CFAR 之外的模块；(b) uint32 线性功率，送给 CFAR；
- fftshift 在输出端用地址重映射实现（BRAM 乒乓读写）。

### P3.4 `pfb_os2`
- 16 相，每相 8 个抽头；延迟线放在 BRAM 中（16 相 × 8 抽头 × 32 位）；
- 8 个复 MAC 单元时分复用。每个输入样本需要 32 次实数 MAC；在 150 MHz 下每个样本有 4.88 个周期，8 个 MAC 单元共提供约 39 次 MAC 的能力，满足要求；
- 循环移位器：`rot = (frame_idx * 8) % 16`，只有 0 和 8 两种取值，实现为二选一多路器；
- 16 点 FFT：radix-4 两级流水，旋转因子用常数乘法实现；
- 输出：AXIS 流，`tuser[3:0]` 为信道号。

### P3.5 `nco_capture`
- 寄存器：`CH_SEL`、`NCO_FCW`（32 位）、`DEC`（1/2/4/8）、`CAP_LEN`、`ARM`、`STATUS`；
- NCO 用 Xilinx DDS Compiler IP（相位位宽 32，输出 16 位），或者 CORDIC；抽取用 CIC（阶数 3）加补偿 FIR（31 抽头）；
- 输出一帧数据，帧头格式为 `{magic 0x5343_4150, timestamp_lo, timestamp_hi, ch_sel, fcw, dec, len, src}`，帧头之后是 IQ 数据，帧尾用 `tlast` 标记；
- 抽取后的 IQ 同时送给 HOC 核（AXIS 广播）。

### P3.6 `disp_engine`
- 时序：使用 Xilinx `v_tc`（软件写寄存器配置时序）+ `v_axi4s_vid_out` + 正点原子 `rgb2lcd` IP（在 `vendor/atk/pynq_ref/ip_repo` 中）；屏幕参数由 `lcd_id_probe` 读出 ID 后，PS 查表写入；
- 屏幕布局与总方案 7.9 节一致：频谱区 (0,0)–(720,200)，瀑布图区 (0,200)–(720,500)，UI 区为剩余部分；
- `trace_renderer`：显示行缓存在 BRAM 中（720×16 位，乒乓双缓冲，在帧消隐期间交换）；在频谱区内，若像素行 y 位于相邻两列曲线值之间（min 与 max 之间），则画出曲线颜色；
- 颜色：平均谱 0x07FF、峰值保持 0xFFE0、CFAR 门限 0xF800（虚线，x 每 4 个像素画 2 个）、目标框 0x07E0；
- `wf_writer`：每个显示帧写一行 720 字节的伪彩索引，通过 AXI4 写入 DDR 环形缓冲（基地址和行数由寄存器配置）；`wf_reader` 从 `head` 行开始回绕读取，经 256 项调色板 LUT（BRAM）转换为 RGB565；
- `layer_mixer`：UI 图层（VDMA，RGB565）的像素等于 0xF81F 时显示 PL 图层，否则显示 UI 图层；
- 验证：testbench 输出一整帧（600×1024 RGB565 的 `.hex`），用 `tools/hex2png.py` 转成 PNG，再与 `data/reference/render/exp_frame.hex` 逐像素比对。

### P3.7 `hoc_moments`（Vitis HLS）
**目录结构**：
```
src/hls/hoc_moments/
  hoc_moments.cpp  hoc_moments.h  tb_hoc_moments.cpp  run_hls.tcl
```
**顶层接口**：
```cpp
void hoc_moments(hls::stream<ap_axis<32,0,0,0>>& s_iq, hls::stream<ap_axis<64,0,0,0>>& m_mom,
                 ap_uint<13> len, ap_uint<5> norm_shift);
#pragma HLS INTERFACE axis port=s_iq
#pragma HLS INTERFACE axis port=m_mom
#pragma HLS INTERFACE s_axilite port=len
#pragma HLS INTERFACE s_axilite port=norm_shift
#pragma HLS INTERFACE s_axilite port=return
```
主循环 `#pragma HLS PIPELINE II=1`，复数乘法使用 `ap_fixed<18,2>`，累加器使用 `ap_int<48>`。

**`run_hls.tcl`**：
```tcl
open_project -reset build/work/hls_hoc
set_top hoc_moments
add_files src/hls/hoc_moments/hoc_moments.cpp
add_files -tb src/hls/hoc_moments/tb_hoc_moments.cpp -cflags "-DREF_DIR=\"$::env(REPO)/data/reference/hoc\""
open_solution -reset sol1 -flow_target vivado
set_part xc7z020clg484-2
create_clock -period 6.667
csim_design
csynth_design
cosim_design -rtl verilog
export_design -format ip_catalog -output $::env(REPO)/src/ip_repo/hoc_moments.zip
```

**命令**：
```powershell
vitis-run --mode hls --tcl src/hls/hoc_moments/run_hls.tcl *> logs/P3.7_hls.log
Expand-Archive src/ip_repo/hoc_moments.zip -DestinationPath src/ip_repo/hoc_moments -Force
```

**优化对比实验 E5**：保存 3 个 solution（`sol0_nopragma`、`sol1_pipeline`、`sol2_pipeline_partition`），从各自的 `syn/report/hoc_moments_csynth.rpt` 中提取 II、延迟和资源，汇总到 `build/reports/e5_hls.md`。

**验收**：csim 和 cosim 都通过，与 `data/reference/hoc/` 逐位一致，II = 1。

### P3.8 `demod_audio`
- 使用 CORDIC IP（矢量模式，输出相位 16 位）；FM 输出为相邻两个相位的差值（模 2π），AM 输出为幅度减去直流（用一阶 IIR 估计直流）；
- 用 CIC 和 FIR 把采样率降到 48 kHz；I2S 主模式输出（MCLK 12.288 MHz、BCLK 3.072 MHz、LRCK 48 kHz，24 位左对齐）；
- 静噪：信道功率低于门限时输出 0。
- **输出端口（板载硬件，见底板原理图第 12 页）**：
  - 耳机：ES8388 的 LOUT1/ROUT1 → 插座 P1（丝印 LINE_OUT，原理图网络名 PHONE）；
  - 喇叭：ES8388 的 **ROUT2** → MD8002A 功放（BTL 输出）→ 喇叭座 **J36**。功放只接了右声道，所以解调音频必须**左右声道复制同一路单声道数据**。
  - PS 侧的 ES8388 初始化（I2C，经 AXI IIC 访问）要同时打开 OUT1 和 OUT2：DAC 电源寄存器 0x04 中 LOUT1/ROUT1/LOUT2/ROUT2 的使能位全部置 1；音量寄存器 0x2E/0x2F（OUT1）和 0x30/0x31（OUT2）设为合适的值。寄存器的具体位定义以 ES8388 数据手册为准（资料盘 `7_芯片数据手册`），也可以参考正点原子 PYNQ base 工程中 `audio_codec_ctrl` 的初始化序列。
  - UI 上提供"耳机 / 喇叭 / 两者"切换：通过开关 OUT1、OUT2 的使能位实现。

### P3.9 `dpx_hist`
- 直方图尺寸 360×128，每格 8 位，用 12 个 BRAM36 实现；每帧对命中的格子做饱和加 1；每隔 `DECAY_N` 帧把所有格子右移 1 位，衰减操作在帧消隐期间逐行完成；
- 显示时把 360 列映射到 720 像素宽、128 级映射到 200 像素高，再经热力图 LUT 着色。

### P3.10 `perf_mon`
- 64 位自由运行计数器（150 MHz）；
- 16 个事件计数器：样本数、各个 FIFO 的溢出次数、FFT 帧数、CFAR 命中数、目标列表条目数、DMA `tready` 为低的周期数等；
- 时延测量：`t_in` 为测试源注入标记样本的时刻，`t_out` 为目标列表就绪中断的时刻，两者之差写入寄存器。

---

## P3 阶段验收与提交

```powershell
# 依次运行所有 testbench
$tbs = "tb_src_mux","tb_spec_front","tb_cfar_core","tb_pfb_os2","tb_nco_capture","tb_disp_engine","tb_perf_mon"
foreach ($t in $tbs) { .\sim\scripts\run_xsim.ps1 -Top $t -Srcs (Get-Content "sim/tb/$t.files") }
# 汇总结果
python tools/sim_summary.py sim/results > sim/results/SUMMARY.md
git add src sim build/scripts build/reports/modules tools runbook/STATUS.md
git commit -m "[P3] custom IP cores with bit-exact verification"
```
- 每个 testbench 旁边放一个 `.files` 文件，列出它需要的源文件，每行一个路径；
- 汇总表 `sim/results/SUMMARY.md` 的列：模块 / PASS 或 FAIL / 一致率 / SQNR / 单模块 LUT·FF·BRAM·DSP / Fmax。
