# Y2 板测检查点：硬件通过，功能指标未全部达标

## 结论与边界

配置 A、TX1A 空、TX 关闭且双路衰减 89.75 dB。用户取消功分器，配置 E 已取消；
后续仍按 A/B 两组录制，B 组次序 7→5→6→8。不新增硬件购买要求。

第二轮 v1d 整机实现和独立审计 PASS：WNS +0.092 ns、WHS +0.037 ns，
TNS/THS 为零。LUT 35568、FF 50450、BRAM 83.5、DSP 76；Slice 占用
98.68%，不能把剩余 LUT 百分比等同于可用布局余量。CDC 报告仍有 ADI 原有
Critical/Unknown 项，不声称零 CDC 告警。实际 ADI 日志使用默认最多五次自动
优化，未继承原计划的两次设置；保留原日志，不修改第三方脚本。

PFB 第三轮及 CFAR 第二轮的原始仿真 PASS 保留。没有第四轮 PFB 或第三轮
整机实现。实现验收：`board/overlay/sentinel_v1d/acceptance.json`。

## 120 秒真实接收结果

独立分析：`board/measurements/x5_station_r3_analysis.json`，所有结果有 SHA256。
LO 96.4 MHz、采样率 3.84 MSPS、RF 带宽仍为 1.5 MHz、信道输出 480 kSPS。
未进行 Y1 的 3 MHz 复测，不把可选项的默认参数写成已经生效。

| 项目 | 实测 | Y2 要求 | 结果 |
|---|---:|---:|---|
| 连续运行 | 120.221 s | ≥120 s | 通过 |
| 实采文件 | 194 份，每份4096 IQ点 | 完整性可追溯 | 逐包头/IQ/时间戳/哈希通过 |
| 首次观察至 LCD APPLIED 时延中位数 | 481.181 ms | ≤1000 ms | 通过（限下述定义） |
| 同一时延最大值 | 3124.752 ms | 无最大值门限 | 如实记录 |
| LCD 帧率中位数 | 28.992 fps | ≥30 fps | 未达标 |
| 95.8 MHz 完整五票后 FM 标签比例 | 3/9 = 33.33% | ≥80% | 未达标 |
| 95.8 MHz 全部滚动投票后 FM 标签比例 | 4/21 = 19.05% | 辅助统计 | 含未满五票阶段 |
| 97 条遥测 processing_status | 全为4 | 故障位0/1均为0 | 无上报溢出/处理错误 |

时延起点为 **PS 首次读到 CFAR 目标**，终点为 LCD UI_APPLIED；未测量此前的
射频检测和轮询等待。第一条标签不要求凑齐五票，完整五票的识别率另行统计。
投票比例仅来自本窗口，样本少且相关，不等同于独立测试集准确率。

95.8 MHz 为用户独立确认的电台。95.45125 MHz 的身份未知，不纳入 FM 真值；
不采用方案中误称“两台均为已知电台”的叙述。98 MHz 窗口无独立真值，未计为通过。
PFB 理想通带显示 95.8 MHz 在当前 LO 下接近信道边界，但尚未证明这就是识别
失败的原因；不得把推测当测量结论。

测试结束 GPIO/source 均0、无在途接收，boot_id 未变、RF 共享库前后 SHA256
一致。没有发射、调参、重训练、断电或复位。目视验收待完成。

## 失败与修正过程（不抹去轮次）

1. station_r1：部署依赖检查对 namespace package 的 `__file__=None` 处理错误；
   在硬件访问前失败。另一次被本地旧 payload 保护拒绝，日志保留。
2. station_r2：位流加载成功，但 PYNQ 2.7 不把 BRAM MEMORY 记入 `ip_dict`；
   绑定失败，未进入 RF 初始化。postflight 安全停止，失败 JSON 保留。
3. station_r3：软件兼容修正后真实接收成功。前置尝试分别被冻结源差异和
   已加载位流不一致门禁拒绝；最终执行成功不覆盖这些失败日志。

独立分析最初把 PERF bit2 `latency_valid` 当成故障。现按 RTL 定义解码：
bit0 overflow、bit1 error；bit2/3/4 为时延握手状态；未知高位拒绝。
修改的是分析器，原始测量不变。新增测试确认状态4合法，状态1/2等仍拒绝。

主机当前进一步加强了 HWH 检查：先验证匹配 bit/HWH 的验收哈希，再检查
LCD 128 KiB 和 power capture 8 KiB 的 MEMORY 地址范围；缺失不能放行。
该加强版只完成 PC 和真实 HWH 文件检查，**尚未部署到本轮实测目录**。

## 硬件冻结与软件补丁分离

- 原 `docs/x5_v1d_prebuild_r2.json` 及验收 JSON 字节保持不变。
- `docs/x5_v1d_prebuild_r3.json` 是当时手工生成、标签不恰当的兼容性清单；
  保留历史字节便于解释 station_r3 启动过程，**不作为第三轮整机或仿真证据**。
- 正式软件补丁入口为 `tools/x5_runtime_patch.py`，明确链接第二轮硬件验收，
  仅允许原冻结项中 `src/ps/sentinel/v1d.py` 的 PS 改动。任何 RTL/约束/IP/
  仿真证据变化均拒绝。运行时完整源清单另外冻结。
- 当前软件补丁清单为 `docs/x5_runtime_patch_2.json`。这是 PC 验证版本，不能
  倒签成 station_r3 的测量软件；后者的实际部署哈希在原 start/execution JSON。
- 后续部署用 `--implementation-attempt 2 --runtime-manifest <清单>`，不以
  软件修订号冒充硬件实现轮次。已有三轮正式站点测试不再继续追加调参。

整机原始报告、DCP、日志、bit/HWH/XSA 已封存：
`report/results/x5_implementation_r2.zip`，539文件逐项校验；入口
`board/measurements/x5_implementation_r2.json`。主机部署 tar 留本地，启动收据
保留其 SHA256。板测失败日志另存 Y2 证据归档，详见检查点 JSON。

## 下一步

保留 Y2 自动指标 FAIL，不重新训练或用未知峰替代真值。原v1d目视已通过，
用户确认“计数增加，列表和点图可见，画面正常”；115份捕获关联见
`board/measurements/y2_visual_link_1.json`及SHA256。Z2 的模式/TX状态、
最近五条事件及五类颜色仍未整机验收；现有四色 UI 不能
声称满足红绿 TX 指示和五类配色。之后按 95_final 推进 Y3；PL 音频实现须重新
审计时序，三轮不通过则走 Y3-S，不延伸 X1–X4 调参。首次播放前必须提醒
用户不要直接戴耳机；未确认 P1 连接前不输出音频。
