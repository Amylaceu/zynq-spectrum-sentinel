# 第三方版权与许可证声明

仓库根目录 `LICENSE` 的 MIT 许可证适用于本项目自有代码，不替代第三方模块、派生文件、工具或生成产物原有的许可条件。

## Analog Devices no-OS

`src/ps/libad9361_pynq/app/z20_init_param.c` 派生自 ADI AD9361 示例初始化表，保留文件中的原版权声明：

> Copyright 2013(c) Analog Devices, Inc.
>
> SPDX-License-Identifier: BSD-3-Clause

其他派生内容的作者和年份以各文件头为准。BSD 条件及免责声明随本仓库分发，见 [ADI-no-OS-BSD.txt](LICENSES/ADI-no-OS-BSD.txt)。这份许可文本按固定 no-OS 提交的 `LICENSE_BSD` 原样保存，其中的 2026 年份不替代派生源文件已有的 2013 年份。

上游：<https://github.com/analogdevicesinc/no-OS/tree/b8f9317a7f426046b9a9004b6c05ae95120fa8fe>。

## Analog Devices HDL

ADI HDL 不是统一的 MIT/BSD 许可代码库。各模块可能适用不同许可证，具体以模块源文件和上游许可文件为准；多数 ADI 模块提供 ADI BSD / GPL v2 双重许可。

- [上游许可证总说明](LICENSES/ADI-HDL-license-overview.txt)。
- [ADI HDL BSD 许可原文](LICENSES/ADI-HDL-BSD.txt)。该许可包含与 ADI 器件连接使用的条件，不应当作无条件的通用 BSD 许可。

本项目面向 AD9361（Analog Devices 器件）。随仓库提供的冻结位流包含上游 HDL 与 AMD 工具/IP 生成内容，其使用及再分发不能仅依据本项目 MIT 许可证判断。复现或移植时应核对实际采用模块的文件头及工具/IP 条款。

上游：<https://github.com/analogdevicesinc/hdl/tree/b62abeff22d613d08e1aeb7f94850ab6a6576a74>。

## 其他依赖与厂商资料

PYNQ、NumPy、SciPy、PyTorch 等依赖均适用各自许可证；安装依赖不改变其许可。AMD Vivado/Vitis、厂商 IP、正点原子资料盘及 PYNQ 系统镜像不因本项目 MIT 许可而获得额外的分发授权。

正点原子 `vendor/atk/` 参考包未随本仓库分发。相关原理图及厂商资料应通过其合法渠道自行获取。
