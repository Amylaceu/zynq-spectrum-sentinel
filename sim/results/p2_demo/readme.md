# P2.7 离线参考演示

复现：加载 tools/env.ps1 后执行 `python -m sim.golden.pipeline --demo --out sim/results/p2_demo`。

场景：30.72 MSPS，四个等功率信号，中心分别为 -9 MHz（16QAM）、-5 MHz（2FSK）、+3 MHz（QPSK）、+8 MHz（FM）。噪声设为 QPSK 占用带宽内 SNR 15 dB；其他带宽的信号具有不同带内 SNR，不宣称每类都严格15 dB。

宽信号的 CA-CFAR 使用单侧128参考单元、48保护单元。默认16/2的窄窗会被宽信号污染，不能把窄窗直接用于约1.35MHz宽信号；这一演示配置和结果均在 targets.json 记录。

本次检测4个目标，中心估计分别 -9 MHz、-5.0025 MHz、+3.015 MHz、+8.0025 MHz，误差不超过1个15kHz频点。中心用检测区间中点估计，不将宽带信号的随机峰值频点当成载波中心。

输出包含 spectrum.png、waterfall.png、constellations.png、targets.json、frame_ref.png。星座图仅展示未经定时/载波同步的捕获IQ，不能把点云图当作调制已识别。分类模型尚未训练，labels明确为null。800×480参考画面目前只有PL图层，UI区域留黑。

这是电脑仿真结果；未接收真实射频，也未下载到LCD或FPGA。
