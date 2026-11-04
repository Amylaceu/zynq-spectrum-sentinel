# F3 空口验证与 B 组演示

## 基线与使用条件

固定使用 `board/overlay/sentinel_v2_100m/`，处理时钟100 MHz、采样率3.84 MSPS。不修改位流、识别模型、CFAR参数或第三方代码。

本次使用两根2.4 GHz折叠胶棒天线，分别直接安装在TX1A/RX1A，约2–3 cm间距，方向一致。该连接由用户确认；遵循`runbook/99_finish.md`的B-直插规则，发射频率固定2.45 GHz、TX1衰减不低于40 dB，TX2保持89.75 dB。RSSI超过−30 dBm立即中止。无衰减器，不允许SMA电缆直连。

## 板端运行命令

以下命令在开发板SSH终端执行。工作目录以实际发布位置为准，默认如下：

```bash
cd /home/xilinx/sentinel/release/v2
sudo sh scripts/sentinel.sh demo B
# 交互提示时，只有实际确认B-直插天线后才输入yes。
# 自动执行前已人工确认时，可显式传入确认和遍数：
sudo sh scripts/sentinel.sh demo B --antenna-confirmed yes --cycles 3
# 单段运行：7环境接收、5十类空口、6 QPSK注噪、8性能。
sudo sh scripts/sentinel.sh demo B --antenna-confirmed yes --segment 8
# 循环模式与--cycles不可同时使用。
sudo sh scripts/sentinel.sh demo B --antenna-confirmed yes --loop
# 另一个SSH终端受控停止：
sudo sh scripts/sentinel.sh stop
```

每遍顺序为7→5→6→8，段内目标时间分别20、60、30、15秒。总时间还包含初始化、模型预热、衰减爬升、位流加载和安全停止，必须使用实际墙钟记录，不能直接将125秒作为整组耗时。

屏幕中的SENT是已知发送类别，识别列表是冻结模型对实际接收IQ的预测，两者独立。显示预测置信度、IQ点图、模式、倒计时、帧号、帧率及温度。注噪段标注AMP幅度，不将其冒充校准SNR。性能段显示实测样本吞吐及PL输入标记到下一CFAR列表的延时，后者不等同射频输入到分类上屏的端到端延时。

## 停止与异常处理

发射退出依次恢复最大衰减、停止TX DMA、清零注噪和信号源、停止射频并读回ENSM=ALERT及双TX89.75 dB；随后读回GPIO/SRC/audio均为0。清理错误会被显式记录。DMA未确认空闲时保留缓冲区及硬件所有权，不以释放内存冒充停止。

第一轮在性能段因PERF历史溢出标记触发保护，且退出时SRC模式位未完全归零，故保留FAIL。修复限定于PS启动及清理流程：性能段重新加载同一份已验收位流；在RF保持复位时清除启动期历史标记，运行期间仍严格检查故障；退出在硬件锁释放前写回SRC=0。没有重新综合或布线，没有放宽最终停机检查。

## 评测结果与适用范围

每类捕获50个4096点IQ窗口，共500个。窗口来自循环发送波形，虽然文件内各窗口哈希不同，也不能视作500次独立波形试验。随后在电脑端对捕获IQ加入固定种子的AWGN，参考值定义为捕获IQ总功率与新增数字噪声功率之比，原始接收噪声未扣除。

| 项目 | 实测结果 | 判定与限制 |
|---|---|---|
| 数字注噪参考10 dB，10类识别 | 83.4% | 达到80%目标；不是校准RF SNR=10 dB的认证 |
| 同条件8大类识别 | 86.0% | 未达到90%目标 |
| 同生成器仿真参考10 dB | 10类90.0%，8大类92.8% | 不包含发射插值、射频及PL信道化，不能与实际链路视为完全等价 |
| 宽带CW标定 | 三轮未达25 dB | 保留FAIL；通道化后的较高CW比值不能替代宽带结果 |
| PL注噪功能 | 通道化CW比值由约41.10 dB变为11.72 dB | 证明该路径注噪有效，不是通用调制SNR标定 |
| 单音检测 | 最高注噪幅度65535时命中15/30，其他已测幅度均30/30 | 异步功率/CFAR快照且输入单bin SNR未标定，Pd@10 dB未认证 |
| TX关闭环境检测 | 2.305/2.345/2.385 GHz命中比例约9.80×10⁻⁶、1.96×10⁻⁵、2.94×10⁻⁴ | 未排除外部发射，且平均滤波改变统计分布；不认证Pfa比值 |

完整曲线、混淆矩阵和预测数组保存在`board/measurements/f3_evaluation_r1/`，原始空口窗口在`board/measurements/f3_capture_r1/`。结果JSON中的PASS可能仅表示程序完成，工程指标以本节和独立验收摘要为准。历史未达标项均保留，不追加训练、调CFAR或更改验收阈值。

## 文件与跨设备交接

- `src/ps/sentinel/app/demo_b.py`：B组调度、上屏与安全清理。
- `src/ps/sentinel/rf/f3.py`：独立发射库封装、40 dB配置限制及看门狗。
- `src/ps/libad9361_pynq/Makefile.f3`、`app/f3_api_c.c`、`app/f3_exports.map`：F3独立C接口，不替换已验收接收库。
- `src/ps/sentinel/f3_signal.py`、`f3_capture.py`、`f3_detection.py`、`f3_evaluate.py`：波形、捕获、检测观察和离线注噪评测。
- `board/scripts/demo_b.py`、`run_f3_probe.py`、`run_f3_pfa.py`：板端入口。
- `tools/prepare_f3_waveforms.py`、`run_f3_probe.py`、`evaluate_f3_captures.py`：准备及评测命令。
- `tools/run_f3_demo.py`、`collect_f3_demo.py`：有界启动和停止后只读收集，已有输出拒绝覆盖。
- `tools/release_board.py`：正式发布包构建，逐文件SHA256校验并保留旧版本。
- `build/f3_library/libad9361_f3.so`及SHA256：已验收ARM库，小文件随本次提交携带；不要在Windows上把它当作主机库加载。缺失时可运行`python tools/fetch_f3_library.py`从已验收板端副本取回，或使用完整快照。
- `data/reference/f3_ota/`：各类发射波形及清单；`board/measurements/f3_*/`：原始结果及哈希。
- `build/f3_release*/`和`build/f3_*.tar.gz`：本地传输暂存，不加入Git，完整快照仍保留。

本轮针对性软件回归为396项通过、18项略过，日志`logs/F3_demo_fix_regression.log`。最终PS及工具回归为605项通过、18项略过，日志`logs/F3_final_regression_env.log`。第一次全量回归因Windows Tcl初始化及标准输出捕获出现1失败、1错误；设置实际Python安装目录的TCL_LIBRARY/TK_LIBRARY并使用pytest的`-s`参数后通过，没有修改被测功能或执行硬件构建，原失败日志保留。

## 最终演示验收（2026-11-04）

第二次正式运行完成3遍、12段，每遍顺序7→5→6→8，所有段及监督进程均正常退出。104个板端文件复制后与原SHA256一致，原始记录位于`board/measurements/f3_demo_r2/raw/`，独立核验见同级`verification.json`。板端日历停留在2021年，目录日期不作真实测试日期；以主机UTC、相同boot_id和单调时间解释记录。

| 项目 | 实测 |
|---|---|
| 整场墙钟时间 | 481.565秒 |
| 每遍段耗时之和 | 159.817、156.827、156.344秒（不含遍间调度开销） |
| 最低TX衰减、最高RSSI | 40 dB、−58.5 dBm |
| 最低显示帧率、最高温度 | 36.563 fps、65.950°C |
| 各段退出 | GPIO/SRC/audio均0；发射段ENSM=ALERT、双TX衰减89.75 dB |
| 最终只读停止复核 | 无运行中监督状态、硬件锁可用、GPIO/SRC/audio均0 |
| 人工反馈 | 用户回复“画面没问题”；仅证明所观察画面正常，不证明三遍全部细节或识别率 |

最终结论为**功能通过、总体指标未达标（F3 FAIL）**。十类数字注噪参考10 dB识别83.4%达到对应目标，八大类86.0%未达90%；宽带标定未达到25 dB，Pd/Pfa未完成校准认证，每遍耗时超过约2分钟目标。第二次成功演示不撤销第一次失败及其他历史FAIL，不再追加训练、调参或构建。

独立发射库SHA256为`e89a131aebe30f35575a7de2ba21b66da0c55eb78d7ed06abb0c2837b858d271`，正式接收库为`b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83`，两者不得混淆。最终验收摘要`board/measurements/f3_acceptance_final.json`及SHA256关联原始测量、传输清单和测试日志。

## 下一步操作

F3已安全停止。按SD卡指南先做本阶段整卡备份：必须先执行`sudo sync && sudo shutdown -h now`并确认停机，再断电取卡，不在上电状态下拔卡。备份后断电插回SD；RX1A恢复选定的20–512 MHz天线，TX1A空着，J22和2.5V跳线保持不变。人工确认配置A和上电状态后才能开始F4仅接收；扫描后半段需另行停止射频并确认配置D。
