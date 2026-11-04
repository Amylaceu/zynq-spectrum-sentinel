# 第三方 HDL / 驱动源码

本目录不包含第三方源码，克隆后用子模块恢复（提交号固定在仓库中）：

```bash
git submodule update --init --recursive
```

| 子模块 | 上游 | 用途 |
|---|---|---|
| `hdl/` | <https://github.com/analogdevicesinc/hdl.git>（分支 `hdl_2026_r1`） | ADI HDL 库、FMCOMMS2/3 工程与 IP |
| `no-OS/` | <https://github.com/analogdevicesinc/no-OS.git> | ADI 驱动源码（AD9361 等） |

固定提交：

| 子模块 | 提交 |
|---|---|
| `hdl` | `b62abeff22d613d08e1aeb7f94850ab6a6576a74` |
| `no-OS` | `b8f9317a7f426046b9a9004b6c05ae95120fa8fe` |

两份源码均为 ADI BSD 授权，未在本仓库中修改；本项目的改动放在 `src/hw/` 覆盖层与本仓库自己的 RTL/软件中。
