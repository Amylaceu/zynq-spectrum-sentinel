# Y3 FM噪声定位与软件保护（2026-11-03）

本轮按用户“接线不变，优化并找出问题”执行。配置A、RX1A、TX空，100MHz开发位流不变，无HDL修改、无重新综合布线。未发射；两路TX衰减始终89.75dB。测试后GPIO/SRC/audio均停止，喇叭静音。

## 已定位到的范围

噪声在部分原始ADC IQ中已存在，不能只归咎于喇叭、I2S或FM解调器。相同算法、相同天线连接和位流下，接收质量会随时间明显变化。具体干扰源、是否与外部设备/供电/接收增益有关仍未定位；未宣称已排除所有模拟或数字问题。

| 对照 | 19kHz导频突出度 | 说明 |
|---|---:|---|
| 历史正常原始IQ，软件解调 | 29.31 / 32.48dB | 两个独立快照，原文件不改 |
| 当前诊断r1原始IQ，软件解调 | 4.81 / 3.64dB | 即使绕过PL PFB和音频输出也很差 |
| 诊断r2前两块，LCD开/关 | 3.91 / 5.94dB | 两种状态都差 |
| 诊断r2后两块，LCD开/关 | 36.77 / 38.81dB | 两种状态都恢复清楚导频 |
| r2后续PL PFB15输出，8块 | 27.33–36.53dB | 同一已验收位流可输出有效FM IQ |

导频突出度是邻近频谱底相对值，**不是校准SNR**。快照有间隙，原始ADC与PFB不是同一时刻的逐样本配对。对照控制通道1不包含95.8MHz，不解释其相对该站频率计算的DC偏移。

RX PN9检查四路均0错误；并非全温、无限时长或整条模拟RF路径验收。原始IQ符号范围均为−2048…2047，未发现当前ADC格式与代码约定不符。历史IQ经现有PFB数学模型后仍保留导频；快速单通道模型与完整浮点多相模型误差小于5e−14。未对完整FM硬件链声明新的逐位验证。

## 已实现的软件优化

- `src/ps/sentinel/fm_quality.py`：对4096点480kSPS IQ计算导频位置/突出度、异常相位跳变比例与幅度。至少连续3块可信才放音，连续2块差则静音。
- `board/scripts/run_y3_audio.py --stereo-quality-gate`：板载喇叭初始保持静音；运行中保留质量、时间戳、开闭状态及实际放音区间。差时LCD标注`WEAK FM: MUTED`，恢复后继续监听。
- 只适用于已独立确认有立体声导频的FM站。**不能用导频缺失否认单声道FM**；不替代AMC，不默认打开其它模式，不改变旧测试证据。
- `tools/run_y3_board.py --stereo-quality-gate`使用独立`*_quality`输出目录，原FM三轮保留。
- 新增IQ诊断和离线分析脚本及测试，均使用相对仓库定位，板端脚本兼容Python3.8。

这是噪声保护和可观测性改进，不会恢复已经丢失的广播信息。此次好转也伴随原始RF信号质量恢复，不能把全部改善归功于静音门控。

## 板测与修正

新增质量门控r1因遥测时间戳取在阻塞IQ/IIC操作之前，把计数误算为约59kHz，在约1.31秒安全停止。已将时间戳移到采集后；原失败保留，非实际音频时钟变化。

r2完成30.0226秒；75/75质量快照可信，实际放音28.9677秒，最低显示40.7784fps，零FIFO下溢、无上游故障；退出静音及GPIO/SRC/audio=0。用户回报：“能看清楚屏幕内容，并且广播比之前清晰”。这只确认短试听改善，不等同5分钟或完全无噪声。

原执行器仍因25条遥测少于旧固定26条门槛记录FAIL。质量采集增加阻塞时间，已改成明确的实际观察间隔检查（每段≤2秒、足够样本、最终粘滞故障检查），并要求实际放音≥80%。独立复核通过；**原执行FAIL回执未覆盖，不为凑计数再播放一轮**。新增可变间隔/长盲区/全静音拒绝回归用例。最后85项针对性测试通过。

## 证据与复现

- `board/measurements/y3_iq_diagnostic_r1/`、`y3_iq_diagnostic_r2/`：原始ADC、PFB快照、结果、实际运行脚本。每个NPZ哈希在result.json中，JSON有SHA256。
- `report/results/y3_iq_diagnostic_r1/`、`y3_iq_diagnostic_r2/`：分析JSON、SHA256及数学音频预览。预览不能替代喇叭实测。
- `board/measurements/y3_quality_frozen_snapshot_validation.json`：冻结坏快照0/8放行、好快照8/8放行，不是盲测准确率。
- `board/measurements/y3_v2_audio_r1_quality*`、`y3_v2_audio_r2_quality*`：两轮部署、失败/成功执行及安全退出证据。
- `board/measurements/y3_noise_diagnostic_checkpoint.json`：独立复核量化结果；其中用户原话经Windows管道编码损坏，正确UTF-8人工回报见`y3_noise_diagnostic_human.json`，后者引用前者哈希修正该文本字段。
- `logs/Y3_quality_final_tests.log`：85项测试。

```powershell
# PC离线重算；输出目录必须不存在，不访问开发板。
.\.venv\Scripts\python.exe tools/analyze_y3_iq_diagnostic.py `
  --capture board/measurements/y3_iq_diagnostic_r2 `
  --out report/results/y3_iq_reanalysis_new
.\.venv\Scripts\python.exe -m pytest -q -s `
  src/ps/tests/test_fm_quality.py tools/tests/test_y3_iq_diagnostic.py `
  tools/tests/test_run_y3_board.py src/ps/tests/test_audio_y3.py `
  src/ps/tests/test_listen_y3.py
```

## 300秒稳定性测试收尾

质量门控r3已完成300.0989秒数字链路测试：665/665质量快照可信，导频突出度最低26.545dB，显示最低40.3784fps，零下溢、无上游错误；温度64.35–65.58°C。初始1.0522秒保持静音确认信号，之后299.0467秒连续放音，未再次触发静音。用户在测试中确认：“广播清楚、只有轻微底噪、没有明显断音”。结束后codec静音、GPIO/SRC/audio=0，同一boot_id。

`y3_v2_audio_r3_quality_execution.json`全部量化检查通过。人工回报及准确放音时长记录在`board/measurements/y3_noise_stability_human.json`及SHA256。**300秒链路测试通过，严格300秒全部解除静音仍差约0.95秒**；不将299.0467秒写成完整300秒连续出声，不覆盖Y3历史FAIL，也不为补这约1秒立即重复第三轮。

用户已要求**下次提高音量**，本轮仍为−15dB。下一次先小幅增加（建议−12dB），必须同步审查CodecOutputs当前−15dB上限和测试；此偏好不是已调高或已验证高音量的记录。若以后需严格连续300秒出声计时，应在初次质量放行后启动该计时，并保留独立最长等待/总运行超时，不用80%放音覆盖率替代正式连续时长要求。

如噪声复发，优先记录原始IQ、增益/RSSI与外部设备状态，做单变量干扰定位，不先重建位流。当前没有证据要求用户更换天线。具体干扰源仍未知，门控不会恢复已丢失信息。
