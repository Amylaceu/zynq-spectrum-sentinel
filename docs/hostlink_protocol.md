# hostlink/1 协议与接入检查点

已实现并部署标准库网络服务、HTTP/SSE及常驻运行时数据绑定。正式配置A只接收测试420.416秒完成；总体FAIL（功能PASS），原因是精确PL帧到PC延迟尚未认证，详见末尾实测范围。

TCP使用9000端口；HTTP/SSE使用8080端口。服务必须绑定明确的本机局域网IPv4地址，不能默认监听所有网卡。最多3个客户端，每个客户端待发送字节不超过2MiB。服务器不提供任何发射、衰减、TxGuard、任意文件路径或Shell命令。

每帧为ASCII JSON头加LF，再跟`len`个二进制字节。头部必填`type`、`seq`、`t_mono`、`len`；最大头长16KiB、最大负载1MiB。每个发送方向的seq严格递增，连接重建后可以重新计数；t_mono为发送设备单调时钟秒数，不能直接跨机器相减推算单程延迟。握手另外携带boot_id及协议版本。NaN、无穷值、重复键、负长度和超限帧拒绝。

| type | 负载/说明 |
|---|---|
| hello | 协议版本、位流SHA256、发布摘要、boot_id、采样率、LO、FFT长度、频谱来源及功率参考 |
| spectrum | 1024个小端int16，0.01dB单位，另带频率起点和间隔、捕获时间与帧号范围；2048点按相邻两点取最大值 |
| detections | JSON目标列表，包括key、频率、带宽、原始功率、首次出现的单调时间 |
| amc | 原始预测及置信度、五票历史和显示标签；保持低分问号规则 |
| iq | 512个小端complex64，实部/虚部交错；标明实际IQ采样时间与采样率 |
| telemetry | 帧率、温度、RSSI、溢出、CPU、内存、TX状态/衰减、音频状态、队列丢帧 |
| event | 与LCD相同的时间、类型、频率及文字 |
| demo | 组、段、标题、剩余时间、已知发送类别与实际识别类别 |
| command / reply / error | 请求seq关联回复；命令不允许携带二进制负载 |

功率数据未做输入端绝对功率标定时，明确使用`power_reference=raw_integer_power`，dB相对原始整数1，不称dBm或dBFS。PS FFT降级时明确`source=ps_fft`、IQ所属带宽和真实更新率，不把重复推送当作新采样。未测到精确的PL帧对应关系时，提供前后帧号范围，端到端延迟标记未认证。

命令头增加`command`及`args`对象，启用认证时增加`token`。认证令牌只在部署设备上配置，不写入源码、日志或测量结果。命令白名单：

| command | args | 限制 |
|---|---|---|
| ping / get_status / snapshot / stop | 空对象 | snapshot只保存服务内部指定目录；stop走正式清理 |
| select_target | key整数 | 非负，执行时还需检查目标仍存在 |
| set_page | page字符串 | SIG/TGT/STAT |
| set_lo | hz有限数值 | 仅monitor，70MHz–2.7GHz；由硬件所有者停流、改频、核验后再启动 |
| listen | mhz有限数值 | 仅monitor/listen，87.5–108MHz；仍需符合已有音频保护与质量门限 |

除表内参数外均拒绝，禁止通过额外字段夹带硬件操作。网络线程只验证和排队请求；采集所有者执行涉及硬件的请求并回报结果。段演示不接受远程改频或播放请求。共享token采用常量时间比较。

有界队列优先丢弃旧spectrum/iq；事件、命令回复不能丢掉冒充成功。控制消息无法保留时断开慢客户端。已经部分发送的帧不可丢弃剩余部分，否则TCP流失去边界；其剩余字节计入同一个2MiB预算。采集线程不得等待网络发送。

## 实现与操作

`app/hostlink.py`以单selectors线程服务TCP/HTTP；`hostlink_runtime.py`的独立采样线程独占功率捕获控制/BRAM，10Hz请求快照，退出先释放采样租约再停源。主采集线程执行硬件白名单命令，网络线程不访问MMIO、RF、IQ DMA或音频。monitor/listen/demo通过`--hostlink`启用；show入口留G5实现。

```sh
sudo sh release/v2/scripts/sentinel.sh monitor --ui v3 --seconds 420 --hostlink
sudo sh release/v2/scripts/sentinel.sh stop
```

在板端项目目录运行。`board/release/config.yaml`配置明确的局域网绑定地址；部署时核对实际网卡。PC连接TCP9000；同网段浏览器访问HTTP8080。共享token通过部署环境变量SENTINEL_HOSTLINK_TOKEN设置，服务端常量时间比较，网页在token启用时返回403，不把token放URL。PC图形界面token输入在G4实现。

配置A上下文进一步限制远程LO不超过512MHz。远程listen只允许已确认电台、已有质量门限及当前接收窗；其他情况拒绝。快照位于本次测量目录host_snapshots/，功率和IQ为独立采样，保留各自时间，不能视为相干捕获。段间保持服务，不重开端口；每段停止采样线程。

## 实测范围与未达标项

配置A、冻结100MHz/3.84MSPS；未发射。基线30.421秒，启用服务420.416秒；两次均正式退出成功。基线LCD中位40.235fps，开启后40.877fps、最低39.563fps。短基线仅用于当前同条件比较，不构成普适加速结论。网络线程CPU为单核3.056%；生产者和客户端丢帧均0；最大待发送7085字节。实际4190次独立功率快照、平均9.966Hz，不宣称精确10.000Hz。

十次PC socket断开均超过30秒后成功重连；没有实际拔网线。网页与SSE通过；4个非法/越界请求全部拒绝并记录；ping/status/切页/快照通过。采样及处理零溢出，perf状态位2是latency_valid，不是溢出位。独立停止检查GPIO/SRC/audio均0。总回归695 passed、18 skipped，hostlink专项31项。

PL只提供LCD帧号前后范围，未实现精确FFT帧映射及跨设备时钟校准。因此150ms的PL→PC指标未认证，整体记FAIL（功能PASS），不通过不同设备单调时钟直接相减伪造延迟。B组hostlink尚未实测，留G5。

原始证据board/measurements/g3_board_r1/，部署、验收和停止检查均有JSON/SHA256。`tools/g3_evaluate.py`校验原始文件全集摘要并重新计算指标。固定位流、第三方源码、CFAR及模型均未改动。
