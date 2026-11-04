# 全景扫描当前成果

## 已完成的真实测量

配置A，RX1A接20–512MHz天线，TX1A空。冻结100MHz位流未修改或重新下载。第一轮完成55个LO、70–512MHz全景，用时78.3498秒（含初始化与恢复，不含主机文件取回）。44,200个10kHz输出格点全部有有效分段覆盖。

每段以30.72MSPS有限DMA取得131,072个RX1复数样本，并保存原始有符号12位ADC计数、4096点Welch谱、实际LO/采样率、增益、RSSI、边界检查和SHA256。两个TX衰减均89.75dB；实测RSSI范围约−101.5至−66.25dBm。

结束后采样率恢复3.84MSPS，LO读回96,049,998Hz，RF带宽请求恢复1.5MHz，慢速AGC恢复；已校验采样率及LO，但原API没有独立带宽/增益模式读回，不能宣称全部恢复参数都已独立读回。RX启动复位后PERF状态为0，退出及独立复核GPIO/SRC/audio均0。

主机从55段原始IQ独立重算全部Welch谱及线性拼接，PSD最大绝对差4.24e−22，覆盖计数一致。数据在`board/measurements/f4_a_scan_r1/raw/`，最终图及复算结果在`analysis_final/`。较早`analysis_r2/`的离屏截图缺字体，已保留；使用`analysis_final/desktop_panorama.png`。

这是分时有限快照。全景扫描时PL处理源始终关闭，PERF的输入FIFO粘滞位为1、ADC状态0x0d，均原样记录；结束后才清理启动状态。此结果不证明连续30.72MSPS处理、快照内全部采样无丢失、连续DMA零溢出或一小时稳定性。电平为dBFS/Hz，未校准天线、AGC与射频功率，不能作dBm或协议识别。

## 上位机

“全景”页现在显示大幅可缩放实测曲线；打开`result.json`时校验JSON、全景NPZ和全部分段的SHA256。当前为已保存全景查看，不是逐段实时上传；单击频段跳台尚未实现。旧exe不包含本次修改。

从仓库根目录启动源码版本：

```powershell
$env:PYTHONPATH = ".;src/ps;tools/host"
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m sentinel_host --panorama board/measurements/f4_a_scan_r1/raw/result.json
```

原始扫描入口（须实际确认天线；凭据通过stdin，不写入命令行参数或日志）：

```powershell
.venv/Scripts/python.exe tools/f4_scan.py --group A --antenna-confirmed --attempt 1 --sudo-stdin
```

已有第一轮输出目录，以上仅为入口说明，不要覆盖重跑。D组必须先停止射频并实际换线确认。

## 新H1方案的接续

78.35秒作为优化前基线保留，不满足H1的A组10秒目标。下一步只扫10个LO，实测完整配置、AGC等待、DMA、Welch、压缩写盘等时间。原接收库将采样率、LO、RF带宽合在一个API中，计时只能标“组合配置”，不可伪造独立调谐耗时。

18MHz单步进与±150kHz中心屏蔽不能同时保证无缺口：相邻LO距离18MHz，大于有效半带宽10MHz，某段被屏蔽的中心频率不在相邻段内。后续必须实测验证覆盖并增加桥接段或采用更小步进，不得填补空白冒充实测。PSD-only、固定增益、64k点、流水线、fastlock仍待H1实现；1小时稳定性及彩排按用户要求后置。


## H1快速版本实测与使用

10LO原始计时见h1_timing_r1.json：组合射频配置0.602秒，Welch2.757秒，压缩写盘4.153秒。固定接收库耦合采样率/LO/带宽，不能独立报告仅调谐时间；目前不引入fastlock或新的射频库。

快速版保留150ms AGC等待和一次丢弃快照，使用65536点、批量FFT、不压缩PSD-only落盘；--keep-iq可选保存原始IQ。9MHz步进保持被屏蔽DC由相邻段覆盖；18MHz单步进不可用。首轮49段70–512MHz耗时43.063秒，较78.350秒下降45.04%，44,200格点均被覆盖。10秒目标保持FAIL，未改目标。快速版PSD-only只能从已存PSD独立重算拼接，不能重新从IQ认证各谱线；原55段完整IQ继续保留。证据h1_a_scan_r1/、h1_fast_comparison_r1.json及SHA256。

快速扫描命令（新attempt目录，不能覆盖已有证据）：

```powershell
.venv/Scripts/python.exe tools/f4_scan.py --group A --antenna-confirmed --profile fast --attempt 3 --sudo-stdin
```

逐段显示源码入口（由扫描工具同步写pano_tiles.jsonl；暂态曲线标注最终校验待完成，收齐结果并独立停止PASS后才显示验证完成）：

```powershell
$env:PYTHONPATH = ".;src/ps;tools/host"
Remove-Item Env:QT_QPA_PLATFORM -ErrorAction SilentlyContinue
.venv/Scripts/python.exe -m sentinel_host --panorama-live board/measurements/h1_a_scan_r2/pano_tiles.jsonl --panorama-final board/measurements/h1_a_scan_r2/raw/result.json
```

此入口也可重新显示已捕获事件，但那是历史快照查看，不能作为新的射频实测。H1实时传输采用独立SSH进度流，不修改冻结孪生线协议；每段4096点float32功率，掩蔽DC/边缘，按段显示，不填未采集空白。逐段显示真板验收、D组、quick及点击定点识别尚未完成。新版exe尚未打包。


## 本轮最终结果

A第二轮42.2247秒，49条pano_tile全部被真实Qt界面消费，最终结果SHA256校验成功，界面错误列表为空。D首轮206.6079秒，243段覆盖512MHz–2.7GHz、218,800个输出格点无缺口；GUI消费全部243条，最终校验成功，独立停止PASS。用户只确认“逐段增加”，未扩大记录为缩放或长期稳定性验收。D数据在h1_d_scan_r1/，界面证据h1_live_D_gui_r1.json/PNG，汇总h1_D_acceptance_r1.json，均附SHA256。

A≤10秒、D≤30秒目标未达，未修改阈值；quick、点击频段转定点识别及带宽/AGC模式独立读回仍未完成。当前接线为D，板保持上电且接收已停止。下一步优先H2手动场景服务；FM演示须先请求换回A，不继续G5彩排或一小时长测。所有历史FAIL保留。

H3a二维码入口说明已保存docs/h3a_router_setup.md，要求安装tools/host/requirements.txt；真实路由器无线连接待用户设备就绪后验证。不要把此按钮或已有电脑局域网连接当作无线联网验收。旧exe未重打包。
