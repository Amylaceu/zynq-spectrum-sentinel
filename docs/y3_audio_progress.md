# Y3 音频开发检查点

## 噪声定位与质量门控收尾（2026-11-03）

用户授权接线不变优化。两轮原始ADC/PFB诊断发现间歇性接收质量恶化，PN9四路通过；LCD开关与好坏无一一对应，具体干扰源尚未确定。新增可选立体声FM质量监测/静音保护，无HDL或位流变化。30秒及300.0989秒链路测试完成，后者零下溢、最低40.3784fps，初始1.0522秒静音后299.0467秒连续放音；用户确认广播清楚、只有轻微底噪、无明显断音。正式300秒全程出声未完整覆盖，Y3历史FAIL保留。详细依据、失败修正和复现入口见`docs/y3_noise_diagnosis.md`。85项针对性测试通过，结果有JSON/SHA256，已静音并关闭RF源。

下次试听用户要求提高音量；本轮保持−15dB，尚未验证更高音量。

## 最新接续（100MHz板载喇叭，2026-11-03）

用户确认r5的1kHz、3秒测试音“听到了，声音正常”；r5数字计数144392帧、零下溢，安全静音。人工证据为board/measurements/y3_v2_tone_human_r5.json及SHA256。

FM 95.8MHz短测r1因瞬时LCD帧率29.790fps低于30自动停机，音频无下溢；r2将SSD1963 BUS_PHASE显式设为2，30.133秒短测量化通过，最低40.782fps、音频零下溢、48kHz计数正常，结束后codec静音和RF停机。用户反馈“能听到，但噪声较大或断续”，因此主观音质未通过，r2不等于5分钟验收。失败与听音证据分别见board/measurements/y3_v2_audio_r1_execution.json、y3_v2_audio_r2_execution.json、y3_v2_audio_r2_human.json及各自SHA256。r2首次部署预检因sudo未提供密码而在RF启动前失败，预检收据单列；重试使用已授权的默认密码，仅通过stdin传递。

r3改用历史FM录音的96.05MHz LO（PFB15、残余−10kHz），用户仍反馈基本全是噪声、听不到内容；主动SIGTERM后在168.566秒停止，数字下溢0、最低40.539fps，codec静音、GPIO/SRC/audio=0、postflight PASS。证据为y3_v2_audio_r3_execution.json、y3_v2_audio_r3_human.json及SHA256。Y3本轮标FAIL：测试音通过不代表FM解调通过，零下溢不证明选台/解调或模拟音质无问题，故障原因未定位。三次板测结束，不自动追加第4轮，不为掩盖问题更改门槛；后续可先分析已有IQ、PFB频响/量化和FM解调，再由人工决定是否增加验证。

## 历史接续（100MHz接收回归后）

100MHz开发审计、数字自检、接收接口及120秒接收功能回归已通过；真实接收191份IQ校验一致且用户目视正常。显示中位28.988fps仍未达30fps，历史Y2 FAIL不变。喇叭1kHz r1/r2因PYNQ2.7将AXI IIC2.1绑定成DefaultIP失败，r3因codec复位未释放失败。修正显式驱动绑定和复位释放后，508项PC回归通过；用户授权r4数字验收PASS（3秒、144395帧、零下溢），人工表示未注意声音，要求−15dB重放r5。人工听音尚待确认，Y3仍DOING，未进入FM监听。详见`docs/v2_board_regression.md`；下文早期“未加载v2”等只作历史记录。

## 最新开发决定（2026-11-03）

用户已明确采用100 MHz继续功能开发，后续可回到具体失败路径优化。当前开发基线为sentinel_v2_100m；v1d保留作已验收回退。T5的+0.210/+0.030ns不等于Z10的+1ns门禁通过，原FAIL、部署收据和板测要求不变。本轮已迁移识别/屏幕监测与隔离部署入口，显式选择v2并记录100MHz时钟；437项PS/工具回归通过。未加载v2、未进行射频或喇叭播放。执行顺序、现有音频接口与后续回归见docs/v2_function_development.md。下文“继续v1d开发”是此前决策，现由本段取代。证据sim/results/v2_function_bridge_r1.json及SHA256。

> 当前输出目标已由用户改为95_final Z7板载喇叭（ROUT2→MD8002A→J36）。
> 下文OUT1-only内容是保留的开发历史。现有运行脚本已迁移OUT1/OUT2、−21dB，
> 支持显式选择150MHz旧镜像或100MHz候选；候选签核未完成，禁止直接部署。先完成1kHz/3秒出声测试，等人工确认后再进行FM连续监听；
> 初始音量约−20dB，按寄存器支持的档位记录实际值。P1耳机不单独开发或验收。

当前尚未初始化ES8388、未播放、未运行Y3射频测试。配置A/P1接线已确认，主观试听尚未验收；首次播放前耳机不要戴上。硬件核对见`y3_audio_preflight.md`。

## 已验证的独立组件

- `src/rtl/audio_y3/i2s_tx_y3.v`：32位时隙、24位有符号单声道复制左右、
  LRCK后延迟一位、缺样输出零、下溢与帧计数饱和、disable/reset静音。
- 第1轮失败是scoreboard未在disable后清除旧期望样本，原日志和源码已归档；
  第2轮修复测试平台后通过。独立组件结果见`sim/results/y3_i2s_r2.json`。
- `fm_stream_y3.py`：连续480k复IQ、抗混叠FIR、10倍抽取、75us去加重、
  固定低增益、PCM24。保存跨块状态，采样序号有间隙时拒绝处理。
- 4项PS测试通过。板端纯CPU合成测试处理10秒IQ耗时5.889537秒，
  实时倍数1.697926，100ms块最大64.178ms；证据
  `board/measurements/y3_fallback_cpu_r1.json`。不涉及RF/PL/I2S。

## 尚待实现与验收

PL FM独立组件第3轮已通过：8193个相位字及820个PCM逐位一致；相位与
独立atan2参考的最大误差为7 LSB。1kHz合成音峰值1000Hz，幅度0.048314，
参考0.048245。第1轮未初始化历史样本问题、第2轮测试提前结束问题及修复
均保留，`sim/results/y3_fm_r1/r2/r3.json`与对应ZIP均有SHA256。
第3轮覆盖长/随机背压和复位，不再追加第4轮组件仿真。
此结果尚未覆盖连续PFB分支、CDC/FIFO、音频时钟和整机。

1. 优先PL连续FM路径；已验证的PS组件仅作降级预备，不冒充完成监听。
2. 音频IIC新增独立地址及A18/A19管脚；0x41620000已被FMC IIC占用。
3. 验证MCLK实际频差、音频数据CDC和长期采样率漂移；FIFO计数可追溯。
4. 连续链路不可拼接Y2有间隔的8.533ms SCAP快照。8KiB、32位mono FIFO
   仅约42.7ms，小于现有100ms块最大64ms处理时间，须预缓冲或调整流水。
5. ES8388只开OUT1、关闭OUT2；寄存器0x04=0x30。24位I2S格式和256Fs
   配置按原厂Rev5手册核实；模拟−30dB对应0x2E/0x2F编码10。
6. 五分钟连续播放、FIFO下溢0、显示帧率、人工听音均须分别验收。

原厂手册本机缓存`build/work/y3_audio/ES8388_v5.pdf`，SHA256
`db9300f79df430d022b754b29eb1b6b17ca08e3b91d3ba833606dadc65898258`。
以上组件通过不代表连续DMA、并行AMC负载或整机音频通过。

## 本轮接续（2026-11-03）

- 用户已确认“配置A未变，P1已接耳机，允许Y3仅接收及低音量试听”。首次播放
  不要戴耳机的提醒已经发出；主观听音尚待实际播放后确认。
- 汇合组件r3 PASS：实际8192词PCM FIFO/4096预填，在+80ppm音频时钟下，
  800个左右声道PCM帧逐位一致，无下溢；不是五分钟板测。
- 三次BD校验已有独立日志，r3通过。它们不是三轮整机布局布线；正式实现r1已启动，
  控制日志为logs/Y3_full_implementation_r1_controller.log，退出标记须等变成0。
- tools/freeze_y3_build.py冻结142项输入并核验原组件归档。汇合仿真后只新增
  audio_drive输出及复位/显式使能门控，冻结器对这处差异逐字核验，DSP通路不得变化；
  高阻管脚仍须整机审计及上板检查。
- tools/audit_sentinel_y3.ps1及tools/accept_sentinel_y3.py检查最终时序、总线偏斜、
  地址、音频时钟和六个音频引脚。未产生PASS收据不能部署。
- 修复PS联调遗漏：复用v1d信道复位和v1b处理链初始化；分频读回用RATE_DIV；
  FIFO退出复位后才启动RF源。已检查板端PYNQ2.7 AxiIIC实际缓冲区API。
- tools/run_y3_board.py使用新隔离部署目录、严格SSH校验和SHA256；支持30秒冒烟
  或300秒正式测试。默认数字/模拟均−30dB，模拟音量参数--volume受限。
  退出核验GPIO/SRC/音频驱动关闭；主观音质仍须人工确认。
- 24项软件测试通过，日志logs/Y3_audio_pc_r3.log。第三方/vendor未修改；
  未开始Y4或任何空口发射。

## 本轮继续（软件证据r3 / 整机实现r2）

- 原软件r1和补录r2均保留。修复板测验收的最后一秒盲区：停音/复位前保存
  FIFO错误锁存器、播放状态和PFB健康快照；独立验收必须检查这份快照。
  同时独立检查30–85°C温度，缺失或非有限值不能通过。
- 当前30项针对性测试通过，证据`sim/results/y3_software_r3.json`及SHA256
  绑定当前运行脚本、驱动与测试；不代表已在板上听到声音。
- 整机r1综合出现`Designutils 20-1307`：XDC不支持`foreach`。
  为避免无有效管脚约束的实现继续运行，仅终止本轮已确认的Vivado进程，
  控制器退出码1；不是一次已完成的时序失败，也未加载位流。
- r1共695个文件已归档至`report/results/y3_implementation_r1.zip`，
  有逐项哈希和JSON/SHA256；原因记录为
  `board/measurements/y3_implementation_r1_failure.json`。
- 六个音频管脚改用逐条`set_property`，引脚分配没有变化。
  硬件输入r2共142项重新冻结并启动正式实现第2轮，日志
  `logs/Y3_full_implementation_r2.log`，继续使用独立Y3目录。
- 后续：整机成功后审计时序/CDC/管脚，通过才允许30秒冒烟及300秒连续板测。
  首次播放前仍须保持耳机离耳；没有人工听音反馈不能把Y3标为DONE。


## Z10第三轮收尾（当前状态）

100MHz候选第三轮最终WNS+0.026ns/WHS+0.042ns，Z10的+1ns目标FAIL，尚未部署。
最新265项PC回归通过（logs/Z10_runtime_full_r3.log及z10_runtime_full_r3.json/SHA256）。
FM与测试音的finally统一调用shutdown_audio_outputs：先静音/关闭DAC，再释放I2S；
编解码器失败仍执行引脚清理并记录错误。Python3.8语法通过。
这些结果均不等于喇叭出声或连续监听；当前不初始化ES8388、不启动射频。

## T5结束后的Y3-S准备（2026-11-03）

独立100MHz候选T5最终 WNS/WHS 为+0.210/+0.030ns，仍未达到+1ns部署门禁；
它不改变已验收v1d的功能与历史实测。Y3 的PS合同已修复为
`cfar_x1`完整版本0x43460002，避免候选位流将来被CfarX1驱动拒绝。

为检验8KiB音频FIFO下的短块处理可行性，新增可选的
`tools/bench_y3_fallback.py --block-ms 20 --attempt 1`。板端仅用合成
480kSPS IQ、NumPy FM解调及PCM24打包，500个20ms块处理共10秒：
吞吐1.5769倍实时，单块最长14.620ms、P95 12.995ms，全部小于20ms；
480万输入/48万输出样本对账通过。JSON及SHA256为
`board/measurements/y3_fallback_cpu_20ms_r1.json`。最新435项PC回归通过，
证据`sim/results/y3_fallback_20ms_pc_r1.json`及SHA256。这只证明独占CPU的
合成流处理性能，不包含实际RX DMA、I2S推流、屏幕/AMC并发、FIFO下溢
或板载喇叭听音；Y3仍为DOING。

下一步若转Y3-S，须先获得仅I2S/FIFO/AXI DMA的最小PL位流并独立审计；
再以20ms连续IQ块、预缓冲、序号校验和FIFO下溢计数完成上板验收。
已有v1d位流本身没有I2S输出，不能仅部署PS解调代码来宣称喇叭功能。
