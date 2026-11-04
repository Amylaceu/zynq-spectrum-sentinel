# P5.2 基础驱动当前范围

已实现Python3.8兼容的MMIO、Overlay校验、Xilinx simple DMA和ADI simple DMAC封装，以及base自检入口。PC端11项测试覆盖：小端/边界、产物时间/哈希、未知自研IP拒绝、版本和scratch恢复、DMA地址边界、提交/完成次序、超时及未完成缓冲区保留。

## 已核实的寄存器契约

手册给出的ADI IRQ_PENDING=0x80不正确。本仓库固定版本的HDL axi_dmac_regmap.v：字地址0x020是IRQ_MASK（字节0x80），0x021是IRQ_PENDING（字节0x84）；no-OS axi_dmac.h同样定义0x84。使用TRANSFER_ID=0x404、SUBMIT=0x408、FLAGS=0x40C、DEST=0x410、SRC=0x414、X_LENGTH=0x418、DONE=0x428。

驱动只支持本项目32位地址、非SG、单次传输。长度寄存器写n_bytes-1；先确认请求已接受，再读取当前transfer ID的完成位，避免误用上一次完成标志。遇到超时或Xilinx错误，停止控制器并保留分配内存；不能在硬件可能仍写内存时释放。异常缓冲区保留在模块隔离区，尚未实现自动硬件复位/回收接口。

## 板端实际验证

`python3 -m sentinel.selftest --stage base --reuse --read-only`已在实际PYNQ解释器执行并通过；不重新下载、不初始化RF、不写GPIO或启动DMA。SYSID=0x10161，AD9361接口核版本=0xA0300，SPI状态=0x25，GPIO=0。见board/measurements/p5_base_selftest_readonly.json。

初轮时间检查正确拒绝了原始生成时间差超过60秒的bit/HWH。它们来自同一次已验证构建，但HWH生成早于实现完成。收集器现保留原始时间和SHA256到provenance.json，并给同一导出集设置统一打包时间。重新收集前后三项bit/HWH/XSA字节哈希相同，未重建或更换逻辑；第二轮板端自检通过。

## 尚未完成

- 没有把PC模拟DMA测试当作板端数据传输验收。
- 本次有AD9361插着，按手册不插射频的完整写入验收前置条件，板端只跑read-only。GPIO bit15写入/恢复仅已模拟验证；此位在基础顶层未接外部管脚。
- 未来自研IP的VERSION/SCRATCH契约需由P3寄存器生成器提供。没有契约时主动拒绝，不能略过未知IP或声称全系统检查通过。
- RF控制库、应用层各模块及真实DMAC数据搬运尚未实现/验收，因此P5.2仍为进行中。
- 旧vendor DMA/LCD组合测试的网络中断原因仍未确定；没有因为新base只读自检成功而将旧测试改为通过。

## 后续实际ADI RX DMA验收（2026-11-02）

在联合RF/LCD位流上，18项PS测试通过；内部RX BIST音通过ADI DMA连续取得4×64KB，两个接收通道均为960kHz且复数主频能量比例>99.999%，首尾64字节边界未变，测试后RF复位、无在途缓冲区。见docs/rx_bist_dma_acceptance.md。此结果更新前文的“未运行ADI DMA”历史状态，不替代旧vendor DMA回环、自研IP契约或持续RF采集验收。

分配所有权更新：已按实际PYNQ2.7 XRT cache/pointer协议添加cma.py并作为DMA默认分配器；实际三轮1MiB分配/释放及16次8MiB接收复用地址验证通过。首轮立即读取CmaFree的验收时机不当，删除NumPy owner/GC后复验通过。未改第三方/系统文件，不推断早前网络中断原因。
