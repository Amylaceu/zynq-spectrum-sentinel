# X0–X4 离线优化交接（2026-11-03）

## 第二轮补充：本地同步与 CFAR 流水候选

证据已封存为 `board/measurements/x0_x4_followup_r1.json` 和 `report/results/x0_x4_followup_r1.zip`，各附 SHA256；ZIP 内含 79 个源码、原始报告及实验文件，并以 manifest 逐文件核验。正式状态仍是 X0 DONE、X1–X4 FAIL。

X4 将 Gardner 串行符号同步循环移到可选 C 动态库，模型、阈值和默认 Predictor 不变。13 个 SNR 档共 260 段完整预测、36 个核心用例的实测差异均为零。150 对配对计时中，P95 从 126.029 ms 降至 98.456 ms，超过 100 ms 的次数从 60 降至 3；最大值仍为 134.450 ms，不能宣布时延通过。完整接口和目标板编译说明见 `docs/amc_native_runtime.md`。本轮未追加训练或准确率验收。

X2 两个候选各通过 18 组黄金向量比较，threshold/hit/db/occupancy/targets/stats 均零差异。以下是带输入输出寄存器边界的局部实现，周期 6.667 ns；与下面第一轮虚拟端口审计不是同一实验条件。

| 候选 | WNS ns | WHS ns | LUT | 寄存器 | BRAM tile / DSP |
|---|---:|---:|---:|---:|---:|
| reference | −0.311 | +0.103 | 6600 | 9239 | 12 / 2 |
| maskpipe | −0.291 | +0.092 | 6587 | 9275 | 12 / 2 |
| cfgpipe | −0.147 | +0.089 | 6591 | 9292 | 12 / 2 |

cfgpipe 相对本组 reference 的 WNS 改善 0.164 ns，但三个版本仍未通过建立时间；不能替换部署位流。保留 OOC 时钟来源警告，局部报告不代表整机或 IO 时序。

**仅 maskpipe** 还完成 30.72 MSPS 整链仿真：131072 个输入 IQ 对应 131072 个功率字，SAMPLE_DROP=0，首 8192 字逐位一致；64 个输入帧中输出 60 帧、FRAME_DROP=4。它证明本用例样本完整，但不代表零帧丢失或宽带板测通过。cfgpipe 尚未做同样的整链验证。

回归结果：`src/ps/tests + tools/tests` 共 280 passed。汇总脚本修正了 Vivado 资源报告空行与重复寄存器统计行的解析；重复值必须一致，原始报告未修改。原始日志只收入证据 ZIP，不直接提交 `logs/`。

后续可直接复核 ZIP manifest 和 JSON 的 SHA256；不要重跑覆盖已有证据。继续优化时优先检查 cfgpipe 剩余建立时间路径，先局部功能/整链/整机时序，再考虑部署。X3 的采集时延瓶颈仍依赖 X2 合格宽带实现。未修改 X5 在途文件，未加载新位流或启动 RF。

## 本轮范围与决定

用户离开并保持板卡上电，授权继续优化 X0–X4。本轮完成隔离 RTL 候选、PC 等价验证与 Cortex-A9 离线推理对比。不安排人工验收，不启动 RF，不更换位流或默认推理器，不覆盖 X5 在途文件。仓库根目录由 Git 核实，以下命令均从仓库根目录运行。

正式状态仍为 **X0 DONE；X1、X2、X3、X4 FAIL**。本轮局部实验通过不能替代整机验收。

| 部分 | 当前结论 | 后续接续条件 |
|---|---|---|
| X0 | SD 整卡备份、phase=3、XADC 温度及接收验收已通过；原证据哈希一致 | 无需重复备份或重复射频验收；继续遵守安全关机规则 |
| X1 | GUARD=8 后容量告警 2.86% 达标，95.8 MHz 检出 73.58% 未达 80% | 不再自动追加调参；保留已有数据，不能用 95.45 MHz 或模型回放替代指标 |
| X2 | 两项 RTL 候选功能仿真通过，OOC 建立/保持时间见汇总 JSON；未接入部署设计 | 需先决定整机集成，再逐级仿真、完整实现及审计；最后才能进行带宽板测 |
| X3 | 首 IQ 到列表中位 629.90 µs，原 <200 µs 未达标；归档/G1 已完成 | 3.84 MSPS、2048 点采集本身约 533.073 µs；推算剩余 96.827 µs 仅供分析 |
| X4 | 缓存版本输出等价，但加速很小；原准确率和单次推理时延仍未达标 | 默认继续使用已冻结 Predictor；不再训练，不将缓存候选作为达标模型 |

## X2 候选接口与证据

- `src/rtl/x2_opt/drop_counter_segmented.v`：32 位饱和计数按 8 位分段，预先寄存进位条件；保持事件计数与 Gray 输出的周期关系。只支持注释约定的参数范围，复位后使用。
- `src/rtl/x2_opt/cfar_cluster_timing_x2.v`：将内部 raw 计数从 SCAN 移至 CANDIDATE，保持发布统计、MMIO、AXIS 顺序与周期。
- `sim/tb/tb_x2_drop_counter.sv`：96238 周期，覆盖连续/间断事件、进位边界、16/32 位饱和、复位与单比特 Gray 转换；32 位大数边界使用一致可达状态注入，未声称遍历 2^32 周期。
- `sim/tb/tb_x2_timing_candidates.sv`：对照原聚类器，32 帧、390 个输出字，逐周期核对控制/统计/MMIO/AXIS，覆盖随机停顿、屏蔽、top-32 与复位。

OOC 审计采用 xc7z020clg484-2；计数器周期 4.069 ns，聚类器周期 6.667 ns，虚拟输入/输出延迟均为 0。计数器原版 WNS/WHS 为 −0.130/−0.105 ns；分段版为 +1.234/−0.275 ns。**建立时间改善 1.364 ns，但保持时间仍失败。** 最差保持路径从虚拟 `event_valid` 输入起始；该结果不能替代真实上下游寄存器和整机布局。

完整四模块的时序/资源数值保存在 `board/measurements/x0_x4_optimization_r1.json`。Vivado 的虚拟端口 HD.CLK_SRC/HD.PARTPIN_LOCS 警告也保留在证据包中，不能忽略后宣称整机通过。没有为了达标放宽时钟或新增 false path。

| OOC 模块 | WNS ns | WHS ns | 决定 |
|---|---:|---:|---|
| drop_counter_reference | −0.130 | −0.105 | 对照基线 |
| drop_counter_segmented | +1.234 | −0.275 | 建立时间改善，保持时间未通过；保留为待集成候选 |
| cfar_cluster_x1 | +0.074 | −0.419 | 对照基线；虚拟端口保持时间失败 |
| cfar_cluster_timing_x2 | −0.174 | −0.419 | 建立时间比原版退化 0.248 ns，不采用此候选 |

CFAR 的局部计数移动并未带来实际时序收益，保留源码和失败对比供排错，后续继续使用原聚类器。本轮不把功能等价误当成时序改善。

## X3 后续优化的量化方向

2048 点的一帧从首个到最后一个采样包含 2047 个采样间隔，3.84 MSPS 对应 533.073 µs。用现有中位总时延减去此项，推算剩余开销为 96.827 µs。只有采集一项也要求采样率严格高于 10.235 MSPS，才可能满足 <200 µs。

若假设剩余开销保持不变，各档总时延估算为：7.68 MSPS 363.364 µs；15.36 MSPS 230.095 µs；24.576 MSPS 180.120 µs；30.72 MSPS 163.461 µs。因此，整机时序通过后优先验证 24.576 MSPS 比在 3.84 MSPS 上微调软件更有希望。**这些数值仅用于规划**；真实丢帧、平均、排队、时钟及实现变化可能改变时延，必须重新测量首 IQ 到列表，原 FAIL 不变。

## X4 缓存候选与 Cortex-A9 实测

`src/ps/sentinel/amc/infer_cached.py` 提供可选 `CachedPredictor`，预缓存六层转置权重，增加常驻缓存 13568 字节。输入、前处理、模型和盲同步细分均沿用原接口。

- `int32`：保持 INT32 点积。
- `exact-fp32`：先检查 INT8 权重绝对值和乘 127 不超过 2^24，保证各整数乘积和任意部分和可由 FP32 精确表示；这是浮点 GEMM 路径，不能称为 INT32 MAC 加速。
- PC：2000 个 SNR=10 dB 独立测试片段的 logits 精确一致；50 个片段、3 次重复的完整预测和细分输出一致。
- 板端：10 类各 5 个、每段 4096 点、480 kSPS，三个后端旋转顺序运行，共 450 次测量；完整输出在程序内逐样本比较一致。原始耗时及标签/置信度保留在 JSON。

| 板端后端 | 中位 ms | P95 ms | 最大 ms | 相对原版中位加速比 |
|---|---:|---:|---:|---:|
| reference_int32 | 52.1066 | 125.9396 | 131.5358 | 1.0000 |
| cached_int32 | 52.0442 | 125.6163 | 131.4701 | 1.0012 |
| cached_exact_fp32 | 51.3559 | 125.2775 | 131.1317 | 1.0146 |

改善不足以证明显著收益，且三种后端均有单次 >100 ms，因此**不切换部署默认后端**。本组 50 段配对实验与原正式验收测试集不同，不能把最大值从 184.668 ms 变成 131.132 ms 当作正式指标改善。

模型保持 round_3，SHA256：`5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935`。原三轮训练/准确率验收不变，本轮不是第四轮训练。板端实验仅在独立 `setup/x4_cached_board_r3` 目录进行，不使用 sudo、RF、MMIO 或 DMA。

## 失败轮次与修正

| 实验 | 轮次 | 结果与修正 |
|---|---|---|
| X2 OOC | 1 | 缺少 Tcl 参数；修正参数传递 |
| X2 OOC | 2 | Vivado 不支持 remove_from_collection；改为 get_ports 过滤输入端口 |
| X2 OOC | 3 | 四模块最终审计，以 JSON 中原始数值为准；不再追加第 4 轮 |
| X4 板端缓存基准 | 1 | 输入布局误判；修正为 INT16 [50,2,4096] |
| X4 板端缓存基准 | 2 | ARM32 的 bincount 要求本机 intp；先验证标签范围再转换 |
| X4 板端缓存基准 | 3 | 450 次配对测量及等价验证完成；不再追加第 4 轮 |

前两次板端失败均发生在计时循环之前；原目录/日志保留。OOC 三轮是独立模块实验，没有启动 sentinel_v1c 第三轮整机实现。

## 文件与复核命令

- `board/measurements/x0_x4_optimization_r1.json` / `.sha256`：独立重算的汇总、正式状态与证据索引。
- `board/measurements/x4_cached_board_r3.json` / `.sha256`：450 条板端耗时、boot_id、模型/源码/传输包哈希。
- `sim/results/x4_cached_pc_r1.json`、`.npz` 及 SHA256：PC 等价与耗时证据。
- `report/results/x0_x4_optimization_r1.zip` / `.sha256`：候选源码、仿真日志、四模块时序/资源报告、失败日志与逐文件 manifest。不直接提交 `logs/` 或 `build/work/`。
- `tools/finalize_x0_x4_optimization.py`：验证证据链并首次生成汇总；已有输出时拒绝覆盖，不要为重跑而删除历史结果。

仅复核现有证据，不触发硬件操作：

```powershell
@'
import hashlib, json
from pathlib import Path
import zipfile
p = Path('board/measurements/x0_x4_optimization_r1.json')
assert hashlib.sha256(p.read_bytes()).hexdigest() == Path(str(p)+'.sha256').read_text().split()[0]
d = json.loads(p.read_text(encoding='utf-8'))
z = Path(d['archive'])
assert hashlib.sha256(z.read_bytes()).hexdigest() == d['archive_sha256']
with zipfile.ZipFile(z) as f:
    for name, digest in json.loads(f.read('manifest.json')).items():
        assert hashlib.sha256(f.read(name)).hexdigest() == digest, name
print(d['formal_status'])
print('OPTIMIZATION_ARCHIVE_VERIFIED')
'@ | ./.venv/Scripts/python.exe -
```

`logs/X0_X4_optimization_tests_r1.log`：`src/ps/tests` 范围 **172 passed**。此范围不等同此前全仓库 252 项回归。板端和 PC 墙钟存在偏差；本轮记录以 PC UTC 时间及板端 boot_id 识别，不据此推算跨设备时延。

## 下一步边界

本轮成果可供后续 agent 直接读取和比较，但不能直接替换已验收位流。继续集成前先阅读本文件、`90_plan.md` 和各正式验收摘要，核对未提交的 X5 工作。X2 若要整机集成，需要新的明确执行记录；新位流必须完整时序审计通过后才能加载。RF 测试仍按相应步骤的用户天线确认执行，换线/目视/听音等人工步骤等待用户返回。保持当前板卡上电；断电前先 `sudo sync && sudo shutdown -h now`。
