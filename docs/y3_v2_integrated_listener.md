# 100 MHz 功能接续：复用原监测程序与可选监听

## 范围与用户最新纠正

150 MHz 已通过的功能直接复用，不因时钟改变重写算法。100 MHz 切换必需的是
时钟参数/计数换算适配、位流审计和新位流回归；原有历史实测仍然有效，但只代表
当时的位流。2026-11-03 用户要求优先运行既有功能，新集成项不应阻塞迁移。

本次没有修改 RTL、硬件约束、识别模型、CFAR 算法或 LCD 绘图实现。旧 v1b/v1d
的 bit/HWH/XSA 已逐项对照 acceptance.json 校验，六个文件均一致。

新增监听是独立可选项，不是迁移的必选步骤；未传 --listen 时仍走原监测流程。
当前既有工程已经包含 PL FM/I2S，本次只连接其软件接口，不增加硬件。

## 已准备的功能

- `src/ps/sentinel/listen_y3.py`：在已复位信道化器上初始化并静音编解码器，
  启动音频 FIFO；等待真实输入预填后解除静音。定期检查 PCM/I2S 速率和 FIFO，
  并在退出前检查最后一个采样间隔的锁存错误。
- `monitor_x5 --image sentinel_v2_100m --listen 95.8e6`：在同一会话中运行
  频谱、CFAR、捕获/识别、星座图与 PL 连续监听。声音来自连续 PFB 分支，
  不拼接识别用的短 IQ 快照。状态栏标记 LISTEN、X4 EXP 和 TX OFF。
- 捕获/推理失败、用户中断、音频异常时，先尝试静音/关闭 DAC 与输出驱动，
  再关闭 RF 会话。清理失败和错误计数会保存，不改成 PASS。
- `tools/run_x5_board.py` 支持 30/120/300 秒、独立监听测量标签、音频量化检查。
  数字检查通过仍不表示人工听音或识别准确率通过。

## 已实际验证

1. 首轮 82 PASS / 1 FAIL：浮点数精确相等断言不合适，改为近似比较。
2. 全套电脑测试第2轮454 PASS，第3轮补齐独立验收反例后462 PASS。
3. 开发板 Python 3.8.2 兼容检查：隔离目录部署纯 Python 源码，注入假I/O，
   正常生命周期和结束前下溢故障均通过；没有导入PYNQ、没有访问MMIO或加载位流。
   第一轮安装复用了需要硬件锁文件的安装器，因启动后锁文件不存在失败；
   第二轮改用独立纯Python安装器通过。不创建硬件锁、不改变共享板端软件。
4. SHA256结果：`sim/results/y3_v2_integrated_software_r1.json`、
   `board/measurements/y3_listener_python_r1.json`（保留失败）、
   `board/measurements/y3_listener_python_r2.json`（兼容性通过）。

## 下一步顺序（未执行）

1. 先完成100 MHz位流的CDC/外部I/O审计与既定部署门禁，复验原有单音、三音、
   8192字回放，再验证配置A下频谱/识别/显示。不要将软件兼容测试当作这些板测。
2. 先单独运行1kHz/3秒音频测试，等待用户听音确认；仍插着耳机时先不要佩戴。
3. 再选择并发监听：30秒冒烟 → 300秒连续播放，人工确认广播可听清。

待门禁和听音前置条件满足后的主机命令（不是现在就可部署的授权）：

```powershell
./.venv/Scripts/python.exe tools/run_x5_board.py --image sentinel_v2_100m --attempt 1 --lo 96400000 --seconds 30 --listen 95.8e6 --volume -21 --confirm-configuration-a --preflight-bit <板端已加载且已验收位流路径>
# 30秒成功后，300秒使用独立测量标签，不覆盖冒烟数据。
./.venv/Scripts/python.exe tools/run_x5_board.py --image sentinel_v2_100m --attempt 1 --lo 96400000 --seconds 300 --listen 95.8e6 --volume -21 --confirm-configuration-a --preflight-bit <板端已加载且已验收位流路径>
```

## 当前位流限制

T5 WNS +0.210ns / WHS +0.030ns 不变，Z10 +1ns门禁未通过。此次未发布收据、
未加载100MHz位流、未射频测试、未初始化ES8388或播放声音。Y3保持DOING。
CDC报告已定位到：ADI ADC DMA106条CDC-1/24条CDC-13、DAC DMA4条CDC-1、
AD9361时钟选择2条CDC-13；另4条CDC-10位于音频控制与ADC复位。
这是定位清单，不能把供应商IP告警直接豁免，也不等于CDC签核。

用户最新要求：后续优先100MHz既有功能复验，避免将尚未验收的新监听集成
当成旧功能迁移的额外要求。原X/Y/Z10/T5失败结论保留。
