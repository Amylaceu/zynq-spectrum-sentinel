# ADI 依赖版本（P0.6 已验收）

日期：2026-11-01。主机 Vivado：2025.2。

| 依赖 | 官方来源 | 分支 | 已检出并登记的提交 |
|---|---|---|---|
| HDL | https://github.com/analogdevicesinc/hdl.git | `hdl_2026_r1` | `b62abeff22d613d08e1aeb7f94850ab6a6576a74` |
| no-OS | https://github.com/analogdevicesinc/no-OS.git | `main` | `b8f9317a7f426046b9a9004b6c05ae95120fa8fe` |

HDL 的本地 `scripts/adi_env.tcl` 声明 `required_vivado_version "2025.1"`。按本项目手册使用 Vivado 2025.2，并由 `tools/env.ps1` 设置 `ADI_IGNORE_VERSION_CHECK=1`；尚未进行 IP 升级、编译或工程移植，不代表这些构建步骤已验收。

## 验收

- `.gitmodules` 登记的是上述官方来源；父仓库用 gitlink 固定版本。
- `projects/fmcomms2/zed/system_bd.tcl`、`library/axi_ad9361` 和 no-OS 的 `drivers/rf-transceiver/ad9361` 均存在。
- 已执行 no-OS 的 `git submodule update --init --recursive --depth 1`，退出码为 0；递归状态无待初始化或错位项。
- HDL、no-OS 的 `git status --porcelain` 均为空；没有修改第三方源码。
- 当前为浅克隆，保留当前提交；需要历史版本时再显式 fetch，不应假定本地具有全部历史。

## 故障与恢复

最初官方 GitHub TLS EOF、备用镜像超时；改用当前进程的 Windows TLS 后端及 HTTP/1.1 后，官方查询和下载成功。TLS 证书验证保持开启，未改变全局 Git 网络设置。

第一次 `submodule add --depth 1 -b hdl_2026_r1` 只取了 main，目标分支检出失败；保留现场暂停。用户要求继续后，显式 fetch 所需分支至 `origin/hdl_2026_r1`，检出该分支，再将现有仓库登记为子模块。未删除目录，未把 main 误作为本项目 HDL 版本。

过程日志：`logs/P0.6.log`（本机保留，不加入 Git）。
