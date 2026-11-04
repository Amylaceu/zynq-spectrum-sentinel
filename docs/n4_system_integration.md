# N4 sentinel_v1集成检查点

当前通过BD验证/输出生成，尚未通过全系统布局布线或上板，N4仍DOING。

## 实际时钟

保持原PS/DDR/GEM配置。原预设IO PLL使FCLK2请求150MHz量化为142.857132MHz，无法把该结果冒称150MHz。改为已验证的L18外部50MHz（原LCD时钟）经clk_wiz/MMCM生成150MHz处理时钟；同一外部50MHz直接供LCD。DSP复位由MMCM锁定和PS复位共同控制；100MHz CPU到150/50MHz AXI使用显式clock converter，ADI地址助手对透明转换器不适用，手动连接GP0下一MI并映射实际下游寄存器段。此为80_next中FCLK2直供的实现修正，不新增引脚或接线。

## 数据与存储

保留原RX/TX ADI DMA。ADC I0/Q0旁路经4096字异步FIFO，src_mux四模式，spec_front，cfar_core，配对LCD快照。完整功率帧旁路观察到8KiB双口RAM，CPU toggle授权下一完整帧写入，不回压处理链。回放用Simple MM2S DMA及100→150MHz AXIS转换。UI32KiB替代旧256KiB双页缓存。关键valid/ready/data线用明确物理pin连接，避免给AXIS接口另接监视支路时被IPI自动切断。

CFAR和LCD IRQ各先toggle同步到100MHz，OR合并到axi_intc一个上升沿输入，PS服务时读取两种计数；同时到达的两个事件共享一次服务，计数器仍分别保留。不是两个独立中断向量。

地址：src0x43C00000，spec0x43C10000，cfar0x43C20000(16KiB)，lcd0x43C60000，perf0x43C70000，UI0x42000000(32KiB)，power0x42010000(8KiB)，capture GPIO0x41220000，replay DMA0x40400000，intc0x41800000。实际导出地址表见sim/results/n4_integration_prebuild.json。

三份板级XDC与原已验证live工程逐字节一致，G22 FMC_PWRGD保留，J7/J8保持2.5V。没有修改third_party或vendor。

## 六轮记录与验收范围

前三轮依次发现IP目录加载时机、自动推断单信号接口、透明AXI地址助手问题，按三轮规则停下。用户明确允许继续后，第4–6轮继续：第4轮修复地址，暴露真实时钟142.857MHz；第5轮换MMCM通过工具命令但关键valid/ready被自动接地及IRQ宽度不符，不能验收；第6轮改全部被观察AXIS为显式物理连线，逐项断言9个关键输入唯一真实驱动，IRQ改显式1路合并，最终输出生成通过。保留版本2025.1/2025.2已知警告和原BRAM字节地址高位截断提示，不宣称零警告。

联合仿真：8192个Welch功率值逐字一致，4帧经CFAR产生2240点门限，frame0的560点频谱/门限快照同帧且无覆盖/错误；观察模块新增合并IRQ输出后重跑通过。11项控制软件测试通过。

下一步完整构建资源门槛LUT≤75%、BRAM≤110、WNS/WHS≥0，再进行有源/回放板端自检及用户显示确认。当前不能宣称实时15fps、RF列表或M-A完成。
