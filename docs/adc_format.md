# N4 ADC tap格式核对

核对对象为固定third_party/hdl版本，而非按总线宽度猜测数据对齐。

- library/axi_ad9361/axi_ad9361_rx_channel.v将12位射频原始数据送入ad_datafmt，随后经过可选DC与IQ校正，再输出16位adc_data_i0/q0。
- library/common/ad_datafmt.v保留原12位在bits11:0；FORMAT_ENABLE与SIGNEXT打开时，高4位复制符号，不会自动左移4位。
- 固定no-OS的axi_adc_core.c初始化使能FORMAT_SIGNEXT、FORMAT_ENABLE和ADC_ENABLE；当前板端通道控制也已实测0x51。DC/IQ校正关闭，输出为右对齐的有符号12位。
- 新adc_tap明确要求通道控制的相关格式/校正位匹配0x51，取每路bits11:0并拼4个0，转成与P2参考一致的左对齐signed16。一帧2048个IQ，每字低16为I、高16为Q；例如0xF800→0x8000、0x07FF→0x7FF0、0xFFFF→0xFFF0。

板端程序应在启动采样前读取I/Q通道控制并验证格式，不能对已左移的回放再次左移，也不能启用16位校正后继续截取低12位。若以后采用全16位IQ校正输出，应明确切换tap格式并重新验证。原ADI DMA路径保持原16位格式，只有新tap支路归一化，不改变既有DMA/控制库的约定。

跨时钟使用AMD xpm_fifo_async，写时钟为ADI l_clk，读时钟为150MHz dsp_clk，FWFT输出服从AXIS背压。ADC源不可暂停，FIFO满则丢弃当前IQ并置sticky overflow；I/Q有效信号不同时置sticky mismatch。状态经两级同步传给dsp域。软件测试/回放时必须持续排空未选中的RF支路；overflow=0仍是N4正式验收条件，不能因频谱看似正常而忽略。

本文件记录源码核对及新模块的数值合同，不代替仿真或上板验收。输入格式/CDC模块测试结果后续记录在sim/results/n4_adc_tap_acceptance.json。

## 电脑端验收

xsim使用实际安装的AMD xpm_fifo_async模型，61.44MHz与150MHz异步时钟，4096个IQ字及两帧TLAST逐位正确；随机背压、FIFO满溢出、I/Q有效不一致及复位清除状态均通过。第1轮缺少XPM CDC模型引用的glbl顶层而未完成展开；仿真工具增加可选-IncludeGlbl，加载安装目录原版glbl.v后第2轮通过。原有N2/N3默认仿真入口不变，未修改AMD文件。

证据sim/results/n4_adc_tap_acceptance.json；日志logs/N4_adc_round2.log。这仅是N4输入模块仿真，尚未生成或下载sentinel_v1，不代表完整系统已通过。
