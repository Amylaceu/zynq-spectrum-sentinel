# P7 交付：对比实验汇总、技能包、设计报告、复现验证、开源发布

> 对应竞赛提交内容 3.3.5.1 至 3.3.5.4，以及评分表中的全部 5 项。

---

## P7.1 优化对比表（"性能与资源优化"，20 分）

```powershell
python tools/make_opt_tables.py --hw build/reports --bench board/measurements/g3/bench --c1 board/measurements/c1 --out report/opt_tables.md
```
输出 E1–E12 共 12 张对比表，以及对应的图表（保存到 `report/figures/e*.png`）。每张表固定包含以下列：
`对比项 | 基线 | 优化后 | 指标 | 基线值 | 优化值 | 提升 | 资源代价 (ΔLUT/ΔDSP/ΔBRAM) | 结论`

资源演变表直接引用 `build/reports/integration_progress.md`（int1 到 int5）。

---

## P7.2 技能包 `skill/`（"大模型协作与技能包"，15 分，通用 PYNQ Skill 另有加分）

### 目录
```
skill/
  README.md                     # 总索引：每一项的适用范围、使用方法、失效条件
  pynq_overlay_check/           # ★S1  来源：src/ps/sentinel/overlay.py
  pynq_dma_kit/                 # ★S2  来源：src/ps/sentinel/dma.py + 踩坑清单
  pynq_lite/                    # ★S3  来源：src/ps/sentinel/mmio.py（/dev/mem + hwh 解析）
  regmap_codegen/               # ★S4  来源：tools/regmap_codegen.py
  golden_compare/               # ★S5  来源：tools/golden_compare.py
  vivado_report_digest/         # ★S6  来源：tools/vivado_report_digest.py
  pynq_video_kit/               # ★S7  来源：disp_engine 的 PS 侧代码 + VDMA/v_tc/rgb2lcd 的 bd 片段
  noos_ctypes_bridge/           # ★S8  来源：src/ps/libad9361_pynq/platform + ad9361.py
  board_port_checklist/         # ★S9  来源：P1 的引脚移植过程
  prompt_workflows/             # S10   来源：report/llm_logs/ 中验证过的提示词
  sdr_pitfalls/                 # S11
  amc_dataset_loop/             # S12   来源：loopback_eval.py
```

### 每个技能的 README 模板（统一格式，必须完整填写）
```markdown
# <技能名>
## 适用场景
## 不适用 / 失效条件
## 依赖
## 使用方法（含命令示例）
## 已验证效果（在哪些工程 / 板卡上实测过，附数据）
## 来源（从哪次失败或观察中总结出来，链接到 report/llm_logs/xxx.md 的具体段落）
## 文件清单
```

### P7.2.1 抽取并去除与本项目的耦合
- 把源代码复制到对应的 skill 目录；**去掉所有与本项目相关的硬编码**（地址、IP 名、路径），改为参数传入或配置文件；
- 每个技能附带一个最小示例 `example/` 和测试 `test_*.py`。

### P7.2.2 可复用性验证（必须执行，评委最看重这一项）
在**另一个与本题无关的小工程**上实际使用 S1–S8：
```powershell
# 新建一个最小工程：Z20 上的 FIR 滤波器 + AXI DMA（HLS 实现 FIR）
python skill/regmap_codegen/regmap_codegen.py skill/regmap_codegen/example/fir_ctrl.yaml --verilog build/work/reuse/rtl --py build/work/reuse/py
vivado -mode batch -source skill/vivado_report_digest/example/build_fir_dma.tcl *> logs/P7_reuse_build.log
python skill/vivado_report_digest/vivado_report_digest.py build/work/reuse/reports --out skill/vivado_report_digest/VERIFIED_fir_dma.md
```
然后在板上运行 `skill/pynq_overlay_check` 和 `skill/pynq_dma_kit` 的示例，把结果记录到各技能 README 的"已验证效果"一节。
如果手头有 PYNQ-Z2 或其他 Zynq 板卡（👤 可选），在上面再验证一次，就能证明"换板卡也能用"。

---

## P7.3 大模型协作记录 `report/llm_logs/`

| 文件 | 内容 |
|---|---|
| `00_index.md` | 按阶段索引的总目录 |
| `p1_hdl_port.md` | 原理图检索 → 引脚映射 → 被模型改正的错误（例如 1.8V/2.5V 的判断过程、FMC IIC 管脚的核实） |
| `p2_golden.md` | PFB 循环移位的推导过程，以及测试如何发现错误 |
| `p3_rtl.md` | CFAR、渲染器 RTL 的生成；testbench 失败 → 修改提示词 → 修正的完整过程 |
| `p3_hls.md` | HLS pragma 的迭代过程（E5） |
| `p4_timing.md` | 读时序报告定位瓶颈的提示词，以及修复结果 |
| `p5_noos.md` | no-OS 平台层的移植，以及链接错误的逐个修正 |
| `agent_workflow.md` | 代理工作流图：runbook → 执行 → 验收 → 失败回退（可以用 Mermaid 绘制） |

每条记录的格式：
```markdown
### [时间] 主题
**提示词**：……
**模型回答（摘要或原文）**：……
**验证**：运行了什么命令、结果如何
**纠错**：哪里错了、怎么发现的、修正后的提示词和结果
**沉淀**：是否提炼为技能包中的某一项（链接）
```
> Claude Code 的会话记录可以从桌面端导出（会话菜单 → Export），导出后放在 `report/llm_logs/raw/`，再从中摘录关键段落。

---

## P7.4 设计报告 `report/design_report.md`（最后导出为 PDF）

章节结构严格按照竞赛 3.3.5.3 的要求：
1. 选题背景与创新点：取自 `design_plan.md` 第 2 节和第 4 节，并补充实测数据；
2. 设计原理与功能框图：第 5、6、7 节，框图重绘为 PNG（draw.io 或 Mermaid）；
3. 软硬件划分依据与接口设计：第 8 节，加上 `40_integration.md` 中的地址表和中断表；
4. 优化过程，包括优化前后的性能与资源对比表：引用 `report/opt_tables.md`；
5. 大模型协作记录：`llm_logs/00_index.md` 的摘要，加上 3 个典型的纠错案例；
6. 技能包的提炼过程：从哪些失败中总结出来、如何验证有效、适用边界如何确定；
7. 复现说明：链接到根目录 `README.md` 的"从零复现"一节；
8. 实测指标：引用 `report/final_metrics.md`；
9. 附录：资源报告、时序报告、引脚表、寄存器表（由 `regmap_codegen` 自动生成 Markdown）。

导出 PDF：
```powershell
# 方案 A：pandoc（安装地址 https://pandoc.org/installing.html）+ wkhtmltopdf 或 xelatex
pandoc report/design_report.md -o report/design_report.pdf --pdf-engine=xelatex -V CJKmainfont="Microsoft YaHei" --toc
# 方案 B：在 VS Code 中安装 Markdown PDF 插件，右键导出
```

---

## P7.5 根目录 README（"复现说明"，从零开始）

必须包含以下内容，并逐条实测：
1. 硬件清单与采购链接：Z20 开发板、AD-FMCOMMS3-EBZ（<https://www.analog.com/en/resources/evaluation-hardware-and-software/evaluation-boards-kits/eval-ad-fmcomms3-ebz.html>）、7 寸 RGB 屏、两根 2.4 GHz SMA 天线（必需）；可选：30 dB SMA 衰减器（DC–6 GHz，≥2 W）和 SMA 线（用于 C1 分支）；
2. ⚠️ 上电前检查清单：J7/J8 设为 2.5V，并测量 VADJ；
3. 软件环境：Vivado 2025.2（下载地址 <https://www.xilinx.com/support/download.html>）、Python 3.10+、git；
4. 一键构建：`git clone --recursive ...` → `.\build\build_all.ps1`；
5. **无需射频板的复现路径**：直接使用 release 中的 `.bit/.hwh` → 烧录 PYNQ 镜像 → `selftest --stage full --source test` → 回放模式运行全部教学 notebook；
6. 完整射频复现路径：G2 → G3（只需要天线，不需要衰减器）；有衰减器时可以再做 C1；
7. 目录对照表（竞赛推荐结构与本仓库结构的对应关系）。

---

## P7.6 复现性验证（"文档质量与可复现性"，15 分）

```powershell
# 1) 干净目录从零构建
Remove-Item -Recurse -Force $env:TEMP\zs_clean -ErrorAction SilentlyContinue
git clone --recursive <repo_url> $env:TEMP\zs_clean
Set-Location $env:TEMP\zs_clean
.\build\build_all.ps1 *> logs/reproduce_build.log
python tools/vivado_report_digest.py build/reports/sentinel --compare $env:REPO\build\reports\sentinel --out report/reproduce_check.md
# 2) 参考数据重新生成后，SHA256 应一致
python -m sim.golden.export_refs --out build/work/refs_check
python tools/check_manifest.py data/reference/manifest.json build/work/refs_check
```
👤 **建议**：请一位没有参与开发的同学，只看 README 从零做一遍（至少走完"无需射频板"的路径），把卡住的地方记录到 `report/reproduce_feedback.md`，然后修正文档。

---

## P7.7 开源发布

```powershell
git remote add origin https://github.com/<user>/zynq-spectrum-sentinel.git
git push -u origin main
# 发布 release：附带位流、hwh、模型权重和参考数据包
# 需要安装 GitHub CLI：https://cli.github.com/
gh release create v1.0 board/overlay/sentinel/sentinel.bit board/overlay/sentinel/sentinel.hwh `
  src/ps/models/weights/amc_v3_int8.npz build/work/reference_data.zip `
  --title "v1.0 competition submission" --notes-file report/release_notes.md
```
发布前的检查清单：
- [ ] 所有目录名和文件名都只含小写英文、数字、下划线或连字符（检查命令：`Get-ChildItem -Recurse | Where-Object { $_.Name -match '[^a-z0-9_.\-]' -and $_.FullName -notmatch 'third_party|\.git' }`）；
- [ ] LICENSE 为 MIT；ADI 子模块保留各自原有的许可证；
- [ ] README 中写明器件型号；
- [ ] 不包含个人隐私信息、账号密码或板子的 IP 地址；
- [ ] `report/design_report.pdf`、`skill/README.md`、`report/llm_logs/` 都存在。

---

## P7.8 演示视频（👤 HUMAN）
建议时长 3–5 分钟，镜头顺序：
1. 硬件全貌，以及 J7/J8 跳线的特写；
2. 开机后自动进入监测界面；
3. FM 广播：检测 → 识别为 FM → 耳机播放声音；
4. 空口闭环：依次切换 10 类调制，识别结果实时变化，混淆矩阵逐步累积；
5. 全景扫频；
6. 回放模式和教学 notebook；
7. 资源和时序报告、对比实验图表。
