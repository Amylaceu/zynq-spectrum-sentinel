# N4板端软件与验收状态

当前：N4 DONE，限定为3.84MSPS仅接收功能验收。详见 [完整验收汇总](n4_acceptance_summary.md) 及 board/measurements/n4_acceptance_summary.json。用户要求完成N4后暂停，N5未开始，M-A尚未完成。

monitor软件默认BUS_PHASE=3；已安装zss-n4-admin仍默认25，命令显式传--phase 3。RTL初始化保守值25不变。真实RF完整显示约49.4fps；PS文字/列表约每秒更新。所有七档目视确认已存档。

两次120秒测试已退出，最终RF GPIO数据0；58项软件测试通过。32目标列表容量告警保留，不能说所有溢出都为零。

## 历史过程记录（保留当时状态，当前结论以上述汇总为准）

monitor.py：支持rf/test/replay，PS只读PL计数/列表并刷新固定UI；频谱/门限/瀑布由PL产生。RF只接收，初始化后检查双TX89.75dB；源/位流使用互斥锁，退出停止源并复位RF。默认BUS_PHASE25、有限时长120s。回放模式按PS逐帧调度，明确不是连续实时RF流。

selftest_v1.py：只用PL测试源和回放，RF保持复位。有限单音峰值误差≤1bin、三音恰好3目标、4帧回放8192个功率字逐位比对；AVG_SHIFT0对应exp_power_shifted.hex，保存所有原始输入/输出/黄金谱与单音三音谱到NPZ，哈希写JSON。Simple MM2S DMA设置23位长度，所有异常路径等待DMA复位完成才释放缓冲区，检查前后64字节边界。

bench_lcd.py：一次只测一个25/12/8/6/4/3/2档，至少10秒后记录帧率，再保持该档默认600秒供用户目视；不会自动遍历档位。SIGTERM/结束后恢复保守25档。记录状态始终是measured_pending_human，只有用户回报才能确认无花屏/错点。未运行任何档位测试。

PS控制/所有权/异常退出/回放DMA释放/目标列表突发复制与序号一致性及最终审计解析器共18项测试通过（logs/N4_app_tests_final.log）。这不是板端自检通过。

## 处理速率的实际限制

16帧联合仿真通过，第一8192功率字仍与黄金模型精确一致。稳定7帧跨度71946个150MHz时钟，饱和反压输入约29.889MSPS，谱帧约14594.279/s；当前CFAR分帧采集/处理串行，尚未证明不暂停ADC的30.72MSPS可以长期无溢出。测试源会反压暂停，不能拿它的requested30.72MSPS冒称实际吞吐。

首次RF联调采用已验证3.84MSPS；后续可实测24.576MSPS等低于该上界的档位。记录真实rate、overflow和板端计数；不要放宽门槛、隐去溢出或把仿真上界写成板测值。LCD≥15fps仍待实测、用户目视确认及N5归档。

板端后续命令：python3 -m sentinel.app.selftest_v1 --source test --load-overlay --out measurements/n4_selftest.json；python3 -m sentinel.app.monitor --source rf --lo 98e6 --rate 3.84e6 --seconds 120。只能在新位流全系统资源/时序验收通过、无另一个RF进程占用后执行。

2026-11-02 本机接手补充：已增加 `sentinel/telemetry.py`，按 IIO 设备名 `xadc` 读取温度并接入 monitor JSON 和 LCD 状态栏；缺失或无效读数显示 N/A。测试源/回放显式设置、读回 RF 复位 GPIO。RF 模式将互斥锁交给 C 驱动后，仅由持锁的 C 驱动关闭和复位 RF；Python 不在驱动释放锁后再次写 GPIO，失败交接也不操作其他进程的 PL。重复 close 不再触碰已释放的设备。58 项 PS 测试通过，见 `logs/N4_app_tests_rf_handoff.log`；尚未在新位流上进行板端验收。

板端 SSH 只读预检见 `logs/N4_board_preflight_readonly.log`：连接正常，未发现运行中的监控/自检程序；`sudo -n` 返回需要密码，尚未取得管理员权限。板端日期停留在 2021 年，后续采集须用 PC 时间、boot_id、单调时钟及产物哈希关联，不能直接用板端墙上时钟推断采集日期。测试源首次仍须 --load-overlay。详细原始交接限制见 `report/HANDOFF_20261102_N4.md`。

## 2026-11-02 N4 上板进展（当前）

- 第三轮整机实现退出码 0；重新打开 post-route 实现的独立审计 PASS：WNS +0.086 ns、WHS +0.046 ns、脉宽裕量 +0.264 ns，失败端点 0；26,625 LUT、49 BRAM、64 DSP。证据 `build/reports/sentinel_v1/acceptance.json` 与 `logs/N4_final_audit_round1.log`。这只证明电脑端实现/产物通过门槛。
- 详细 CDC 和方法学复查保存在 `build/reports/sentinel_v1/final_cdc_details.rpt`、`final_methodology.rpt`、`final_bus_skew.rpt`：136 个 Critical CDC 分类涉及 ADI ADC/DAC DMA 和 AD9361/divclk 内部路径，新增 adc_tap 状态同步器在报告中为 CDC-3 Safe；bus-skew 有正裕量。Vivado 仍报时钟定义/关系及 18 个无 input delay、41 个无 output delay，不能声称全设计 CDC/IO 时序零风险。不得为消除告警盲目扩大 false-path。
- 用户明确授权仅尝试一次 PYNQ 默认密码；已在交互式 SSH 中成功安装 `board/scripts/install_n4_admin.sh`，返回 `N4_ADMIN_INSTALLED`。`sudo -n /usr/local/sbin/zss-n4-admin health` 通过；安装不加载位流、不访问 RF。该入口会以 root 运行仓库可写的 Python 代码，属于开发便利而非对仓库写权限用户的安全边界。
- `tools/deploy_n4.ps1` 只同步 N4 必需文件，避开板端已有 root 所有的 notebook/测量文件，且核对 bit/hwh/xsa 哈希。`logs/N4_deploy_round4.log` 返回 PASS。旧 `tools/board.ps1 push` 因旧 notebook 权限无法覆盖而中断，相关日志保留；无需删旧测量。
- 首次 `selftest` 被错误的软件 GPIO 三态寄存器读回条件阻断：AXI GPIO 第一通道综合为 `C_ALL_OUTPUTS=1`，0x00 是输出数据，0x04 的三态寄存器读回固定为全 1。只读板测得到数据 0、三态全 1；修正为只写/核对 0x00，未更改 PL，58 项 PS 测试重跑通过（`logs/N4_gpio_fix_tests_round2.log`）。
- 第二轮板端自检通过：单音峰值 bin 1088（误差 0）、三音目标 bins 724/1088/1324（3 个目标）、四帧回放 8192 个功率字逐位零错，TX 未请求。板端结果 `board/measurements/n4_selftest_round2.json` 与原始 `n4_selftest_round2.npz` 已拉回，PC 独立复核 `n4_selftest_round2_acceptance.json` PASS。`perf.status=4` 为标记完成位，不是 overflow/framing 位（掩码 3 均为 0）。
- LCD 首档 `BUS_PHASE=25` 在三音源下实测 72 帧/10.010 s = 7.193 fps；`board/measurements/n4_bench_phase25_round1.json` 的 `human_visual_acceptance` 仍为 `pending`。用户目视确认前不换档。该 benchmark 只启动硬件测试源与显示，右侧 UI 列表未必有软件填充；RF 目标列表须在 monitor 阶段确认。
- 待办：逐档 LCD 目视及 ≥15fps 验证；3.84MSPS RF 接收显示；N4 完整验收后再做 N5。当前无 TX，RF 自检仍保持复位。

## N4 BUS_PHASE=25 静态照片复核（2026-11-02）

照片归档为 board/measurements/n4_bench_phase25_visual.jpg，评价及 SHA256 见 board/measurements/n4_phase25_visual_acceptance.json。将照片按 800×480 屏幕方向观察，三条窄谱峰及对应瀑布轨迹与三音测试源一致，未见明显的静态花屏或坐标错位。右侧列表/状态栏空白符合 bench_lcd.py 不写入 UI 像素的测试范围。板端10.010秒输出72帧，即7.193fps。单张照片无法验证闪烁、偶发错点或瀑布动态滚动，故原测量 human_visual_acceptance 维持 pending；尚不能认定25档动态验收通过。下一步先完成动态目视，再按12/8/6/4/3/2逐档测试，之后进行3.84MSPS仅接收RF显示验收。

## N4 LCD动态验收检查点（2026-11-02）

- 原固定三音瀑布在稳定输入下看起来静止，不能凭此认定显示停止；bench_lcd.py 已在10秒无UI帧率基准测量结束后增加底部PL FRAME计数，人工观察阶段含UI刷新，不能把前段帧率称为完整UI帧率。
- 首次增加UI时，高速CFAR列表在Python读回期间更新而触发一致性保护；失败测量 n4_bench_phase25_ui_r1.json 保留。bench动态检查现只显示帧计数，完整信号列表仍在RF monitor单独验收，不以空列表替代。
- 用户确认25档“计数持续增加、画面正常”，7.1927fps；证据 board/measurements/n4_phase25_ui_acceptance.json。
- 用户确认12档“计数增加、画面正常”，14.5853fps；证据 board/measurements/n4_phase12_ui_acceptance.json。
- 8档基准21.3914fps，目视待确认；6/4/3/2尚未验收。N4保持DOING，完成后按用户要求暂停，不进入N5；不执行git提交/推送。

2026-11-02 N4：用户确认“8档计数增加、画面正常”。BUS_PHASE=8纯频谱/瀑布基准21.3914fps，动态阶段179次UI更新及帧计数推进；证据 board/measurements/n4_phase8_ui_acceptance.json。6/4/3/2及RF显示待验收，N4仍DOING，完成后暂停，不推进N5。

2026-11-02 N4 LCD：用户确认6档、4档均计数增加且画面正常；基准分别27.7720、39.5600fps。证据 board/measurements/n4_phase6_ui_acceptance.json、n4_phase4_ui_acceptance.json。3/2档、默认档RF含UI显示仍待验收，N4保持DOING。
