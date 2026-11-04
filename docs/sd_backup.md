# SD整卡备份记录

## 最新：F3备份重试 / G0恢复校验通过（2026-11-04）

- 文件：`E:\zip\zss_sd_backup_20261104_retry2`（原文件无扩展名，保留原名）。
- 整卡长度：31,266,439,168字节。
- SHA256：`ca4bac9ce83f3373420e54ed7cdfa3f3130859211c22c007d725fd85c8476f94`；镜像旁已生成同名`.sha256`。
- 用户明确确认Read成功、SD插回板卡、已上电且配置A正确。核验复用同一卡F0容量/分区身份记录，没有从已回板的源卡重新读取容量。
- MBR布局、FAT/ext签名、全文件哈希及核验期间大小/修改时间一致性通过。证据 `board/measurements/g0_sd_retry2_verified.json` 及SHA256，日志 `logs/G0_sd_retry2_verify.log`。
- 正式selftest及安全停止读回PASS，详见 `board/measurements/g0_acceptance.json`；不会覆盖历史成功或失败镜像。
- 未做恢复演练、文件系统健康检查；结构和SHA256通过不表示已证明无损恢复。镜像含系统及密钥，仅本地保存，不提交或发布。

备份已完成，本轮保持板卡上电推进G1；G5结束后再提醒整卡备份。下文均为历史记录。

## SD整卡读取成功后的最新检查点

用户已确认读取成功。E盘zip目录下 zss_sd_F0_retry1.img 已完成校验：31,266,439,168字节，分区布局、FAT/ext签名及完整SHA256通过；核验期间镜像未变。证据 board/measurements/f0_sd_retry1_verified.json 及.sha256，日志 logs/F0_sd_retry1_verify.log。失败的旧镜像和X0备份保留。没有访问源SD或板卡；未做恢复演练或文件系统健康检查。下一步等待用户安全弹出、确认板卡断电后插卡、配置A接线就绪；先不开机，准备串口采集后再通知上电。F1仍DOING，部署、自检、停止读回及−12dB试听待执行。

镜像完整SHA256：`3c2ac43c27b8fdf8468b8bee01c0385259bbde7bd1f3d7580316a4564bef67dc`。镜像旁已保存同名.sha256，不提交镜像。


## F0读取失败后重试（2026-11-03，当前）

用户报告首轮Read报错，错误代码未保留。只读核对E:\zip\zss_sd_F0_full.img为9,028,239,360字节，小于源卡31,266,439,168字节，不能当作完整备份。E:仍有约112GB空间，尚无证据确定故障原因；H: PYNQ健康Warning仍在，不能单凭此判定卡坏。旧X0完整镜像及其验收记录保留，未覆盖。

用户确认SD仍在读卡器，开发板是取出SD后才上电。已提示关闭无卡板卡、不要热插卡；尚未收到断电确认。建议换USB口/读卡器后使用新文件名E:\zip\zss_sd_F0_retry1.img重试Read；用户最新报告正在读取，实际新镜像路径及成功结果仍待确认。禁止Write、格式化或扫描修复，不向部分镜像续写。本轮未访问源SD，也未SSH或板测；用户授权继续F1电脑端工作，详见docs/f1_release_progress.md。

用户确认Read Successful后，再核实实际镜像路径，用tools/verify_sd_image.py和board/measurements/f0_sd_source.json生成新的验收JSON及SHA256。不要覆盖旧验收证据。下文“尚未启动读取/目标不存在”仅为此前记录。

## F0新增备份：等待人工Read（不覆盖下方X0历史镜像）

用户已确认开发板断电、SD卡接读卡器。本轮重新枚举：Disk3，USB Mass Storage Device，序列号121220160204，整卡31,266,439,168字节；启动分区H:、卷标PYNQ，第二分区为Linux。G:为另一只约64GB闪存盘，不是目标SD。源身份记录：board/measurements/f0_sd_source.json及SHA256。

Win32 Disk Imager：Device选H:，Image File填E:\zip\zss_sd_F0_full.img；取消Read Only Allocated Partitions（如有），点击Read。目标镜像当前不存在，E盘可用空间超过121GB，足够存储整卡；不覆盖旧X0镜像。读取完成前保持读卡器连接，不上电、不取卡；Windows格式化/修复提示取消。当前FAT卷报告Warning，保留此事实，不主动修复，也不据此认定整卡损坏；镜像与文件系统健康须分开判断。

本次尚未启动读取或验证新镜像；等待用户确认Read成功后执行tools/verify_sd_image.py，使用新的source-record和输出路径，避免覆盖历史证据。断电前关机过程本轮未验证。

## X0历史备份（不代表F0新镜像完成）

历史状态：PASS（整卡镜像大小、分区签名与SHA256核验通过）。用户当时已确认Read完成、安全弹出和断电插卡，恢复上板并通过X0复测。

| 项目 | 值 |
|---|---|
| 镜像 | `build/sd_boot_backup/zss_sd_20261103_full.img` |
| 大小 | 31,266,439,168 字节（整卡） |
| SHA256 | `23d0c3b936df87745aab7b8700c691c020bcd0792b2d0b149c4b0018317b5e80` |
| 读取方法 | Win32 Disk Imager：Read整卡，用户确认完成 |
| 核验时间 | 2026-11-03T01:24:09.166847+08:00 |
| 核验范围 | 容量、MBR分区布局、FAT/ext签名、完整SHA256；哈希期间镜像大小和修改时间未变 |
| 核验记录 | `docs/sd_backup_verification.json`及`.sha256` |
| 日志 | `logs/X0_sd_image_verify_r1.log` |
| 恢复演练 / 文件系统健康 | 均未验证；不将备份PASS表述为无损健康镜像 |

镜像已确认Git忽略；含系统与密钥，仅本地保存，不提交或发布。X0默认BUS_PHASE=3、温度板测及目视确认已通过，见docs/x0_acceptance_summary.md。

## 历史记录（以下为原时点状态，不覆盖当前状态）

# SD整卡备份记录

状态：PENDING-HUMAN（2026-11-03）；尚未备份，不得视为X0完成。

待按docs/antenna_sd_guide.md第3.3节完成：确认无活动测试，执行sudo sync && sudo shutdown -h now，确认系统停止后断电取卡，用读卡器和Win32 Disk Imager的Read读取整卡。不要Write、格式化或Windows修复。镜像保存在PC磁盘而非SD卡。

完成后用户提供镜像完整路径；代理计算整文件SHA256，记录文件大小、时间、读取方式、卡容量及操作者确认。不要把只含FAT启动分区的文件拷贝当作整卡镜像。镜像含SSH密钥等本机数据，保存在本地备份目录且不提交Git。

| 项目 | 值 |
|---|---|
| 镜像路径 | 计划：`build/sd_boot_backup/zss_sd_20261103_full.img`（尚不存在） |
| 文件大小 | 待核验 |
| SHA256 | 待计算 |
| Read整卡完成 | 待用户确认 |
| 恢复验证 | 未执行 |

## 本次备份前状态

2026-11-03已通过SSH完成sudo sync && sudo shutdown -h now，COM10捕获reboot: System halted；当前可以断电取卡。证据board/measurements/x0_safe_shutdown_recovery_r1.json。SD设备mmcblk0报告31,266,439,168字节，含FAT启动分区和ext4根分区。启动前存在未正常卸载/日志恢复告警，所以此备份是恢复点，不是已验证无损的健康镜像。镜像及其SHA256仍待生成；恢复测试未做。


## 最新检查点：SD已接读卡器（2026-11-03）

用户已确认断电、SD已接读卡器。再次核验目标为Disk 3 / H: PYNQ / USB序列号121220160204 / 容量31,266,439,168字节；G:是另一只U盘，不选择。详细身份见docs/x0_sd_source.json及.sha256；重插拔后须重新枚举。目标build/sd_boot_backup/zss_sd_20261103_full.img尚不存在。工具命令行下载三轮超时后停止，用户回复“没有工具，我用浏览器下载”。等待用户完成整卡Read，不假定备份成功，不向已关机板发送SSH。确认Read完成后再运行tools/verify_sd_image.py --confirm-read-complete，记录logs/X0_sd_image_verify_r1.log；该工具仅语法检查通过，尚未验证真实镜像。X0仍BLOCKED-HUMAN，X1未开始。

## 最新进展：读取中与离线准备（2026-11-03）

用户确认“SD仍在读卡器，继续读取，暂不上电”。Win32DiskImager正在读取；目前镜像只有部分数据，尚未做真实镜像SHA256或标PASS。电脑端新增14项合成镜像校验测试，连同原61项PS回归共75项通过，证据docs/x0_offline_preparation.json及.sha256。已整理docs/x0_resume_after_backup.md（5段PowerShell语法校验通过，命令未执行）和docs/x1_interface_preparation.md（只做接口预研，X1未实现/构建/板测）。不影响源SD，不执行SSH或RF；读取成功后先校验镜像，再恢复X0板测。
