# 开源发布说明

- 项目名称：频谱哨兵智能监测终端（Spectrum Sentinel）。
- 仓库：<https://github.com/Amylaceu/zynq-spectrum-sentinel>。
- 维护账号：Amylaceu；项目作者：赵敬泽。
- 首次公开发布整理日期：2026-11-04。

## 发布内容

本仓库公开项目源码、RTL/HLS、约束与构建脚本、测试、设计文档、图表、冻结位流、模型权重及整理后的验收证据。模型权重位于 `src/ps/models/weights/`，随本次项目发布保留。

本次发布使用整理后的独立初始历史，不包含原开发仓库的完整提交历史。已有的失败记录和未达标实测结果保留，功能状态以 README、各阶段验收说明和 `runbook/STATUS.md` 为准。

## 不随仓库分发的内容

- `vendor/atk/` 正点原子资料、原理图及厂商参考包。
- AMD Vivado/Vitis 安装包、许可证和 PYNQ 系统镜像。
- 本地虚拟环境、构建工作目录、运行日志、崩溃转储和交接压缩包。
- 大型合成训练数据及已剔除的现场 Wi-Fi 采集、解码隐私资料。

这些内容不因本项目使用 MIT 许可证而获得新的分发授权。复现者应分别从相应权利方获取所需资料，并遵守各自的许可证。

## 许可证与第三方依赖

项目自有代码按仓库根目录的 MIT 许可证发布。`src/ps/libad9361_pynq/` 派生代码保留 ADI 的原始版权及 BSD-3-Clause 声明；第三方文件适用其各自的许可证。

ADI HDL 与 no-OS 通过 git 子模块引用固定的上游提交，不将其源码复制为本项目自有代码：

| 子模块 | 固定提交 |
|---|---|
| `third_party/hdl` | `b62abeff22d613d08e1aeb7f94850ab6a6576a74` |
| `third_party/no-OS` | `b8f9317a7f426046b9a9004b6c05ae95120fa8fe` |

获取方式：`git submodule update --init --recursive`。

## 硬件与使用边界

当前发布版本面向正点原子 Z20、AD-FMCOMMS3-EBZ 与 J22 SSD1963 8080 LCD。不得把 Z20 引脚约束直接用于 ZedBoard 等其他载板。

保持 J7/J8 为 2.5 V；插拔 FMC 子板前完全断电。设备默认不发射，初始化后 TX 衰减设为 89.75 dB；没有衰减器时禁止用 SMA 电缆直连 TX 与 RX。实际射频操作仍须遵守当地规定和项目运行手册。

此次发布整理未重新综合、实现、生成位流或向 FPGA 下载程序。
