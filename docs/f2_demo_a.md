# F2 接收演示 A 组

沿用 sentinel_v2_100m、100 MHz、3.84 MSPS。配置 A：选定20–512 MHz天线接RX1A，TX1A空；J22屏幕及J7/J8=2.5V不变。音频通过J36板载喇叭，默认−12dB。没有改动RTL、位流、模型或CFAR参数。

## 执行入口

在开发板SSH终端运行：

```bash
cd /home/xilinx/sentinel/release/v2
sudo sh scripts/sentinel.sh demo A
# 单段重录：1自检、2监测识别、3喇叭、4内部三音
sudo sh scripts/sentinel.sh demo A --segment 3
# 循环直至受控停止；不可断电或按复位结束
sudo sh scripts/sentinel.sh demo A --loop
# 有界重复三遍，用于自动验收
sudo sh scripts/sentinel.sh demo A --cycles 3
```

另一个SSH终端可执行 `sudo sh scripts/sentinel.sh stop`。停止信号逐层传给当前工作进程，等待静音和关闭后检查GPIO/SRC/audio均为0。后台日志、各段结果及SHA256均在正式发布目录的logs与measurements中。未设置开机自启。F3的B组尚未实现，当前入口会在硬件操作前拒绝B组。

## 行为与安全

- 自检10秒、监测40秒、FM喇叭30秒、内部三音15秒。时长从各段完成初始化后计时，实际整组时间包含位流加载、射频校准和停止读回，不能用95秒替代实测墙钟时间。
- 自检对已确认且处于同一LO配置的立体声电台逐个检查三份IQ质量，合格者按中位IQ功率选择。当前候选表只有95.8MHz；这不是整个FM频段的自动搜台，也不能把分类器预测当作电台真值。
- 喇叭播放持续沿用导频/相位质量门控。没有可信候选或整个音频段始终静音时，演示记录失败并停止，不以无崩溃冒充收听成功。
- 三音段仅使用PL内部测试源，AD9361保持复位。段间进行独立读回、校验结果文件哈希；子进程错误、清理错误及结果状态不完整均中止整组。
- 屏幕右上软件区域显示段标题和倒计时，底部显示模式、LO、帧率、温度和TX OFF，列表按FM白色、AM黄色、数字/未确定青色着色。识别分数仍为未校准的实验模型输出。

## 未达成的完整方案项

1. 冻结LCD接口仅支持黑、白、黄、青四色，因此TX OFF为青色，无法实现原方案绿色；全屏顶部为PL绘制，段标题放在右上PS区域。为保持位流冻结，不修改硬件。
2. 现有PCM路径仅送I2S，PS没有连续PCM回读接口。4096点PFB捕获是间断快照，不能拼接冒充30秒连续喇叭录音。当前未生成WAV，保存为明确缺项；不据此重新构建PL。
3. 单组约1.5分钟目标须按墙钟实测评定，不能排除每段初始化与停机开销。

## 当前验证

73项针对性测试和365项PS/发布回归通过，证据`board/measurements/f2_software_r1.json`及SHA256。90文件发布包安装并逐项哈希通过，旧F1发布目录保留，证据`f2_deployment_r1.json`。首个免密sudo部署命令在安装前被系统拒绝，后续依已有授权使用默认密码成功，日志均保留。

用户已回复“全部正确”，确认本轮目视和听音，证据`f2_human_r1.json`。三遍自动运行已结束：共12段全部正常，466文件SHA256一致，最终codec静音、GPIO/SRC/audio均0。总墙钟521.462秒，每组平均173.821秒；各段进程时间之和每组142.569/142.772/143.126秒，其余为段间校验。三轮音频实际放音28.958/28.954/28.947秒，均零下溢；接收监测最低39.289fps，最高65.581°C，零处理错误。F2主功能与目视/听音通过，整体因上列缺项保持FAIL。证据`board/measurements/f2_acceptance_r1.json`与`f2_demo_r1/verification.json`及各自SHA256。后续按方案推进F3，不追加硬件构建。

## 文件定位

- `src/ps/sentinel/app/demo.py`：A组分段调度、单段重录、循环、候选选台及段间验收。
- `board/scripts/demo_a.py`：正式发布启动桥接。
- `board/scripts/release_entry.py`：统一入口、进程监管、受控停止。
- `board/scripts/release_selftest.py`：射频自检与可信候选测量。
- `board/scripts/run_test_display.py`：无射频三音段、画面计数与健康检查。
- `board/scripts/run_y3_audio.py`：原监听程序增加演示标题/倒计时，清理错误显式失败。
- `src/ps/sentinel/lcd_x5.py`及`app/monitor_x5.py`：PS界面扩展与识别显示复用。
- `src/ps/sentinel/release_support.py`：可信候选选择、质量证据和SHA256。
- `tools/release_board.py`：哈希打包与安装，旧发布版保留用于回退。
- `src/ps/tests/test_demo_f2.py`、`tools/tests/test_release_board_f1.py`：软件和调度安全回归。
