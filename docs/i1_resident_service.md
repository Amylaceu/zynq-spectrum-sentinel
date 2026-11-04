# 常驻接收服务与场景切换

本实现保持一个射频会话，切换接收场景时不释放会话或清零 AD9361 的 GPIO。固定使用 sentinel_v2_100m、100 MHz、3.84 MSPS；没有修改位流、模型和 CFAR 参数。配置 S1 已获得仅接收授权。

## 文件与入口

- `src/ps/sentinel/app/resident.py`：场景控制、质量门控、射频和音频读回、统一清理。
- `src/ps/sentinel/app/resident_control.py`：仅 root 可访问的本地 Unix socket，限定 scene/status/stop。
- `board/scripts/serve_resident.py`：常驻进程，单次运行有最长 3600 秒边界。
- `board/scripts/release_entry.py`：已有发布管理入口，新增 serve/scene/status，复用原停止协议。
- `src/ps/sentinel/app/hostlink_protocol.py`、`hostlink_runtime.py`：resident 模式的白名单场景请求。
- `tools/i1_board_check.py`：独立候选部署、50 次随机接收场景切换、独立停止核对及证据取回。
- `tools/tests/test_i1_resident.py`：所有权、异常、静音顺序、请求校验等离线测试。

## 板端操作

下列命令在已部署的候选目录执行。此轮目录为 `release/i1_r3`，相对于开发板现有 sentinel 工作目录。正式 `release/v2` 未覆盖。启动前停止其他接收程序；不并行启动两个硬件所有者。不要在自动验收期间另行执行场景命令。

```sh
cd release/i1_r3
sudo sh scripts/sentinel.sh verify
sudo sh scripts/sentinel.sh serve --seconds 3600 --hostlink
```

serve 为前台命令，日志与原始结果保存于该候选的 logs/ 和 measurements/。需要手动选择场景时，在第二个 SSH 终端进入同一个候选目录：

```sh
sudo sh scripts/sentinel.sh status
sudo sh scripts/sentinel.sh scene check
sudo sh scripts/sentinel.sh scene fm
sudo sh scripts/sentinel.sh scene listen
sudo sh scripts/sentinel.sh scene perf
sudo sh scripts/sentinel.sh scene idle
sudo sh scripts/sentinel.sh stop
```

默认监听 95.8 MHz。已验收的 i1_r3 候选默认音量仍为 −12 dB；按用户后续增大音量的要求，源码配置已改为 −6 dB，供下次打包使用，保护上限仍为 −6 dB。独立试听使用命令行音量覆盖，不修改候选清单。idle 为静音且保持接收，**不是断电条件**；stop 后还须核对 GPIO/SRC/audio 全部为 0。需要断电时，在停止完成后执行 `sudo sync && sudo shutdown -h now`，确认系统 halt 后再关闭电源、取 SD 卡。

## 实现范围与验收口径

- 已实现 check/fm/listen/perf/idle 的接收控制链。perf 目前切换到已有统计视图，完整性能汇总仍待补齐。
- check 包含固定镜像摘要、芯片 ID、温度、TX 衰减读回及导频；网络 RTT 尚须由客户端补充，不把预检全部项目标为通过。
- pano/wifi 暂不可用；ota/noise 返回 REPLAY_REQUIRED。未安装回放素材时不得把拒绝请求表述为回放完成。`--arm-ota` 明确拒绝，不会发射。
- 单次场景记录中的 ready_s 是板端开始处理至数字就绪，不含 SSH 启动、发布摘要校验或上位机传输排队。ssh_roundtrip_s 单独保留；上位机按钮端到端指标留待 I2。
- listen 的数字就绪要求导频门控通过、解除 codec 静音、播放位有效且样本计数增长；人的听音确认独立记录，不以数字计数代替。
- 切入 listen 时短暂停止源以避开音频 FIFO 复位忙窗口，再恢复源；不复位 AD9361，不重新载入镜像。
- 长时间常驻稳定性、全部讲解场景、网络点击时间、发射断网保护不属于本轮五场景短测的已通过结论。

## 证据与回退

第一、第二轮均在服务或射频启动前失败：分别是 PYNQ 已加载镜像路径身份不匹配，以及测试目标候选未部署。失败 JSON 与日志保留。第三轮先核对部署摘要，再运行接收测试；结果以 `board/measurements/i1_board_r3/acceptance.json` 及 SHA256 为准。

本地既有回归记录 `logs/I1_regression_final.log` 为 137 passed、1 skipped；跳过项是 Windows 上的 Unix socket 测试。其摘要和源文件身份需随本轮验收归档。

如需回退，先在当前候选内 stop 并确认停止，再进入原 `release/v2` 使用已有 monitor/listen/demo 入口。不要删除候选证据、跨目录停止不相符的进程、覆盖正在使用的位流或手工清理未知所有者的 socket。

第三轮五场景各 10 次、随机共 50 次均数字就绪。板内 P90 为 check 0.551 s、fm 0.234 s、listen 2.200 s、perf 0.264 s、idle 0.251 s；所有单次均在板内时间目标内。位流、RF、模型、codec 各初始化一次，运行 233.975 s，最终 GPIO/SRC/audio 均为 0，取回 174 个带摘要文件一致。SSH 往返中位 3.985 s、P90 4.875 s；尚不满足以此入口声称点击到出声 ≤3 s。汇总为 `board/measurements/i1_acceptance_summary.json`。

用户反馈随机切换期间广播间隔出现短句，未据此认定全部听音通过。随后独立既有音频入口 −9 dB 连续试听 60 s，全部自动指标通过，用户确认广播连续但音量偏小；按要求追加 −6 dB 试听。该试听不是常驻服务稳定性验收，也不是增加第四轮随机切换测试。整体 I1 仍有上文所列缺项，不标全部完成。

## 用户要求的喇叭独立增益

−9 dB 与 −6 dB 连续试听均通过自动检查，用户均确认广播连续，但仍嫌声音小。核查本地 ES8388 Rev5 第28页：ROUT2 音量 code 30 为 0 dB；现有数字 DAC 音量已经为 0 dB，功放本身没有本软件可调寄存器。新增显式 `--speaker-volume 0`，只改变 ROUT2（0x31），OUT1 与 LOUT2 继续保持 −6 dB 上限；不开放正增益。该路径在独立 `release/audio_volume_r1` 测试，原 i1_r3 与正式 v2 保留。

独立 60 秒试听入口为 `tools/i1_audio_volume_check.py --antenna S1 --antenna-confirmed --attempt 1 --volume -6 --speaker-volume 0 --sudo-stdin`，sudo 密码仅从标准输入读取。切勿在其他硬件所有者运行时执行。新候选通过 PYNQ 重新加载同一冻结位流，仅为路径所有权匹配，没有综合或布线。音量检查为独立子项，不把它当作第四轮常驻随机切换验收。源码常规发布配置默认仍为 −6 dB；ROUT2 额外增益需显式选择，已接入源码常驻初始化、直接 listen 和 A 组演示入口的配置转发，UI 调音尚未接入；需要下一软件包部署后生效。

0 dB 喇叭试听 60 秒全部自动指标通过：门控实际放音 58.749 秒、导频最低 22.816 dB、中位 34.602 dB，零下溢，独立停止通过。用户确认“音量合适”；没有把该回复扩展为未明确反馈的画面或失真逐项结论。当前已自动静音、GPIO/SRC/audio 全部为 0。最后回归 146 passed、1 skipped，见 i1_final_software.json；源码默认 ROUT2=0 dB、OUT1=−6 dB，原候选与正式发布保持不变，下一部署再采用新配置。
