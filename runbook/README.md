# Runbook：可直接逐步执行的完整实施手册

> 项目：基于 Zynq-7000 与 AD9361 的实时频谱智能监测与自动调制识别终端（初级组）
> 硬件：正点原子 Z20（XC7Z020-2CLG484）+ AD-FMCOMMS3-EBZ + ATK-MD0700 V2.4 SSD1963 J22 8080 屏（800×480）
> 设计依据：`report/design_plan.md`（v2 总方案）。本目录只规定"怎么做"，设计细节以总方案为准。
> 执行对象：人工或代理（Claude Code 等）。**代理先读仓库根目录的 `AGENTS.md`**（环境、工具下载、执行协议、安全规则），再读本文件。

---

## 1. 文件索引（按执行顺序）

| 文件 | 阶段 | 内容 | 主要执行者 |
|---|---|---|---|
| `review_20261102.md` | 评审 | 当前成果评审及 R1–R8 改进建议 | 代理 |
| `80_next.md` | N0–N9 | 后续主执行方案；M-A（N0–N5）最优先 | 代理 + 人工 |
| `review_20261103.md` | — | **第三阶段评审**：N0–N4 成果与 D1–D8 不足 | 代理先读 |
| `90_plan.md` | X0–X9 | **第三阶段执行策划案，优先于 80_next.md 和 30–70** | 代理 |
| `95_final.md` | Y0–Y7 | **第四阶段最终方案：功能闭环优先，优先于 90_plan** | 代理 |
| `99_finish.md` / `KICKOFF_F.md` | F0–F6 | 收尾方案与交接指令 | 代理 |
| `G_showcase.md` / `KICKOFF_G.md` | G0–G6 | **演示增强：LCD v3、上位机、show 联动（插在 F4 之前）** | 代理 + 用户 |
| `H_interactive.md` / `KICKOFF_H.md` | H1–H3 | **快速扫描、上位机讲解控制台（取代 G5 彩排）、无线电扩展** | 代理 + 用户 |
| `I_presentation.md` / `KICKOFF_I.md` | I0–I6 | **讲解定稿：一键场景、讲解模式、WiFi 信标（取代 H 未完成部分）** | 代理 + 用户 |
| `J_polish.md` / `KICKOFF_J.md` | J0–J6 | **最终阶段：展示定稿与上位机重点打磨（取代 I 未完成部分）** | 代理 + 用户 |
| `KICKOFF_Y.md` | — | 第四阶段交接提示词 | 用户 |
| `../docs/antenna_sd_guide.md` | — | 天线配置 A/B/C/D 与 SD 卡安全规则 | 用户 + 代理 |
| `00_env.md` | P0 | 工具安装、仓库初始化、依赖拉取 | 代理 + 人工（安装授权） |
| `10_hw_base.md` | P1 | ADI HDL 移植到 Z20，生成基础位流 | 代理 |
| `20_golden.md` | P2 | 信号生成、全链路黄金模型、模型训练 | 代理 |
| `30_rtl_ip.md` | P3 | 自研 RTL/HLS IP 与逐模块仿真比对 | 代理 |
| `40_integration.md` | P4 | 系统集成、时序收敛、构建与报告 | 代理 |
| `50_ps_sw.md` | P5 | PYNQ 端驱动、AD9361 驱动、应用与 UI | 代理 + 人工（上板） |
| `60_board.md` | P6 | 上板门禁 G1/G2/G3（**主线，不需要衰减器**）+ 备选分支 C1（有衰减器时执行） | **人工为主**，代理分析 |
| `70_deliver.md` | P7 | 对比实验、技能包、报告、开源发布 | 代理 |
| `STATUS.md` | — | 每一步的执行状态（代理维护） | 代理 |

**2026-11-03 起，按 `90_plan.md` 的 X0→X9 执行；90 > 80 > 30–70，M-A为X0–X3。N0–N4为既有验收基线。** 原 J26/RGB/VDMA/v_tc/rgb2lcd/GT9147 显示方案作废，统一采用 J22 SSD1963 8080 直驱；触摸暂不实现。原分册不冲突的数值规格和验收要求继续使用。

**依赖关系**（箭头表示"必须先完成"）：
```
00 ──▶ 10 ──▶ 40 ──▶ 60(G1) ──▶ 60(G2) ──▶ 60(G3) ──▶ 70
 │           ▲  ▲                 ▲
 ├──▶ 20 ──▶ 30 ┘                 │
 └──▶ 50(S1/S2 可提前) ────────────┘
```
P1、P2、P5 前半部分可以并行；P3 的每个模块依赖 P2 中对应的黄金模型。

---

## 2. 代理执行协议（必须遵守）

1. **一步一步执行**：每一步都有唯一编号（如 `P1.3`）。按编号顺序执行，除非文件中注明"可并行"。
2. **执行前**：检查该步的"前置条件"。不满足就停止，并在 `STATUS.md` 中写明缺什么。
3. **执行中**：
   - 命令一律在 PowerShell 中执行，工作目录为 `$env:REPO`（除非步骤另有说明）；
   - 每条长命令（Vivado、HLS、训练）的输出重定向到 `logs/<步骤号>.log`；
   - 只修改该步骤"产出文件"列出的文件，不得改动 `third_party/` 下的 ADI 源码（需要改动时，按 P1 的"覆盖层"机制操作）。
4. **执行后**：运行该步的"验收命令"，把结果写入 `STATUS.md`：`DONE` / `FAIL` / `BLOCKED-HUMAN`。
5. **失败处理**：按该步的"排错"小节尝试修复，最多 3 次；仍失败则标记 `FAIL`，附上日志关键行，停下来等待人工。
6. **人工步骤**：标注 `👤 HUMAN` 的步骤，代理不得自行假定已完成。代理应输出清晰的操作说明，等待用户回报结果后再继续。
7. **大模型协作记录**：每完成一个阶段，把本阶段的关键提示词、模型回答、出错与纠正过程整理到 `report/llm_logs/<阶段号>_<主题>.md`（竞赛评分项要求）。
8. **提交**：每一步验收通过后执行一次 git 提交，提交信息格式为 `[P1.3] 简述`。

---

## 3. 全局约定

### 3.1 路径与变量

| 名称 | 值 |
|---|---|
| 仓库根目录 `$REPO` | `$env:REPO` |
| Vivado | `$env:XILINX_ROOT\Vivado\bin\vivado.bat` |
| Vitis（HLS / XSCT） | `$env:XILINX_ROOT\Vitis\bin\vitis-run.bat`、`$env:XILINX_ROOT\Vitis\bin\xsct.bat` |
| xsim 工具 | `$env:XILINX_ROOT\Vivado\bin\xvlog.bat` / `xelab.bat` / `xsim.bat` |
| 正点原子参考资料 | `vendor/atk/`（只读；`docs/` 是原理图和装配图，`pynq_ref/` 是 PYNQ 例程和 IP，见 `vendor/atk/README.md`） |
| Python 虚拟环境 | `$env:REPO\.venv` |
| ADI HDL | `$env:REPO\third_party\hdl`（Vivado 2025.2 用分支 `hdl_2026_r1`，2026.1 用 `main`） |
| ADI no-OS | `$env:REPO\third_party\no-OS`（main 分支，记录 commit） |
| 开发板 | `$env:BOARD_IP`（取自 `docs/board_info.md`），用户 `xilinx`，板上仓库目录 `/home/xilinx/sentinel` |

**每次打开新的 PowerShell 终端，先在仓库根目录执行**：
```powershell
. .\tools\env.ps1
```
它会设置 `REPO`、自动探测 `XILINX_ROOT`、把 Vivado/Vitis 加入 PATH、设置 `ADI_IGNORE_VERSION_CHECK=1`、读取 `BOARD_IP`，并激活 `.venv`。

**路径书写规则**：PowerShell 中用 `$env:REPO\...`；Tcl 中用 `$::env(REPO)/...`；Python 中用相对于 `__file__` 的路径。**禁止写死盘符**。
> 历史写法对照：旧文档中的 `third_party/atk_ref/` 一律等于 `vendor/atk/pynq_ref/`；`$ATK\3_开发板原理图\...` 一律等于 `vendor/atk/docs/...`。

### 3.2 命名规范
- 仓库内所有目录名和文件名只用**小写英文、数字、下划线、连字符**（竞赛要求）。
- RTL 模块名与文件名一致，如 `cfar_core.v` 中的模块就是 `cfar_core`。
- 每个模块配一个 testbench：`sim/tb/tb_<module>.sv`；对应的参考数据放在 `data/reference/<module>/`。

### 3.3 数据格式（全项目统一）
| 数据 | 格式 |
|---|---|
| 复 IQ 样本 | int16 交织 `[I0,Q0,I1,Q1,...]`，小端。AD9361 的 12 位数据**左对齐到 16 位**（I = adc << 4），满幅 = ±32752 |
| 文件格式 | 仿真参考用 `.npy`；实采和录制用 SigMF（`.sigmf-data` + `.sigmf-meta`） |
| 功率谱 | uint32，线性功率 |
| dB 值 | Q8.8 有符号定点（int16，单位 dB） |
| 信号列表条目 | 16 字节：`start_bin:u16, stop_bin:u16, peak_bin:u16, flags:u16, peak_pwr:u32, sum_pwr:u32` |

### 3.4 安全规则（任何步骤都不得违反）
1. **J7、J8 必须设为 2.5V**，在插 FMCOMMS3 前完成（见 `60_board.md` G2.1）。严禁 3.3V；1.8V 在 HR Bank 上无法输出 LVDS。
2. **没有接衰减器时，禁止用电缆直连 TX→RX**。主线只允许：BIST 数字回环、天线接收、空口闭环（软件强制 TX 衰减 ≥ 30 dB）。
3. 软件中 TX 衰减的下限由 `TxGuard` 控制：空口模式为 30 dB，电缆模式为 10 dB（只有显式确认串接了 30 dB 衰减器才允许切换）。
4. AD9361 初始化后，必须先把 TX 衰减设为 89.75 dB，并保持 TX 关闭，直到用户显式开启。
5. 空口发射只能使用 ISM 频段（433.05–434.79 MHz、2400–2483.5 MHz、5725–5850 MHz）。

### 3.5 Linux 主机对照（仅当目标设备是 Linux 时使用）
| PowerShell | bash |
|---|---|
| `. .\tools\env.ps1` | `source tools/env.sh`（由代理按 env.ps1 的逻辑改写，`XILINX_ROOT` 探测 `/tools/Xilinx`、`/opt/Xilinx`、`~/Xilinx`） |
| `vivado.bat` / `vitis-run.bat` | `vivado` / `vitis-run`（先 `source $XILINX_ROOT/Vivado/settings64.sh`） |
| `*> logs/x.log` | `> logs/x.log 2>&1` |
| `Test-Path a` | `test -e a` |
| `.\tools\sync_hw.ps1 -Proj X` | `tools/sync_hw.sh X`（rsync 实现） |
| ADI 库编译 `adi_make::lib all` | 在工程目录直接执行 `make`（会自动编译依赖的库） |

---

## 4. 时间预估（连续推进，供参考）

| 阶段 | 代理工作量 | 是否依赖人工 |
|---|---|---|
| P0 环境 | 1–2 小时 | 需要人工授权安装 |
| P1 HDL 移植 | 4–8 小时（含 IP 库编译） | 否 |
| P2 黄金模型 | 6–10 小时 | 否 |
| P3 自研 IP | 2–4 天 | 否 |
| P4 集成 | 1–2 天 | 否 |
| P5 软件 | 2–3 天（与 P3 并行） | 上板调试需要人工 |
| P6 上板 | 1–2 天 | **是** |
| P7 交付 | 1–2 天 | 否 |

**衰减器策略**：主线 G1 → G2 → G3 完全不依赖衰减器，全部提交物都能在没有衰减器的情况下完成。G3 中的"识别率–SNR 曲线"用"空口闭环 + PL 数字噪声注入"得到，SNR 可控、可复现。如果之后拿到 30 dB 衰减器，执行备选分支 C1（约半天），用电缆闭环的数据**补充或替换**报告中的对应指标；不执行 C1 也不影响提交。
