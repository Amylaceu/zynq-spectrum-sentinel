# P2 黄金模型、信号生成与调制识别模型

> 目标：用 NumPy 实现与硬件**位宽一致**的全链路参考模型，作为 RTL/HLS 仿真比对和上板逐位比对的唯一基准；同时训练第一版调制识别模型。
> 代码位置：`sim/golden/`（Python 包，`sim/golden/__init__.py` 必须存在）；测试位置：`sim/golden/tests/`（pytest）。
> **可与 P1 并行执行。**

---

## P2.0 全局参数文件 `sim/golden/params.py`

后续所有模块，包括 RTL 的 `localparam` 和 PS 驱动，都从这里取值；RTL 一侧由 `tools/gen_params_vh.py` 自动生成 `src/rtl/common/sentinel_params.vh`。

```python
FS_DEFAULT   = 30.72e6     # 采样率
NFFT         = 2048
IQ_BITS      = 16          # AD9361 的 12 位数据左对齐到 16 位
WIN_BITS     = 18          # 窗系数位宽（Q1.17）
FFT_OUT_BITS = 24          # FFT IP 输出位宽（缩放后）
PWR_BITS     = 32
WELCH_ALPHA_SHIFT = 3      # 指数平均系数 2^-3
CFAR_N       = 16          # 单侧参考单元数
CFAR_G       = 2           # 单侧保护单元数
CFAR_MODES   = {"CA": 0, "GO": 1, "SO": 2}
CFAR_ALPHA_FRAC = 8        # 门限系数 alpha 用 Q8.8 定点表示
CLUSTER_GAP  = 2
MAX_TARGETS  = 32
DC_MASK_BINS = 3           # 屏蔽 DC 两侧各 3 个频点
PFB_M        = 16
PFB_D        = 8           # 2 倍过采样
PFB_TAPS_PER_PHASE = 8
PFB_COEF_BITS = 18
NCO_PHASE_BITS = 32
CAPTURE_LEN  = 1024
DISP_W, DISP_SPEC_H, DISP_WF_H = 720, 200, 300
MOD_CLASSES  = ["BPSK","QPSK","8PSK","16QAM","64QAM","2FSK","GFSK","OOK","AM-DSB","FM"]
```

**命令**：
```powershell
python tools/gen_params_vh.py sim/golden/params.py src/rtl/common/sentinel_params.vh
```
`tools/gen_params_vh.py` 的功能：导入 `params.py`，把其中所有 int 类型的大写变量输出为 `` `define SP_<NAME> <value> ``。

---

## P2.1 信号生成器 `sim/golden/siggen.py`

**接口**（必须实现）：
```python
def gen_mod(mod: str, n: int, sps: int, fs: float = 30.72e6, snr_db: float = None,
            cfo_hz: float = 0.0, phase: float = 0.0, beta: float = 0.35,
            iq_imb_db: float = 0.0, iq_imb_deg: float = 0.0, multipath: list = None,
            seed: int = 0) -> np.ndarray:  # complex64, 平均功率 = 1（加噪声之前）
    """生成单个调制信号的基带样本。"""
def gen_wideband(signals: list[dict], n: int, fs: float, noise_dbfs: float, seed: int) -> np.ndarray:
    """多个信号按各自的 f_off 搬频后叠加，再加噪声，模拟宽带场景。"""
def to_int16_iq(x: np.ndarray, backoff_db: float = 12.0) -> np.ndarray:  # 交织 int16，模拟 AD9361 的 12 位量化后左移 4 位
def from_int16_iq(b: np.ndarray) -> np.ndarray
def lfsr_gauss_fixed(n: int, seed_i: int, seed_q: int) -> np.ndarray   # 与 RTL test_src 位精确一致：32 位 Galois LFSR，取 12 个均匀样本求和
def add_noise_fixed(iq_int16: np.ndarray, noise_amp: int, seed_i: int, seed_q: int) -> np.ndarray
    # 与 RTL src_mux MODE=3 位精确一致：sat16(iq + ((noise*amp) >> 15))
def noise_amp_for_snr(sig_power_lsb2: float, snr_db: float, occ_bw_hz: float, fs: float) -> int
    # 根据实测信号功率和目标带内 SNR，计算 NOISE_AMP 寄存器的值（板端 loopback_eval 也使用这个函数）
```
各调制的实现要点：
- PSK/QAM：随机符号 → 根升余弦滤波（`beta`，跨度 8 个符号）。QAM 星座按格雷码映射，并归一化为单位平均功率。
- 2FSK：调制指数 h = 1；GFSK：BT = 0.5，h = 0.5；OOK：基带包络经根升余弦整形。
- AM-DSB：消息信号为 300–3000 Hz 多音或带限噪声，调制度 0.5–0.9；FM：频偏 5–75 kHz。
- 加噪声：`snr_db` 指"信号带宽内"的 SNR，噪声方差需要按 `fs / (符号率 × (1 + beta))` 换算到全带宽。

**测试** `sim/golden/tests/test_siggen.py`：
- 每类调制生成 4096 点，功率误差 < 0.1 dB；
- 对 QPSK 理想采样后，星座点到最近理想点的 EVM < 1%（无噪声、无频偏）；
- `to_int16_iq` → `from_int16_iq` 往返后，量化 SNR > 60 dB。

**命令**：
```powershell
pytest sim/golden/tests/test_siggen.py -q *> logs/P2.1.log
```

---

## P2.2 频谱模型 `sim/golden/spectrum.py`

**接口**：
```python
def window_coefs(kind: str = "bh4", n: int = 2048, bits: int = 18) -> np.ndarray   # int，用于 ROM
def fft_fixed(x_int16: np.ndarray, win: np.ndarray) -> np.ndarray
    # 与 Xilinx FFT IP（Pipelined Streaming，定点，缩放）的行为一致；
    # 缩放方案 SCALE_SCH 取 [2,2,2,2,2,1]（radix-4 每级右移 2，最后一级右移 1，总计 1/2048）
def power_u32(X: np.ndarray) -> np.ndarray                       # I² + Q²，取高位截断为 uint32
def welch_update(P: np.ndarray, pw: np.ndarray, shift: int) -> np.ndarray   # P + ((pw - P) >> shift)，算术右移
def to_db_q88(p_u32: np.ndarray) -> np.ndarray                    # 前导零 + 256 项查表，与 RTL 实现一致
```
> **与 Xilinx FFT IP 逐位一致的方法**：最可靠的做法是用 Vivado 自带的 C 模型（`xfft_v9_1` bitacc cmodel，位于 `$env:XILINX_ROOT\Vivado\data\ip\xilinx\xfft_v9_1\...`，部分版本需要另外下载）。如果找不到 C 模型，就按"SQNR > 70 dB"作为比对标准，并在报告中说明。代理先执行：
> ```powershell
> Get-ChildItem $env:XILINX_ROOT -Recurse -Filter "*xfft*bitacc*" -ErrorAction SilentlyContinue | Select -First 5 FullName
> ```

**测试**：单音信号的峰值落在正确频点上；Blackman-Harris 窗的旁瓣低于 −90 dBc；`to_db_q88` 的误差 < 0.05 dB。

---

## P2.3 CFAR 与聚类 `sim/golden/cfar.py`

**接口**：
```python
def cfar(p: np.ndarray, mode: str, n: int, g: int, alpha_q88: int, dc_mask: int, edge: str = "wrap"
         ) -> tuple[np.ndarray, np.ndarray]   # (门限 uint32, 命中 0/1)
def alpha_for_pfa(pfa: float, n: int, mode: str) -> int        # 返回 Q8.8；CA 用闭式解，GO/SO 用蒙特卡洛查表
def cluster(hit: np.ndarray, p: np.ndarray, gap: int, max_targets: int) -> np.ndarray
    # 结构化数组，字段 start, stop, peak_bin, flags, peak_pwr, sum_pwr
def pack_targets(t) -> bytes                                    # 按 README 3.3 节的 16 字节格式打包
```
**硬件一致性约定**（RTL 必须完全按这个实现）：
- 左窗和 L = Σ p[k−g−n … k−g−1]，右窗和 R = Σ p[k+g+1 … k+g+n]，用 40 位累加；
- CA：Z = (L+R) >> log2(2n)；GO：Z = max(L,R) >> log2(n)；SO：Z = min(L,R) >> log2(n)；
- 门限 T = (Z × alpha_q88) >> 8，饱和到 uint32；命中条件为 p[k] > T；
- DC 屏蔽：k ∈ [NFFT/2 − dc_mask, NFFT/2 + dc_mask]（频谱已做 fftshift）时，命中强制为 0；
- 聚类：从左到右扫描，两个命中段之间连续 0 的个数 ≤ gap 时合并为一个目标；目标数超过 max_targets 后丢弃，并在 flags 的 bit0 置溢出标志。

**测试**：在纯噪声上统计 1e5 个频点，实测虚警率与目标值的比值在 [0.5, 2] 之间；在 3 个信号的场景中，检测出的起止频点误差 ≤ 1 bin。

---

## P2.4 多相信道化器 `sim/golden/pfb.py`

**接口**：
```python
def design_prototype(m=16, taps_per_phase=8, atten_db=70, bits=18) -> np.ndarray  # Kaiser 窗设计，返回 int 系数
def pfb_os2(x: np.ndarray, h: np.ndarray, m=16, d=8) -> np.ndarray   # 输出形状 [frames, m]，复数
def pfb_os2_fixed(x_int16, h_int, m=16, d=8) -> np.ndarray          # 与 RTL 位宽一致的定点版本
def channel_center(ch: int, fs: float, m=16) -> float
def select_channel(f_hz: float, fs: float, m=16) -> tuple[int, float]  # (信道号, 信道内残余频偏)
def nco_mix(y: np.ndarray, f_res: float, fs_ch: float, phase_bits=32) -> np.ndarray
def decimate(y: np.ndarray, r: int) -> np.ndarray                    # CIC + 补偿 FIR，或半带滤波级联
```
**关键点**：2 倍过采样 PFB 的循环移位校正。第 n 帧的 FFT 输入要循环移位 `(n*d) % m` 个位置。必须写测试验证：在每个信道中心放一个单音，只有对应信道输出能量，相邻信道的抑制 ≥ 60 dB。

---

## P2.5 HOC 特征 `sim/golden/hoc.py`

```python
def moments_fixed(x_int16: np.ndarray, norm_shift: int) -> dict   # M20, M21, M40, M41, M42, M60, M61, M62, M63，按 48 位定点累加
def cumulants(m: dict) -> dict                                     # C20, C21, C40, C41, C42, C60, C61, C62, C63
def hoc_features(x: np.ndarray) -> np.ndarray                      # 8 维：|C20|/C21, |C40|/C21², |C41|/C21², |C42|/C21², |C60|/C21³, |C61|/C21³, |C63|/C21³, |C62|/C21³
```
**测试**：无噪声的 BPSK、QPSK、16QAM，|C40|/C21² 与理论值（2、1、0.68）的误差 < 0.05。

---

## P2.6 解调与显示参考模型

`sim/golden/demod.py`：
```python
def fm_demod(y) -> np.ndarray   # 相邻样本共轭相乘后取相角，CORDIC 位宽与 RTL 一致
def am_demod(y) -> np.ndarray
def resample_to_48k(a, fs_in) -> np.ndarray
```

`sim/golden/render.py`：生成显示引擎每一帧的像素级参考（输出 `uint16` RGB565 数组，尺寸 600×1024）：
```python
def render_frame(spec_db_q88, peak_db_q88, thr_db_q88, targets, wf_rows, dpx_hist, ui_rgb565, cfg) -> np.ndarray
```
> 规则必须与 `30_rtl_ip.md` 中 P3.6 的显示引擎规格逐条一致，包括曲线连续性、颜色键 0xF81F、调色板 LUT。

---

## P2.7 全链路串联与可视化 `sim/golden/pipeline.py`

```python
def run(iq_int16: np.ndarray, cfg: dict) -> dict
    # 返回：spec_frames, targets_per_frame, captures(每个目标的 IQ), hoc, labels(若提供模型)
```
命令行入口：
```powershell
python -m sim.golden.pipeline --demo --out sim/results/p2_demo
```
`--demo` 时生成一个场景：QPSK（+3 MHz，1 Msps）、2FSK（−5 MHz）、FM（+8 MHz）、16QAM（−9 MHz），SNR 15 dB。

输出文件：
- `sim/results/p2_demo/spectrum.png`（频谱，叠加 CFAR 门限和目标框）
- `sim/results/p2_demo/waterfall.png`
- `sim/results/p2_demo/constellations.png`
- `sim/results/p2_demo/targets.json`
- `sim/results/p2_demo/frame_ref.png`（`render.py` 渲染的完整一帧屏幕参考图）

**验收**：`targets.json` 中有 4 个目标，中心频率误差 ≤ 1 bin（15 kHz）。

---

## P2.8 导出硬件参考数据集

```powershell
python -m sim.golden.export_refs --out data/reference
```
`export_refs.py` 为每个硬件模块导出"输入 + 期望输出"文件（`.npy`，同时导出 `.hex`，供 `$readmemh` 读取）：

| 子目录 | 输入 | 期望输出 |
|---|---|---|
| `spectrum/` | 4 帧 int16 IQ（2048×2×4） | 加窗 FFT 输出、功率、Welch 平均结果、dB 值 |
| `cfar/` | 功率谱（多种场景，分别对应 CA/GO/SO） | 门限、命中、目标列表（二进制） |
| `pfb/` | 16384 点 IQ（每个信道中心一个单音，外加一个 QPSK 信号） | 每帧 16 信道输出 |
| `nco_capture/` | 指定信道号、NCO 频率字、抽取比 | 1024 点捕获结果 |
| `hoc/` | 1024 点 IQ × 10 类调制 | 9 个矩（48 位） |
| `demod/` | FM 和 AM 信道 IQ | 48 kHz 音频 int16 |
| `render/` | 一组显示输入 | 一帧 RGB565（`.hex` 和 `.png`） |

另外生成 `data/reference/manifest.json`，记录每个文件的 SHA256 和生成参数，用于复现性检查。

---

## P2.9 调制识别模型训练

**产出文件**：`src/ps/models/amc_train.py`、`src/ps/models/amc_net.py`、`src/ps/models/weights/amc_v1_fp32.pt`、`amc_v1_int8.npz`、`report/figures/amc_v1_confusion.png`、`amc_v1_acc_vs_snr.png`

**数据集**（`python -m src.ps.models.make_dataset --out data/synthetic/amc_v1`）：
- 10 类调制，SNR 取 −4 到 20 dB（步长 2 dB），每类每个 SNR 生成 2000 段，每段 1024 点；
- 随机化参数：每符号采样点数 4–16、残余频偏 ±2% 符号率、相位 0–2π、IQ 不平衡 ±1 dB / ±5°、两径瑞利信道（50% 的样本加入）；
- 保存为 `amc_v1_{train,val,test}.npz`，比例 8:1:1。同时用 `hoc.moments_fixed` 预先计算 HOC 特征，保证与硬件定点结果一致。

**网络**（`amc_net.py`，与总方案 7.6 节一致）：
```python
class AMCNet(nn.Module):
    # IQ 分支：Conv1d(2,16,7,s2)-BN-ReLU-MaxPool2 → Conv1d(16,32,5)-BN-ReLU-MaxPool2 → Conv1d(32,48,3)-BN-ReLU-GAP
    # HOC 分支：Linear(8,16)-ReLU
    # 融合：concat(64) → Linear(64,32)-ReLU-Dropout(0.3) → Linear(32,10)
```

**训练命令**：
```powershell
python -m src.ps.models.amc_train --data data/synthetic/amc_v1 --epochs 40 --bs 256 --lr 1e-3 --out src/ps/models/weights *> logs/P2.9_train.log
```

**量化与导出**：
```powershell
python -m src.ps.models.export_int8 --ckpt src/ps/models/weights/amc_v1_fp32.pt --calib data/synthetic/amc_v1/amc_v1_val.npz --out src/ps/models/weights/amc_v1_int8.npz
```
- BN 先融合进前面的卷积层；权重做 per-channel 对称 INT8 量化；激活值做 per-tensor 量化，量化系数取校准集激活值的 99.9 百分位；
- 同时导出 `src/ps/sentinel/amc/infer_np.py`，这是纯 NumPy 的 INT8 推理实现，板端使用；
- 编写测试，比对 PyTorch FP32、PyTorch 模拟量化、NumPy INT8 三者在测试集上的准确率。

**验收**（在仿真测试集上）：
- SNR = 10 dB 时总体准确率 ≥ 88%；
- INT8 相对 FP32 的准确率下降 ≤ 1%；
- 再对比两个对照模型（对比实验 E7）：只用 CNN（去掉 HOC 分支）、只用 HOC 特征加决策树（sklearn，可选），把 accuracy–SNR 曲线画在同一张图里。

---

## P2.10 阶段验收与提交

```powershell
pytest sim/golden/tests -q *> logs/P2_all_tests.log; Get-Content logs/P2_all_tests.log -Tail 3
python -m sim.golden.pipeline --demo --out sim/results/p2_demo
Test-Path data/reference/manifest.json, src/ps/models/weights/amc_v1_int8.npz
git add sim src/ps/models data/reference report/figures tools runbook/STATUS.md
git commit -m "[P2] golden models, reference vectors, AMC v1"
```
`data/reference` 的总大小控制在 50 MB 以内；超过时只提交生成脚本和 manifest，数据本身发布到 GitHub Release。
