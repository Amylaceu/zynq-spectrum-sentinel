# AGENTS.md —— 执行代理入口（先读本文件）

> 2026-11-03收尾覆盖规则：先读本文件、`runbook/CONTEXT.md`、`runbook/99_finish.md`、天线指南及STATUS顶部F表。99_finish优先于旧方案及下方历史进度说明。固定100MHz/3.84MSPS位流，不重新训练、调CFAR或构建；F1–F3确因PL缺陷受阻时须先征得用户同意。F0先提交和完整快照；F阶段只允许2400–2483.5MHz发射，保留所有历史FAIL。

> 项目：**zynq-spectrum-sentinel**：基于 Zynq-7000 与 AD9361 的实时频谱智能监测与自动调制识别终端
> 竞赛：全国大学生嵌入式芯片与系统设计竞赛'2026 · FPGA 创新设计赛道（AMD）· 自主选题赛道（初级组）
> 你的身份：执行代理。目标是严格按照 `runbook/` 中的步骤，把本仓库从"方案"推进到"可提交的完整作品"。
> 运行设备：**与写方案的设备不同**。所有路径一律相对仓库根目录，或使用下文的环境变量，**不要假设任何绝对路径**。

---

## 1. 阅读顺序（2026-11-03起）

1. 本文件。
2. `runbook/review_20261103.md`。
3. `runbook/90_plan.md`（当前主计划 X0–X9）。
4. `docs/antenna_sd_guide.md`。
5. `runbook/STATUS.md`、`docs/n4_acceptance_summary.md`。
6. 需要细节时阅读 `80_next.md`、`30–70` 分册及总方案。

当前Y阶段冲突优先级：用户当前指令 > `95_final.md`（含Z7–Z9）> `90_plan.md` > `80_next.md` > `30–70`。旧方案和原始验收保留作历史证据。Y0已完成后先复核状态，不重复初始化工程；X1–X4及Y2原量化FAIL保留。Y3改为板载喇叭，先做1kHz/3秒出声测试；每个子项最多3轮，未达标据实记录后按当前方案继续。

仓库根目录 = 经 `git rev-parse --show-toplevel` 核实后的当前工作目录。若启动目录不是仓库，先定位并进入实际仓库；不在旧规划目录执行，不写死盘符。脚本由 `$PSScriptRoot` 或 `__file__` 定位，操作相对仓库根目录。

每步开始说明天线配置，只有用户确认后才进行射频操作。X0配置A已于2026-11-03确认。板卡断电前须执行 `sudo sync && sudo shutdown -h now`；测试中不得直接断电/复位。SD整卡备份是人工步骤。

本轮已授权本地Git提交；姓名邮箱仅配置本仓库，不修改全局身份、不推送或发布GitHub。每步通过后按 `[Xn] ...` 提交；未验收的步骤不得标DONE。

`report/execution_plan.md` 为历史规划，不执行。

---

## 2. 硬件事实（不可更改，已由原理图核实）

| 项目 | 值 |
|---|---|
| 开发板 | 正点原子 Z20 ZYNQ（核心板 `ZYNQ7020_484_CORE_1V0_250304` + 底板 `ZYNQ7020_484_BASE_1V0_250716`） |
| 器件 | **xc7z020clg484-2** |
| PS | 双核 Cortex-A9 767 MHz；DDR3 MT41J256M16 ×2（32 位，533 MHz，共 1 GB） |
| 射频 | AD-FMCOMMS3-EBZ（AD9361），插在底板 FMC LPC 座 J31 |
| FMC 所在 Bank | Bank33 + Bank34，均为 HR Bank；**VCCO 由跳线 J7（B33）、J8（B34）选择，必须为 2.5V** |
| 显示 | ATK-MD0700 V2.4（SSD1963，8080 16 位，800×480）接 J22；触摸暂不使用 |
| 音频 | 当前按95_final Z7：ES8388 ROUT2 → MD8002A → J36板载喇叭；P1/LINE_OUT不再单独开发或验收。软件已迁移OUT1/OUT2及约−21dB初始化；尚未上板播放或验收。 |
| 板载软件 | 正点原子 PYNQ 2.7 镜像（`ATK-Z20-2.7.0.img`） |
| 用户已完成 | AD9361 和 LCD 已在板上"能点亮、能初始化"，但还没有实现任何处理功能。**用户已有的工程不在本仓库中**，如需复用，在 `runbook/STATUS.md` 中标记 BLOCKED-HUMAN，请用户提供 |

板级参考资料（原理图、装配图、引脚表、正点原子 PYNQ 例程与 IP）已放在 `vendor/atk/`（见 `vendor/atk/README.md`）。**不要再到外部寻找正点原子资料盘**。

---

## 3. 开发环境（目标设备）

### 3.1 操作系统
- **首选 Windows 10/11 x64**。runbook 中的命令都是 PowerShell 写法。
- Linux（Ubuntu 22.04/24.04）也可以：PowerShell 命令按 `runbook/README.md` §3.5 的对照表改写；ADI 库可以直接用 `make` 编译。

### 3.2 硬件要求
| 项目 | 最低 | 推荐 |
|---|---|---|
| 内存 | 16 GB | 32 GB |
| 磁盘剩余 | 80 GB（Vivado 约 50 GB + 工程约 30 GB） | 150 GB SSD |
| 网络 | 能访问 GitHub、PyPI、AMD 官网 | — |
| 与开发板的连接 | 同一局域网（SSH / Jupyter），以及一根 USB 串口线 | — |

### 3.3 必需工具（第一次运行前检查，缺少的按链接安装）

| 工具 | 版本 | 下载 | 检查命令 |
|---|---|---|---|
| AMD Vivado + Vitis（统一安装包） | **2025.2**（首选，与方案一致）或 2026.1 | 2025.2：<https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2025-2.html>；2026.1：<https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2026-1.html>（需要 AMD 账号） | `vivado -version` |
| Git for Windows | ≥ 2.40 | <https://git-scm.com/download/win> | `git --version` |
| Python | **3.10–3.12** | <https://www.python.org/downloads/windows/> | `python --version` |
| OpenSSH 客户端 | Windows 自带 | 设置 → 可选功能 → OpenSSH 客户端 | `ssh -V` |
| 7-Zip（解压镜像） | 任意 | <https://www.7-zip.org/> | — |
| balenaEtcher（烧录 SD 卡，人工操作） | 任意 | <https://etcher.balena.io/> | — |
| CH340 串口驱动（人工操作） | — | <https://www.wch.cn/downloads/CH341SER_EXE.html> | 设备管理器中出现 COM 口 |
| 串口终端（人工操作） | — | MobaXterm <https://mobaxterm.mobatek.net/> 或 PuTTY | — |

**Vivado 安装要求**：
- 安装时勾选 **Vivado** 和 **Vitis**（Vitis 包含 HLS 和 XSCT）；器件只需要 **Zynq-7000**，可以显著减小体积。
- 许可：xc7z020 属于免费器件。2025.2 选 "Vivado ML Standard"；2026.1 选免费档（安装界面中名为 BASIC 或 Standard 的那一档，以实际安装界面为准）。
- **版本记录**：实际安装的版本写入 `docs/toolchain.md`。如果用了 2026.1，后续 ADI HDL 改用与之匹配的分支（见 `runbook/10_hw_base.md` 的 P1.0）。

### 3.4 环境变量（由 `tools/env.ps1` 设置，P0.4 生成）

| 变量 | 含义 | 示例（仅为示例，以实际为准） |
|---|---|---|
| `REPO` | 仓库根目录 | `D:\work\zynq-spectrum-sentinel` |
| `XILINX_ROOT` | Vivado 安装目录中的版本目录 | `C:\AMDDesignTools\2025.2` 或 `C:\Xilinx\2025.2` |
| `ADI_IGNORE_VERSION_CHECK` | 跳过 ADI 的 Vivado 版本检查 | `1` |
| `BOARD_IP` | 开发板 IP 地址（从 `docs/board_info.md` 读取） | `192.168.1.50` |

`tools/env.ps1` 会**自动探测** `XILINX_ROOT`：依次搜索 `C:\AMDDesignTools`、`C:\Xilinx`、`D:\Xilinx`、`D:\AMDDesignTools`、`E:\Xilinx`、`F:\Vivado`、`F:\Xilinx`，找到 `*\Vivado\bin\vivado.bat` 即可。找不到时，读取用户设置的环境变量 `XILINX_ROOT`。

### 3.5 仓库路径要求
- 仓库放在**短路径**下，例如 `D:\zs` 或 `C:\work\zs`。ADI 工程的路径很深，长路径会触发 Windows 的 260 字符限制。
- 路径中不能有中文、空格或特殊字符。
- 开启 git 长路径支持：`git config --global core.longpaths true`

---

## 4. 执行协议（必须遵守）

1. **按编号顺序执行**（`P0.1` → `P0.2` → …）。只有步骤中注明"可并行"时，才能交叉执行。
2. **执行前**检查"前置条件"，不满足就停下，在 `STATUS.md` 中写明原因。
3. **每条长命令**（Vivado、HLS、训练、编译 IP 库）都要把输出重定向到 `logs/<步骤号>.log`，并在后台运行；完成后检查日志末尾。
4. **执行后**运行该步的"验收"命令，把结果写入 `runbook/STATUS.md`：`DONE` / `FAIL` / `BLOCKED-HUMAN`，并附上日志路径或产物路径。
5. **失败处理**：按步骤中的"排错"小节尝试，**最多 3 轮**。仍然失败就标记为 `FAIL`，摘录日志关键行，停下来等待人工处理。
6. **人工步骤**（标注 `👤 HUMAN`）：输出清晰的操作说明，然后**停下等待用户回报**，不得自行假定已经完成。
7. **不得修改** `third_party/` 中的第三方源码。需要修改 ADI 工程时，使用 `src/hw/<proj>/` 覆盖层，再用 `tools/sync_hw.ps1` 同步过去。
8. **不得修改** `vendor/atk/` 中的文件（只读参考）。
9. **提交**：每个步骤验收通过后执行一次 `git commit -m "[P1.3] <简述>"`。不要提交 `logs/`、`build/work/`、`vendor/atk/`、`.venv/`。
10. **大模型协作记录**（竞赛评分项）：每完成一个阶段，把关键提示词、回答、出错与纠正过程整理到 `report/llm_logs/<阶段>_<主题>.md`，格式见 `runbook/70_deliver.md` 的 P7.3。
11. **不确定时停下来提问**，不要猜测硬件连接或引脚。

---

## 5. 射频安全规则（任何步骤都不得违反）

1. **J7、J8 必须设为 2.5V**，并且在插 FMCOMMS3 之前用万用表测量 FMC 的 G39/H40 引脚，读数应为 2.40–2.62V（👤 人工完成）。
2. **主线方案不使用衰减器**。**禁止**用 SMA 线把 TX 和 RX 直接连起来。
3. 收发验证按以下优先级进行：
   - **(a) BIST 数字回环**：在 AD9361 芯片内部，从数字接口回环，不经过射频；
   - **(b) 低功率空口闭环**：TX 和 RX 各接一根天线，间距 ≥ 30 cm，软件强制 TX 衰减 ≥ 30 dB（RSSI 超过 −30 dBm 时自动停止）；
   - **(c) 电缆闭环**：**只有**在串接了 30 dB、DC–6 GHz 衰减器之后才允许，属于备选分支 C1。
4. 软件中 `TxGuard` 的下限：`air` 模式为 30 dB，`cable` 模式为 10 dB（必须显式确认已接衰减器才能切换）。
5. AD9361 初始化后，**立即**把 TX 衰减设为 89.75 dB，并保持 TX 关闭。
6. 空口发射只能使用 ISM 频段：433.05–434.79 MHz、2400–2483.5 MHz、5725–5850 MHz。

---

## 6. 仓库结构（目标形态）

```
zynq-spectrum-sentinel/
├── AGENTS.md                 # 本文件
├── README.md                 # 面向评委/用户：简介 + 复现步骤（P7.5 完成）
├── LICENSE                   # MIT
├── runbook/                  # 执行手册（00–70 分册 + STATUS.md）
├── report/                   # design_plan.md（总方案）、design_report.md、llm_logs/、figures/
├── docs/                     # hardware_bom.md、board_info.md、toolchain.md、hw 汇总等
├── vendor/atk/               # 正点原子参考资料（只读，不提交）
├── third_party/              # hdl、no-OS（git submodule）
├── tools/                    # env.ps1、sync_hw.ps1、collect_hw.ps1、board.ps1、各类 Python 工具
├── src/
│   ├── hw/<proj>/            # ADI 工程覆盖层（fmcomms2_z20、sentinel_z20）
│   ├── rtl/  hls/  regs/  ip_repo/  constraints/
│   └── ps/                   # sentinel Python 包、libad9361_pynq、models
├── sim/                      # golden/、tb/、scripts/、results/
├── build/                    # build_all.ps1、scripts/、reports/
├── board/                    # overlay/、notebooks/、scripts/、measurements/
├── data/                     # reference/、synthetic/、captured/
├── skill/                    # 技能包
└── logs/                     # 运行日志（不提交）
```

---

## 7. 跨设备交接方式（人工）

`vendor/atk/` 已加入 `.gitignore`，**通过 git 推送不会带过去**。请按以下方式之一把仓库交给目标设备：
- **方式 A（推荐）**：把整个仓库目录（包括 `vendor/`）压缩，通过 U 盘或网盘拷贝到目标设备的短路径下（如 `D:\zs`）；
- **方式 B**：目标设备上 `git clone` 仓库后，再单独拷贝 `vendor/atk/`（约 83 MB）到仓库根目录；
- **方式 C**：目标设备上也有正点原子资料盘时，执行 `python tools/pack_vendor.py "<资料盘根目录>"` 重新生成。

以下文件是早期产物，执行代理可以忽略：`runbook.rar`、`1.txt`、`report/execution_plan.md`。

## 8. 第一次运行时的动作（复制执行）

```powershell
# 0) 进入仓库根目录（路径以实际为准）
Set-Location <仓库根目录>
# 1) 阅读进度
Get-Content runbook/STATUS.md
# 2) 从 runbook/00_env.md 的 P0.1 开始
```
