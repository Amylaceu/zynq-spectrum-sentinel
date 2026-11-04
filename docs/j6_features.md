# FPGA 功能对比界面 J-v6

入口：`.venv/Scripts/python.exe tools/host/product.py --connect 192.168.2.99`。
默认进入十卡界面，旧界面可用 `--legacy`。软件包部署到独立候选目录，正式 v2 不覆盖。

F1–F10 复用冻结的 100 MHz 位流；逐项启动、停止和连续切换证据在
`board/measurements/j6_dma_r1/`。本轮不发射，TX 双路保持 89.75 dB。

F8 最终候选 j6_audio_r3 重新初始化接收及音频状态，按已验收广播入口的顺序启动。
质量门控仍保留。启动实测 1.7094 秒；60 秒试听后用户确认“已清楚，基本连续”。
证据：`board/measurements/j6_audio_final_r3/`，旧入口对照在 `j6_audio_legacy_r1/`。
早期无声、噪声、超时及错误验收记录均保留。不能把数字就绪当听音通过。

F3 的整数三音切矩形窗后主瓣变窄，不预设为变宽；F4 测量为空间标准差。
F5 门限曲线来自本轮 PL 功率的软件黄金模型重建，不是门限寄存器读回。
F6 注噪开关通过，预期的功率比趋势未达，不作为噪声鲁棒性指标通过。
F10 CPU/PL 的时间范围不同，仅报告所列口径耗时比，不声称等价计算加速。

源码：板端 `src/ps/sentinel/app/features_j6.py` 与 `board/scripts/serve_features_j6.py`；
电脑界面 `tools/host/sentinel_host/features_v6.py`；传输部署 `tools/j6_serve.py`。
最新针对性回归 65 项通过，日志 `logs/J6_final_regression_r3.log`。
新应用卡和 Wi-Fi 一键采集尚未接入，按 KICKOFF_J6b 继续。
