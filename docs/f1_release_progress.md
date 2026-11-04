# F1 发布准备与接续说明

2026-11-03。电脑端工作已完成，板端验收待进行。执行依据为runbook/99_finish.md，基线固定sentinel_v2_100m、100MHz、3.84MSPS。所有历史FAIL保留。

## 已完成

- board/release/config.yaml集中配置：BUS_PHASE=2、RF带宽1.5MHz、95.8MHz电台及96.05MHz LO、音量默认−12dB/上限−6dB、运行上限300秒、TX衰减89.75dB、无开机自启。文件使用JSON格式（YAML子集），板端无需新增YAML依赖。
- tools/release_board.ps1及.py生成相对仓库的发布目录；只有显式传入--deploy/-Deploy才访问板卡。包内含PS源码、模型、脚本和冻结位流；冻结模型与位流哈希检查、Python3.8语法检查均已执行。
- board/scripts/install_release.py校验压缩包、清单和每个成员，持有应用/RF锁后安装到/home/xilinx/sentinel/release/v2。复用原板端已验收.so并校验固定哈希，拒绝静默覆盖现有发布版；显式替换时保留旧目录。
- sentinel.sh统一monitor、listen、selftest、stop、verify入口；demo A/B明确报未实现，留待F2/F3，不冒充已完成。
- 停止通过核验PID身份后发送TERM，等待程序清理，不强制杀死进程；随后要求GPIO/SRC/音频控制读回均严格等于整数0。异常或锁未释放时报告失败，不自动复位或断电。
- 已确认立体声电台启动检查导频；导频突出度不足20dB时显示RF NOISY并保存IQ、实际增益、RSSI及哈希。自检同时要求既有相位/幅度质量检查通过。该判断仅适用于配置中的已确认立体声电台，不能判定所有单声道广播为噪声，也不是物理干扰源定位。
- 音频保持原质量门控，新增20dB导频条件；模拟输出保护范围−45至−6dB、1.5dB步进，非法值在硬件写入前拒绝。尚未实测新的−12dB音量。

## 产物与验证

- 本地发布包：build/releases/f1_offline_checked_20261103/release_v2.tar.gz。
- 包清单：同目录v2/manifest.json及SHA256，87个有效载荷文件；包摘要package.json及SHA256。
- 完整软件回归：563项通过，日志logs/F1_offline_final.xml.log，JUnit为build/releases/f1_offline_tests_final.xml。新增模拟部署边界测试，确认远端安装器哈希不匹配时不会调用特权安装命令。测试中的时序配置字样来自模拟/临时文件测试，不是新FPGA构建。
- 发布日志：logs/F1_package_checked.log。
- 可追溯证据：board/measurements/f1_offline_checked.json及SHA256。
- 代码位置：src/ps/sentinel/release_support.py、board/scripts/release_*.py、board/scripts/install_release.py、tools/release_board.*；针对性测试为src/ps/tests/test_release_f1.py和tools/tests/test_release_board_f1.py。
- 发布包逐项重验：89个归档成员与manifest一致，成员SHA256全部通过；87个是payload文件，其余为manifest和sidecar。代码证据覆盖246个PS/板脚本/工具Python源码哈希。
- 本轮未访问SD原盘、未SSH、未加载位流、未播放音频；离线成功不代表板端selftest或停止读回通过。

## SD读取成功后的接续顺序

1. 等用户确认Read Successful及实际镜像完整路径。运行tools/verify_sd_image.py，使用board/measurements/f0_sd_source.json和新的输出文件名，核对31,266,439,168字节、分区签名及完整SHA256。保留失败镜像和旧X0备份。此检查不能证明文件系统健康或恢复成功。
2. 用户退出读取工具、安全弹出读卡器；确认板卡断电后插卡，连接USB UART和GE_PS。确认配置A（RX1A接20–512MHz、TX1A空、J7/J8=2.5V）。采集启动串口，再上电；不热插卡、不按复位。
3. 核验SSH、启动日志和板端原.so哈希；检查是否存在旧release/v2，不自动覆盖。安装不启动射频。部署后确认包及成员SHA256。
4. 使用PYNQ环境显式运行sudo /home/xilinx/sentinel/release/v2/scripts/sentinel.sh selftest。确认配置A授权有效；结果保存JSON和SHA256。
5. 运行monitor检查显示，再从另一SSH终端运行stop；验证GPIO/SRC/音频均0及日志。运行listen 95.8时需低音量试听，默认−12dB，用户确认音质；测试期间不拔卡或断电。
6. 全部达到F1指标后更新STATUS、提交[F1]，再进入F2。当前不宣称已完成部署、板测或阶段提交。

电脑端重新打包示例（仓库根目录，输出必须为新目录）：

```powershell
./tools/release_board.ps1 -OutputDirectory build/releases/f1_next_package
```

板端就绪并核验接线后再使用同一脚本的-Deploy参数。不要在SD读取期间执行部署或板端命令。
