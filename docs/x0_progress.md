# X0执行记录（2026-11-03）

## 当前验收：DONE

X0最终结果见docs/x0_acceptance_summary.md和board/measurements/x0_acceptance_r2.json。下文均为历史过程，旧BLOCKED/备份读取中记录不覆盖本结果。


## 最新检查点：整卡备份核验通过

用户确认Read完成。整卡31,266,439,168字节；容量/分区签名/SHA256核验PASS，见docs/sd_backup_verification.json及.sha256。尚未恢复供电、SSH或RF；等待安全弹出、断电插回SD、USB UART/GE_PS和配置A确认。恢复后按docs/x0_resume_after_backup.md执行r2默认3档/温度验收。X0仍BLOCKED-HUMAN，不标DONE。X1整体core 18组36864bin逐位比对通过，IP打包完成；整机时序与板测仍待验证。


## 当前结果

- 阶段BLOCKED-HUMAN；配置A已由用户确认，本地Git身份已配置。
- 当前工作目录经Git核实；未在启动时的旧规划目录写入文件。脚本使用相对路径。
- 初始实际14个修改文件、65个未跟踪文件（27个N4测量文件），评审13+7为旧快照。修改前归档logs/X0_before_changes.zip及哈希见docs/x0_baseline_audit.json。
- 40个历史哈希匹配；39个板端文件与本地完全一致，同一boot_id；新读XADC61.397°C。原N4未存完整PS源码清单，不把现在的比对当作追溯到当时的新增证明。
- 58项基线测试通过：logs/X0_baseline_tests_r1.log。N4独立提交9c931d9共74文件，包含已核实代码、报告、位流和测量。
- Git原全局autocrlf=true，仅本仓库设false防止证据换行变动；所有N4暂存字节与快照一致。原始报告的尾部空白不清理，代码空白单独检查通过。
- monitor已默认3，bench和管理员入口本地改为3，RTL复位保持25；bench人工观察阶段增加已有XADC温度读取。未修改telemetry算法，因为它已实现正确数据源且现有测试通过。
- AGENTS、README、HANDOFF和NEXT_AGENT_PROMPT已对齐新主计划和相对路径。

## 尚待完成

- PC测试61项通过且恢复补丁已部署并核验；硬件复测仍待完成。
- 默认3档运行与状态栏温度30–85°C的板测、用户目视确认。
- 安全关机后人工整卡备份；镜像路径、文件大小、SHA256和真实读取方法记录docs/sd_backup.md。
- 所有门禁通过后X0提交，git status干净；之后才开始X1。

## 口径修正（原策划案保留）

- N4的40%是约每秒遥测记录的容量告警比例，不代表全部CFAR帧；X1应同时提供同帧计数定义。
- 3.84MSPS为采样率，N4 RF滤波带宽实际配置1.5MHz，不能记成约3MHz已测通带。
- 98MHz/3.84MSPS不包含95.8MHz；X1容量测试保留98MHz，95.8MHz检出率另在96.4MHz同参数窗口复测并关联旧106条基线。
- ADI内部CDC和IO告警需要路径证据解释，不能无条件声称不影响功能或全部安全。

## 当前阻塞（2026-11-03）

- N4提交后74文件逐个对比初始快照，Git对象字节全部一致；原N4测量哈希仍一致。
- 本地修改后58项测试再次通过，三个软件入口默认3；板端bench和管理员入口更新，4个关键文件SHA256与本地一致。旧管理员入口以.pre-x0-<sha256>保存在原目录，sudoers未改。
- 只读XADC温度61.397°C，后续预检49.216°C，均在30–85°C范围；新截图/目视确认仍待用户。
- 在配置A确认后发送180秒仅接收命令，故意不传phase以验证新默认；SSH发送命令退出0，不代表测试运行成功。取回结果时连接超时，第二次只读检查仍超时。PC以太网192.168.2.10且Link Up，板IP邻居解析未得到MAC；不能据此断定根因。未重复启动测试。
- X0标BLOCKED-HUMAN；先等用户报告LCD/供电/网线状态，再核实板端进程、结果和退出GPIO。测试状态未知时不得让用户拔电/复位/取卡。完整SD镜像仍未取得，不得标X0完成或执行X1。
- 本轮新增审计脚本初版因字符串换行语法失败，第二轮修复并全部通过；后续复核一度未指定UTF-8导致读取失败，已改为UTF-8复核通过，不改变原始数据。

## 启动保护修复与等待串口（2026-11-03）

用户反馈LCD不变、网线和电源仍连接。初次只读文件审计boot_id与N4相同，但启动前预检boot_id已改变，表明其间发生重启；原因和操作人未推断。代理发送monitor时没有显式load-overlay，这是本次启动流程缺口。

本地代码确认SentinelOverlay在MMIO契约检查之前未调用is_loaded，而Session的检查发生在V1构造之后；现已将加载检查放到构造器首次check之前，并在registers/check入口再次检查。新增三项回归证明未加载或已更换位流时不映射寄存器，全套61项通过。另补管理员monitor的--load-overlay显式选项与monitor的硬件访问前原子启动JSON。故障根因仍需板端日志确认，不能把上述缺陷直接认定为本次死机唯一原因。

这些恢复补丁仅在本地，因SSH不可达未部署；此前3档默认与bench温度更新已部署。不要误认board端已有启动保护。恢复后应先只读取得日志/boot_id/活动进程，再传输并核验这些文件；管理员入口更新要校验当前哈希，不盲目覆盖。确认RF锁和系统状态正常后，显式加载已通过哈希验收的位流，再重做本X0板测（轮次r2）。

检测到CH340(COM10)，115200 8N1、DTR/RTS不置位；被动读取5秒只有一个无效字符，发送CRLF后6秒无响应。未发复位、关机、登录口令或寄存器指令。等待用户确认USB UART接线；不擅自硬断电。记录docs/x0_checkpoint.json及SHA256。

## UART人工确认后的第三轮诊断

用户确认USB UART连接正确。COM10在115200 8N1重新读取8秒并仅发送CRLF，0字节有效输出；SSH仍超时。三轮串口诊断到此停止，不无限重试。没有执行断电/复位，无法送达sync/shutdown，不假定Linux已安全停止。已询问是否允许一次应急强制断电重启（说明SD数据损坏风险）或保存现场暂停，等待明确决定。

被动启动日志采集工具tools/capture_uart_passive.ps1已准备，必须显式传入已确认的COM口和新的X0标签。工具不发送任何字符、BREAK、DTR或RTS，拒绝覆盖既有日志；记录原始字节、文本、SHA256。尚未启动恢复，也没有让用户实施断电。恢复后先取回原X0日志/启动信息/文件系统状态，部署本地保护修复并验收前不得重跑射频。

## 重新上电后的恢复与正常关机（2026-11-03）

用户报告已重新上电并重新插拔USB。重新识别CH340(COM10)，串口出现xilinx@pynq提示符，SSH恢复；新boot_id见board/measurements/x0_safe_shutdown_recovery_r1.json。无活动监测/基准/自检程序。启动日志有ext4 recovery complete、systemd日志非正常关闭，以及FAT分区未正常卸载告警；未对已挂载分区运行修复，不宣称SD卡健康。上次X0测试输出及/tmp日志均未找到，无法证实具体死机原因或测试成功。

先归档启动日志、文件哈希和卡容量，再以同目录临时文件+fsync+原子替换部署overlay加载保护和monitor启动JSON；旧文件以内容哈希备份。管理员入口更新前后校验旧/新SHA256，保留旧入口备份，sudoers不变。关键三文件哈希和板端py_compile通过，helper health确认不触碰硬件。未加载位流、未操作RF，也未重跑测试。

确认无监测进程后执行sudo sync && sudo shutdown -h now；COM10被动日志实录reboot: System halted和/boot卸载完成。SSH断开是关机过程，完成证据是串口终止标记。板端现已正常停止，可让用户断电取卡。等待用户接读卡器或提供整卡镜像路径，X0仍BLOCKED-HUMAN，X1不启动。恢复与关机证据board/measurements/x0_safe_shutdown_recovery_r1.json及.sha256。

SD读出容量31,266,439,168字节（约29.1GiB）；整卡镜像应覆盖整个设备而非只复制启动分区。没有镜像之前不能记录备份PASS。完成备份后才恢复供电、重做默认3档和温度目视验收。


## 最新检查点：SD已接读卡器（2026-11-03）

用户已确认断电、SD已接读卡器。再次核验目标为Disk 3 / H: PYNQ / USB序列号121220160204 / 容量31,266,439,168字节；G:是另一只U盘，不选择。详细身份见docs/x0_sd_source.json及.sha256；重插拔后须重新枚举。目标build/sd_boot_backup/zss_sd_20261103_full.img尚不存在。工具命令行下载三轮超时后停止，用户回复“没有工具，我用浏览器下载”。等待用户完成整卡Read，不假定备份成功，不向已关机板发送SSH。确认Read完成后再运行tools/verify_sd_image.py --confirm-read-complete，记录logs/X0_sd_image_verify_r1.log；该工具仅语法检查通过，尚未验证真实镜像。X0仍BLOCKED-HUMAN，X1未开始。

## 最新进展：读取中与离线准备（2026-11-03）

用户确认“SD仍在读卡器，继续读取，暂不上电”。Win32DiskImager正在读取；目前镜像只有部分数据，尚未做真实镜像SHA256或标PASS。电脑端新增14项合成镜像校验测试，连同原61项PS回归共75项通过，证据docs/x0_offline_preparation.json及.sha256。已整理docs/x0_resume_after_backup.md（5段PowerShell语法校验通过，命令未执行）和docs/x1_interface_preparation.md（只做接口预研，X1未实现/构建/板测）。不影响源SD，不执行SSH或RF；读取成功后先校验镜像，再恢复X0板测。

## 用户授权并行推进X1（2026-11-03）

用户明确要求先推进后续任务，现已允许X0备份等待与X1电脑端开发并行；板测/部署仍等待X0门槛。新增独立cfar_x1黄金模型、新版本寄存器契约、驱动和cluster RTL，旧v1运行链不变。140项离线测试通过，20组cluster仿真和323条128位目标记录独立比对零差异，证据sim/results/x1_cluster_r1_acceptance.json及.sha256。独立150MHz OOC进行中，不能声称整机或板测通过。恢复时先阅读docs/cfar_x1_contract.md，再按X0恢复清单收口。环境脚本tools/env.ps1已修复：自动探测仅固定磁盘，避免读取期间探测H盘导致Access denied。

## X1离线工作最新验收（2026-11-03）

用户授权备份期间推进PC端：已完成独立X1黄金模型、寄存器契约及生成常量、新版本驱动、聚类RTL和20组仿真。完整离线回归215项通过，323条128位目标记录逐位一致。150MHz独立OOC：LUT3846、FF6747、BRAM0、DSP0，WNS+0.067ns、内部hold+0.147ns，但总体WHS=-0.419ns/269个hold失败端点，因此验收为FAIL，不能引用原脚本PASS作为时序通过；已修正脚本并保留原始报告/执行脚本。整机接入、时序闭合、板测仍未完成。所有证据见docs/x1_offline_progress.json及.sha256，X0仍等待SD读取成功。无SSH/射频/板端部署，不提交未完成阶段。
