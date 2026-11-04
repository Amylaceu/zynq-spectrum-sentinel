# 本机工具检查（P0.1）

检查日期：2026-11-01。实际项目根目录为 `D:\FPGA\ZSS\zss`。
本文件记录本机探测结果；后续构建脚本必须使用环境变量或相对路径，不应复制这些绝对路径作为固定配置。

## 已验证工具

| 项目 | 结果 | 验证方式 / 路径 |
|---|---|---|
| Git | 2.53.0.windows.2，满足 >=2.40 | `git --version`；`D:\1111\Git\cmd\git.exe` |
| 默认 Python | 3.13.1，不符合项目 3.10–3.12 要求 | `python --version`；`D:\Scripts\python.exe` |
| 项目选用 Python | 3.12.10，符合要求 | `py -0p` 发现；`D:\数学建模\工具\Python312\python.exe`；仅在本次验收子进程中调整 PATH 后验证 `python --version` |
| SSH | OpenSSH_for_Windows_9.5p2 | `ssh -V`；Windows 自带客户端 |
| Vivado | 2025.2，SW Build 6299465 | `D:\FPGA\AMD_2025\2025.2\Vivado\bin\vivado.bat -version` |
| Z20 器件 | `xc7z020clg484-2` 可用 | Vivado Tcl `get_parts -quiet xc7z020clg484-2`，返回唯一器件 |
| Vitis HLS 命令入口 | 可运行 | `D:\FPGA\AMD_2025\2025.2\Vitis\bin\vitis-run.bat --help`，退出码 0；未进行 HLS 编译 |
| XSCT | 2025.2.0，可运行 | `D:\FPGA\2025.2\Vitis\bin\xsct.bat` 执行仅打印标识并退出的 Tcl，退出码 0；未连接硬件 |
| xsim | 启动文件存在 | 与 Vivado 同目录的 `xsim.bat`；本步骤未运行设计仿真 |
| CH340 | COM5，状态 OK | Windows PnP 查询；未打开串口 |
| 已有 JTAG 下载器 | USB Serial Converter，状态 OK | Windows PnP 查询；未连接、编程或复位 FPGA |
| 7-Zip | 26.05 x64，可运行 | `D:\7zip\7-Zip\7z.exe`；信息查询、创建及解压测试均退出 0，解压文件 SHA256 与原文件一致 |
| MobaXterm Portable | 26.6.0.5560，已解压并找到程序 | `D:\MobaXterm\Portable_v26.6\MobaXterm_Personal_26.6.exe`；未启动界面或连接串口 |
| balenaEtcher | 2.1.9，已人工安装 | `C:\Users\<your-name>\AppData\Local\balena_etcher\balenaEtcher.exe`；注册信息及文件版本一致，用户截图确认界面已打开 |
| vendor/atk | 目录存在 | 尚未执行 P0.7 的逐项资料校验 |

## 环境注意事项

- runbook 列出的默认 Vivado 搜索目录没有覆盖这台电脑的实际安装位置。本次增加了对 FPGA 工作目录的有限深度探测，没有安装新版本工具。
- 原安装根目录 `D:\FPGA\AMD_2025\2025.2` 提供 Vivado 和 `vitis-run`，其中没有 `Vitis\bin\xsct.bat`。已在另一套同版本安装中找到并实际运行 XSCT。P0.4 必须处理这个安装目录差异，不能仅拼接一个根目录就假定所有工具存在。
- 本次 Python 3.12 的选择只在检查子进程中生效，没有修改系统 PATH，也没有提前创建 P0.4 的环境脚本或 P0.5 的虚拟环境。
- 内存约 15.7 GiB；检查时 C 盘可用约 80.7 GiB，D 盘约 279.9 GiB。
- P0.4 环境脚本已验收通过：自动发现匹配版本的安装路径，选用 Python 3.12，支持重复加载；实际 Vivado Tcl 查询版本和 Z20 器件库、XSCT 运行均退出 0。仅查询版本的命令在本机原版 loader.bat 第 549–551 行明确返回 1，最初将其判为启动故障是验收脚本错误，现已纠正。后续自动构建仍须检查实际运行退出码与验收标识，不能无条件忽略非零退出。

加载方式：在 PowerShell 执行 `. ./tools/env.ps1`。`XILINX_ROOT` 指向 Vivado 的版本目录；`VITIS_ROOT`、`XSCT_ROOT` 可指向不同的同版本安装目录；可用 `ZSS_PYTHON` 指定受支持的 Python 可执行文件。所有设置仅对当前进程生效。

## P0.5 Python 隔离环境

- 项目 `.venv`：Python 3.12.10；NumPy 2.1.3、SciPy 1.18.1、PyTorch 2.10.0+cpu、SigMF 1.14.0、PyYAML 6.0.3、PyMuPDF 2.0。
- `requirements.txt`、`requirements-board.txt` 按手册生成；板端依赖尚未安装。`tools/env.ps1` 会自动激活项目 `.venv`，不修改系统 Python。
- 首轮最新 CPU wheel 元数据重定向到 download-r2.pytorch.org，TLS EOF；第二轮改用可达的官方 2.10.0 CPU cp312 Windows wheel，并校验 SHA256 `21cb5436978ef47c823b7a813ff0f8c2892e266cfe0f1d944879b5fba81bf4e1`。保持 TLS 证书验证，没有使用 trusted-host 或跳过证书校验。
- 验收：手册的核心包导入全部通过，确认运行在隔离环境且 `torch.version.cuda is None`，`pip check` 无依赖冲突，环境脚本激活后的 Python 指向 `.venv`。
- 全部实际安装版本在本机 `logs/p0_5_installed.txt`；过程及验收在 `logs/P0.5.log`，均不加入 Git。PyMuPDF 的旧 `fitz` 导入仍成功但有弃用提示，后续新代码优先使用 `pymupdf`。

## 安装跟进

- 7-Zip 已解决：用户提供新安装位置后，在 `D:\7zip\7-Zip\` 验证 26.05 x64 可运行并可正确解压。此前开始菜单快捷方式仍指向已缺失的旧目录，不作为新安装的调用入口。
- balenaEtcher 已由用户安装并提供主界面截图，安装路径、文件版本和卸载注册信息已核实。MobaXterm Portable 已解压，程序版本信息可读；串口通信留待 P0.8 板端准备时验收。
- 初始交接目录无 `.git`；P0.2 已使用用户提供身份配置 Git，并读回核验姓名、邮箱、长路径和换行设置。具体身份不抄入本文件。P0.3 已初始化 main 仓库并补交检查记录。

## 验收与日志

- `runbook/00_env.md` P0.1 列出的核心验收项（Git、Python 3.10–3.12、SSH、Vivado）全部通过。
- 原缺失的辅助工具已补齐，P0.1 验收通过；因交接目录最初没有 Git 元数据，提交在按顺序完成 P0.2 配置、P0.3 初始化后补交。
- 后台检查日志：`logs/P0.1.log`，扩展记录 `logs/P0.1_extended.log`，Vivado 器件库记录 `logs/P0.1_vivado.log`。
- 机器可读结果：`logs/p0_1_tools.json`、`logs/p0_1_extended.json`。
- 未进行任何射频操作、位流下载、跳帽调整、模型训练或第三方库编译；`third_party/` 和 `vendor/atk/` 未修改。
