# X5 / Y2 集成记录

## 最新检查点（2026-11-03）

以下“r2后台运行”等内容是历史过程，不再代表当前状态。r2整机与审计已通过，
120秒站点实采也已完成。自动验收FAIL：28.992fps、95.8MHz完整五票FM 3/9；
481.181ms中位首次上屏时延达标（只计PS观察→LCD APPLIED）。接收已停止。
实现539文件已封存，229项软件测试通过；目视与Z2未完成。详见
`docs/y2_board_checkpoint.md` 和 `board/measurements/x5_station_r3_analysis.json`。
配置E按用户最新方案取消。软件兼容修订与硬件r2单独冻结，不存在新的整机r3。

当前工作延续原 X5，衔接 `runbook/95_final.md` 的 Y2。X1–X4 的正式 FAIL
结论保持；不继续训练，不把新版本局部仿真算作旧项目板测通过。

## 已确认结果

- PFB/NCO 第三轮 PASS：32769 个 3.84 MSPS 输入，4097 帧 / 65552 个 PFB IQ
  与黄金模型逐位一致，SCAP 4104 字逐位一致；复位及反压回放通过。
- NCO 独立第三轮 4513 字逐位一致；核心 OOC 150 MHz 的 WNS +0.296 ns、
  WHS +0.032 ns。证据：`sim/results/x5_core_acceptance.json` 及 SHA256。
- `docs/x5_pl_interface.md` 包含验收前的“仍在运行”文字；它是核心验收哈希
  覆盖的历史文档，保留原字节。本文件及验收 JSON 给出最终结果。
- v1d 整机第一轮 FAIL：最终 `timing_impl.log` WNS −0.383 ns、WHS +0.051 ns。
  最差路径为 CFAR `reg_alpha_reg[21]` 至性能计数器 `frames_reg[10]/CE`；
  次要违例涉及 mask/bin 至聚类控制。不能只读取某个时钟组的正裕量认定整机通过。
- 第一轮工程、最终 DCP、bad-timing XSA、时序报告和日志已在重新生成工程前
  封存：`report/results/x5_implementation_r1.zip`，526 文件逐一校验；索引
  `board/measurements/x5_implementation_r1.json`。均有 SHA256。失败 XSA 不部署。

## 第二轮改动

独立 `cfar_core_x5` IP，不覆盖 X1 已验收 IP 或第三方源码。复用先前通过黄金
比对的 cfgpipe 结构：注册配置合法性，在分离的 AXI AW/W 写事务及响应期间
禁止启动新帧；已有帧继续使用锁存配置。屏蔽结果与 blocked sideband 一同
进入单级弹性寄存器，完整保持反压契约。聚类三项饱和加法改为 carry-save
后单次进位传播；raw 私有计数移至既有 CANDIDATE 周期，不改变发布内容。

`sim/results/x5_cfar_r2.json`：18 组黄金向量逐字一致，覆盖 threshold/hit/db/
occupancy/targets/stats，分离 AXI 写、帧中配置变化、无效配置、复位、下游反压。
另有 216 组饱和边界组合和 10000 组随机三项和检查。

集成 UI 在置信分数 <0.5 时显示 `?`；`P` 显示 CFAR 峰值的原始线性计数，
不是校准的 dBm。模型保留第三轮实验候选，未重新训练。

## 执行入口与门禁

1. `tools/test_cfar_x5.ps1 -Attempt 2`、`tools/package_cfar_x5.ps1 -Attempt 2`。
2. `tools/build_sentinel_v1d.ps1 -Attempt 3 -ValidateOnly`：这是第三次连接验证，
   **不是第三次整机实现**；整机实现仍仅完成第一轮。
3. `python tools/verify_x5_pc.py --attempt 2 --validation-attempt 3`。
4. `python tools/freeze_x5_build.py --attempt 2`，然后
   `tools/build_sentinel_v1d.ps1 -Attempt 2`。最多两次 ADI 自动物理优化，
   时序及频率要求不变，未添加 false path 或降频。
5. 实现合格后 `tools/audit_sentinel_v1d.ps1 -Attempt 2`，方可使用
   `tools/run_x5_board.py --attempt 1 --implementation-attempt 2 --confirm-configuration-a`。

用户之前已确认配置 A 并授权 X5 仅接收。TX 保持关闭、89.75 dB，不发射。
LO 96.4 MHz 的 95.8 MHz 电台测试单独记录；98 MHz 窗口未知真值，不能根据
识别器自己的输出推断 FM 正确率。所有目视结论须等待用户，不能代填。

时延目前从 PS 首次观察到 CFAR 目标至 LCD UI_APPLIED；在此之前的检测及
轮询等待未测，不能宣称完整 RF 目标出现至屏幕时延达标。原 X5 的 <500 ms
与新 Y2 的 ≤1 s 指标须分别报告，不能用新目标改写旧结论。

## 板测后的独立复算

`python tools/analyze_x5_board.py --tag x5_station_r1` 从已取回的执行凭据、
result.json 和原始 SCAP 包复算每个目标的投票、低分 `?` 显示和首次上屏时延。
同时列出启动阶段不足五票的结果与完整五票的 FM 显示比例；Y2 的 80% 门槛
只用完整五票结果判断。没有独立电台真值或完整五票时，结果为未评估。
自动量化通过也不能替代用户目视确认。

大量 NPZ/SHA256 文件使用 `tools/x5_transfer.py` 分批 SCP，每批最多 64 文件且
命令小于 24000 字符，避免 Windows 长度限制；传输失败立即停止，不静默遗漏。
26 项针对错误投票、伪造时延、暖机不足、安全遥测及大批量传输的检查通过，
记录 `sim/results/x5_board_tools_r1.json` 及 SHA256。它们不改变冻结硬件输入，
不代表实际板测已通过。v1d 第二轮整机实现仍在后台运行。

## 捕获通带的已知边界

`tools/analyze_x5_passband.py` 直接读取冻结的 Q1.17 系数，计算理想 FIR 响应并以
七个正弦输入的卷积交叉核对。输出采样率 480 kSPS 不意味着通带宽 480 kHz：
相对信道中心 ±106 kHz 内约为 −3 dB 以内，±120 kHz 处约 −6.023 dB。
LO=96.4 MHz 时，95.8 MHz 目标选中通道 14、残余 −120 kHz，恰在信道边界。
以目标两侧各 75 kHz 作为示意范围时，两端理想增益差异很大；这不是该电台
实际占用带宽的测量，也未包含 RF 模拟滤波器或定点 FFT 的影响。

后置 NCO 不能恢复已被 PFB 原型压低的边带。若板测发现 95.8 MHz 捕获失真，
应据原始 IQ 确认后再决定调整 LO 使目标靠近信道中心，或按计划走 PS DDC
降级；不能把失真直接归咎于模型，亦不能用此解释替换 X1 的历史验收。
当前冻结 RTL、系数、LO 板测入口均未改动。

证据：`board/measurements/x5_prototype_response.json` 及 SHA256；曲线
`report/figures/x5_prototype_response.png`。95.45125 MHz 只作为高检出峰的位置
示意，其电台身份仍未经独立确认，不加入识别正确率真值。
