# X1 CFAR列表优化验收

当前X1为FAIL：实现、自检通过，原三轮及用户授权的一轮追加RF指标未同时达标；已授权转入X2。所有路径相对仓库根目录，测量与验收JSON附SHA256。总检查点为 `board/measurements/x1_acceptance_summary.json`。

## 实现与仿真

- 保留N4的v1，新增显式V1b入口、独立CFAR黄金模型/RTL/寄存器/驱动；默认Session仍使用V1。
- 最小宽度、间隙合并、最多16个硬边界屏蔽区间、功率top32，以及同帧列表/状态/统计原子发布。
- core r3：18组36864bin，门限、hit、dB、占用度各36864字，目标2304字、统计126字零差异；40位加减等价检查10096组通过。
- 整链r2：16帧32768输入、8192功率字、8960门限像素和560列快照配对通过。饱和输入吞吐约29.89MSPS，仅为仿真结果；不是X2零丢样带宽验收。
- 整机r1因WNS −0.155ns失败，未部署。改用等价carry-save加减后r2通过，未放松时钟/例外约束。
- 最终r2：WNS 0.000ns、WHS +0.032ns、WPWS +0.264ns，setup/hold/pulse失败端点均0；31条bus-skew最小裕量+2.997ns。
- 资源：30626 LUT、42779 FF、47.5 BRAM、64 DSP。129项冻结输入与构建一致。

证据：`sim/results/x1_core_r3_acceptance.json`、`sim/results/x1_chain_r2_acceptance.json`、`board/overlay/sentinel_v1b/acceptance.json`、`docs/x1_v1b_prebuild_r2.json`。

## 板端有限自检

文件部署r1共16项，保留v1及旧runtime备份。自检单音误差0bin；三音724/1088/1324共3目标；4帧8192功率字经PC独立NPZ重算零差异。前后boot_id不变，自检未初始化射频。

证据：`board/measurements/x1_deployment_r1.json`、`x1_selftest_r1.json`、`x1_selftest_r1_acceptance.json`及原始NPZ。

## 接收测试

配置A，仅接收，TX1A空，双TX衰减89.75dB；采样率3.84MSPS、RF带宽1.5MHz、BUS_PHASE=3。98MHz容量窗口与96.4MHz电台窗口各120秒，必须使用同组参数。电台按95.8MHz±25kHz内峰值计分；不能删掉漏检/缺失记录，统计分母为周期遥测快照，并非全部PL帧。

屏幕LO显示接收中心频率，Signals显示由FFT峰值换算的信号频率。检测95.8MHz时LO=96.4MHz属于预定配置，信号偏移−600kHz；3.84MSPS对应数字频率范围±1.92MHz，当前RF滤波带宽1.5MHz，不能将数字范围全部视为平坦有效通带。

第一轮：AVG_SHIFT=3、MIN_WIDTH=2、MERGE_GAP=6、ALPHA=1974、DC_MASK=3，无额外mask。

| 窗口 | 快照 | 容量告警 | 95.8MHz检出 | 显示中位fps | 目标数中位 |
|---|---:|---:|---:|---:|---:|
| 98MHz r1 | 101 | 0/101 | 不在该窗口内 | 49.422 | 4 |
| 96.4MHz r1 | 103 | 0/103 | 68/103，66.02% | 49.460 | 7 |

第一轮检出率未达80%，`x1_rf_metrics_r1.json`为FAIL_METRICS，保留原始记录。两窗口均无快照缺失或采样溢出。用户确认r1画面动态正常、看到95.8MHz附近且与当地电台相符的条目；目视通过不替代数值验收。r1停止后GPIO/SRC=0、boot_id不变。

第二轮仅将AVG_SHIFT改为4，其余参数保持一致：capacity为104条快照，告警0、采样溢出0、中位49.398fps；station为103条快照，检出61/103=59.22%、告警0、采样溢出0、中位49.454fps。`x1_rf_metrics_r2.json`为FAIL_METRICS。

第三轮保留AVG_SHIFT=4，仅将ALPHA改为1536（系数6.0），MIN_WIDTH=2、MERGE_GAP=6、DC_MASK=3，无额外mask。capacity完成105条快照，容量告警37/105=35.24%，超过5%上限；station检出58/106=54.72%，容量告警0，中位49.415fps。两窗口均无快照缺失或采样溢出。降低门限这轮的容量压力更大，但顺序空口测试不是相同输入回放，不能完全排除外部信号随时间变化。

三轮均未达到联合指标，X1标FAIL；最终独占锁内停止检查PASS，GPIO/SRC均0、boot_id不变，未开始X2。总检查点校验24项直接证据及冻结输入，失败代码/测量均保留。用户随后授权另做两根天线各一次对比，须先确认型号及换线，独立归档，不覆盖上述三轮或自动改为DONE。

## 限制

WNS为0，不能宣称有充足时序余量、全温或长期稳定性。CDC的20行时钟对摘要与N4一致，但继承的ADI Critical条目仍保留；摘要一致不是逐路径CDC证明。独立cluster OOC r1的hold失败记录亦保留，整机最终时序单独判定。

本步仅验收3.84MSPS频谱/CFAR/显示，不包含30.72MSPS、全FM带宽、自动调制识别或耳机监听。失败试验和旧快照保持原样，最新结论由总验收JSON和STATUS关联。

## 用户授权的GUARD=8追加轮与最终结论

用户明确允许只追加一轮联合验证，仍失败则记录后继续X2。固定AVG_SHIFT=3、GUARD=8，其余原验收参数和阈值不变。定向18组RTL逐位仿真及216项回归通过；原三轮证据和冻结源未覆盖。

98MHz容量窗口105次快照，告警3/105=2.86%（通过）；96.4MHz窗口106次快照，95.8MHz±25kHz检出78/106=73.58%（未达80%），告警0。两个窗口各120秒，快照缺失/采样溢出均0，中位49.38/49.39fps，温度60.04–61.15°C，双TX衰减89.75dB；结束GPIO/SRC=0、boot_id一致。95.45MHz补充结果106/106，不取代原95.8MHz指标，不作为独立信号身份验证。用户答“是”确认本轮动态画面与列表观察。

X1最终保持FAIL，不再追加调参；按用户授权进入X2。量化证据为`board/measurements/x1_guard8_metrics.json`，目视为`x1_guard8_visual.json`，最终检查点为`x1_final_checkpoint.json`，均附SHA256。该失败仍是M-A质量限制，不因后续带宽开发而消失。
