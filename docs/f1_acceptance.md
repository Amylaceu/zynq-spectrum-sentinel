# F1 正式发布版验收

2026-11-03，固定100MHz/3.84MSPS，配置A，无发射；无HDL修改、综合、布线或训练。

正式路径：/home/xilinx/sentinel/release/v2；已校验87个包成员及既有射频库，未设置开机自启。

- sentinel.sh selftest通过：AD9361 ID=10，温度50.69°C、RSSI −91.75dBm、TX双路89.75dB，导频突出度32.04dB。
- sentinel.sh monitor正常运行85.190秒，144份捕获；用户确认“LCD显示正常”。
- sentinel.sh listen 95.8默认−12dB，运行103.130秒、实际放音102.085秒；最低40.62fps、最高62.01°C，零音频下溢；用户确认“清楚”。本次主动停止，不是300秒连续验收。
- monitor/listen均由正式stop入口受控停止，codec已静音、GPIO/SRC/audio均0。
- 音量范围−45至−6dB、1.5dB步进已离线验证；本轮只实测−12dB，不把−6dB上限当作试听通过。

证据：board/measurements/f1_board_acceptance_r1.json及SHA256；原始结果、日志在同名目录，清单含每个文件SHA256。启动警告、板端时钟偏差及执行环境错误如实保留；未做文件系统修复或恢复演练。

下一步F2沿用配置A开发PS演示，不重建位流。
