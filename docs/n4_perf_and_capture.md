# N4性能计数器与非侵入读回

独立模块验收通过，完整N4尚未完成。

perf_mon运行150MHz，AXI-Lite基址0x43C70000。按valid&&ready计样本、FFT帧末、命中；按列表就绪脉冲计列表。样本和周期64位；SNAP_TOKEN触发同时锁存全部计数，SNAP_ACK回报后读，避免高低字撕裂。CLEAR_TOKEN清计数与粘滞状态。ARM_TOKEN仅支持一个未完成标记，标记定义为其后第一个被接受的IQ样本，到下一次列表就绪的周期差；测量前须停止并排空旧帧。这不是每个目标的射频端到端时延，32位时延按模2^32计数。

150MHz布局布线WNS +1.828ns，内部hold +0.142ns，265 LUT/903 FF/0 BRAM/0 DSP。OOC虚拟端口保持时间不代表整机通过。首轮寄存器生成把带reset的RO字段当常量，导致缺动态输入端口，删去动态RO的reset项后第二轮仿真通过；未改生成器。

sentinel_capture旁路观察2048点线性功率，CPU arm_toggle跨到DSP后等待bin0，写完整一帧到8KiB双口BRAM；完成toggle同步回CPU，下一次arm前不覆盖，不回压主处理流。sentinel_events将CFAR/LCD单周期脉冲转toggle同步到100MHz中断控制器；相邻事件须超过同步往返间隔，实际FFT/显示帧间隔远大于此值。

仿真验收：两帧4096字精确，跳过arm时残帧、不接受背压样本、不覆盖未授权快照，20个跨时钟中断无丢失。PS驱动、LCD和CFAR相关测试9项通过。

地址对齐修正：spec_ctrl.yaml及C/Python/TB常量的BASE改为0x43C10000，匹配runbook40，避免与src_mux的0x43C00000重叠；spec_ctrl_regs.v内容没有变化，既有N2数值验收不变。

自研IP封装包括三音ROM和LCD初始化头文件，LCD头文件已导入包内，移除源目录的绝对include依赖；时钟明确为src/perf150MHz、LCD AXI50MHz及DSP150MHz。独立check_integrity全部通过。不等于BD验证通过。

复现：tools/test_perf_mon.ps1 -Attempt 2；tools/test_sentinel_observers.ps1 -Attempt 1；build/scripts/synth_module.tcl参数perf_mon src/rtl/perf 150；日志logs/N4_perf*、N4_observers*、N4_package_*_round2.log。
