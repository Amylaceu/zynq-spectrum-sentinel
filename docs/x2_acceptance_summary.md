# X2 阶段结果：时序失败，宽带优化延期

状态：**FAIL（延期优化）**。按用户优先推进功能的要求，第2轮实现结束后不再追加第3轮，继续使用已通过时序的3.84 MSPS版本开发后续功能。

| 项目 | 结果 | 证据 |
|---|---|---|
| 30.72 MSPS、64帧链路仿真 | SAMPLE_DROP=0，FRAME_DROP=4；8192功率字一致 | `sim/results/x2_simulation_acceptance.json` |
| 整机实现r1 | WNS −0.331 ns，未加载 | `docs/x2_implementation_r1_failure.json`，282文件本地归档 |
| 整机实现r2 | WNS −0.709 ns、WHS −0.058 ns，失败 | `docs/x2_implementation_r2_failure.json`，267文件本地归档 |
| PS/PC回归 | 235项通过 | `logs/X2_python_tests_fast_r2.log`；哈希见汇总JSON |
| 软件交接 | 24文件冻结、板端Python 3.8语法兼容 | `docs/x2_software_predeployment_r2.json` |
| 7.68/15.36/24.576/30.72 MSPS板测 | 全部NOT_TESTED | 未部署、未加载X2，不能声明零丢样带宽达标 |

可恢复的快速板测入口已保存：四档各60秒筛选，最高通过档600秒持续验收，采集约14分钟，另计初始化与自检时间。低档仅标SCREENING_ONLY，不等同原四档各600秒。入口见 `docs/x2_execution.md`，须先解决整机时序再运行。

首轮关键路径包含CFAR配置扇出、功率对数/帧队列路径及ADC丢样计数器；仅改变实现策略未解决问题。后续应结合流水级、扇出与布局重新设计，保留现有冻结仿真和实现证据，不用放宽时钟约束来掩盖未达标。

X3使用已接受的`sentinel_v1b`、3.84 MSPS版本。该版本时序通过不代表X1列表质量指标已通过，X1仍为FAIL。X2目标最低24.576 MSPS尚未达到，M-A不得宣称原计划全部指标达成。

总记录：`board/measurements/x2_deferred_summary.json`及SHA256；失败归档ZIP位于本机`build/reports/sentinel_v1c_r1_failed/`及`sentinel_v1c_r2_failed/`，不提交Git。
