# 完整快照登记

## 2026-11-04 J0 增量检查点

文件：`dist/zss_snapshot_J0_20261104.zip`，1,149,485,552 字节；14,115 个新增或变化文件，未压缩 1,530,877,247 字节。

SHA256：`7150a7e8845bdb36737cfa0b9a6497558fa1c4d0ffacafb85c4262a6f64b9b20`。

已逐成员重新读取 ZIP 并核验长度/SHA256，通过。基线为下节原 F0 完整包
`zss_snapshot_20261103.zip`，基线 ZIP 全文件哈希亦已复核。
恢复必须先解压 F0 到新目录，再覆盖解压 J0 增量；不能单独用增量恢复。
内嵌 `zss/INCREMENTAL_MANIFEST.json` 记录原包名、哈希、每个文件及当前缺失路径。
缺失路径仅作提示，不自动删除恢复目录中的任何文件。

包含 F0 之后的原始 IQ/NPZ、u32、zsr 会话、传输包、当前代码和方案；没有删除源数据。
原始大文件留在本机及归档，小 JSON/SHA256 进入 Git；已经跟踪的历史数据不移除。
排除项沿用完整快照工具：Git历史、虚拟环境、日志、SD整卡镜像、Vivado增量工作目录及DCP。
创建时提交 `361ca6dbdd7a4ea67ab87b2a1386d0350a0f6813`；最终登记、回归摘要和后续提交在归档创建后产生，
不宣称它们包含在这个冻结包中。

外部副本：已复制到用户指定 `E:\zip\zss_snapshot_J0_20261104.zip`，完整 SHA256 与原件相同，
配套 `.json` / `.sha256` 一致。证据 `board/measurements/j0_external_backup.json` 及摘要。
无需用户重复复制；请与原 F0 包一同保留。此归档不是 SD 卡镜像，本轮不要求拔卡或断电。

工具：`tools/make_incremental_snapshot.py`；测试覆盖同长度内容变更、忽略的原始文件恢复、
拒绝覆盖、错误基线哈希与损坏载荷。完整回归使用 Windows 兼容的 `-s` 关闭 Tcl 输出捕获。

## 2026-11-03 F0完成，独立硬盘副本已核验

文件：`dist/zss_snapshot_20261103.zip`

SHA256：`058786e1eb619efc1565c9440582e1cc38684f88ffa931a07f45dc2ad639c4c7`

大小：9,663,493,316字节（约9.66GB）。同时保存同名`.sha256`和`.json`。复制目标需支持大于4GB的文件，例如exFAT/NTFS存储或网盘。

创建时提交：`8b72aeded47e8918c17921396d50854bc54d4f29`。包含14,250个实际文件，未压缩10,094,338,433字节；另含内嵌`zss/SNAPSHOT_MANIFEST.json`。1241个vendor资料文件、9253个第三方源码文件、全部现存数据集、各版位流和测量大文件均已打包。93个此前已跟踪的快照专用文件从索引移除，但本机及归档中原字节均保留。

验证：解压到`dist/F0_restore_20261103/zss`，14,250个文件长度/SHA256全部通过；初始分类的769个文件全部一致。PowerShell Get-FileHash独立复算ZIP哈希一致。解压目录执行`python -m pytest src/ps/tests tools/tests/test_make_handoff_zip.py -q -s`，312 passed（PS309，快照工具3）。使用本机Python3.12.10现有依赖，不宣称全新系统安装验收。

F0前三组提交分别在暂存树独立导出目录通过309项PS测试。第四组只记录验收和修正一个测试文件入库时的换行规范化：`test_v2_clock.py`的工作区原字节未更改，快照也保存原字节。最终提交前再次按同样范围验证，日志`logs/F0_commit4_tests.log`。

验收JSON：`board/measurements/f0_acceptance.json`及SHA256；环境版本：`board/measurements/f0_environment.json`及SHA256；分类：`board/measurements/f0_inventory.json`及SHA256。恢复步骤与排除项见`docs/snapshot_restore.md`。

归档是冻结检查点：它不包含打包后才生成的本登记、最终验收JSON及最终提交，也不包含Git历史、虚拟环境、SD整卡镜像或增量构建目录。不要为加入自身哈希而重新覆盖归档；后续成果在F6生成新的最终交付包。原始证据中的本机build/work路径只作历史追溯，不改写其哈希。

外部备份状态：**PASS**。用户提供`E:\zip`，完整ZIP实测9,663,493,316字节，Get-FileHash复算与上列SHA256一致；`.sha256`一致，缺少的`.json`已补齐。E盘为物理磁盘0（UMIS），原仓库F盘为物理磁盘1（KIOXIA），确为两块不同硬盘。证据`board/measurements/f0_external_backup.json`及SHA256。原f0_acceptance.json保留当时等待人工的历史状态，由本次独立验收补充，不覆盖历史证据。

SD整卡备份：**本次尚未执行**。用户已报告开发板断电；本轮未核实断电前是否执行sync/shutdown，也未连接开发板。保持断电后可取卡接读卡器，须重新核对设备身份再使用Read读取整卡，不能沿用历史盘符；取消Windows格式化或修复提示。不得把本ZIP当作板端系统备份。以后断电前仍须正常停止板端运行并执行`sudo sync && sudo shutdown -h now`。
