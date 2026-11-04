# SD备份期间的离线仿真与数据复核

2026-11-03。基于提交 aedeb08，执行方案仍为 runbook/99_finish.md。
本轮为用户明确要求的离线准备，不访问开发板或SD原盘。F1保持DOING，F2未开始。

## 已完成及其用途

- 黄金模型112项通过：信号生成、定点注噪、AMD FFT C模型、频谱、CFAR、PFB、HOC、解调与显示参考。可用于后续演示输入和数字注噪评测的数值基准；不等于空口准确率或硬件时序通过。
- PS软件339项通过：包含FM分块连续性、质量门控、输出音量保护及发布配置等。默认−12dB、上限−6dB仍未进行新版本板端试听。
- 黄金参考文件142份与原manifest的大小、SHA256全部一致。
- 冻结100MHz所用CFAR的历史18案例重新逐字比较：阈值、hit、dB、占用、目标、计数共149886字，零差异；历史记录中源码及输出哈希均一致。这是既有RTL仿真证据复核，本轮没有重新运行RTL仿真。
- 历史FM原始IQ文件67108864字节，原SigMF SHA512通过。重新处理第0、8个快照，单信道滤波与独立多相参考最大差分别3.9145e−14、4.2412e−14；导频突出度30.15、30.71dB。保留4份WAV和JSON，未归一化噪声为人声，未播放。
- 16份历史PFB IQ重新计算质量指标，与既有记录一致；按F1的20dB导频条件和原相位/幅度条件，较差组0/8放行，较好组8/8放行。仅用于确认已知快照的门控行为，不证明任意干扰下的误判率，也不能将导频突出度当音频SNR。

## 全量回归的未通过部分

| 轮次 | 结果 | 原因与处理 |
|---|---|---|
| 1 | 662通过、13失败 | 当前进程未初始化XILINX_ROOT，AMD FFT模型无法加载；未改算法。 |
| 2 | 674通过、1环境错误 | 初始化tools/env.ps1后全部112项黄金测试通过；一个Tcl策略测试无法读取init.tcl。独立Tcl查询随后返回8.6.15，完整回归内异常的根因尚未确认。 |
| 3 | 671通过、4环境错误 | 执行时错误地从虚拟环境路径推导TCL_LIBRARY/TK_LIBRARY，指向不存在的.venv/tcl；这是本轮执行命令错误，非FPGA缺陷。 |

三轮全部保留，不能写成“完整675项通过”。环境变量只作用于本次子进程，未修改系统环境或tools/env.ps1。
本轮不追加第四轮。后续维护测试环境时，应优先使用已记录的pytest -s以避免Windows捕获相关问题；若显式设置Tcl路径，应从sys.base_prefix定位并先验证init.tcl存在，不能从虚拟环境解释器路径推导。该建议本轮未进一步执行验证。

## 文件和复现

- 总证据：sim/results/f1_offline_evidence_final.json及.sha256，含各轮测试计数、失败名称、来源哈希和16份质量结果。
- JUnit：sim/results/frozen_offline_regression_20261103.xml、同名前缀_r2.xml、_r3.xml；均纳入总证据SHA256。
- IQ重放：sim/results/f1_frozen_iq_20261103/analysis.json及.sha256、4份WAV；WAV哈希保存在分析JSON中。
- 日志：logs/F1_frozen_offline_regression_20261103*.log、logs/F1_frozen_iq_20261103.log、logs/F1_offline_evidence_20261103.log。
- 最终证据补充核验SigMF源文件与元数据，并收录三轮日志哈希；较早审计JSON保留为过程记录。
- 审计脚本：tools/verify_f1_offline_evidence.py，使用仓库相对路径，仅读取历史数据并生成新证据，拒绝覆盖已有输出。

复核本轮已保存的数据（在仓库根目录，指定尚不存在的输出文件）：

```powershell
./.venv/Scripts/python.exe tools/verify_f1_offline_evidence.py --out sim/results/f1_offline_evidence_next.json
```

历史IQ分析复现（输出目录必须不存在；仅电脑端计算，不播放音频）：

```powershell
./.venv/Scripts/python.exe tools/analyze_y3_iq_diagnostic.py --out sim/results/f1_frozen_iq_recheck
```

以上复核不运行完整pytest。不要在SD读取期间执行发布脚本的Deploy选项。恢复板测仍按docs/f1_release_progress.md：确认Read成功、校验镜像、安全弹出、断电插卡、确认配置A后采集启动日志，再部署并验收F1。
