# P6 上板门禁：G0 → G1 → G2 → G3（主线，不需要衰减器）｜ C1（备选，有衰减器时执行）

> 本阶段**以人工为主**。代理的职责是：给出每一步的命令和期望现象，分析用户发回的日志和照片，判断是否通过。
> 每个门禁的结果记录在 `board/measurements/<门禁>/`，并更新 `runbook/STATUS.md`。
> **任何步骤都不得违反 `runbook/README.md` 第 3.4 节的安全规则。**
>
> **运行环境**：
> - PC：目标设备上的 PowerShell，已执行 `. .\tools\env.ps1`，`$env:BOARD_IP` 已设置；
> - 板端：PYNQ 2.7，用户 `xilinx`，代码目录 `/home/xilinx/sentinel`，Python 解释器使用 `docs/board_info.md` 中的 `board_python`；
> - 所有 `.\tools\board.ps1 run "<cmd>"` 都会在板上以 root 权限、`PYTHONPATH=/home/xilinx/sentinel/ps` 执行 `<cmd>`。

| 门禁 | 是否需要 FMCOMMS3 | 是否需要衰减器 | 产出 |
|---|---|---|---|
| G0 现状确认 | 用户已插好 | 否 | `docs/board_info.md` 补全、用户已有工程的信息 |
| G1 位流可用 | 否（可拔下） | 否 | 测试源 / 回放模式下全链路逐位比对 |
| G2 射频接收 | 是 | 否 | BIST 回环、FM/WiFi 接收、实采样本 |
| G3 全功能 | 是 | **否**（空口闭环 + 数字注噪） | 混淆矩阵、识别率–SNR 曲线、对比实验数据 |
| C1 电缆闭环 | 是 | **是**（备选） | 更精确的识别率–SNR、Pd、Pfa |

---

## G0 👤 现状确认（用户已经让 AD9361 和 LCD"能用"）

用户在原设备上已经做到：LCD 能点亮，AD9361 能初始化，但还没有任何处理功能。代理需要向用户收集以下信息，写入 `docs/board_info.md` 的 `## existing_setup` 小节：

| 问题 | 用途 |
|---|---|
| J7、J8 当前跳在哪一档？是否测过 VADJ？读数是多少？ | 如果已经是 2.5V 并且测过，G2.1 可以跳过 |
| AD9361 是在什么环境下初始化的：PYNQ 镜像 + Python？Vitis 裸机 no-OS？还是 ADI Kuiper Linux + IIO？ | 决定 P5.3 的 AD9361 驱动路线：如果用户的方法已经可用，优先复用 |
| 用的是哪个 Vivado 工程或位流？能否把工程目录或 `.xsa`/`.bit`/`.hwh` 拷贝到 `board/overlay/user_existing/`？ | 作为 P1 的对照参考（引脚、ADC_INIT_DELAY 等） |
| LCD 是通过正点原子 PYNQ 例程点亮的，还是自己的工程？屏幕分辨率是多少？ | 决定显示时序参数 |
| SD 卡里是什么系统？板子 IP 是多少？ | 补全 `board_ip` 和 `board_python` |

**判定**：
- 如果用户的 AD9361 方案是 **ADI Kuiper Linux + libiio**，可以在 P5.3 中增加"路线 B：pyadi-iio"作为备选，但主线仍然保持 PYNQ 镜像（便于加载自研 Overlay）。
- 所有信息收齐后，标记 `G0 DONE`。

---

## G1 位流可用（不插 FMCOMMS3）

**前置条件**：P4 完成（`board/overlay/sentinel/` 已生成），P5.2 完成。

### G1.1 👤 HUMAN 硬件状态
- FMCOMMS3 **不插**；7 寸 LCD 接到 J26；网线、串口线已连接；SD 卡中是 PYNQ 镜像。

### G1.2 测试源模式全链路自检
```powershell
.\tools\board.ps1 push
.\tools\board.ps1 run "python3 -m sentinel.selftest --stage full --source test --out measurements/g1"
.\tools\board.ps1 pull board/measurements/g1
```
`selftest --stage full --source test` 依次检查以下各项，每一项都生成一个 JSON 结果文件：

| 检查项 | 方法 | 通过条件 |
|---|---|---|
| overlay | `SentinelOverlay.check()` | 所有 IP 返回 ok |
| test_tone | 测试源产生一个单音（+5 MHz），读取 FFT 输出 | 峰值频点 = round(5e6/15e3) + 1024 ± 1 |
| cfar | 测试源产生 3 个单音和噪声 | 目标列表中正好 3 个目标，频点误差 ≤ 1 |
| capture | 选中 +5 MHz 那个目标，读取捕获数据 | 捕获的 IQ 经 FFT 后能量集中在 0 频附近（误差小于 1 kHz） |
| hoc | 用回放源注入 `data/reference/hoc` 中的 QPSK 数据 | 9 个矩与参考值逐位一致 |
| replay_bitexact | 回放 `data/reference/spectrum/in_iq.npy` | 平均功率谱与参考值逐位一致 |
| display | 读回 `wf_writer` 写入 DDR 的行数据，与 `render.py` 的输出比对 | 一致 |
| amc | 用回放源注入 10 类调制（SNR 20 dB）的 IQ | 识别准确率 ≥ 95% |
| perf | 读取 `perf_mon` | overflow = 0；测得的 PL 检测时延 |
| fps | 运行 10 秒 | 显示帧率 ≥ 50 fps，PS 的 CPU 占用 < 30% |

### G1.3 👤 HUMAN 屏幕观察
在板上运行 `python3 -m sentinel.app.main --mode monitor --source test`，确认以下现象，并拍照保存为 `board/measurements/g1/screen.jpg`：
- 频谱区能看到 3 个峰，叠加了 CFAR 门限的红色虚线和绿色目标框；
- 瀑布图区平稳滚动；
- 信号列表中有 3 行；
- 点击屏幕上的某个信号，右侧显示星座图（测试源发出的是单音，所以星座图是一个旋转的圆环）。

**G1 通过条件**：G1.2 全部 PASS，G1.3 的照片符合描述。
> G1 通过后，"功能正确性"和"可复现性"两项评分就有了完整证据，即使后面射频部分受阻，作品也能完整演示。

---

## G2 射频接收正常（插 FMCOMMS3，TX 关闭）

### G2.1 👤 HUMAN 改跳线并测量电压（⚠️ 最关键的一步）
1. **断开 12V 电源**。
2. 找到底板上的 J7（VCCIO_B33）和 J8（VCCIO_B34），各是一个 2×3 的排针，可选 3.3V / 2.5V / 1.8V。
   - 位置和丝印对照：`vendor/atk/docs/z20_base_assembly.pdf` 第 2 页。J8 在上、J7 在下，位于核心板右侧；丝印依次为 B34 +3.3V / +2.5V / +1.8V 和 B33 +3.3V / +2.5V / +1.8V；
   - 原理图 `vendor/atk/docs/z20_base_schematic_1v0.pdf` 第 3 页（03_PMIC）：VCCIO 与所选电压之间用跳线帽短接。**以实物丝印为准**，跳线帽插在中间一行（+2.5V）。
   - 如果 G0 中确认已经是 2.5V 并测量过，这一步只需要复测一次。
3. 把 J7 和 J8 的跳线帽都插到 **2.5V** 那一组。
4. **FMCOMMS3 先不插**，接通 12V 电源。
5. 用万用表测量（黑表笔接 GND）：
   - FMC 连接器 G39 或 H40 引脚（VADJ）：**必须是 2.40–2.62V**；
   - Bank33/34 附近的测试点或电容（可选）。
6. 测量结果写入 `board/measurements/g2/vadj.txt`，并拍照。
7. 断电，插上 FMCOMMS3，用铜柱支撑好，避免连接器受力。

> **如果测得的电压不是 2.5V，严禁插上 FMCOMMS3**。把读数发给代理，排查跳线位置。

### G2.2 👤 HUMAN 上电检查
1. RX1A 接天线（用户现有天线见 `docs/hardware_bom.md`）：
   - 收 FM 广播时，用磁吸长鞭天线，或把拉杆天线拉满（约 76 cm）；
   - 70–512 MHz 扫频用 20–512 MHz 磁吸天线（粗长那根）；
   - 2.4 GHz 用板状天线。
   **TX1A、TX2A 不接任何东西**（如果有 50 Ω 负载，可以接上）。
2. 上电，观察 FMCOMMS3 的电源指示灯；1 分钟后用手背靠近 AD9361 和 FMCOMMS3 的稳压芯片，确认不烫手。

### G2.3 AD9361 初始化与接口调优
```powershell
.\tools\board.ps1 run "python3 -m sentinel.selftest --stage rf_init --out measurements/g2"
```
检查项：

| 检查 | 通过条件 |
|---|---|
| SPI 读取产品 ID（寄存器 0x037） | `(读数 & 0xF8) == 0x08`（低 3 位是芯片版本号，常见读数为 0x0A） |
| BBPLL、RX PLL 锁定 | 锁定位为 1 |
| TX 衰减 | 读回值为 89.75 dB；TX 状态机处于关闭状态 |
| 数字接口调优 | 找到有效窗口，窗口宽度 ≥ 3 档；结果写入 `tuning.json` |
| BIST 数字回环（`z20_bist_loopback(1)`） | TX DMA 发送 PRBS 或已知序列，RX DMA 收到的数据逐位一致；**这一步不经过射频，TX 天线口没有输出** |
| FMC EEPROM（若 P1.6 中确认了 IIC 管脚） | 读出的字符串中包含 "FMCOMMS3" |

**排错**：

| 现象 | 处理 |
|---|---|
| 产品 ID 读成 0x00 或 0xFF | 检查 SPI 的 CPOL/CPHA 设置、片选极性、`gpio_resetb` 是否为高；用 ILA 抓取 SPI 波形（在 P4 工程中加入 `system_ila`） |
| 接口调优找不到窗口 | 降低采样率重试（15.36 MSPS）；检查 LVDS_25 和 DIFF_TERM 约束；检查 VADJ 是否为 2.5V；把调优得到的 `ADC_INIT_DELAY` 回填到 `system_bd.tcl` 后重新构建 |
| BIST 有误码 | 增大调优步长；检查 Bank34 上的 `tx_data_out[3]`（LA10）与其他 TX 线的走线差异（LA10 在 Bank34，其他 TX 线在 Bank33） |

### G2.4 👤 HUMAN 天线接收
```powershell
.\tools\board.ps1 run "python3 -m sentinel.app.main --mode monitor --source rf --lo 98e6 --rate 30.72e6"
```
期望在屏幕上看到：
- 88–108 MHz 范围内有多个 FM 电台的峰（中心频率设为 98 MHz 时，可以看到约 83–113 MHz）；
- 信号列表中，FM 电台被识别为 **FM**，频率与本地电台的实际频率一致，误差 ±15 kHz；
- 点击某个 FM 电台，开启监听：插在 **P1（丝印 LINE_OUT，位于底板右边缘、SD 卡座上方）** 的 3.5 mm 有线耳机里能听到广播声音。喇叭（J36）当前不使用。

然后依次检查：
- `--lo 2.44e9`：能看到 WiFi 的突发信号，余辉图上能看到突发的轮廓；
- `--lo 433.9e6`（可选，**需要 433 MHz 遥控器，当前没有，跳过**）：按下遥控器，屏幕上出现 OOK 信号并被识别为 OOK。OOK 的识别验证改在 G3 的空口闭环中完成（TX 自己发 OOK，两根拉杆天线调到约 17 cm）。
- 其他不需要额外器材的真实信号（任选，用来丰富演示）：
  - `--lo 935e6`：GSM900 下行，或其他移动通信下行信号；
  - `--lo 1.8e9` 或 `--lo 2.1e9`：LTE / 5G 下行；
  - `--lo 409.75e6` 或 `--lo 446e6`：公众对讲机（FM 语音，需要有人在附近使用）；
  - `--lo 2.44e9` 时打开手机蓝牙并播放音乐：蓝牙跳频（GFSK）在余辉图上非常明显。

录制实采样本：
```powershell
.\tools\board.ps1 run "python3 -m sentinel.app.record --lo 98e6 --rate 30.72e6 --seconds 0.5 --label fm_broadcast --out data/captured/samples"
.\tools\board.ps1 run "python3 -m sentinel.app.record --lo 2.44e9 --rate 30.72e6 --seconds 0.5 --label wifi --out data/captured/samples"
.\tools\board.ps1 pull data/captured/samples
```
屏幕照片和录像保存到 `board/measurements/g2/`。

**G2 通过条件**：G2.3 全部 PASS；FM 广播能正确检测、识别并能听到声音。

---

## G3 全功能上板（包括低功率空口闭环）

### G3.1 👤 HUMAN 空口闭环接线
- **主频点 2.45 GHz**：TX1A 和 RX1A 各接一根 2.4 GHz 板状天线，**两根相距 ≥ 30 cm**，摆成同一方向（都竖直）。有 SMA 延长线时，把 TX 天线拉开更远。
- **辅频点 433.9 MHz（可选）**：两根拉杆天线各拉到约 17 cm，接法与上面相同。
- **严禁**把两根天线贴在一起，也严禁用 SMA 线把 TX 直接连到 RX。
- 确认附近没有对 2.4 GHz 干扰敏感的设备（测试时间短、功率极低，一般没有影响）。

### G3.1b 无衰减器条件下得到"可控 SNR"的方法（主线方案）
没有衰减器时，空口链路的损耗不可控，也不精确。为了得到可复现的**识别率–SNR 曲线**，采用以下方法：
1. TX 以固定衰减（从 89 dB 起步，直到 RX 端的 SNR ≥ 25 dB 为止；同时必须满足 ≥ 30 dB 的下限）发送高 SNR 的已知调制信号，作为"干净基准"；
2. 在 PL 中使用 `test_src` 的噪声发生器，在 **src_mux 之前**把高斯噪声**叠加**到实时 IQ 上。`src_mux` 增加一个"RF + 注噪"模式（寄存器 `NOISE_ADD_EN`、`NOISE_AMP`）：
   - 噪声功率按带宽内 SNR 换算，范围 −4 到 20 dB，步长 2 dB；
   - 噪声幅度由板上实测的信号功率自动校准：先测得信号功率 Ps，再按目标 SNR 计算噪声幅度；
3. 这样得到的曲线 = 真实射频损伤（频偏、IQ 不平衡、相位噪声、多径）+ 精确可控的 SNR；
4. 报告中如实说明：SNR 是"数字注入"的，不是"射频衰减"得到的。

> 需要同步修改 `30_rtl_ip.md` P3.1：`src_mux` 增加 `MODE=3`（RF + 注噪），即输出 = sat16(rf_iq + noise × amp)；黄金模型 `siggen.py` 中实现同样的定点算法。

### G3.2 空口闭环评测（软件强制 TX 衰减 ≥ 30 dB + 数字注噪扫描 SNR）
```powershell
# 第 1 步：链路标定。从 89 dB 开始逐步减小 TX 衰减，直到 RX 端的 SNR ≥ 25 dB，或者到达 30 dB 下限为止
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval calibrate --link air --lo 2.45e9 --att-start 89 --att-floor 30 --target-snr 25 --out measurements/g3/air_cal"
# 第 2 步：固定 TX 衰减，用数字注噪扫描 SNR，10 类调制 × 13 个 SNR 点 × 200 段
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval sweep --link air --lo 2.45e9 --att-from measurements/g3/air_cal/cal.json --snr -4:20:2 --mods all --segments 200 --out measurements/g3/air_eval --save-dataset data/captured/air_v1"
# 第 3 步（可选）：433.9 MHz 辅频点，每个 SNR 点 100 段
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval calibrate --link air --lo 433.9e6 --att-start 89 --att-floor 30 --target-snr 25 --out measurements/g3/air_cal_433"
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval sweep --link air --lo 433.9e6 --att-from measurements/g3/air_cal_433/cal.json --snr -4:20:4 --mods all --segments 100 --out measurements/g3/air_eval_433 --save-dataset data/captured/air_433"
.\tools\board.ps1 pull board/measurements/g3
.\tools\board.ps1 pull data/captured/air_v1
```
`loopback_eval` 的保护逻辑：
1. TxGuard 固定为空口模式（下限 30 dB）；TX 衰减只能从 89 dB **逐步减小**，每一步都读取 RSSI；
2. RSSI 高于 −30 dBm 时，**立即停止并恢复 TX 衰减为 89.75 dB**（双重保护），报告"耦合过强，请把天线拉开"；
3. 程序退出时（包括异常退出、Ctrl-C），`finally` 中必须关闭 TX，并把衰减恢复为最大；
4. 输出：`confusion_snr<k>.png`、`acc_vs_snr.png`（与仿真曲线叠加在同一张图上）、`summary.json`。

### G3.2b 不需要衰减器的检测性能指标
| 指标 | 方法 | 命令 |
|---|---|---|
| 实测虚警率 Pfa | RX 接天线但 TX 关闭，选一段**空闲频段**（比如 2.45 GHz 附近没有 WiFi 的时段，或 2.30–2.39 GHz）；有 50 Ω 负载时优先接负载。统计 1e6 个 bin 的命中次数，与设定的 Pfa 比较 | `python3 -m sentinel.bench.pfa_measure --lo 2.35e9 --frames 500 --out measurements/g3/pfa` |
| 检测概率 Pd 曲线 | 使用"RF + 注噪"模式：TX 发单音或 QPSK，扫描注入噪声，统计 CFAR 命中率 | `python3 -m sentinel.bench.pd_curve --link air --att-from measurements/g3/air_cal/cal.json --snr -6:16:1 --out measurements/g3/pd` |
| 回放模式 Pd（完全可复现） | 回放 `data/reference` 中按 SNR 生成的场景 | `python3 -m sentinel.bench.pd_curve --source replay --out measurements/g3/pd_replay` |

### G3.3 用空口数据微调模型（第一次微调）
在 PC 上执行：
```powershell
python -m src.ps.models.amc_train --data data/synthetic/amc_v1 --finetune data/captured/air_v1 --init src/ps/models/weights/amc_v1_fp32.pt --epochs 10 --lr 2e-4 --out src/ps/models/weights --tag amc_v2_air
python -m src.ps.models.export_int8 --ckpt src/ps/models/weights/amc_v2_air_fp32.pt --calib data/captured/air_v1/val.npz --out src/ps/models/weights/amc_v2_air_int8.npz
```
然后在板上用新模型重跑 G3.2 中的一个衰减值，对比微调前后的准确率（E9 的初步结果）。

### G3.4 其他功能逐项验收
| 功能 | 命令 | 通过条件 |
|---|---|---|
| F9 扫频 | `python3 -m sentinel.app.sweep --start 70e6 --stop 3e9 --out measurements/g3/sweep` | 输出全景频谱图，可以看到 FM 广播、GSM/LTE、WiFi 等频段；记录扫频用时 |
| F10 告警 | `python3 -m sentinel.app.main --alarm-band 2.40e9:2.42e9:-60` | TX 在该频段发射时，告警触发、PL_LED 点亮，事件日志中带 RTC 时间戳 |
| F11 录制与回放 | 录制 0.5 秒，然后用 `--source replay` 回放 | 回放时的目标列表与实时处理时一致 |
| F14 远程 | PC 端运行 `python tools/pc_viewer.py --board <ip>` | PC 上实时显示频谱和目标列表 |
| F16 健康状态 | UI 状态栏 | 能显示温度，overflow = 0 |
| 稳定性 | 实时监测模式连续运行 1 小时 | overflow = 0，不崩溃，内存不增长 |

### G3.5 优化对比实验的硬件数据（E1–E8、E10–E12）
```powershell
.\tools\board.ps1 run "python3 -m sentinel.bench.run_all --out measurements/g3/bench"
.\tools\board.ps1 pull board/measurements/g3/bench
```
`sentinel/bench/` 中每个实验一个脚本，输出 CSV 文件和图表。对比项与总方案 11.3 节一致。E9（只用仿真数据训练 vs 加入实采数据微调）在主线中用空口数据 `air_v1` 完成；如果之后执行了 C1，再补充电缆闭环数据的结果。

### G3.6 生成最终指标（主线，不需要衰减器）
```powershell
python tools/make_final_metrics.py --in board/measurements --out report/final_metrics.md --mode air
```
`report/final_metrics.md` 是设计报告中"评测指标"一节的数据来源，包括：识别率–SNR 曲线（空口 + 注噪）、Pd 曲线、实测 Pfa、各项时延、帧率、资源、功耗。如果之后执行了 C1，用 `--mode air+cable` 重新生成，同时保留两套数据作对比。

**G3 通过条件**：G3.2 和 G3.2b 都有完整的输出；G3.4 中所有行都通过；G3.5 的 CSV 文件齐全；`final_metrics.md` 已生成。**到这里作品就具备提交条件**，可以直接进入 P7。

---

## C1（备选分支）有衰减器时的电缆闭环（约半天，可选）

> **触发条件**：用户确认手上有 **30 dB、DC–6 GHz、≥ 2 W 的 SMA 固定衰减器**，以及 SMA 公对公线。没有这些条件时**不执行**本节，`STATUS.md` 中把 C1 标记为 `SKIPPED (no attenuator)`。
> **作用**：用比空口更稳定的链路**补充**识别率–SNR 曲线和 Pd 数据，并在 433 MHz、915 MHz、5.8 GHz 多个频点验证。不替代主线结果，报告中两套数据并列展示。
> **软件准备**：C1 所需的代码（`--link cable`、`TxGuard` 电缆模式）在 P5 中已经实现并通过单元测试，这里只需要接线和运行。

### C1.1 👤 HUMAN 电缆连接
```
TX1A ──SMA 线──▶ [30 dB 固定衰减器，DC–6 GHz] ──SMA 线──▶ RX1A
```
1. **先启动软件，确认 TX 已关闭**（`python3 -m sentinel.selftest --stage rf_init` 输出 `tx_state=off, tx_att=89.75`）；
2. 然后接线；
3. 在软件中切换到电缆模式（需要明确确认已接衰减器）：
```python
from sentinel.rf.safety import TxGuard
g = TxGuard(); g.set_mode("cable", confirm_attenuator=True)
```

### C1.2 定量测试
```powershell
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval calibrate --link cable --confirm-attenuator 30 --lo 2.45e9 --att-start 89 --att-floor 10 --target-snr 30 --out measurements/c1/cable_cal"
.\tools\board.ps1 run "python3 -m sentinel.app.loopback_eval sweep --link cable --confirm-attenuator 30 --lo 2.45e9 --att-from measurements/c1/cable_cal/cal.json --snr -4:20:2 --mods all --segments 500 --out measurements/c1/cable_eval --save-dataset data/captured/cable_v1"
.\tools\board.ps1 run "python3 -m sentinel.bench.pd_curve --link cable --confirm-attenuator 30 --out measurements/c1/pd"
.\tools\board.ps1 run "python3 -m sentinel.bench.pfa_measure --out measurements/c1/pfa"   # 测量前把 RX 口换成 50 Ω 负载（👤）
```
在 433 MHz、915 MHz 和 5.8 GHz 上各重复一次 `cable_eval`（每个频点 `--segments 200`）。

### C1.3 正式微调与最终指标
```powershell
python -m src.ps.models.amc_train --data data/synthetic/amc_v1 --finetune data/captured/cable_v1,data/captured/air_v1 --init src/ps/models/weights/amc_v1_fp32.pt --epochs 15 --lr 2e-4 --out src/ps/models/weights --tag amc_v3
python -m src.ps.models.export_int8 --ckpt src/ps/models/weights/amc_v3_fp32.pt --calib data/captured/cable_v1/val.npz --out src/ps/models/weights/amc_v3_int8.npz
python tools/make_final_metrics.py --in board/measurements --out report/final_metrics.md --mode air+cable
```
最后把板端模型切换为 `amc_v3_int8.npz`（修改 `src/ps/sentinel/app/config.yaml` 中的 `amc_weights`），然后重新执行 `.\tools\board.ps1 push`。

**C1 通过条件**：`final_metrics.md` 中同时有空口和电缆两套数据；SNR = 10 dB 时识别准确率 ≥ 90%（目标值；如果没达到，如实报告实际数值）。
