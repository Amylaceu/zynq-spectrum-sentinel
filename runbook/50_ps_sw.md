# P5 PS 端软件：驱动、AD9361 控制、应用与 UI

> 运行环境：正点原子 PYNQ 2.7 镜像（Ubuntu 20.04 系，Python 3.8，`pynq` 2.7）。板端仓库路径约定为 `/home/xilinx/sentinel`。
> 开发方式：在 PC 上写代码，通过 `scp` 或 Jupyter 上传到板上。板上可以直接用自带的 gcc 编译 C 代码，不需要交叉编译。
> S1、S2 可以在 P1 完成后立即开始（使用 `base_z20` 位流）；S3 依赖 P4 的完整位流。

---

## P5.0 板端连接与同步脚本

**产出文件**：`tools/board.ps1`

```powershell
# 用法：
#   .\tools\board.ps1 push                 # 把 src/ps 和 board/ 同步到板上
#   .\tools\board.ps1 run "python3 -m sentinel.selftest"
#   .\tools\board.ps1 pull board/measurements
param([Parameter(Mandatory)][string]$Cmd, [string]$Arg = "")
$ip = (Get-Content $env:REPO\docs\board_info.md | Select-String "board_ip=(.+)").Matches[0].Groups[1].Value.Trim()
$u = "xilinx@$ip"; $dst = "/home/xilinx/sentinel"
switch ($Cmd) {
  "push" {
    ssh $u "mkdir -p $dst"
    scp -r $env:REPO\src\ps $env:REPO\board\overlay $env:REPO\board\notebooks $env:REPO\board\scripts $env:REPO\data\reference "${u}:$dst/"
  }
  "run"  { ssh $u "cd $dst && sudo -E env PYTHONPATH=$dst/ps $Arg" }
  "pull" { scp -r "${u}:$dst/$Arg" "$env:REPO\$Arg\.." }
}
```
> Windows 10/11 自带 OpenSSH 客户端。如果没有，在"设置 → 可选功能"中添加"OpenSSH 客户端"。PYNQ 默认账号和密码都是 `xilinx`。建议配置免密登录：
> ```powershell
> ssh-keygen -t ed25519
> type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh xilinx@<ip> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
> ```

---

## P5.1（S1）平台验证 notebook：`board/notebooks/test_00_platform.ipynb`

**内容**（每个代码单元的输出都保存在 notebook 中，作为证据）：
1. 打印 `uname -a`、`python3 -V`、`pynq.__version__`、`/proc/cpuinfo` 中的 CPU 主频、内存大小；
2. 加载正点原子例程 `4_dma_tutorial` 的位流，做一次 DMA 回环测试；
3. 加载 `6_ov5640_lcd` 位流，把帧缓冲填成 8 色彩条，在屏幕上显示（没有摄像头也可以）；
4. 用 `lcd_id` 读取屏幕 ID（正点原子 notebook 中有现成的读法），记录分辨率；
5. **E1 基线**：计时 `numpy.fft.fft` 处理 2048 点 complex64 的耗时，重复 1000 次取中位数，并计算每秒最多能处理的帧数；
6. 计时 NumPy 实现 CFAR（使用 `sim/golden/cfar.py`）处理一帧的耗时；
7. 计时 Pillow 绘制一帧 1024×600 频谱图和瀑布图的耗时（E10 的基线）。

**命令**：
```powershell
.\tools\board.ps1 push
# 在浏览器中打开 http://<ip>:9090，运行 test_00_platform.ipynb，保存后取回
.\tools\board.ps1 pull board/notebooks
```
**验收**：notebook 中能看到 DMA 回环通过、屏幕彩条照片（👤 拍照后存为 `board/measurements/p5_lcd.jpg`）、三项基线数据。

---

## P5.2（S2）驱动框架 `src/ps/sentinel/drivers/`

### 目录结构
```
src/ps/sentinel/
  __init__.py
  overlay.py          # 加载 Overlay、校验 VERSION 寄存器（技能包 S1）
  mmio.py             # 当 pynq.MMIO 不可用时，退回 /dev/mem + mmap（技能包 S3 pynq_lite）
  dma.py              # 带超时和状态解码的 AXI DMA 封装（技能包 S2）；ADI axi_dmac 的封装
  regs/               # regmap_codegen 生成的寄存器类（自动生成，不要手改）
  rf/ad9361.py        # ctypes 封装 libad9361_pynq.so
  rf/safety.py        # TX 保护逻辑
  hw/spectrum.py hw/cfar.py hw/capture.py hw/hoc.py hw/display.py hw/audio.py hw/srcmux.py hw/perf.py
```

### overlay.py 的要求
```python
class SentinelOverlay:
    def __init__(self, bit="/home/xilinx/sentinel/overlay/sentinel/sentinel.bit", check=True): ...
    def check(self) -> dict:
        # 1) .bit 与 .hwh 的文件修改时间差 < 60 秒（防止用错 hwh）
        # 2) hwh 中声明的每个自研 IP，在地址 0xFC 读到的 VERSION 高 16 位与 YAML 契约一致
        # 3) 对每个可写的 SCRATCH 寄存器做写入/读回测试
        # 返回 {ip: "ok"/"fail:<原因>"}，有任一失败就抛出异常
```

### dma.py 的要求
- 统一的接口 `recv(n_bytes, timeout_s)` / `send(buf, timeout_s)`；超时后读取 DMASR 状态寄存器，并把出错位解码成可读文字（如 DMAIntErr、DMASlvErr、DMADecErr、Halted）；
- 缓冲区用 `pynq.allocate` 分配（物理连续、非缓存），所以不需要手动 flush/invalidate；如果改用可缓存的缓冲区，必须在传输前后调用 `flush()` / `invalidate()`；
- ADI `axi_dmac` 驱动（RX/TX 原始 IQ）：寄存器 `0x400 CTRL`、`0x40C FLAGS`、`0x410 DEST_ADDR`、`0x418 X_LENGTH`、`0x408 SUBMIT`、`0x428 TRANSFER_DONE`、`0x080 IRQ_PENDING`。具体以 `third_party/hdl/library/axi_dmac/axi_dmac_regmap.v` 为准，代理必须先阅读该文件。

### 验收（使用 base_z20 位流，不插射频板）
```powershell
.\tools\board.ps1 push
.\tools\board.ps1 run "python3 -m sentinel.selftest --stage base"
```
`sentinel/selftest.py --stage base` 的检查项：
- 加载 `base_z20` 位流成功；
- `axi_sysid` 读出的 ID 正确；
- `axi_ad9361` 的 `REG_VERSION`（偏移 0x0000）读数非零；
- AXI GPIO 写入后读回一致；
- AXI Quad SPI 的 `SPISR` 复位值正确。

---

## P5.3 AD9361 控制库 `src/ps/libad9361_pynq/`

**思路**：直接编译 ADI no-OS 的 `drivers/rf-transceiver/ad9361/` 驱动源码，平台层用自己写的 3 个文件替换，全部通过 `/dev/mem` 访问 AXI 寄存器。ADI 官方的 `linux-userspace` 平台要求设备树提供 spidev、gpiochip 和 UIO 节点，PYNQ 镜像中没有这些，所以不采用。

### 目录与文件
```
src/ps/libad9361_pynq/
  Makefile
  platform/z20_mmio.c        # 打开 /dev/mem，mmap 映射几段地址窗口
  platform/z20_spi.c         # 实现 no_os_spi_platform_ops：驱动 AXI Quad SPI（0x41E00000）
  platform/z20_gpio.c        # 实现 no_os_gpio_platform_ops：驱动 AXI GPIO（0x41200000），位定义见 10_hw_base.md P1.0
  platform/z20_axi_io.c      # 实现 no_os_axi_io_read/write，供 axi_adc_core/axi_dac_core 访问 0x79020000
  platform/z20_delay.c       # no_os_udelay/mdelay，用 nanosleep 实现
  app/ad9361_api_c.c         # 面向 ctypes 的 C 接口
  app/z20_init_param.c       # AD9361_InitParam 默认值，从 no-OS 的 projects/ad9361/src/app/main.c 中复制并修改
```

### AXI Quad SPI 寄存器（PG153，标准模式）
| 偏移 | 寄存器 | 用法 |
|---|---|---|
| 0x40 | SRR | 写入 0x0A 软复位 |
| 0x60 | SPICR | 0x186 = 主模式 + SPE + 手动片选 + 收发 FIFO 复位；CPOL 和 CPHA 必须与 AD9361 的 SPI 模式一致（no-OS 默认 mode 1：CPOL=0，CPHA=1，写入 bit4 = 1） |
| 0x64 | SPISR | bit0 RX_EMPTY，bit2 TX_EMPTY |
| 0x68 | SPI_DTR | 发送数据 |
| 0x6C | SPI_DRR | 接收数据 |
| 0x70 | SPISSR | 0xFFFFFFFE 选中片选 0；0xFFFFFFFF 释放 |

`write_and_read(desc, data, len)` 的流程：
1. SPISSR 写 0xFFFFFFFE（选中）；
2. 逐字节写入 DTR。FIFO 深度为 16，len 超过 16 时分批：每批写满后清除 SPICR bit8（主事务禁止位）启动传输，等待 TX_EMPTY，再读空 DRR；
3. 读回的字节写回 `data`；
4. SPISSR 写 0xFFFFFFFF（释放）。

### Makefile 关键部分
```make
NOOS ?= /home/xilinx/sentinel/third_party/no-OS
CFLAGS = -O2 -fPIC -Wall -DAXI_ADC_NOT_PRESENT=0 -D_GNU_SOURCE \
  -I$(NOOS)/include -I$(NOOS)/drivers/rf-transceiver/ad9361 \
  -I$(NOOS)/drivers/axi_core/axi_adc_core -I$(NOOS)/drivers/axi_core/axi_dac_core -Iplatform -Iapp
SRCS = $(wildcard $(NOOS)/drivers/rf-transceiver/ad9361/*.c) \
       $(NOOS)/drivers/axi_core/axi_adc_core/axi_adc_core.c \
       $(NOOS)/drivers/axi_core/axi_dac_core/axi_dac_core.c \
       $(NOOS)/drivers/api/no_os_spi.c $(NOOS)/drivers/api/no_os_gpio.c \
       $(NOOS)/util/no_os_util.c $(NOOS)/util/no_os_alloc.c $(NOOS)/util/no_os_mutex.c \
       platform/*.c app/*.c
libad9361_pynq.so: $(SRCS)
	$(CC) $(CFLAGS) -shared -o $@ $^ -lm
```
> 代理必须先执行 `Get-ChildItem third_party/no-OS/drivers/rf-transceiver/ad9361`，以及 `Get-ChildItem third_party/no-OS/util`，核对实际文件名，再相应调整 `SRCS`。no-OS 的版本不同，文件布局也会不同。缺少的符号可以根据链接错误逐个补上；需要的话可以加 `-DNO_OS_LOG_LEVEL=...`。

### C 接口（`app/ad9361_api_c.c`）
```c
int  z20_ad9361_open(uint32_t rate_hz, uint64_t rx_lo_hz, uint64_t tx_lo_hz); // 初始化，并完成数字接口调优
void z20_ad9361_close(void);
int  z20_set_rx_lo(uint64_t hz);   int z20_set_tx_lo(uint64_t hz);
int  z20_set_rate(uint32_t hz);    int z20_set_rf_bw(uint32_t rx_hz, uint32_t tx_hz);
int  z20_set_rx_gain_mode(int mode /*0 mgc,1 fast,2 slow,3 hybrid*/);
int  z20_set_rx_gain(int32_t db);  int z20_get_rssi_db100(int32_t *rssi);
int  z20_set_tx_atten_mdb(uint32_t mdb);   // 单位 0.001 dB；由 Python 侧的 safety.py 做保护
int  z20_bist_loopback(int mode);           // 0 关闭，1 数字 TX→RX 回环
int  z20_get_tuning_result(int *clk_delay, int *data_delay, int *window); // 接口调优窗口
int  z20_fastlock_store(int profile);  int z20_fastlock_recall(int profile);
```
`z20_ad9361_open` 的初始化顺序固定如下：
1. 复位芯片；
2. 调用 `ad9361_init`；
3. **立即**调用 `ad9361_set_tx_attenuation(phy, 0, 89750)`，并把 TX 状态机保持在关闭状态；
4. 设置 RX 参数；
5. 返回接口调优结果。

### 板上编译（代理只生成代码，编译在板上进行）
```powershell
.\tools\board.ps1 push
scp -r $env:REPO\third_party\no-OS\drivers $env:REPO\third_party\no-OS\include $env:REPO\third_party\no-OS\util xilinx@<ip>:/home/xilinx/sentinel/third_party/no-OS/
.\tools\board.ps1 run "make -C ps/libad9361_pynq -j2"
```

### Python 封装（`src/ps/sentinel/rf/ad9361.py` + `safety.py`）
```python
class TxGuard:
    MODES = {"air": 30.0, "cable": 10.0}     # 空口模式下限 30 dB；电缆模式下限 10 dB（必须串接 30 dB 衰减器）
    def __init__(self, mode="air"):
        assert mode in self.MODES; self.mode = mode
    def check(self, att_db: float):
        lo = self.MODES[self.mode]
        if att_db < lo: raise PermissionError(f"TX atten {att_db} dB < {lo} dB in {self.mode} mode")
    def set_mode(self, mode, confirm_attenuator: bool = False):
        if mode == "cable" and not confirm_attenuator:
            raise PermissionError("cable mode requires confirm_attenuator=True (30 dB inline)")
        self.mode = mode

class AD9361:
    def __init__(self, lib="/home/xilinx/sentinel/ps/libad9361_pynq/libad9361_pynq.so", guard=None): ...
    def open(self, rate=30.72e6, rx_lo=100e6, tx_lo=2.45e9) -> dict  # 返回接口调优结果
    rx_lo, tx_lo, rate, rx_bw, rx_gain, rx_gain_mode   # 属性形式访问
    def set_tx_atten(self, db: float)                  # 每次调用都先经过 guard.check
    def bist_loopback(self, on: bool)
```
**单元测试**（在 PC 上就能运行，用 mock 代替 so 库）：`src/ps/tests/test_safety.py`，覆盖以下情况：
- 空口模式拒绝 29.75 dB；
- 电缆模式未确认时拒绝切换；
- `loopback_eval` 在模拟 RSSI > −30 dBm 时停止，并把衰减恢复为 89.75 dB；
- 抛出异常后，TX 处于关闭状态。

> 电缆模式（C1 备选分支）的代码在这里**一并实现并测试**，这样衰减器到货后无需改代码即可执行 C1。

---

## P5.4（S3）应用层 `src/ps/sentinel/app/`

| 文件 | 职责 | 对应功能 |
|---|---|---|
| `pipeline.py` | 启动和停止 PL 处理链；`set_source(rf/replay/test)` | 创新点 7 |
| `acq.py` | 采集线程：等待列表就绪中断 → 读取目标列表、占用度和告警 | F3、F10 |
| `tracker.py` | 关联前后帧的目标，分配跟踪 ID，多次结果投票 | F3 |
| `scheduler.py` | 选择下一个要识别的目标，写入 `nco_capture`，取回 IQ 和 HOC | F4 |
| `amc/infer_np.py` | INT8 推理（由 P2.9 导出） | F6 |
| `estim.py` | 中心频率、带宽、SNR、符号速率估计 | F5 |
| `sync.py` | 四次方频偏估计 + Gardner 定时 + Costas 载波环，计算 EVM | F7 |
| `sweep.py` | 全景扫频：分段调谐 → 等待 PLL 锁定 → 采集 K 帧 → 拼接 | F9 |
| `record.py` | ADI RX DMA 录制原始 IQ，保存为 SigMF；回放 DMA 注入 | F11 |
| `txgen.py` | 用 `siggen` 生成调制信号，经 ADI TX DMA 循环发送（经过 TxGuard） | F12 |
| `loopback_eval.py` | 闭环评测，两个子命令：`calibrate`（TX 衰减从 89 dB 逐步减小，直到达到目标 SNR 或触及下限，输出 `cal.json`）；`sweep`（固定 TX 衰减，通过 `src_mux` MODE=3 数字注噪扫描 SNR，10 类调制轮流发送，统计混淆矩阵并保存带标签的数据集）。参数 `--link air\|cable`，其中 cable 必须带 `--confirm-attenuator 30`。RSSI > −30 dBm 时自动停止；`finally` 中关闭 TX | F13 |
| `bench/pfa_measure.py`、`bench/pd_curve.py` | 实测虚警率（空闲频段或 50 Ω 负载）；Pd 曲线（空口注噪 / 回放） | 指标 |
| `net.py` | 通过 UDP 推送频谱和目标列表（端口 5005，JSON 格式），PC 端客户端放在 `tools/pc_viewer.py` | F14 |
| `health.py` | 读取 XADC（`/sys/bus/iio/devices/iio:device*/in_temp0_*`）和 `perf_mon` | F16 |
| `ui/` | UI 图层绘制（Pillow，RGB565）、GT9147 触摸驱动（AXI IIC）、事件路由 | F7、F17 |
| `main.py` | 多进程入口（采集和 UI 在 CPU0，识别在 CPU1，用 `os.sched_setaffinity` 绑定） | 全部 |

**开机自启**（`board/scripts/sentinel.service`）：
```ini
[Unit]
Description=Spectrum Sentinel
After=network.target
[Service]
Type=simple
User=root
Environment=PYTHONPATH=/home/xilinx/sentinel/ps
Environment=XILINX_XRT=/usr
WorkingDirectory=/home/xilinx/sentinel
ExecStart=/usr/local/share/pynq-venv/bin/python3 -m sentinel.app.main --mode monitor
Restart=on-failure
[Install]
WantedBy=multi-user.target
```
> PYNQ 2.7 的 Python 路径可能是 `/usr/local/share/pynq-venv/bin/python3` 或 `/usr/bin/python3`。代理根据 `docs/board_info.md` 中记录的信息确定。

安装命令：
```powershell
.\tools\board.ps1 run "cp scripts/sentinel.service /etc/systemd/system/ && systemctl daemon-reload && systemctl enable sentinel"
```

---

## P5.5 教学 notebook（`board/notebooks/lab_01..lab_08`）

每个 notebook 都包含：原理说明（Markdown）、参数控件（`ipywidgets`）、实时图表、思考题。
**默认使用回放模式**（读取 `data/reference` 和 `data/captured/samples`），这样没有射频板也能完成全部实验。

| 文件 | 主题 |
|---|---|
| `lab_01_fft_window.ipynb` | 窗函数与频谱泄漏 |
| `lab_02_cfar.ipynb` | CA、GO、SO 三种 CFAR 的对比，以及 Pfa 与 Pd 的关系 |
| `lab_03_channelizer.ipynb` | 临界采样与过采样 PFB 的对比 |
| `lab_04_hoc.ipynb` | 高阶累积量 |
| `lab_05_amc_train.ipynb` | 训练并部署自己的调制识别模型 |
| `lab_06_analog_demod.ipynb` | AM/FM 解调与监听 |
| `lab_07_sync.ipynb` | 同步与 EVM |
| `lab_08_recon.ipynb` | 综合侦察 |

---

## P5.6 阶段验收
- PC 端：`pytest src/ps/tests -q` 全部通过；
- 板端（base_z20 位流）：`python3 -m sentinel.selftest --stage base` 通过；
- 板端（sentinel 位流，测试源模式）：`python3 -m sentinel.selftest --stage full --source test` 通过（具体检查项见 `60_board.md` 的 G1）。
```powershell
git add src/ps board/notebooks board/scripts tools runbook/STATUS.md
git commit -m "[P5] PS software stack"
```
