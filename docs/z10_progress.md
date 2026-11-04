# Z10：100 MHz 与结构时序修改的执行记录

第三轮完整实现与独立审计均已结束。最终 WNS +0.026 ns、WHS +0.042 ns，
基础时序通过，Z10 的全局 +1 ns 目标仍 FAIL（差 0.974 ns）。三次完整实现已用完；
没有开启第四轮、签发 v2 部署收据、加载位流或播放音频。
第三轮消除了重复主时钟定义，旧 FIFO 复位旁路及黑盒均为 0。
最新审计为 `board/measurements/z10_v2_audit_gates_clock_root_review_r1.json`，
最终汇总为 `board/measurements/z10_final_r3.json`，均有 SHA256。
下面的构建记录按历史保留；后续详细检查和最小修改见 `docs/z10_t5_next.md`。

## 范围与基线

以经 Git 核实的仓库为根目录。独立候选工程为
`src/hw/sentinel_v2_100m/`；保留既有 v1b/v1d 位流、正式 FAIL 结论及旧测量。
本轮仅做电脑端修改、仿真和构建，没有加载位流、启动射频或播放音频。

后续 Y2/Z2/Y3 的硬件集成以 v2 候选为基础，但只有完整签核和板测通过后，
才能切换部署默认值。软件必须按位流选择时钟，不能把旧 150 MHz 测量按
100 MHz 重新解释。

## 修改与验证

| 项目 | 已完成内容 | 证据/限制 |
|---|---|---|
| T1 | MMCM 输出 100 MHz；时钟敏感 IP 元数据独立打包；PS 按镜像选择时钟参数 | BD 校验通过；旧 PS/DDR/AD9361 时钟保持原合同 |
| T2/T3 | OOC jobs=6、maxThreads=8；复用已完成 IP；实现单独重跑入口 | 并行不等于时序通过；不承诺固定构建耗时 |
| T4 ADC | 两域分别使用 XPM 复位同步器，FIFO rst 在写时钟寄存；上电保持原始复位请求 | 最新8192字、背压、溢出、I/Q不匹配及单侧复位通过；日志sim/results/z10_impl2_reset_r1/tb_adc_tap_v2.log |
| T4 CFAR | 搜索表读取与比较分两拍，索引/候选和状态一起保持 | 18 组黄金比较，阈值、命中、列表、统计等零差异；吞吐及整机时序仍待验收 |
| 时钟回归 | 100 MHz/3.84 MSPS 的源选择器、性能计数器及 PS 参数回归 | 16384 字零差异，23 项软件测试通过 |

复核发现上一版 ADC 仿真虽然打印 PASS，却有上电复位重复触发的 XPM
断言错误，因此不能当作有效通过。原日志已保存在
`logs/Z10_prior_adc_r2/`。修改后第三轮通过且无该断言错误；
`tools/test_adc_tap_v2.ps1` 会把该错误作为失败处理。

## 构建恢复记录

- `continue_r1`：一个 OOC 进程启动时出现
  `Could not open 'C' for writing / tclapp::load_apps`，不是时序违例。
- `continue_r2`：恢复脚本未识别 Vivado 的
  `Using cached IP results / Scripts Generated` 状态，尚未开始实现；已纠正。
- `continue_r3`：发现 ADC 外部 HDL 已变更但其 OOC 未自动标记过期，
  在签核前停止，日志和缓存保留。
- `continue_r3_adc_refresh`：显式重建 ADC 及其依赖顶层，其余 IP 复用。
  本次恢复仍属于同一候选的构建恢复，不能算成已经取得三次整机时序结果。
  完整实现最多三轮；启动失败、人工中断与实际时序结果分别记录。
- `continue_r3_reset_fix_r1`：修复首轮整机违例后重建ADC与顶层，保留其他OOC缓存；`run_sentinel_v2.tcl`现在会在显式刷新ADC时同步强制重建顶层，避免复用旧综合网表。该轮已结束：WNS+0.012ns/WHS+0.028ns，Z10目标FAIL。

恢复时会将待重建 run 的日志、报告和 Tcl 先存入本次
`build/reports/sentinel_v2_100m/<tag>/prior_runs/`，然后仅 reset 对应 run。
后续修改 BD module reference 的 RTL 时，不能只信任 `NEEDS_REFRESH`；
必须核对源文件与 checkpoint 输入，对 ADC 使用 `-RefreshAdc`。

## 可复现命令（PowerShell 7）

这些命令是入口说明；已有同名测量/退出文件时不要覆盖，按实际状态复用。
Vivado 长任务使用后台 PowerShell 并重定向 stdout/stderr 到 `logs/`；
本轮相关任务已启动，切勿在同一工程上重复运行。

```powershell
. ./tools/env.ps1
# 独立仿真；只在未使用的轮次运行，不覆盖历史日志
./tools/test_v2_clock.ps1 -Attempt 2
./tools/test_adc_tap_v2.ps1 -Attempt 3
# 已有 BD 校验后恢复；本轮已启动此命令
./tools/build_sentinel_v2.ps1 -Attempt 3 -ContinueBuild -ValidatedLog logs/Z10_v2_validate_r2.log -ResumeId adc_refresh -RefreshAdc
# 后续仅改实现策略：必须先确认 synth_1 完整且输入未变
./tools/build_sentinel_v2.ps1 -Attempt 1 -ImplOnly
# 保存阶段快照，不会出具位流验收或部署许可
python tools/record_z10_checkpoint.py --tag r1
```

## 签核和后续功能

整机必须读取实际报告，检查全局与各时钟域的 WNS/WHS、CDC、DRC、引脚、
未约束路径和约束例外；Z10 目标为 WNS ≥ +1 ns、WHS ≥ 0。
不能用 false_path/multicycle 隐藏 CFAR 数据或 FIFO 复位违例。
既有第一同步级和异步控制口例外仍需逐条审查，不可扩展成全域屏蔽。

板测另需按配置 A 确认接线，完成单音、三音、回放 8192 字精确比较，
3.84 MSPS 下 SAMPLE_DROP=0 和显示 ≥30 fps。未完成不得将 Z10 标 DONE。
板载喇叭仍按 Y3/Z7 单独验收，组件仿真通过不代表已经出声。

后续优先复用既有寄存器、DMA、J22 UI 及 PS：演示控制、占用度告警、
Web 监看、扫频无需为每个功能新增 PL。新增 PL 时先模块仿真与局部预检，
再整机；LUT 超过 75% 时优先把 FM 解调迁到 PS。100 MHz 不是免验收保证。

阶段归档已生成：board/measurements/z10_checkpoint_r1.json，状态 PARTIAL，
配套 ZIP 与 SHA256 已核对。综合诊断为 WNS +0.433 ns / WHS -6.882 ns，
仅供定位；不能代替布线结果。实现进程退出后，在仓库根目录后台运行
tools/audit_sentinel_v2.ps1 -Tag r1，并将控制台输出重定向到 logs/。
审计会保存例外摘要及覆盖范围、未约束路径、时钟交互、CDC、DRC、方法学、
I/O 和同步器首级引脚。逐条复核既有 CDC/I2C 例外；不准用 false_path
或 multicycle 掩盖 CFAR 数据路径、复位 recovery 或其他真实违例。

## 第二轮结果及最后一轮

- 第二轮完整实现（reset_fix_r1）：基本时序通过，WNS +0.012ns、WHS +0.028ns；Z10 +1ns目标仍FAIL。LUT 39,253（73.78%）、BRAM 92。测量与审计为board/measurements/z10_v2_route_reset_fix_r1.json、z10_v2_audit_reset_fix_r1.json、z10_v2_audit_gates_reset_fix_r1.json，均附SHA256。
- 独立审计确认旧ADC FIFO复位D脚数量0、黑盒0，总线偏斜及音频引脚检查通过。CDC仍有110条CDC-1、4条CDC-10、26条CDC-13；不能整体豁免。旧50MHz输入的TIMING-4/27各2条重复定义需修复。
- 独立Clocking Wizard小工程证实PRIM_SOURCE=No_buffer会删除层级输入主时钟定义，同时保留OOC输入约束。第三轮clock_root_r1将该配置用于DSP和音频两块MMCM；不更改输入/输出频率、不添加false_path/multicycle，未修改第三方源码。
- 第三轮构建开始前冻结源码与封装IP，清单在build/reports/sentinel_v2_100m/inputs_Z10_v2_continue_r3_clock_root_r1.json及SHA256。综合及完整实现均已完成；TIMING-4/27在最终独立审计中均为0。日志logs/Z10_v2_continue_r3_clock_root_r1.log，退出文件是同名_exit.txt。
- 第三轮是本阶段第三次完整实现，不是无限重试。若仍未达到目标，保留FAIL，停止新的整机调参，明确列出目标与实测差异后请用户决定。

## WHS解释与后续入口

WHS +0.028ns为28ps正裕量，上一轮报告在Fast Process Corner分析。它满足当前WHS>=0约束，但仍须核实实际时钟/IO假设和CDC；正数不保证尚未审计的完整系统可靠。降频主要改善setup，通常不直接增加同沿hold裕量；要对具体短路径/时钟偏斜采用实现工具的hold修复。不得在RTL加入任意组合延迟链，也不得用false_path隐藏。

音频入口已支持--image sentinel_v2_100m，保留旧sentinel_y3默认值。V2部署在读取receipt、输入哈希、bit/HWH和时钟前不访问硬件。历史55项兼容/安全回归及4项审计解析测试通过；最新完整回归为265项，见下文；board/measurements/z10_runtime_bridge_r3.json仅代表PC测试。selftest_x1支持显式--image sentinel_v2_100m，复用原单音/三音/4x2048功率字回放，输出JSON+SHA256；尚未实际板测。

## 第三轮最终结果与详细复核

最终WNS/WHS +0.026/+0.042ns，LUT39,262（73.80%）、FF54,278、BRAM92、DSP79。
最差setup是250MHz RX域的ADI时钟监测计数器CE路径（4级、走线69.82%）；
最差hold为控制寄存器至DDS寄存器，+0.042ns、偏斜0.258ns。不能沿用第二轮
路径描述。100MHz FFT域仍只有+0.611ns且走线占96%，CPU域+0.517ns。

独立审计DRC无Error/Critical、路由错误0、偏斜和音频引脚映射通过；
CDC Critical为110/4/26，TIMING-6/7各3，外部no_input_delay=20、no_output_delay=44，
仍需逐接口复核，不整体豁免。拥塞报告未找到5级以上窗口；不能笼统归因为全局拥塞。

发现两次power_opt_design均开启，最差路径含cooolgate逻辑；它是待验证的修改方向，
不是已证实的根因。T5文档已列复用综合、单因素关闭功耗优化的方案及CDC保留条件；
尚未启动新完整实现。原三轮FAIL和旧v1b/v1d验收保持原样。

新补DRC缺失/错误及路由报告缺失的保守审计检查，4项新测试。完整PC回归
265 passed in 4.20s，证据z10_runtime_full_r3.json及SHA256；不代表任何板测通过。
本轮音频清理统一先静音/关DAC再释放I2S，异常仍做后续清理；7项相关测试已纳入。

T5第1轮（总第4次完整实现）已结束：关闭两步power_opt、复用综合，最终WNS/WHS为+0.210/+0.030ns，距+1ns目标仍差0.790ns；新最差setup转至CPU域高扇出复位网。独立审计仅自动setup余量门禁失败，但CDC/板外约束仍须人工复核。证据board/measurements/t5_result_r1.json、z10_v2_audit_t5_r1.json及SHA256。原Z10三轮FAIL不变，未部署v2、未播放喇叭；下一步以已验收v1d推进功能。
