# 100 MHz 开发审计与音频接口修复

状态：r2局部布线完成，PC开发审计通过；仅签发非负裕量开发收据，不代表上板、听音或Z10原指标通过。

## 授权与可追溯性

用户已允许开发门槛 WNS/WHS≥0；+1 ns 是后续优化目标，Z10/T5 原 FAIL 不改。配置 A 已确认，当前仅允许接收。原代码与位流已备份到仓库同级 `backup_before_inplace_20261103_175628`，含工作树、Git bundle、差异与逐文件哈希。原 T5 实现输入在修改约束前重新验证通过。

只读审计 `audit_development_r2`：WNS +0.210 ns、WHS +0.030 ns，TNS/THS=0；无内部未约束端点、无多重时钟、无黑盒。PC 软件回归495项通过。部署规则的33项新增检查覆盖显式授权、review完整性、产物绑定、负裕量/非有限数拒绝，不能靠修改policy字符串绕过检查。

## CDC 逐组结论与运行条件

- CDC-1 110项以及DMA的CDC-13 24项：ADI请求FIFO/传输结束标记RAM。`util_axis_fifo.v`零深度异步分支通过双向地址toggle握手保持payload，`request_arb.v`的EOT按请求ID保留，ID通过`sync_gray.v`同步；有效约束导出中存在相应datapath max-delay。不能按多位总线逐位打拍修改它们。
- divclk的CDC-13两项：ADI BUFGMUX选择信号，仅允许停止采集/初始化期间改变1R1T和接口模式；运行中不改。不得直接把两种分频输出当作一个时钟。
- CDC-10两项ADC复位：OR请求进入三层XPM异步置位/同步释放，FIFO复位再由ADC域三层同步产生；旧普通D端复位旁路为0。断言可能异步，释放不能绕过同步器。
- CDC-10两项音频控制：复位与静态使能组合进入同步器，音频配置只在静音且关闭时修改，先确认ES8388从机模式后再打开BCLK/LRCK驱动，退出先静音再释放。不能热改tone/channel/FCW或时钟。
- CDC-2/5：ADI状态及静态通道使能双级同步，缺少ASYNC_REG的警告保留；通道配置在停止态改变，状态为监测信息，不作异步单周期脉冲控制。
- CDC-6：ADI单步递增ID经注册Gray码同步；不得以二进制计数直接跨域。
- CDC-15/17：AXI converter握手、多时钟FIFO及ADI捆绑数据保持结构。CPU/DSP即使同为100 MHz也不删除转换器。
- TIMING-6/7所列3组时钟间路径分别检查496、410、37条；端点为AXI握手、XPM FIFO、power_capture双级arm/done/error同步和event_bridge toggle同步。正slack本身不是CDC通过依据。PDRC-190所列为power_capture已同步的第二级到同CPU域GPIO的再同步，不是原异步首级到次级。

以上是结构及协议审查，不能宣称CDC报告零告警、MTBF测量通过或所有工作模式均经过验证。当前模式固定3.84 MSPS、仅RX1、单个硬件会话；后续TX另行测试。

## 板外接口

LCD保持50 MHz、BUS_PHASE=3。完整min/max路径报告给出C到pad延迟3.423–9.439 ns；即使额外预留10 ns时钟/板线差，60 ns相位仍有充足的写低电平及建立保持余量。SSD1963 Rev1.1 p83规定tDSW≥4 ns、tDHW≥1 ns、tAS≥1 ns、tAH≥2 ns、写低≥12 ns。无输出延迟警告不能当作自动通过；这是8080协议的边沿计算，仍需目视回归。线路电平上升沿和实际板线偏差尚未示波器测量。

AD9361原有LVDS接口仍有无input/output-delay报告。既有源同步接口和运行时PN校准用于开发验证，不能声称完成全PVT的板级静态时序签核。迁移后需重新进行当前3.84 MSPS下PN/延迟窗检查，再接收；原150 MHz时期的测量不能替代此次证据。SPI/I2C是低速控制协议；TX口本阶段禁用，GPIO模式运行中固定。

## 实际发现的音频问题与修复范围

ES8388 Rev5 pp32–33要求SDIN setup/hold均≥10 ns、LRCK相对SCLK下降沿在±10 ns内。原约束hold写5 ns，并把只在BCLK下降沿改变的输出按每个MCLK边沿变化检查，造成LRCK/DACDAT长绕线。r1物理报告LRCK slow最大23.333 ns、BCLK slow最小7.591 ns，不能签核±10 ns关系。

不重写音频算法、不重跑综合。局部修复r1失败：6.5 ns的max-delay被既有20 ns输出延迟扣减，且粗略min=-10 ns使静态三态控制出现保持违例。失败checkpoint未部署。r2从原T5重新开始，BCLK max-delay=10 ns、LRCK/DACDAT=30 ns（其中包含20 ns输出延迟），约束C→pad实际路径≤10 ns；粗略min恢复-5 ns。该min值不是ES8388保持时间的签核依据。

r2的实际Fast/Slow C→pad范围：BCLK 4.015–8.311 ns、LRCK 4.386–8.929 ns、DACDAT 4.115–8.284 ns。完整时钟路径显示Fast/Slow插入约1.668/4.648 ns（DACDAT约1.669/4.649 ns）。按各信号的总到达时间跨corner取保守包络，不再假定插入差≤1 ns。LRCK相对BCLK最坏差预留2 ns板线差后约9.895 ns，小于10 ns；裕量较小，后续板线/示波器测量仍有价值。同一MCLK发射边沿的公共源抖动抵消；DACDAT相对下一BCLK上升沿的setup/hold另预留两倍报告时钟不确定度，均超过150 ns，满足10 ns要求。

三条输出的datapath max-delay会优先于普通min分析。为读取最小物理延迟，只在一次性内存审计视图用`set_false_path -setup -reset_path`清除该路径例外；这些临时视图不保存到DCP/bit，也不用于整体时序通过结论。实际部署checkpoint没有新增false_path或multicycle。详见`audio_early_r2b/`、`development_export_r2/*_physical.rpt`及开发收据内的逐条计算。

新增RTL边沿合同仿真含18000个周期、1577次输出变化，覆盖开关使能、输入断流和随机样本，验证LRCK/DACDAT只在BCLK下降沿改变以及高低脉宽。日志`sim/results/y3_audio_edges_r1/tb_audio_edge_contract.log`。

局部修复r2只解布三条serializer输出网，`route_design -preserve`保持其他完成的布线，布线约67秒。WNS/WHS=+0.210/+0.030 ns，TNS/THS=0，bus-skew 69条、最小+3.216 ns，路由错误0，DRC无Error/Critical；LUT37982（71.4%）/FF54244/BRAM92/DSP79。新旧引脚、电压表一致。所有构建输入逐项哈希复核；原T5与修复r1的FAIL保留。

导出XSA会再次生成bit，两个文件仅头部时间字段不同，配置payload逐字节一致；部署bundle直接提取XSA内的bit/HWH，确保部署文件与XSA完全一致。开发收据绑定冻结输入、修复脚本、checkpoint、报告和本文哈希。完整PVT接口签核仍未完成；上板顺序固定为数字自检→3.84MSPS PN/延迟窗→真实接收显示→低音量喇叭，不能用旧150 MHz实测替代。全程未修改third_party或vendor。
