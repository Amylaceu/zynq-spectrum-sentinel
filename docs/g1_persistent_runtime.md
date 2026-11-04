# 演示运行时与验收范围

基线保持 `sentinel_v2_100m`，100 MHz、3.84 MSPS。此次仅修改处理器端程序，没有重新综合、布线、训练或调整 CFAR。

## 运行方式

在开发板正式发布目录运行：

```sh
sudo sh scripts/sentinel.sh demo A --cycles 3
```

默认使用常驻运行时。原有逐段子进程和重新下载方式保留：

```sh
sudo sh scripts/sentinel.sh demo A --isolated --cycles 1
```

单段重录继续使用 `--segment 1` 至 `--segment 4`。配置 A 为 RX1A 接选定的 20–512 MHz 天线、TX1A 空置。B 组必须另行确认直插双天线；本次配置 A 验证不证明 B 组发射功能通过。

## 文件与职责

| 文件 | 职责 |
|---|---|
| `src/ps/sentinel/app/runtime_v2.py` | 缓存已核验的位流、DMA对象、模型及段入口，负责停止读回、异常拒绝复用和两帧就绪检查 |
| `src/ps/sentinel/app/demo.py` | A组调度、每遍墙钟记录、站点选择、结果和SHA256验证；支持隔离回退 |
| `src/ps/sentinel/app/demo_b.py` | B组复用入口、发送类别与识别结果分离、墙钟倒计时；发射异常保护保持 |
| `board/scripts/release_selftest.py` | 接收自检及可信站点选择，可显式注入运行时 |
| `src/ps/sentinel/app/monitor_x5.py` | 复用分类器与硬件，保留检测、IQ留存、推理、显示和射频保护 |
| `board/scripts/run_y3_audio.py` | 保留已验证的PL播放、导频门控、音量和下溢保护，复用编解码器对象 |
| `board/scripts/run_test_display.py` | 三音测试，保持射频复位和停止读回 |

段入口通过 `main(argv=None, runtime=None)` 接收依赖，不替换全局 Session、命令行或驱动对象。直接命令行运行时仍使用原 Session。运行时在段后恢复信号处理器，停止请求向外层传播，失败后不继续复用可能损坏的 DMA 状态。

## 不能同时满足的条件

每段结束要求 GPIO、SRC、audio 全部读回零。其中 GPIO=0 会拉住 AD9361 硬件复位。因此下一接收段必须重新初始化射频，不能宣称整组三遍只初始化一次 AD9361。射频初始化次数和复位前双路 89.75 dB 读回均写入证据。编解码器在段末静音并掉电，下次播放仍进行寄存器初始化和读回。

冻结位流的音频控制接口提供状态、采样计数和下溢标志，没有实际播放 PCM 的读取口。因此 `--record-audio PATH` 明确返回 `UNSUPPORTED_NO_PLAYBACK_PCM_READBACK`，不创建 WAV，不把稀疏 IQ 的重解调、零填充或模拟音频当作实际播放录音。播放功能与录音指标分别判定。若后续必须获得实际播放流，需要经授权增加数据路径，或采用能保证播放与录制来自同一连续流的软件音频方案；此次没有进行这类变更。

## 计时及证据解释

`cycles_timing` 为每遍完整墙钟时长；`duration_wall_s` 包含单段初始化、内容和清理。后续运行时还记录启动、两帧就绪、内容起点及清理终点，切换耗时据实际时间戳计算。冷启动与热运行分别报告，不能去掉首遍来宣称三遍全部达标。

板测发布包位于 `build/g1_package_r1/` 与 `build/g1_package_r2/`，部署证据分别为 `board/measurements/g1_deployment_preflight.json` 和 `board/measurements/g1_deployment_r2.json`。包目录不提交Git，完整快照时保留；发布包和安装结果分别有SHA256，板端旧目录保留供回退。原始F2/F3及X/Y阶段FAIL结论保持不变。

离线重新核验取回的结果：

```powershell
python tools/g1_evaluate.py board/measurements/g1_demo_r2/demo_20211119T002416Z_ef0bca2d --output build/g1_recheck.json
```

校验器要求段结果与 SHA256、主结果中的引用一致；逐段及最终停止状态均需归零。缺少内容起点时间戳时，切换时间标为未测，不能用零代替。冷启动首遍始终计入时长指标。

## 实测结果与未达标项

最终代码连续三遍完成12段，完整墙钟分别116.731、109.500、110.217秒，平均112.149秒，相对历史173.821秒缩短约35.5%。只加载一次位流、一次模型并预热一次；九次接收段均重新初始化射频，保持段末安全复位。

11次切换耗时中位4.693秒、最大5.001秒，最大值达到6秒要求，中位数未达到3秒要求。首遍包含10.898秒冷启动；不排除首遍或取最短一遍代替整体结论。三次实际出声分别28.961、28.959、29.154秒，音频下溢均0；30秒内容窗口包含质量门控的初始静音，不能写成30秒连续出声。

逐段以及最终GPIO/SRC/audio均归零；接收段复位前双路TX衰减均89.75dB。第二次板测460个原始文件取回后逐文件核验SHA256通过，正式入口退出码0，最终独立停止读回通过。第一轮用户确认“显示与声音均正常”；第二轮未另行取得人工目视或听音确认，不能扩大该反馈范围。

因此G1状态为FAIL、功能PASS：三遍时长未全部达到110秒，切换中位数未达3秒，实际播放WAV仍不可获取。两轮结果完整保留，不追加第三轮；按方案继续G2。B组仅完成常驻化离线回归，真实发射验证留待G5。

证据索引：

- `board/measurements/g1_acceptance_r1.json`：首轮实测汇总，缺少切换时间戳。
- `board/measurements/g1_acceptance_final.json`：最终代码实测汇总。
- `board/measurements/g1_demo_r2/verification.json`：460个远端文件与本地摘要比对。
- `board/measurements/g1_postflight_final.json`：三遍结束后的独立停止检查。
- `board/measurements/g1_software_final.json`：软件回归、Python3.8载荷检查及冻结文件摘要。

上述JSON均附`.sha256`。本地包不入Git，现发布目录保留；第二次安装前的版本位于板端`release/v2_previous_efe6269ccc6b426db194d1a25cb633d5`。保持开发板上电，射频和音频已停止；G5之后再进行下一次整卡备份。
