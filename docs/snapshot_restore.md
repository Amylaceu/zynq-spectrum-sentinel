# F0完整快照的范围与恢复

本快照固定100MHz、3.84MSPS的已板测开发基线，不能视为所有竞赛性能指标通过。历史X/Y/Z失败记录保留；不触发重新综合、布线、训练或射频。

## 内容与排除项

- 包含源码、脚本、执行手册、报告、全部现存测量与SHA256、全部data（含合成数据）、模型、vendor/atk、third_party源码和各版本位流。
- 包含只在本机保存的report/results ZIP、build/reports原始报告，以及大于5MiB的原始IQ。F0把93个历史大文件/报告从Git索引移除，磁盘内容仍保留；具体清单为board/measurements/f0_inventory.json。
- 不包含.git元数据/历史、.venv、logs、build/work、SD整卡镜像、Vivado缓存、松散DCP、Python缓存及dist自身。历史证据ZIP保持原字节，不修改其内部内容。
- 因而这是可离线检查源码、数据和既有位流的工作区快照，不是Vivado增量构建环境备份，也不是SD系统备份。历史验收JSON指向build/work或原电脑路径时，不应改写历史哈希；需要重新构建时按源代码重建，但F阶段须遵守事先批准规则。
- 归档根为zss/，SNAPSHOT_MANIFEST.json列出每个文件的长度和SHA256、创建时Git提交号。外部ZIP的SHA256位于同名.sha256；归档自身不可能包含自己的最终哈希或打包后验收记录，它们保存在仓库docs/snapshots.md及board/measurements/f0_acceptance.json。

## 另一台Windows电脑恢复

先将ZIP和同名.sha256复制到目标电脑，校验：

```powershell
Get-FileHash -Algorithm SHA256 <快照完整路径>
```

结果须与.sha256完全一致。使用支持ZIP64的解压工具将归档解到新的短路径目录；或从可信仓库使用以下校验解压命令（目标目录必须尚不存在）：

```powershell
python tools/make_handoff_zip.py <快照完整路径> --extract-to <新目录>
```

进入解压后的zss目录，建议Python3.12 x64（与F0核验环境相同）。首次安装依赖需要网络；完成后PS测试不需要开发板。不要复用另一台电脑的.venv：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest src/ps/tests -q -s
```

F0验收将快照解到本机另一干净目录，用本机现有Python环境验证；不声称已在全新操作系统重新安装全部依赖。Windows采用-s禁用捕获，以规避此前环境的Tcl捕获问题；测试范围不变。

快照不附Git数据库；如需在新设备独立继续版本管理，可在解压目录执行git init并按需创建本地初始提交。third_party为固定版本源码副本，版本以manifest和原验收清单为准，不要直接用submodule update覆盖。此操作不推送GitHub。

板端应用在F1才整理为正式release/v2；F0不宣称sentinel.sh已完成。SD卡仍按docs/antenna_sd_guide.md整卡备份；先正常停止程序并sync/shutdown，确认停机后再断电取卡。

## 快照工具行为

python tools/make_handoff_zip.py dist/zss_snapshot_20261103.zip

不覆盖已存在的ZIP/partial/sidecar，遇到变化中的文件或符号链接则停止。失败的.partial保留供排查；新尝试使用新文件名。大数据流式写入，NPZ/ZIP等已压缩文件不重复高压缩。解压时拒绝路径穿越、重复条目、缺失/多余文件，并逐成员复算SHA256。
