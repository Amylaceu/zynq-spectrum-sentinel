# X1 同帧诊断补充（2026-11-03）

这是三轮 X1 RF 联合指标未达标之后的用户授权诊断。X1 保持 FAIL，未启动 X2，也未追加第四轮参数验收。

## 已完成的证据

`board/measurements/x1_diagnostic_rf_r2.json` 及同名 `.npz` 保存 96 组门控 RF 功率帧。分析产物为 `x1_diagnostic_rf_r2_analysis.json` 与 `x1_diagnostic_rf_r2_model.npz`，全部附有 SHA256；执行回执为 `x1_diagnostic_rf_r2_execution.json`。

PC 分析状态为 `PASS_PAIRING`：196608 个功率字、576 个计数字段、214 条目标记录与黄金模型逐项配对一致。95.8 MHz ±25 kHz 范围内 77/96 帧含发布峰值（80.21%）；决策标签另有 13 帧涉及最小宽度筛选、6 帧容差内屏蔽后无 hit，标签允许重叠，不能直接相加解释为互斥漏检原因。

门限、hit、mask 和段决策由 PC 黄金模型重建，不是测得的硬件中间输出。无原始 IQ 或独立信号真值，不能据此判定电台实际缺失、天线损坏或射频物理根因。有限门控帧也不能替代连续 120 秒的 RF 联合验收，因此本次 80.21% 不改变 X1 状态。

## 频率读回与修正

LO 请求 96400000 Hz、读回 96399998 Hz，相差 2 Hz。诊断入口允许 ±5 Hz 的 LO 读回误差并保存实际读回；目标频率 ±25 kHz 判定保持不变。r1 在采集前因逐 Hz 校验失败退出，原始失败证据保留；r2 完成采集，退出后 GPIO=0、SRC=0，boot_id 不变。

## 回归与复现

已运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q src/ps/tests/test_x1_diagnostic.py tools/tests/test_x1_diagnostic_analysis.py
```

27 项通过。日志 `logs/X1_diagnostic_regression_r2.log`；分析日志 `logs/X1_diagnostic_rf_analysis_r1.log`；控制日志 `logs/X1_diagnostic_rf_control_r2.log`。

分析命令如下。既有产物禁止覆盖；重分析须先查看工具支持的独立输出选项。

```powershell
.\.venv\Scripts\python.exe tools/analyze_x1_diagnostic.py --input board/measurements/x1_diagnostic_rf_r2.json
```

后续优先保存同帧证据，使用冻结帧离线对照算法取舍；新 RF 调参仍需遵守三轮限制的流程授权和天线确认，不能仅为通过指标硬编码 95.8 MHz。
