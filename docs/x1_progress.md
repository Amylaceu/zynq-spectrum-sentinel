# X1电脑端开发检查点

已完成X1黄金模型、契约、驱动、cluster、AXI寄存器与core集成。最新core r2：18组/36864bin，门限、命中、dB、占用度各36864字、目标2304字、统计126字全部零差异；源文件SHA256再次核对一致。证据sim/results/x1_core_r2_acceptance.json及.sha256。

sentinel_v1b独立工程已派生，CFAR IP已打包且check_integrity通过（logs/X1_cfar_package_console_r1.log）；尚未完成BD校验、整链仿真、整机实现和板测。已验收v1保留作为X0恢复路径。

此前215项离线回归和cluster r1是历史检查点；cluster源码新增alarm/frame_error后不能将旧r1哈希当成当前源码。新的core仿真覆盖本次版本，后续再跑完整回归。

独立cluster OOC r1仍为FAIL：总体WHS -0.419ns/269端点；WNS +0.067ns、内部hold +0.147ns不能替代总体hold验收。不得通过放松约束掩盖失败；整机结果待真实连接下验证。

SD整卡核验已PASS。恢复硬件需先按X0清单完成插卡/供电/配置A确认，默认3档和温度验收；X1未部署，不宣称30.72MSPS或X1完成。

## 最新：整链通过，整机实现中

sim/results/x1_chain_r1_acceptance.json：16帧32768输入，8192功率逐位、8960阈值像素、560列首帧配对通过；稳态7帧71946周期（饱和输入下约29.89MSPS），不能宣称30.72零丢样。BD校验通过，215项回归通过，输入快照docs/x1_v1b_prebuild_r1.json。整机实现r1日志logs/X1_v1b_implementation_console_r1.log，完成后必须单独最终时序/资源/HWH/产物哈希审计；尚未部署。X0已通过。

## 软件接入与当前板端状态

X0已提交8263e8e，用户再次确认X1配置A。板端接收已停止且GPIO/SRC=0。V1b、独立monitor_x1、单音/三音/回放自检、部署和两窗口指标工具已准备，234项PC回归通过；默认Session仍V1，只有显式hw_factory=V1b才使用新版。软件快照docs/x1_software_predeployment_r1.json。位流布局布线进行中，尚未部署X1。

## 2026-11-03 02:04续接核对

配置A授权已记录于docs/x1_board_configuration_a.json，不重复询问。板端SSH可用，boot_id仍为c562cb48-bc51-431d-af31-54146bb89f56，无活动monitor。整机r1仍在布线，禁止以中间WNS作通过结论。

最新软件快照为docs/x1_software_predeployment_r2.json（16文件）；r1保留为历史。补跑src/ps/tests、tools/tests及X1黄金模型共148项全部通过（logs/X1_predeploy_tests_r2.log），这是不同范围的回归，不替代或累加此前234项结果。板端脚本通过Python3.8语法检查。用N4三音原始NPZ复核X1默认min_width=2/gap=6，仍得到724/1088/1324三个峰；此项为离线检查，不代表X1上板自检。


## 最新检查点：整机r1失败，修复后r2准备构建

整机r1最终时序WNS -0.155ns/WHS +0.034ns/WPWS +0.264ns，75个setup失败端点；归档build/reports/sentinel_v1b_r1_failed/failure.json及SHA256，原工程和IP移至build/work/x1_failed_r1/。未部署失败产物，不放松时钟或例外约束。

新增cfar_detect_x1.v，用carry-save变换保持40位模运算与原握手周期不变，消除窗和更新的串联进位链。core r3：18组36864bin和全部数据窗口逐位一致，另10096组边界/确定性随机算术检查通过。整链r2：16帧32768输入、8192功率、8960阈值像素、560列配对通过；吞吐仍约29.89MSPS，不代表X2已完成。IP r2完整性检查通过。

最终审计新增独立report_bus_skew，解析器7项测试通过，历史真实报告31条路径的最小裕量3.107ns已验证解析。整机r2输入快照为docs/x1_v1b_prebuild_r2.json；通过最终时序/资源/总线偏斜审计前不部署。配置A授权仍有效，板端保持停止接收。

第2轮整机实现已后台启动（logs/X1_v1b_implementation_console_r2.log，输入快照129文件）。构建期间冻结输入，继续检查部署与板测衔接，不改正在使用的RTL/IP。

## 板测验收脚本续接检查

配置A授权继续有效。只读SSH确认boot_id未变，无活动monitor/bench进程。新版未部署。
板测指标解析增加遥测时间、64位输入样本数、32位显示/FFT/CFAR序号推进检查，拒绝静止或重复快照及非有限数值；32位正常回绕允许。缺失快照仍保守计入分母，不删除原始记录。
165项相关PC回归通过（logs/X1_predeploy_tests_r3.log），板端文件Python3.8语法检查通过。软件快照docs/x1_software_predeployment_r3.json及SHA256保留当前部署输入；此前r1/r2快照不回写。129个冻结硬件输入逐一复核未变化。

## 整机r2审计通过，进入板测

构建退出0，最终独立审计PASS：WNS 0.000ns、WHS +0.032ns、WPWS +0.264ns，setup/hold/pulse失败端点均0；30626 LUT、42779 FF、47.5 BRAM、64 DSP。31条bus-skew最小裕量+2.997ns；129项冻结输入哈希均未变化。证据board/overlay/sentinel_v1b/acceptance.json及build/reports/sentinel_v1b/final_*.rpt。

20行时钟对CDC摘要与N4完全一致（docs/x1_cdc_baseline_comparison.json及SHA256）；继承的ADI Critical条目仍保留，不把摘要一致称为逐路径CDC证明。WNS为0，不能宣称具有充足时序余量或全温稳定性。

文件部署r1通过，共16文件；原runtime备份保留，已验收v1不覆盖。board/measurements/x1_deployment_r1.json及SHA256。配置A确认继续有效，接下来先新版有限自检，再120秒两窗口RF指标。X1仍DOING，人工目视和提交待完成。

## 新版板端有限自检通过

板测selftest r1执行与PC独立NPZ复核均通过：单音峰1088，误差0bin；三音峰724/1088/1324，CFAR目标3个；四帧8192功率字逐位零差异。前后boot_id一致，未初始化射频。证据board/measurements/x1_selftest_r1.json、x1_selftest_r1_execution.json、x1_selftest_r1_acceptance.json及原始NPZ，各有SHA256关联。

配置A授权有效，正在执行98MHz容量窗口；之后使用同参数执行96.4MHz窗口，验证95.8MHz±25kHz检出率。有限自检通过不代表RF指标或人工目视通过，X1保持DOING。

98MHz容量窗口r1已完成120秒，101条同帧快照，无缺失、无容量告警、无采样FIFO溢出；目标数中位4，显示中位49.422fps，温度59.80–61.27°C，双TX衰减89.75dB，boot_id未变。证据board/measurements/x1_capacity_r1.json及执行回执、SHA256。96.4MHz电台窗口r1已启动，待完整指标、用户本轮目视和停止状态检查；尚未完成X1，不提前提交。

## RF第1轮未达标，保留证据后调整平均

电台窗口r1已完成：103条快照无缺失、无容量告警、无采样FIFO溢出，中位49.460fps；95.8MHz±25kHz检出68/103=66.02%，低于80%，故x1_rf_metrics_r1.json为FAIL_METRICS。用户本轮确认“画面动态正常，看到约95.8 MHz条目且与当地电台一致”，仅作目视验收，不替代检出率。停止后独占锁下GPIO/SRC均0、boot_id不变，证据x1_visual_r1.json、x1_postflight_r1.json及SHA256。

漏检35条中未保留95.8MHz附近目标；已检出峰均在频率容差内。疑似弱目标偶发仅剩窄段而被宽度过滤，缺少漏检帧原始功率，不能认定物理根因。启动时单帧黄金模型诊断仅供参考，见docs/x1_rf_r1_diagnosis.json。第2轮仅将AVG_SHIFT由3增至4，两窗口均保持MIN_WIDTH=2、GAP=6、ALPHA=1974及原频率/时长，测量编号r2，不覆盖r1；若仍不达标，按最多3轮限制处理。

## RF第2轮未达标，进入最后一轮

AVG_SHIFT=4、ALPHA=1974：capacity r2为104条快照、容量告警0、采样溢出0；station r2为103条快照、检出61/103=59.22%、容量告警0、采样溢出0。中位显示49.398/49.454fps，boot_id未变。x1_rf_metrics_r2.json为FAIL_METRICS，原始证据和SHA256全部保留。

第3轮保留AVG_SHIFT=4、MIN_WIDTH=2、GAP=6、DC_MASK=3，仅将ALPHA由1974降至1536（Q8.8系数6.0），以提高弱目标检出概率，并完整复测容量影响。频率容差±25kHz、周期快照分母及120秒窗口不变；配置A授权有效、仅接收、TX衰减89.75dB。若仍未达标，按三轮上限停止并记录FAIL，不进入X2。

## RF三轮收口：X1为FAIL，新增天线对比待确认

r3完整结果：capacity告警37/105=35.24%，station检出58/106=54.72%，分别显示49.447/49.415fps。全部快照有效、无采样溢出。停止后GPIO/SRC=0、boot_id不变，证据x1_postflight_r3.json。三轮均未同时达到联合指标，X1标FAIL，X2未启动；总检查点x1_acceptance_summary.json校验24项证据及129项硬件/18项软件冻结输入。代码和失败测量完整保留，不提交通过标签。

用户随后明确授权两根不同天线各测一次比较适配性。这是新增天线实验，不覆盖X1的三轮记录，不自动将X1改为通过。等待用户说明天线型号与当前连接，射频保持停止。

## 用户授权的天线对比：粗长完成，细短待确认

用户确认“粗长天线已接RX1A，TX空，可以开始”后，完成独立120秒仅接收窗口。LO=96.4MHz，95.8MHz±25kHz，3.84MSPS、RF带宽1.5MHz、BUS_PHASE=3、AVG_SHIFT=3、ALPHA=1974、MIN_WIDTH=2、MERGE_GAP=6、DC_MASK=3，无额外mask。16/104=15.38%检出，容量告警0/104、快照缺失0、采样FIFO溢出0，显示中位49.428fps，温度59.80–61.15°C，双TX衰减89.75dB。接收机RSSI中位−116.5dBm，仅作遥测，不等于电台SNR或天线增益。退出后GPIO/SRC均0、boot_id不变。

原始记录、执行回执、单根汇总及SHA256位于board/measurements/antenna_compare_long_r1*；日志logs/X1_antenna_compare_long_r1.log。第二根细短、馈线长的天线尚未测量，等待用户换接RX1A并确认，期间保持RF停止。两根之间不改参数，摆放尽量相同。此时不能选定胜者，不改变X1三轮FAIL，不开始X2。

## 用户新增三天线对比：全部完成

上述待测描述保留为历史。本轮用户先确认细短天线已接RX1A、TX空、摆放一致，之后新增第三根；第三根型号/频段未提供，用户明确要求直接接收，未再次明确确认相同摆放。三次均固定原参数，只接收120秒，没有新一轮X1调参。

粗长16/104=15.38%，细短61/105=58.10%，第三根50/104=48.08%。容量告警分别0/104、2/105、0/104；快照缺失及采样溢出均0。显示中位49.428/49.382/49.462 fps。第三根温度59.55–60.91°C，RSSI中位−81.5 dBm；不将RSSI换算为目标SNR或天线增益。

本次FM接收暂优先细短天线，比第三根检出率高10.02个百分点；一次顺序测量不代表全频段或可重复的天线增益比较。三次位流、配置、boot_id、monitor一致，18项冻结软件输入核验通过，退出GPIO/SRC均0。全部JSON、回执和SHA256已保存，最终汇总board/measurements/antenna_comparison_three_r1.json；详见docs/antenna_comparison.md。X1维持FAIL，X2未开始；当前RX停止，第三根仍由用户连接，下一次射频测试须重新确认连接。
