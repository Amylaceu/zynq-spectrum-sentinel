# N4 LCD直驱引擎阶段验收

本记录只覆盖显示引擎电脑端，不是完整N4或M-A验收。尚未下载sentinel_v1。

- 50MHz LCD/AXI和150MHz DSP双时钟；双bank频谱/门限快照按帧序号配对，请求/确认交换，忙时整帧跳过，不覆盖正在读取的bank。
- 560×160绿色频谱、红色虚线门限，560像素单行瀑布，SSD1963整行硬件滚动；右上6条目标分页和底栏使用2位调色板，总25600字节，外接32KiB UI BRAM。
- AXI地址0x43C60000；BUS_PHASE复位25，UI_EPOCH发布后必须等UI_APPLIED再改UI存储。Python驱动校验版本、索引范围和缓冲所有权；不自动加快总线。
- 像素黄金模型89600点及瀑布560点逐点一致；12个快照中2个完整消费、10个整帧跳过；调度器SSD1963命令模型验证全屏清除、完整UI、两帧频谱/瀑布及滚动起点162；封装接口仿真通过；Python驱动3项通过。
- 布局布线：50/150MHz，WNS +1.900ns、内部hold +0.089ns；1493 LUT、948 FF、2 BRAM36等效、1 DSP。CDC 68个端点安全、0不安全、0未知；无共同主时钟/异步时钟组提示保留。虚拟OOC端口hold不作为板级验收，N4全系统仍需setup/hold闭合。
- 第一轮实现组合路径超时2.479ns；将dB运算缩窄为17/16位，增加同步RAM缓存/像素流水寄存器。最终像素、快照、调度、封装仿真全部重跑通过，第二轮实现通过。首轮快照测试的无符号ID与-1比较错误仅修正测试初始化判断。

复现：tools/test_lcd_render.ps1 -Attempt 3，tools/test_lcd_scheduler.ps1 -Attempt 2，tools/test_lcd_engine.ps1 -Attempt 2，tools/synth_lcd_engine.ps1 -Attempt 2（长任务后台，日志logs/N4*）。驱动测试：.venv/Scripts/python -m pytest src/ps/tests/test_lcd_direct.py -q。

证据：sim/results/n4_display_acceptance.json、build/reports/modules/lcd8080_engine_*.rpt。report/figures/n4_trace_simulation.png只为数字仿真预览，非真实射频截图。

下一步：性能计数器、独立IP封装、sentinel_v1 BD时钟/复位/地址/中断、回放捕获、全系统构建与板端验收。15fps、完整RF列表和总线稳定档位尚未验收。
