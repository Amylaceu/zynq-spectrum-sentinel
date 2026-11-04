# X0：备份完成后的恢复清单

状态：本次恢复已执行并通过；本文保留执行清单，证据见docs/x0_acceptance_summary.md。不要重跑r2覆盖结果。PC命令在已核实的仓库根目录执行。
用户已确认插卡和上电，180秒复测完成，接收已退出；开发板保持供电。

## 1. 确认读取成功并校验

读取期间不拔卡、不插回开发板、不对增长中的镜像做完整哈希。
必须取得用户“读取成功”确认；文件达到预期大小不能代替成功提示。
原卡容量31,266,439,168字节，身份见docs/x0_sd_source.json。
H:只是最近盘符，重插拔后必须重新核对。

~~~powershell
$source = Get-Content docs/x0_sd_source.json -Raw | ConvertFrom-Json
$imagePath = Join-Path (Get-Location) $source.image_relative_path
Get-Item -LiteralPath $imagePath | Select-Object FullName,Length,LastWriteTime
# 用户确认完成后，代理在后台执行。输出存在时使用新轮次，禁止覆盖。
./.venv/Scripts/python.exe tools/verify_sd_image.py --image $imagePath --confirm-read-complete --out docs/sd_backup_verification.json *> logs/X0_sd_image_verify_r1.log
if ($LASTEXITCODE -ne 0) { throw 'SD image verification failed' }
~~~

核对PASS、容量、分区和完整SHA256，以及JSON自身的.sha256。
更新docs/sd_backup.md和检查点；镜像继续Git忽略。
这不是文件系统修复或恢复演练通过的证明。

## 2. 人工恢复供电

👤 校验结束后退出读取工具、安全弹出读卡器；板子断电状态下插回SD。
配置A：RX1A接粗长20–512MHz天线，TX1A空，J22屏幕、J7/J8=2.5V。
用户确认实际连接后才能射频。先准备被动串口采集，再请用户上电。

~~~powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID,Name
# 核实端口后填写$port，不能盲用历史COM10；后台运行，ready后再上电。
./tools/capture_uart_passive.ps1 -Port $port -Seconds 120 -Tag X0_backup_return_boot_r1
~~~

## 3. 只读预检

~~~powershell
$facts = @{}
foreach ($line in Get-Content docs/board_info.md) {
    if ($line -match '^([a-z_]+)=(.*)$') { $facts[$matches[1]] = $matches[2].Trim() }
}
if ($facts.board_ip -notmatch '^\d{1,3}(\.\d{1,3}){3}$' -or $facts.board_user -notmatch '^[a-z_][a-z0-9_-]*$') { throw 'Invalid board facts' }
$target = "$($facts.board_user)@$($facts.board_ip)"
$sshOptions = @('-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','ConnectTimeout=8')
& ssh @sshOptions $target 'cat /proc/sys/kernel/random/boot_id; uptime; ps -eo pid,args'
if ($LASTEXITCODE -ne 0) { throw 'SSH preflight failed' }
& ssh @sshOptions $target 'sudo -n /usr/local/sbin/zss-n4-admin health'
& ssh @sshOptions $target 'sha256sum /usr/local/sbin/zss-n4-admin /home/xilinx/sentinel/ps/sentinel/overlay.py /home/xilinx/sentinel/ps/sentinel/app/monitor.py'
~~~

- 保存新boot_id、PC时间和启动日志；检查文件系统/启动错误。
- 对照board/measurements/x0_recovery_deployment_r1.json核验三个部署文件。
- 确认无活动monitor/bench/selftest，无其他硬件控制者；状态未知不重复启动。
- health不访问硬件。不要先映射自定义MMIO，默认位流不等同于sentinel_v1。

## 4. X0默认3档与温度复测

前置：备份PASS、启动/SSH正常、部署一致、配置A已确认、无活动测试。
原r1结果缺失，保留故障记录；本轮使用r2，不覆盖旧证据。

~~~powershell
# 由代理后台运行；故意不传--phase以验证默认3。首次恢复显式加载。
./tools/board.ps1 -Cmd run -Arg 'sudo -n /usr/local/sbin/zss-n4-admin monitor --source rf --lo 96400000 --rate 3840000 --seconds 180 --load-overlay --tag x0_default_temp_r2' *> logs/X0_default_temp_r2.log
~~~

检查启动JSON，不能只凭SSH命令发出判为通过。👤 请用户观察FRAME增长、
SOC TEMP在30–85°C、无明显花屏/错点；目视确认与机器遥测分别记录。
结束后仅拉取本轮JSON，不覆盖整个测量目录：

~~~powershell
$remoteResult = '/home/xilinx/sentinel/measurements/n4_monitor_x0_default_temp_r2.json'
$localResult = 'board/measurements/n4_monitor_x0_default_temp_r2.json'
if (Test-Path $localResult) { throw 'Preserve prior evidence; choose new tag' }
& scp @sshOptions ('{0}:{1}' -f $target,$remoteResult) $localResult
if ($LASTEXITCODE -ne 0) { throw 'Result pull failed' }
Get-FileHash $localResult -Algorithm SHA256
~~~

核对completed、非信号提前停止、bus_phase=3、实际3.84MSPS、完整约180秒；
温度30–85°C、TX89.75dB、RSSI安全、溢出和帧计数；保存JSON/SHA256、退出证据。
列表容量告警归X1优化，不等同ADC溢出。全部X0门槛通过才标DONE和提交。
X1预研见docs/x1_interface_preparation.md，之后仍须配置A确认和按序执行。
