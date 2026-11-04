# Y0 / Z7 状态复核（2026-11-03）

仓库通过`git rev-parse --show-toplevel`定位，脚本继续使用相对路径。
这次是已有Y0的复核与在途工作归档，不重复初始化工程，也不重跑X1–X4。

## 已核实状态

- Y0原提交为`5086ec3`；Y1为SKIPPED。
- X5核心第3轮PASS：32769输入、4097帧、65552个PFB IQ字、4104个SCAP字；
  NCO独立4513字、复位突发2048字比对通过。相关JSON/SHA256、7份日志/报告
  和3份关键RTL哈希已重新核对。
- 核心OOC时序WNS +0.296ns、WHS +0.032ns；不能混同整机结果。
- v1d整机r2独立审计PASS：WNS +0.092ns、WHS +0.037ns；Y2板测28.992fps、
  95.8MHz五票FM比例3/9，原量化FAIL保持；用户已确认旧画面正常。
- Y3还未上板或播放。旧OUT1-only软件30项测试PASS，只是历史软件证据。
  正式实现r1因XDC不支持foreach而停止；695文件已归档。显式管脚约束修复后
  的r2仍在电脑端构建，不能把RUNNING记为PASS。

## 本轮开始时未提交文件

共6个已修改文件：

- `.gitignore`
- `docs/antenna_sd_guide.md`
- `docs/hardware_bom.md`
- `runbook/95_final.md`
- `runbook/KICKOFF_Y.md`
- `runbook/STATUS.md`

另有102个未跟踪文件，主要是以下组：

- `src/hw/sentinel_y3/`、`src/rtl/audio_y3/`及PS音频驱动/测试；
- `board/scripts/run_y3_audio.py`、`y3_postflight.py`及Y3构建/审计/运行工具；
- Y3 FM、I2S、FIFO各轮仿真JSON、SHA256、证据ZIP；
- Y3失败整机归档、r1/r2硬件输入清单、软件r1/r2/r3证据；
- `runbook/CONTEXT.md`及Y3开发检查点。

完整逐文件清单、字节数、当时内容哈希见
`board/measurements/y0_z7_inventory_before_1.json`及SHA256。
清单记录的是修改方案之前的快照；后续文档对齐产生的差异属本轮预期修改。

## 当前方案与下一执行点

- Z7为唯一音频主线：板载喇叭、1kHz正弦3秒人工出声确认，之后5分钟FM；
  旧OUT1-only代码按在途版本归档，下一步迁移，不能直接宣称喇叭可用。
- 接收保持3.84MSPS，只用RX1A；A/B分组录像，无功分器、无第二屏/HDMI。
- Z9按实测资源判断；v1d实测35,568 LUT、83.5 BRAM、76 DSP，旧估算不充当验收。
  Y3超过75% LUT时优先PS解调；连续流必须可证明，不能拼接间歇识别快照。
- Y3使用配置A；本轮Y0只做电脑端文件处理，没有射频、下载位流、播放或关机操作。
- Y4及之后未开始；在Y4射频前仍须配置B/C确认。没有推送GitHub。

本地提交只表示归档和规则对齐，不代表Y2/Y3量化指标已通过。
