# 最新检查点：J-v7 主界面集成（2026-11-04）

执行依据 KICKOFF_J7.md / J_polish.md 文末 v7。实际 Git 根为工程操作目录；冻结 100 MHz/3.84 MSPS 位流、接收库及模型，不构建或训练。

| 子项 | 状态 | 本轮实测 |
|---|---|---|
| 13 卡与界面精简 | 软件完成，12 卡已逐一板测 | F3/F9 卡移除；F9 并入 F2；CFAR 仅 F5、窄带图仅 F7/F12；真实短瀑布、灰白前曲线 |
| F0–F13 连续启动/停止 | 12 卡流程完成，有指标限制 | 无 GUI 数据错误，均有停止恢复读回；F2 约 40–41 fps、0 bin、8192 字 0 不一致；截图见 j7_acceptance_summary.md |
| F8 搜台及换台 | 可用，启动时限未全达 | 已搜台并换三个候选格点；邻近频点不等于不同电台身份；单次启动约 3.13 秒，不冒充 P90 |
| F8 同步录音 | FAIL，正式界面不显示 | 三轮 ADC 溢出，最后 5 秒候选约 3.59 秒失败；恢复成功，不再追加第四轮，无新录音听音验收 |
| F11 | 功能可用，时限 FAIL | 约 34 秒，总时限 15 秒未达，首段约 1 秒 |
| F12 | NOT_QUALIFIED | 质量 10/10，FM 4/10 未达 9/10；不显示可靠标签 |
| F13 | 本轮板端推理通过 | 500 条与参考逐项一致；十类 83.4%、八类 86%；输入为实测录波，本轮不发射 |
| F14 | PASS（本轮有限快照完整流程） | 主界面13信道/52段，9条网络记录、27个FCS通过信标；采集63.34秒、解码41.69秒、MATLAB退出码0；基线读回正常。用户换回S1并在界面确认，已观察到锁定→解锁 |

65 项应用、恢复、Wi-Fi及发布定向回归通过；后续中性显示门禁22项通过。汇总 board/measurements/j7_acceptance_summary.json 与 SHA256；说明 docs/j7_features.md。
人工断电后的旧服务异常保留；当前 boot_id 496c33e4-3824-4548-8ef7-82e5b95e6a01，候选 j7_final / live_final。F14 前停止读回正常，未在线修复文件系统。后续不直接断电或复位。

以下内容为历史检查点，不能代替本轮状态。

# 最新检查点：J-v6 十卡及广播修复已保存

十卡数字验收见 board/measurements/j6_dma_r1/acceptance.json。F8 最终候选 j6_audio_r3 启动1.7094秒，用户确认“已清楚，基本连续”，证据 j6_audio_final_r3。历史FAIL不覆盖；65项定向回归通过。详细限制见 docs/j6_features.md。当前进入 J-v6.1 四张应用卡及 Wi-Fi 集成，尚未完成，不作通过。

# 当前补充检查点：Wi-Fi 名称现场解码（2026-11-04）

| 子项 | 状态 | 结果 |
|---|---|---|
| AD9361 信标采集与电脑解码 | PASS（有限快照） | 13信道/52段，12个宣告网络；Zynq 4个CRC有效帧，宣告信道13。用户确认名称与列表清楚。采集约73.63s、解码47.94s，不是即时/连续识别。 |
| 名称窗口及主上位机菜单 | 软件及单次实测通过 | 独立窗口人工确认；源码菜单“工具与导出→显示本轮 Wi-Fi 名称”已接入，44项相关回归通过；旧exe未打包。主窗口一键采集/恢复常驻服务尚未集成。 |
| 当前硬件与窗口 | 主上位机已打开，服务到时停止 | RX1A为2.4GHz天线，手机热点已开；本次无发射。SSID采集结束曾恢复3.84MSPS/本振96.05MHz并读回gpio/source/audio=0；随后既有900秒常驻服务重新运行，核对时TCP9000已连接，不以早先停止值充当当前状态。最终900秒服务已自动结束；新增独立停止检查PASS，gpio/source/audio=0，见j_ssid_main_open_postflight.json。再做广播须先确认恢复低频天线。 |

证据：`board/measurements/j_ssid_live_r1/`，说明：`docs/j_ssid.md`。历史热点能量对照的未确认结论保留，不改旧验收；本次仅以新信标解码和用户确认作为名称显示证据。

以下为历史记录。

# 当前补充检查点：现场数据与广播录音（2026-11-04）

以用户最新要求及 runbook/J_live.md 为准。旧回放兜底要求作历史保留，不用于现场演示。

| 子项 | 状态 | 结果 |
|---|---|---|
| 主界面现场数据门禁 | 软件检查通过，整机功能待逐项接入 | 禁止历史会话/资料自动加载，过期遥测清空；完整回归859通过/19跳过（最后同步录音扩展之前）。旧exe未替换。 |
| 匹配2.4GHz天线热点复核 | 采集通过；热点身份未确认 | off/on各13窗口、208段，有能量变化但有饱和与增益变化，无协议/SSID解码。 |
| 现场广播录音基础 | 短测数值通过，听音待确认 | r1溢出FAIL；r2独立录音通过；r3板载播放期间同步录制，WAV约5.167秒，零观察到的溢出/音频下溢。用户撤回了先前听音答复。 |
| 演示内录制/停止/播放/回直播 | DOING | 专用脚本与本轮播放器已有；主界面按钮尚未集成，不声称已完成。 |
| 当前运行状态 | 主上位机已打开 | 用户要求打开主界面，已启动既有i2_r2仅接收resident（900秒），PC已连接；默认待机静音，当前接线恢复低频广播天线。 |

总摘要：board/measurements/j_live_progress_20261104.json；当前详情见CONTEXT顶部。下方旧状态为历史记录。

# 执行状态（由代理维护，每完成一步更新一次）

## 当前执行点：J 修订 v4，十页风格已确认、继续集成（2026-11-04）

以 `J_polish.md` 文末修订 v4 为准：十功能页，52 项主成果拆为 63 个独立入口，导航不触发板端，页内开始才执行。
取消讲解模式/提词/双窗口/计时/J6；仅接收与真实数据回放，不发射。
S1接线与仅接收授权不变；此前最后独立停止 GPIO/SRC/audio=0。本轮只操作电脑端，没有重新连接板卡，当前硬件状态尚未重新读回。

| 步骤 | 状态 | 当前结果 / 后续条件 |
|---|---|---|
| J0 | DONE | 已分主题保存源码/方案及G4/I2小JSON/SHA；大文件不删除，14,115文件增量ZIP逐项摘要通过，1,149,485,552字节，E盘副本SHA256一致。首轮Tcl捕获失败保留，关闭捕获后两次全范围823通过/19跳过。见j0_inventory/j0_regression/j0_snapshot/j0_external_backup及SHA256；恢复须配套原F0包。 |
| J1 | TODO | 正式v3及一键入口；v2回退保留，先读协议与场景能力，不虚称tone/pano/回放可用。 |
| J2 | DOING（风格已确认） | 十页/63 入口、资料浏览/本地 WAV、五场景命令门禁及待机确认后回放/关窗已实现；用户已批准十页风格。随后已去除队伍名，使用中性标题，预览 host_j_v4_r4；该修改回归842通过/19跳过。新布局真板尚待验证，动态功能继续集成。原离线清单/测量保留，不代表全部动态功能完成。 |
| J3 | TODO | 三音与F3实测数据回放，不发射。 |
| J4 | TODO | 参考全景与实时补扫，独立参数恢复检查。 |
| J5 | TODO | 十页专用兜底、两遍走查、用户确认及备份；host_coverage 已建立且缺口明确。当前通用 FM 会话不充当各页专用兜底。 |
| J6 | CANCELLED | 按用户修订不再添加新功能。 |

I2历史短测：四场景各3次共12次就绪，GUI无错误，141.547秒/1204条频谱；
整体FAIL（真板孪生视口923px<1100px），原r1失败保留，人工目视待补。
119份带摘要文件一致；汇总 `board/measurements/i2_acceptance_summary.json` 及SHA256。
未完成十次P90、七场景/九页走查、长测或新exe；不得沿用旧显示确认填补本轮验收。

## 展示定稿 I 阶段准备

I0两候选实测与选型已完成（有限制）：配置S选S1，优先广播；S1空口目标FAIL、S2广播FAIL、两者热点归因不确定均保留。空口展示采用明确标REPLAY的降级路线，素材接入待I1/I2/I6。用户已恢复S1并授权后续仅接收，I1开始独立候选开发。详见i0_antenna_s.json及SHA256。

| 步骤 | 状态 | 当前结果 / 后续条件 |
|---|---|---|
| I0 | DONE（有限制选型） | 选S1固定展示：FM导频最低25.153/中位34.751dB，用户确认清楚；S1空口17.721dB未达25dB，S2空口50dB衰减时29.472dB通过但FM门控放音0秒且用户确认无广播。两者热点off/on均仅环境能量、归因不确定，未解SSID。原始IQ/独立复算/JSON/图/SHA256和停止检查通过，i0_antenna_s.json汇总；天线指南与协作记录已更新。空口展示要求REPLAY，封装和按钮接入仍待完成。已收到恢复S1的用户确认，原选型测量不改。 |
| I1 | DOING（五场景短测PASS） | 第三轮随机50次均READY，五场景各10次；板内P90：check 0.551s、fm 0.234s、listen 2.200s、perf 0.264s、idle 0.251s。overlay/RF/模型/codec各1次，233.975s运行结束GPIO/SRC/audio=0，174文件SHA256取回一致。SSH往返P90 4.875s，不冒充点击端到端达标。前两轮启动失败保留；后续−9/−6dB独立试听用户确认广播连续但偏小，ROUT2=0dB/OUT1=−6dB独立60秒全自动通过，用户确认音量合适；源码默认已接入，下一部署生效。最终146 passed/1 skipped。pano/wifi/REPLAY及完整预检性能页未完成。见i1_acceptance_summary.json及docs/i1_resident_service.md。 |
| I2 | FAIL（短测部分通过，后由J v2取消） | 已保存hostlink直连、严格关联请求、回放门禁和历史讲解入口；12次切换就绪但宽度923px未达1100px，目视待补。J v2后续移除讲解UI，改九功能页。 |
| I3/I4 | TODO | 播放状态与短片段录音；WiFi先探测，不承诺信标解码结果。 |
| I5 | DOING（复用H1结果） | A/D完整全景和逐段PC显示已存档；≤5秒讲解快扫及独立RF恢复读回待开发。 |
| I6 | TODO | 兜底与完整走查后置，当前不进行彩排。 |

## 当前执行点：H阶段（2026-11-04）

用户要求彩排与一小时长测后置，优先功能；H_interactive.md 接续 F4。固定100MHz位流，配置A持续授权，只接收，不启动PC连续音频。

| 步骤 | 状态 | 当前结果 / 后续条件 |
|---|---|---|
| H3a | DOING | 路由器设置说明 docs/h3a_router_setup.md 已准备；二维码按钮已实现、22项相关测试通过；真实路由器接入待用户配置。 |
| H1 | DOING | 原55段A全景78.350秒、独立IQ复算PASS；10LO实测分解已存。快速49段A扫描43.063秒（缩短45.04%），44,200格点无缺口，PS频谱落盘及停止PASS，未达到10秒。第二轮A扫描42.225秒、49条实时事件被GUI消费且最终摘要校验成功；D组243段206.608秒、218,800格点无缺口，243条GUI事件/最终校验/独立停止PASS，用户观察“逐段增加”；A≤10s/D≤30s均FAIL；quick、点击定点识别、完整RF参数独立读回待完成。 |
| H2 | TODO | 常驻serve/scene及现场手动控制台尚未实现；G5彩排不阻塞开发。 |
| H3b/H3c | TODO | 依赖H1/H2；新配置B/D仍须用户确认，不根据文档授权措辞自行发射。 |


## 演示增强 G 阶段（2026-11-04；与下方历史 G0–G3 门禁表不同）

执行顺序：G0→G1→G2→G3→G4→G5→F4→F5→F6；依据 `G_showcase.md`，冻结 100MHz/3.84MSPS 位流。历史 FAIL 不变。

| 步骤 | 状态 | 当前结果 / 后续条件 |
|---|---|---|
| G0 | DONE | 新整卡镜像31,266,439,168字节，分区签名及完整SHA256通过；用户确认SD回板、已上电、配置A。正式selftest PASS，温度43.926°C、TX双路89.75dB，停止GPIO/SRC/audio=0。证据 `board/measurements/g0_acceptance.json` 及SHA256。 |
| G1 | FAIL（功能PASS） | 最终代码A组3遍/12段完成，116.731/109.500/110.217秒，平均112.149秒（历史173.821秒）；切换中位4.693秒/最大5.001秒，未满足全部时长及中位目标。overlay/模型各载入1次，RF重初始化9次以保留逐段GPIO复位；全部停止归零、TX双89.75dB、音频零下溢。播放PCM无读回口，WAV不生成。两轮原始证据保留，最终460文件摘要通过，见 `board/measurements/g1_acceptance_final.json` 及SHA256、`docs/g1_persistent_runtime.md`；B组留G5实测。 |
| G2 | FAIL（功能PASS） | G2第三轮600.929秒完成，785次提交零错误，最低38.965fps；用户确认画面正常。UI总耗时中位36.108ms/P95 165.069ms，未达25/40ms，记FAIL（功能PASS），不增加第四轮。最终停止GPIO/SRC/audio=0，冻结LCD驱动/位流未变。证据board/measurements/g2_acceptance_final.json及SHA256，原始目录g2_monitor_r3_raw。 |
| G3 | FAIL（功能PASS） | G3正式420.416秒完成；十次PC断开≥30秒重连通过，网页/SSE和4/4非法命令拒绝通过。LCD中位40.235→40.877fps，网络单核3.056%，4190快照/9.966Hz，零丢帧/溢出，独立停止GPIO/SRC/audio=0。精确PL帧→PC延迟未认证，G3记FAIL（功能PASS）；原始证据g3_board_r1/，汇总g3_acceptance_final.json及SHA256。 |
| G4 | DOING | 采用G4+三栏中文布局；旧G4a短测20epoch读回一致、用户确认点击同步，点击531/736.4ms仍FAIL。新布局离线检查通过，四图风格已获用户确认；真实字段与新版exe短回放通过；DMA长测及PC音频未通过，30分钟与完整演示仍待完成。 |
| G4a | FAIL（功能PASS） | 150秒短测：20个随机epoch BRAM与网络字节一致；点击19/20匹配，中位531ms/P95 736.4ms未达。用户确认孪生显示与点击同步正常，未确认PC听音。g4a_board_r1/validation.json及SHA256。 |
| G4c | FAIL（功能PASS） | 用户确认中文、放大和LCD点击联动正常；180秒真板六次点击全正确，更新9.436fps，点击中位329ms/P95 633ms未达；刷新回调P95 7.606ms、切页最大37.112ms。停止GPIO/SRC/audio=0。g4c_acceptance_r1.json及SHA256；不为15fps追加调参，继续G4d。 |
| G4d | FAIL（字段PASS，音频受阻） | 45秒观察82条AMC/36条遥测，Top-5及整机CPU/内存检查PASS；124文件发布摘要通过。DMA三轮：首次溢出、10秒短测通过、600秒请求提前溢出（最后无溢出记录53.513秒），不追加第四轮。PC音频保持禁用，FM/WAV模块仅离线测试。新版exe20秒真实A会话回放零错误，352文件压缩包已生成；83项回归及1项打包证据测试通过。停止GPIO/SRC/audio=0。见g4d_acceptance_final.json及SHA256、docs/g4d_progress.md。 |
| G5 | DEFERRED（自动FAIL保留） | 用户要求彩排后置，转F4；show已部署，A两轮原始证据保留，第二轮音频计数完整性失败，未完成三遍。用户观察切页/LCD/广播正常；停止GPIO/SRC/audio=0。docs/g5_progress.md。 |
| G6 | SKIPPED | 默认不改调色板或构建位流，须用户书面授权。 |

本轮备份是G0恢复测试前的镜像，不含后续软件改动；暂不为刚完成的G0自检再次要求取卡。G5后按规则再做整卡备份。镜像结构/哈希验证不证明文件系统健康或恢复成功。板端时钟仍为2021年，使用主机时间与boot_id关联。第一次仅文件取回时遗漏scp递归参数，未重新板测，修正取回后5个板端文件已留存。

当前用户调整：G5彩排及1小时长测后置，先完成F4配置A扫频全景与上位机文件查看；备份阻塞已解除。

## F4离线基础准备完成，SD备份重试待完成（2026-11-04）

用户授权备份期间继续电脑端任务；随后报告Read约29%处错误1117（I/O设备错误），建议新文件名、更换USB接口/读卡器，不能将中断镜像当作成功备份。本轮未访问开发板、源SD或不完整镜像，未改现有monitor/发布入口、RTL、位流、模型及CFAR。

新增独立panorama/stability模块和复现工具：17项针对性测试通过；合成A/D分别55/274个LO，无覆盖缺口，谱峰误差最大5kHz；3601条合成遥测验证整小时判定器及流式SHA256，不是一小时实测。完整PS/工具回归622 passed、18 skipped（logs/F4_regression_r1.log），新增文件Python3.8语法、112文件发布清单验证通过；没有构建或部署发布包。证据board/measurements/f4_offline_r1/result.json、f4_offline_software_r1.json及SHA256，文档docs/f4_offline_preparation.md。真实原始DMA扫频和monitor流式长测入口尚待接入；F4保持BLOCKED-HUMAN，备份、配置A确认和真实板测未完成，不把基础模块完成记作F4 DONE。

## F3收尾完成，等待F4人工准备（2026-11-04）

F3正式状态FAIL，功能PASS：B组第二次运行连续3遍/12段全部完成，104个板端文件SHA256一致；整场481.565秒，每遍段耗时159.817/156.827/156.344秒。最低TX衰减40dB、最高RSSI−58.5dBm、最低36.563fps、最高65.950°C；发射段退出ENSM=ALERT及双TX89.75dB，所有段GPIO/SRC/audio均0，最终只读停止复核PASS。用户回复“画面没问题”，仅记录实际观察画面正常，不扩大为完整三遍逐项人工确认。

数字注噪参考10dB下十类83.4%、八大类86.0%；八大类未达到90%，宽带标定三轮未达到25dB，Pd/Pfa未校准，每遍耗时超过约2分钟目标。原始循环波形窗口不是独立试验，数字参考SNR不是校准RF SNR。首次演示FAIL及所有历史FAIL保留；只修复PS启动/退出协议，没有综合、布线、训练或调CFAR。

最终PS/工具回归605 passed、18 skipped（logs/F3_final_regression_env.log）；第一次全量回归Windows Tcl初始化/捕获失败日志保留，环境修正后通过。独立F3发射库e89a…d271、正式接收库b329…1683，勿混淆。汇总board/measurements/f3_acceptance_final.json及SHA256，文档docs/f3_ota_demo.md，协作记录report/llm_logs/F3_ota_demo.md。

当前仍为配置B-直插且测试已停止。F4尚未进行射频；等待F3整卡备份及配置A确认（RX1A接选定20–512MHz天线、TX1A空，J22/2.5V不变）。取卡前必须sync/shutdown并确认halt，再断电；不能直接拔卡。备份后确认A及上电状态才恢复接收，之后换D另行确认。F1部分旧NPZ未在本地的问题仍待交付复核，不宣称全部历史证据完整。

以下检查点是历史记录，不覆盖本节当前状态。

## F3 演示测试进行中（2026-11-04）

已核验实测数据：10类各50窗口，数字注噪参考10dB时10类83.4%（达到80%）、8大类86.0%（未达到90%）；循环波形窗口不视作独立试验，参考SNR不视作校准RF SNR。宽带标定三轮未达25dB，不再加轮。Pd/Pfa没有完成校准认证，最高注噪档单音命中比例50%，不得写成全档100%。原始证据保持不变。

已修正B组退出的显式ENSM/衰减读回、注噪幅度归零、异常清理及DMA隔离保留；393项软件测试通过、18项略过，122文件Python3.8语法通过。独立F3库取回SHA256与原验收一致；110文件发布包已安装，旧版回退目录保留。启动前板端无测试进程，GPIO/SRC/audio=0。证据f3_software_r1.json、f3_library_retrieval.json、f3_deployment_r2.json及SHA256。

现运行正式入口demo B --cycles 3，PID10361，板端测量目录demo_20211118T230557Z_6afbc313；主机启动时间2026-11-04 00:20（板端历史时钟2021，不作真实时间）。配置B-直插沿用用户确认，仅2.45GHz、下限40dB。首段7已PASS，后续仍运行；已请用户目视标题/FRAME/发送类别/列表及点图，人工确认待回复。日志在板端release/v2/logs/20211118T230557Z_6afbc313.log，启动证据f3_demo_r1_start.json。不得宣称F3 DONE，不进入F4，不复位/断电。

额外核查：宽范围历史sidecar检查发现F1板验收副本中部分原始NPZ未在本地，不能宣称所有历史证据完整；本次F3范围47份sidecar全部通过，F1原始数据完整性留交付复核。

## F3进行中：直插天线及独立发射保护已核查

用户明确确认两根2.4GHz折叠胶棒直接接TX1A/RX1A，间距约2–3cm；采用99_finish更新后的40dB下限，不使用电缆直连。板端独立F3库编译通过，正式接收库哈希不变；最大衰减预检通过：双TX89.75dB，结束ENSM=ALERT、GPIO/SRC=0。MODE3目前仅完成控制读回，不能记注噪功能验收。证据f3_library_r1.json、f3_preflight_r1_execution.json及SHA256；原X/Y/F2不足保留。正在继续看门狗及短时标定，未完成G3/演示B。

## F2验收收尾，等待F3配置B确认

F2主功能PASS：正式A组连续3遍/12段完成、466文件SHA256核验通过，三次音频实际放音28.958/28.954/28.947秒、零下溢；段间及最终GPIO/SRC/audio均0、codec静音。用户明确回复“全部正确”。监测最低39.289fps、最高65.581°C、零处理错误；TX仅接收段均89.75dB，测试源段RF复位。

整组每遍平均173.821秒（3遍521.462秒），不满足约1.5分钟目标；连续WAV未实现，冻结四色LCD不能绿色TX OFF/全宽顶部标题。因此F2整体记FAIL并保留功能PASS，不自动追加重构/板测，按99_finish及用户要求继续F3。证据board/measurements/f2_acceptance_r1.json、f2_demo_r1/verification.json及SHA256；说明docs/f2_demo_a.md。73项针对性、365项PS/发布回归通过；补充单段/循环/3次调度12通过、18项重复组合略过。F1回退目录已保留。开发板保持上电，运行已安全停止。F3尚未发射，须确认2.4GHz双天线配置B（距离至少30cm）。

## F2 A组首次板测进行中（配置A已确认）

用户已确认配置A未变并允许F2仅接收、测试源显示及−12dB喇叭演示。73项针对性及365项PS/发布回归通过，90文件发布包哈希安装通过，F1目录已保留。初次部署因sudo需要密码在安装前失败；依既有授权使用默认凭据完成部署，未改sudo策略。证据f2_software_r1.json、f2_deployment_r1.json、f2_demo_launch_r1.json及SHA256。

正式入口sentinel.sh demo A --cycles 3已启动（PID3574，板端logs/F2_demo_r1.log）；首段自检完成且GPIO/SRC/audio均0，第二段监测开始。等待三遍结果及用户本轮目视/听音；未宣称F2通过。现有WAV连续录制未实现，冻结LCD仅四色，TX OFF为青色；每段重载/初始化会增加总时长，须实测说明。源码位于实际Git仓库F:/.zss/zss，启动目录F:/project为旧规划资料，二者不是父子目录。

## F1已完成，进入F2电脑端开发

用户确认LCD正常、−12dB广播清楚。正式发布、selftest和受控stop均PASS；音频运行103.130秒、实际出声102.085秒，零下溢，退出codec静音及GPIO/SRC/audio=0。证据f1_board_acceptance_r1.json及SHA256，详见docs/f1_acceptance.md。F1 DONE；F2 DOING（电脑端），继续配置A，后续上板前再次说明并确认。


用户随后确认“LCD显示正常”。monitor已通过正式stop入口受控停止，GPIO/SRC/audio均0；证据f1_monitor_stop_r1.json及SHA256。已启动sentinel.sh listen 95.8（PID1726，默认−12dB，配置A，最长300秒自动静音退出），初始遥测显示约41fps、音频48004帧/秒、零下溢、TX双路89.75dB。等待用户试听确认；测试中不复位或断电。


## F1部署与自检通过，等待监视画面人工确认

2026-11-03用户确认断电插卡就绪后上电；SSH正常，boot_id=30cc40d8-3cb0-49ab-85bd-4c7445a962a7。F1正式包87文件与.so哈希安装通过；板端selftest PASS，温度50.69°C、RSSI −91.75dBm、TX双路89.75dB、导频突出度32.04dB，停止GPIO/SRC/audio均0。证据f1_deployment_r1.json、f1_boot_preflight_r1.json、f1_selftest_board_r1.json及SHA256。启动仍有FAT未正常卸载和journal恢复告警，未修复；UART仅捕获登录提示，完整启动信息来自dmesg。板端时钟为2021，证据按主机时间/boot_id/单调时钟解释。电脑端两次前置失败为导入路径/GBK解码，发生于硬件调用前；日志F1_selftest_r1/r2保留，r3板端自检通过。monitor r1未提权无法写root日志、未启动；r2已提权启动（PID1471），最长300秒自动结束。等待用户确认屏幕，之后执行sentinel.sh stop验证，再做−12dB试听。F1仍DOING，F2未开始；禁止断电/复位。


## SD整卡读取成功后的最新检查点

用户已确认读取成功。E盘zip目录下 zss_sd_F0_retry1.img 已完成校验：31,266,439,168字节，分区布局、FAT/ext签名及完整SHA256通过；核验期间镜像未变。证据 board/measurements/f0_sd_retry1_verified.json 及.sha256，日志 logs/F0_sd_retry1_verify.log。失败的旧镜像和X0备份保留。没有访问源SD或板卡；未做恢复演练或文件系统健康检查。下一步等待用户安全弹出、确认板卡断电后插卡、配置A接线就绪；先不开机，准备串口采集后再通知上电。F1仍DOING，部署、自检、停止读回及−12dB试听待执行。


## F阶段最新检查点（2026-11-03）

SD读取期间离线补充：112项黄金模型及339项PS测试通过；142份黄金文件哈希/大小一致，历史v2 CFAR18案例149886字重比零差异；2份历史原始IQ快照完成独立PFB参考复核，16份历史PFB IQ按F1质量条件重放（差组0/8、好组8/8）。本轮未重新运行RTL仿真或构建。完整675项回归三轮结果分别662通过/13失败、674通过/1错误、671通过/4错误；未初始化AMD环境及Tcl环境异常保留，第三轮Tcl路径由执行命令错误设置，不能宣称全量通过。不再追加第四轮。详见docs/f1_offline_simulation.md和sim/results/f1_offline_evidence_final.json及SHA256。未访问板卡/SD，F1保持DOING。

唯一执行方案为 `runbook/99_finish.md`，下方X/Y/Z记录保留为历史，不再据旧TODO/FAIL自动追加实验。固定 `board/overlay/sentinel_v2_100m`、100MHz、3.84MSPS；F0期间仅本机归档，无射频、音频、训练或构建。F1–F3若被实际PL缺陷阻塞，重建前须用户批准。

| 步骤 | 状态 | 内容及证据 |
|---|---|---|
| F0 | DONE | 技术验收PASS：初始33修改/213折叠未跟踪（展开643），分主题提交；93个历史文件只移除索引、本机和快照保留。完整快照9,663,493,316字节、14,250成员全部SHA256通过；解压目录312测试通过。用户提供E:\zip，完整ZIP复算SHA256一致；E与F分别在物理磁盘0/1，sidecar齐全。docs/snapshots.md、f0_external_backup.json及SHA256。用户已断电，提醒并等待SD整卡备份人工操作；本次未连接开发板，F1尚未开始。 |
| F1 | DONE | 正式发布版87文件哈希安装、selftest、monitor/stop、−12dB喇叭试听均通过；用户确认LCD正常、广播清楚。证据f1_board_acceptance_r1.json及SHA256，docs/f1_acceptance.md。 |
| F2 | FAIL | A组主功能及人工确认PASS，连续3遍/466文件哈希通过；平均173.821秒超目标，连续WAV/绿色状态字未实现。f2_acceptance_r1.json及SHA256、docs/f2_demo_a.md。已安全停止，继续F3。 |
| F3 | FAIL | 功能PASS：B组三遍/12段、104文件哈希通过，用户所观察画面正常；十类83.4%、八大类86.0%，Pd/Pfa未校准、宽带标定未达标、每遍156–160秒超目标。605测试通过、18略过；f3_acceptance_final.json及SHA256、docs/f3_ota_demo.md。已安全停止，历史FAIL保留。 |
| F4 | DOING | A组55LO实测78.350秒、原始IQ独立复算PASS；快速49LO实测43.063秒、无缺口但H1时间目标未达。PS发布已核验，最终停止GPIO/SRC/audio均0。A/D逐段显示及最终校验完成；H1时间目标、quick和点击定点识别未完成，一小时长测后置；彩排/长测按用户要求后置。见 docs/f4_panorama_progress.md、board/measurements/h1_fast_comparison_r1.json及SHA256。 |
| F5 | TODO | 按G_showcase调整：报告增加UI/hostlink/PC章节，E11/E12和S15/S16；集中说明未达标项。 |
| F6 | TODO | 按G_showcase调整：增加PC离线回放、exe、三机位录像；最终交付和SD备份，不推送GitHub。 |

100MHz回归与质量门控监听已有实测及用户确认；历史FAIL保持原结论。原始IQ噪声曾间歇出现，LCD开/关均有好坏样本，具体干扰源仍未定位；不能表述为已证明“与LCD无关”。音频链路300.0989秒、实际放音299.0467秒，不等同质量放行后连续300秒。

## 100 MHz上板回归（2026-11-03，最新）

用户已确认配置A并授权非负裕量开发门槛。`sentinel_v2_100m` r2已独立打包，bit/HWH直接从同一XSA提取，头部时间不同的两次bit导出其配置payload完全一致。整体WNS/WHS=+0.210/+0.030ns、TNS/THS=0；原Z10/T5的+1ns FAIL保留。开发审计明确保留CDC告警、AD9361板外全PVT未签核及2ns PCB差预算的限制。物理边沿解析首版漏算最后一段时钟网延迟，已隔离到`build/reports/sentinel_v2_100m/package_rejected_parser_r1/`且从未部署；修正解析器3项测试通过，LRCK最坏差9.894ns、DAC setup/hold下界152.338/152.412ns。

- 数字回归DONE：`board/measurements/y3_v2_selftest_r1_execution.json`及SHA256。实际加载100MHz新位流；单音0bin误差、三音3目标，四帧8192字回放逐字一致，同一boot，退出GPIO=0、SRC关闭、音频关闭。
- 接收接口回归DONE：`board/measurements/y3_v2_rx_interface_r1_execution.json`及SHA256；3.84MSPS，前后500ms PN四路全0，16×16扫描153点通过，原设置data窗口16档、clock窗口4档，寄存器精确恢复0x02。双TX衰减89.75dB，退出GPIO=0、SRC关闭、音频关闭。仅内部RX诊断，不是发射或全PVT验收。
- 真实接收/识别显示功能回归DONE：r1/r2启动即报ADC FIFO历史溢出，已停止并保留FAIL。r3仅修PS启动协议：AD9361初始化及3.84MSPS配置完成后，源保持停止，AXI ADC RSTN由3→2→3（MMCM不复位），再清PERF并确认无故障；运行中的故障保护不变。120.467秒、191份捕获逐字/哈希校验通过，94条遥测无溢出，TX双路89.75dB，退出GPIO/SRC/audio均0、boot不变；用户确认FRAME增加、频谱/瀑布及列表/点图正常。中位28.988fps（最低27.711）仍<30，首次PS观察到上屏中位534.941ms；95.8MHz仅1份捕获且未识别为FM，不能据此声称准确率通过，Y2仍FAIL。证据`board/measurements/y3_v2_receive_regression_r3.json`及SHA256；503项软件测试PASS（Windows Tcl需pytest -s）。
- 喇叭1kHz测试：r1/r2在播放前因PYNQ2.7未绑定AXI IIC2.1驱动失败；r3因ES8388软件复位未释放失败。修复后r4数字验收PASS；用户要求放大并授权r5（−15dB，3秒），r5实测3.000489秒、144392个I2S帧、零下溢，退出GPIO/SRC/audio均0，用户明确确认“听到了，声音正常”。人工证据为board/measurements/y3_v2_tone_human_r5.json及SHA256；原失败收据保留。
- Y3 FM监听FAIL（本轮三次板测）：配置A，95.8MHz，TX双路89.75dB。r1因LCD瞬时29.790fps自动停机；r2改BUS_PHASE=2，30.133秒量化短测通过、最低40.782fps且零下溢，但用户报告噪声较大或断续。r3改用历史FM录音的96.05MHz LO，用户报告“基本上全是噪声，听不到内容”；168.566秒时主动发送SIGTERM提前停播，零下溢、最低40.539fps，codec已静音、GPIO/SRC/audio均0，postflight PASS。原因为何尚未确定，不能把零下溢当作音质通过，也不能宣称5分钟完成。不自动追加第4次板测；后续只做离线诊断或按人工决定继续。见y3_v2_audio_r1/r2/r3_execution.json、r2/r3_human.json及各自SHA256。

以下旧检查点是历史过程；关于“尚未加载v2”的陈述不再代表当前状态。

## 本轮功能接续与纠正（2026-11-03）

用户确认FPGA上电，SSH可达；再次明确150MHz既有功能应直接复用，优先100MHz位流检查与原功能回归，不重写已验证算法。本轮未改RTL/约束，v1b/v1d六个bit/HWH/XSA哈希全部保持一致。新增可选FM监听会话接入monitor_x5（默认不启用），支持与捕获/识别/UI同跑、退出前错误快照和先静音后关RF。462项PC回归通过；板端Python3.8.2使用假I/O兼容检查第2轮通过，第1轮硬件锁文件前置不适用的失败保留。未加载位流、未射频或喇叭播放，Y3仍DOING；+1ns门禁与CDC/I/O待审计不变。新入口仅作后续准备，不作为迁移100MHz的必选项。详见docs/y3_v2_integrated_listener.md及sim/results/y3_v2_integrated_software_r1.json/SHA256。

## 100 MHz开发恢复检查点（2026-11-03）

用户已明确授权以WNS/WHS≥0推进开发，+1ns留作后续优化；Z10/T5历史FAIL保留。用户再次确认配置A（RX1A接20–512MHz、TX1A空），仅接收授权有效。原工程已备份到仓库同级backup_before_inplace_20261103_175628。

音频局部修复r1失败且未部署；r2从原T5实现重新出发，只解布serializer三条输出网，不重跑综合。r2全局WNS+0.210/WHS+0.030ns、TNS/THS=0、布线错误0；69条bus-skew最小裕量+3.216ns；LUT37982、BRAM92、DSP79。所有DRC条目为Warning。20ns输出延迟须计入max-delay预算，不能把粗略MCLK hold检查当作ES8388真实10ns验收；实际边沿审计与产物一致性核验仍在进行。日志logs/Y3_v2_audio_route_repair_r2.log、build/reports/sentinel_v2_100m/audio_route_repair_r2/。新增板测入口Python3.8语法/导入检查通过，100项相关PC回归通过；尚未加载v2、尚未射频或播放，Y3仍DOING。

## 最新开发决定（2026-11-03）

用户已明确采用100 MHz继续功能开发，后续可回到具体失败路径优化。当前开发基线为sentinel_v2_100m；v1d保留作已验收回退。T5的+0.210/+0.030ns不等于Z10的+1ns门禁通过，原FAIL、部署收据和板测要求不变。本轮已迁移识别/屏幕监测与隔离部署入口，显式选择v2并记录100MHz时钟；437项PS/工具回归通过。未加载v2、未进行射频或喇叭播放。执行顺序、现有音频接口与后续回归见docs/v2_function_development.md。下文“继续v1d开发”是此前决策，现由本段取代。证据sim/results/v2_function_bridge_r1.json及SHA256。

状态取值：`TODO` / `DOING` / `DONE` / `FAIL` / `BLOCKED-HUMAN` / `SKIPPED`
## 当前执行点（2026-11-03，Z10三轮FAIL、T5单因素对比FAIL；继续Y3功能开发）

| 子项 | 状态 | 证据与下一步 |
|---|---|---|
| Z10 时序收敛 | FAIL | 三次完整实现已结束：r1 WNS−0.774/WHS+0.050ns，r2 +0.012/+0.028ns，r3 +0.026/+0.042ns。r3基础时序通过，距Z10全局WNS≥+1ns仍差0.974ns；重复主时钟已消除，旧FIFO复位旁路和黑盒均0。LUT39,262（73.80%）/BRAM92/DSP79；CDC与板外约束仍待逐组复核。265项PC回归PASS；冻结硬件输入与v1b/v1d产物哈希通过。证据board/measurements/z10_final_r3.json、z10_v2_audit_gates_clock_root_review_r1.json及SHA256，详见docs/z10_t5_next.md。未签发v2收据、未部署、未播放；原三轮已封存，后续T5独立计次，见下行。 |

| T5 功耗优化单因素对比 | FAIL | 第1轮、总第4次完整实现；复用综合并关闭两步power_opt。最终WNS+0.210/WHS+0.030ns，基础时序通过、距+1ns目标仍差0.790ns；LUT37,982/BRAM92/DSP79。最差setup转为CPU 100MHz域高扇出复位网（298负载、走线8.813ns），不是原RX计数器CE路径。独立审计的自动门禁仅WNS目标失败，CDC/外部约束仍需人工复核。434项PC测试在Windows禁用pytest捕获时通过；Y3 CFAR合同已修复为驱动版本0x43460002，未上板。证据board/measurements/t5_result_r1.json、z10_v2_audit_t5_r1.json及SHA256；Z10原三轮FAIL不变，v2不得部署，继续已验收v1d的PS/UI功能开发和Y3降级评估。 |

继续按 95_final.md 推进；旧 X0–X4 正式状态不变，不重新训练或追加调参。用户已取消功分器/配置E，采用A/B两组演示。配置A的X5仅接收授权有效，不推送GitHub。v1d整机r2及独立审计PASS；120秒实采完成且安全停止，Y2帧率/已知FM识别指标FAIL。用户已确认旧v1d界面计数增加、列表和点图可见、画面正常；该目视不覆盖识别率、量化帧率或Z2新UI。Z2整机r1失败，已有DCP链接连续两次崩溃，原因未明，恢复分支停止且未上板。保留已通过时序的v1d功能基线，Z2专属八色/事件区未完成。FM/I2S组件通过不代表连续播放。详见docs/y2_visual_z2_progress.md与docs/y3_audio_progress.md。

### Y 阶段衔接

2026-11-03 Y3诊断最终检查点：质量门控r3完成300.0989秒链路测试，初始静音1.0522秒后连续放音299.0467秒；665/665质量快照可信、最低40.3784fps、零下溢，用户在测试中确认广播清楚/轻微底噪/无明显断音。退出codec静音、GPIO/SRC/audio=0。证据y3_noise_stability_human.json、y3_v2_audio_r3_quality_execution.json及SHA256；无需HDL或重新布线。Y3历史FAIL保留，严格300秒全程出声尚差约0.95秒，不自动追加第四轮；具体干扰源未确定。下次播放按用户要求小幅提高音量，当前仍−15dB，须先同步修改并验证软件音量保护范围。

2026-11-03 Y3追加诊断：用户授权接线不变优化。原始ADC即出现间歇性噪声，RX PN9四路0错误；LCD开/关均存在好坏快照，具体干扰源未定。新增可选立体声导频质量门控，无HDL或位流变更。门控r1遥测时间戳错误已修复且失败保留；r2 30.0226秒、实际放音28.9677秒、75/75可信质量样本、最低40.7784fps、零下溢，用户确认广播比此前清晰。旧每秒固定样本数门槛造成原回执FAIL，独立实际间隔覆盖复核通过，原证据保留。85项针对性测试通过；安全静音并停止RX。详见docs/y3_noise_diagnosis.md、y3_noise_diagnostic_checkpoint.json及人工回报JSON/SHA256。5分钟及干扰源未完成，Y3正式FAIL不变。

| 步骤 | 状态 | 备注 |
|---|---|---|
| Y0 状态与归档 | DONE | 原提交5086ec3保留。Z7复核：PFB第3轮PASS及7份日志/报告哈希一致；新增6已修改+102未跟踪文件清单，归档Y3在途工作并统一板载喇叭方案。详见docs/y0_z7_rebaseline.md及y0_z7_inventory_before_1.json。不把状态归档等同喇叭功能验收。 |
| Y1 RF带宽复测 | SKIPPED | 可选项暂略过，优先识别上屏；尚未复测、未更改既有RF带宽，不重写X1结论。 |
| Y2 识别上屏 | FAIL | PFB/NCO最终PASS；整机r2 WNS+0.092/WHS+0.037ns。120.221秒194捕获校验通过，首次PS观察至上屏中位481.181ms，28.992fps<30；95.8MHz完整五票FM为3/9=33.33%<80%。原v1d目视PASS。Z2组件通过，整机r1失败，已有DCP两次链接分别EXCEPTION_BREAKPOINT/EXCEPTION_ACCESS_VIOLATION，未产生完整DCP/位流，停止恢复、不上板。保留v1d，Z2新配色/事件未完成。x5_station_r3_analysis.json、y2_visual_link_1.json、z2_link_failure_1/2.json及SHA256。 |
| Y3 FM板载喇叭 | FAIL | 100MHz开发基线已上板；1kHz r5（−15dB、3秒）数字和人工出声通过。FM三轮：r1帧率门禁失败；r2 BUS_PHASE=2、30.133秒量化通过但主观噪声大；r3 LO=96.05MHz仍基本全是噪声，168.566秒主动停止。两次后者零下溢、最低40.782/40.539fps；静音及GPIO/SRC/audio关闭均通过。5分钟与主观音质未通过，三轮结果封存，不自动追加板测；docs/y3_audio_progress.md、y3_v2_audio_r2/r3_human.json及SHA256。 |
| Y4 空口闭环 | TODO | 配置B/C须用户确认后发射；不额外训练。 |
| Y5 扫频/稳定性 | TODO | 配置A/D，换线须人工确认。 |
| Y6 对比/技能包 | TODO | 据实列出未达标项。 |
| Y7 交付 | TODO | GitHub发布仍须用户给定地址及授权。 |

| 步骤 | 内容 | 状态 | 时间 | 备注 |
|---|---|---|---|---|
| X0 | N4归档、默认参数、温度与SD备份 | DONE | 2026-11-03 | 整卡31,266,439,168字节/SHA256通过；180秒默认3档RF完成，161条遥测无采样溢出，中位49.38fps，43.31–52.66°C。用户确认画面正常；退出GPIO/SRC均0。215项回归、40项N4历史哈希通过。docs/x0_acceptance_summary.md；board/measurements/x0_acceptance_r2.json。独立X1在途改动保留，未宣称工作区全净。 |
| X1 | CFAR列表质量优化 | FAIL | 2026-11-03 | 原三轮失败保留；用户授权仅追加GUARD=8一轮，98MHz容量告警3/105=2.86%通过，95.8MHz检出78/106=73.58%未达80%。95.45MHz补充106/106；目视正常；无快照缺失或采样溢出，中位约49.39fps，停止GPIO/SRC=0、boot_id不变。x1_final_checkpoint.json及SHA256，docs/x1_acceptance_summary.md。按用户授权不再调参、转入X2；X1不得标DONE。 |
| X2 | 全带宽流水化 | FAIL | 2026-11-03 | 时序优化延期，不追加第3轮。30.72MSPS/64帧仿真SAMPLE_DROP=0、FRAME_DROP=4、8192功率字精确一致。r1 WNS−0.331ns；r2复用综合/ExtraTimingOpt仍FAIL：WNS−0.709ns、WHS−0.058ns，188冻结输入及267文件归档有JSON/SHA256。235项PS/PC测试通过、软件r2冻结24文件。四档60秒筛选+最高600秒快速入口已准备但未板测；无X2部署/加载/目视/带宽通过结论。按用户优先功能要求，以已通过时序3.84MSPS基线继续X3，原≥24.576MSPS目标未达到。docs/x2_acceptance_summary.md及x2_deferred_summary.json。 |
| X3 | E1/E10/带宽/时延与G1 | FAIL | 2026-11-03 | 对比/归档完成，原<200µs指标未达标：1000次中位629.90000µs、最大629.91333µs；连续吞吐3,839,999.78IQ/s、1875.20帧/s，FFT+CA组合吞吐比22.75（非FFT单项加速）。接收复测30秒49.45205fps、进程占单核7.23%、最高61.03°C、零溢出，退出GPIO/SRC=0；原失败轮次保留。G1独立重算8192字零错；244项回归通过。docs/x3_acceptance_summary.md、x3_analysis.json及SHA256。M-A仅为保留X1/X2/X3不足的阶段检查点，不宣称全通过；按用户优先功能要求继续X4。 |
| X4 | 分层AMC v2 | FAIL | 2026-11-03 | 三轮十类@10dB为78.60%/88.45%/87.65%，总体均FAIL；第三轮大类97.85%、QPSK79.5%、8PSK90.5%，板端中位49.265ms/最大184.668ms，十类/QPSK/单次耗时未达标。混合精度INT8、4096点480kSPS，第三轮仅作为FAIL实验候选供X5集成。252项回归及28份测量哈希通过，三轮源码/模型/曲线归档有SHA256。docs/x4_acceptance_summary.md；按计划不再训练，继续X5。 |
| X5 | 信道捕获及识别上屏 | FAIL | 2026-11-03 | 原PFB/NCO/CFAR仿真PASS保留，整机r1失败/r2时序通过；120秒站点实采完成。自动Y2帧率及FM识别未达标，原X5的98MHz窗口无独立FM真值，不能标DONE。详见Y2行、docs/y2_board_checkpoint.md及带SHA256检查点y2_board_checkpoint_1.json；接收停止，原v1d人工目视PASS，Z2待完成。 |
| X6 | FM耳机实时监听 | TODO | | M-B，配置A+P1耳机 |
| X7 | 空口闭环与数字注噪 | TODO | | M-C，配置B或C |
| X8 | 扫频及一小时稳定性 | TODO | | M-C，配置A转D |
| X9 | 报告与交付 | TODO | | M-C，开源另需地址 |

### X0–X4 第二轮离线优化归档（2026-11-03）

用户继续授权优化X0–X4。X4可选C同步后端在板端260段/13档SNR与36个核心用例零差异；150对配对计时P95由126.029降至98.456ms，>100ms由60次降至3次，但最大134.450ms仍FAIL。模型/训练/默认Predictor不变。X2 maskpipe与cfgpipe各18组黄金向量零差异；寄存器边界局部WNS/WHS分别−0.291/+0.092ns、−0.147/+0.089ns，对照−0.311/+0.103ns，建立时间仍失败。仅maskpipe完成30.72MSPS整链仿真：131072样本无丢失、8192功率字精确一致、64帧中丢4帧；不是宽带板测通过。280项PS/工具回归通过；79文件及manifest已封存，汇总与ZIP均附SHA256：board/measurements/x0_x4_followup_r1.json、report/results/x0_x4_followup_r1.zip。正式状态X0 DONE、X1–X4 FAIL保持；未启动RF、未加载新位流，X5在途文件保留。详见docs/x0_x4_optimization.md与docs/amc_native_runtime.md。

### X0–X4 用户离开期间的离线优化（2026-11-03）

用户授权继续优化X0–X4并保持板卡上电。本轮未启动RF、未加载位流、未改变部署默认Predictor；保留X5在途文件及原正式结论（X0 DONE，X1–X4 FAIL）。原六份关键验收/完整性JSON哈希一致，PS测试范围src/ps/tests为172 passed。

X2隔离计数器和聚类器功能仿真通过：96238周期计数边界/饱和/复位及32帧390输出字逐周期对照；r3 OOC四模块时序与资源原始报告归档到优化ZIP。分段计数器WNS由−0.130改善至+1.234ns，但WHS仍−0.275ns；CFAR候选WNS由+0.074退化为−0.174ns，不采用。虚拟端口OOC不代表整机时序通过，未开始v1c第三轮整机实现或宽带板测。X3补充各采样率的时延估算，仅供规划，不替代原629.90µs实测。

X4缓存候选：PC 2000段logits精确一致，板端50段×3次×3后端共450次完整预测等价。板端reference/cached_int32/exact_fp32中位52.1066/52.0442/51.3559ms，最大131.5358/131.4701/131.1317ms，均有>100ms；加速约0.1%–1.4%，默认后端保持原版。本轮不是第四次训练或准确率验收。板端r1数据布局、r2 ARM32 bincount类型错误在计时前修复，r3完成；OOC r1参数、r2 Tcl兼容问题日志保留，不再自动追加轮次。

详见docs/x0_x4_optimization.md；汇总board/measurements/x0_x4_optimization_r1.json及SHA256、report/results/x0_x4_optimization_r1.zip及SHA256。汇总工具独立重算450条耗时、核验模型/源码/传输包与报告哈希；成果为隔离实验交接，不宣称整机/带宽/识别指标通过。人工步骤等用户返回。

### X1 补充诊断与新增天线对比

2026-11-03：同帧RF诊断r2已完成，96组功率帧与PC黄金模型配对通过（196608功率字、576计数字段、214目标记录）；95.8MHz峰值77/96=80.21%。这是有限门控帧诊断，不替代连续120秒及98MHz容量窗口联合验收，X1仍FAIL。13帧有宽度筛选标签、6帧容差内无屏蔽后hit，标签可重叠；无原始IQ和独立信号真值。27项诊断回归通过，结果和限制见docs/x1_paired_diagnostic_summary.md。退出GPIO/SRC=0、boot_id不变。

用户确认原第二根（细短、馈线长20–512MHz）接RX1A、TX空、摆放固定，并授权与新找到的同频段天线对比。新增基准antenna_compare_short_r2完成120.012秒：检出21/102=20.59%、容量告警0、快照缺失0、采样溢出0，中位49.435fps。用户再确认新天线换好及摆放一致后，antenna_compare_new_r1完成120.035秒：检出26/107=24.30%、容量告警3/107=2.80%、缺失/采样溢出均0，中位49.388fps。两次温度59.80–61.27°C，退出GPIO/SRC=0、boot_id不变，18项冻结软件及位流/日志/测量哈希通过。最终antenna_comparison_new_r1.json及SHA256已保存，详见docs/antenna_comparison.md。新天线仅高3.71个百分点、单窗且有时段波动，不能确认为稳定最优；第二根此前58.10%不与本轮直接排名。当前新天线接RX1A、TX空、接收停止。此独立对比不追加X1调参轮次、不覆盖前三天线数据，X1仍FAIL，X2未开始。

### X1 冻结输入复核及95.45MHz补充（2026-11-03）

用户确认接好后要求继续，并反馈两根天线的95.45MHz检出率高。电脑端复核五个历史120秒窗口，95.45MHz±25kHz检出依次104/104、105/105、104/104、101/102、107/107，峰均为约95.45125MHz；原95.8MHz指标仍原样保留。95.45MHz尚无独立信号身份验证，不宣称已确认电台或全频段天线优劣。它相对LO偏移约−950kHz，位于当前1.5MHz标称RF带宽之外，不能将数字范围当有效通带。

同一96帧冻结功率作10种固定单因素模型对照：原95.8MHz检出77/96，GUARD由2改8后94/96，改合并间隙无改善；仅为模型结果，未部署。本组容量告警0不替代98MHz连续窗口，前后半段不是独立验证。产物board/measurements/x1_frozen_replay_r1.json及SHA256；文档docs/x1_frozen_replay_summary.md给出一次额外GUARD=8联合验收的具体建议。45项回归通过，logs/X1_frozen_replay_tests_r1.log。本轮未访问开发板、未追加RF调参、未开启X2、X1仍FAIL。用户已明确授权：只追加一轮GUARD=8联合板测，仍失败则保留FAIL并继续X2。原三轮上限、失败证据和指标保留；本次是一次明确的流程例外，不授权无限调参。

旧N5–N9保留为历史映射，以X0–X9推进；C1仍SKIPPED。以下为历史状态，不覆盖本节。

## 当前暂停点（2026-11-02 N4收尾）

N0–N4已完成；N4的3.84MSPS功能验收、量化结果及已知限制见 docs/n4_acceptance_summary.md。按用户要求暂停，**N5不启动，M-A未完成**。本机不配置Git身份、不commit/push；P0.2中的旧设备身份记录不授权本机提交。后面的交接和测试过程保留原时点状态，DOING/待确认叙述不覆盖本节和N0–N9主状态表。



> 已知前提（2026-11-01）：用户已在原设备上让 AD9361 和 LCD"能初始化、能点亮"，但还没有处理功能；用户的原工程不在仓库中（见 G0）。天线：2.4 GHz 板状天线 ×2、拉杆天线 ×2、磁吸长鞭天线 ×1、20–512 MHz 磁吸天线 ×2（都是 SMA 公头，部分待确认）。耳机：3.5 mm 有线耳机。衰减器：**暂无**。

| 步骤 | 内容 | 状态 | 时间 | 备注（日志 / 产物 / 原因） |
|---|---|---|---|---|
| P0.1 | 检查并安装工具 | DONE | 2026-11-01 | 核心工具及辅助工具已齐备；Etcher 人工安装截图及安装路径已核实；已补交 [P0.1] 提交。见 docs/toolchain.md、logs/P0.1.log |
| P0.2 | 👤 GitHub 仓库与 git 身份 | DONE | 2026-11-01 | 用户身份已配置并验证；longpaths=true、autocrlf=false；docs/board_info.md 的 repo_url 暂空，板端字段等 P0.8 人工确认；logs/P0.2.log |
| P0.3 | 仓库骨架 | DONE | 2026-11-01 | main 仓库及所需目录已创建，README/LICENSE/.gitignore 完成；本地日志和 vendor 排除已验证；logs/P0.3.log |
| P0.4 | tools/env.ps1 | DONE | 2026-11-01 | 已纠正版本命令退出码误判；本机 loader.bat 版本分支明确 exit /b 1。实际 Vivado Tcl、器件库及 XSCT 均退出 0；logs/P0.4.log |
| P0.5 | Python venv | DONE | 2026-11-01 | 隔离环境导入、CPU torch、pip check 和 env 自动激活通过；numpy 2.1.3、torch 2.10.0+cpu；logs/P0.5.log |
| P0.6 | ADI hdl / no-OS submodule | DONE | 2026-11-01 | 恢复后补取目标分支成功；HDL/no-OS 均登记官方子模块，路径及源码无改动检查通过；版本见 docs/third_party_versions.md，logs/P0.6.log |
| P0.7 | 解压正点原子参考资料 | DONE | 2026-11-01 | 手册列出的 9 个原理图、约束、PYNQ 例程及 IP 路径全部存在；只读校验，logs/P0.7.log |
| P0.8 | 👤 PYNQ 镜像与板端信息 | DONE | 2026-11-02 | 用户确认完成；192.168.2.99 严格主机密钥免密SSH返回ok；PYNQ2.7.0/Python3.8.2/内核及板端解释器实测，docs/board_info.md；logs/P0.8_acceptance.log |
| P1.1 | PS7 预设 | DONE | 2026-11-01 | 从只读 HWH 生成 278 项板级参数；纠正 Bank/MIO 设置顺序及派生方向参数；Vivado 实际加载、8 项关键参数读回通过，round2 无 ERROR；logs/P1.1.log |
| P1.2 | z20_system_bd.tcl | DONE | 2026-11-01 | Z20 基础 BD 文件完成；helper API 核实，实际 Quad SPI/GPIO IP 参数验证通过，完整 BD 连接待 P1.8；logs/P1.2.log |
| P1.3 | fmcomms2_z20_bd.tcl（关闭 SG） | DONE | 2026-11-01 | SG=0 两处、无 m_sg_axi；TDD 输入接地，保持地址/IRQ/HP1/HP2；Tcl 完整性检查通过，完整 BD 待构建；logs/P1.3.log |
| P1.4 | system_bd / system_project / Makefile | DONE | 2026-11-02 | 入口脚本及 9 项 IP 依赖完成；实际 ADI API/器件选择逻辑核实，Tcl 完整性检查通过；logs/P1.4.log |
| P1.5 | system_top.v | DONE | 2026-11-02 | 单向 GPIO/Quad SPI/AD9361 顶层完成，xvlog 语法分析通过；生成 wrapper 后仍需做端口绑定检查；logs/P1.5.log |
| P1.6 | XDC 约束 + 管脚交叉检查（FMC IIC 待核实） | DONE | 2026-11-02 | 55 路无重复及板载外设 XDC 重叠；Bank 电压类别核对通过；原理图确认 SCL=G21、SDA=G20（纠正手册暂定顺序）；logs/P1.6_pincheck.txt |
| P1.7 | ADI IP 库编译 | DONE | 2026-11-02 | 独立 checkout 中 9 项 IP 及递归依赖构建通过；原 third_party/hdl 无改动。logs/P1.7.log、logs/P1.7_lib.log |
| P1.8 | 基础位流构建 | DONE | 2026-11-02 | 实现/位流成功；WNS +0.524ns、WHS +0.008ns，无 ERROR；bit/hwh/xsa 与 SHA256 已收集。已知版本/IOB/时序方法学警告待后续收敛，非上板验收；logs/P1.8.log |
| P1.9 | 记录与提交 | DONE | 2026-11-02 | 基础资源/时序/警告及 IDELAY 初值已归档；docs/hw_base_summary.md、report/llm_logs/p1_hdl_port.md；P1 电脑端完成，板端门禁未开始 |
| P2.0 | 全局参数及 RTL 常量 | DONE | 2026-11-02 | 30 项整数参数 Python/RTL 完全一致，显示边界检查通过；实际 800×480 屏；logs/P2.0.log |
| P2.1 | 信号生成与定点注噪 | DONE | 2026-11-02 | 十类调制、灰码星座/RRC、ADC量化、带内SNR、确定性LFSR及饱和注噪：18项测试通过；理想接收参考 EVM 约0.80%；logs/P2.1_round2.log |
| P2.2 | 频谱模型 | DONE | 2026-11-02 | 官方 XFFT C模型实际调用；12项测试通过，BH4旁瓣 -92.047dBc、dB最大误差0.01872dB；16位FFT/24位左对齐契约见 docs/spectrum_numeric.md；logs/P2.2.log |
| P2.3 | CFAR 与聚类 | DONE | 2026-11-02 | 11项测试通过；26万频点 Pfa CA/GO/SO=0.001007/0.001049/0.001038；定点窗和、饱和、DC屏蔽、聚类及16字节打包通过；logs/P2.3.log |
| P2.4 | 多相信道化器 | DONE | 2026-11-02 | 28项测试通过；16信道中心映射/移位、独立调制滤波组比对、定点/NCO/抽取；docs/pfb_numeric.md、logs/P2.4.log |
| P2.5 | HOC 特征 | DONE | 2026-11-02 | 第二轮7项测试通过；48位回绕/溢出、1024点定点星座及六阶公式独立验证；长捕获量化偏差如实记录于 docs/hoc_numeric.md；logs/P2.5_round2.log |
| P2.6 | 解调与显示参考 | DONE | 2026-11-02 | 9项测试通过；FM相位16位SQNR77.23dB；800×480像素/层级/色键/瀑布环回验收；docs/display_reference.md、logs/P2.6.log |
| P2.7 | 全链路演示 | DONE | 2026-11-02 | 四目标中心误差≤15kHz；5项演示产物和捕获/HOC已生成，像素图视觉检查通过；尚无分类器，标签明确null；sim/results/p2_demo、logs/P2.7.log |
| P2.8 | 硬件参考数据集 | DONE | 2026-11-02 | 142文件11.1MB；全部SHA256通过，两次独立生成manifest完全一致；全套86测试通过；data/reference/manifest.json、logs/P2.8_repro.log |
| P2.9 | AMC v1 训练与量化 | FAIL | 2026-11-02 | 三轮77%/67.15%/75.9%未达88%；用户明确暂缓识别模型，优先AD9361与LCD联调。保留失败证据，不追加训练。docs/amc_attempts.md |
| P2.10 | P2 阶段验收 | TODO | | |
| P3.0 | 仿真与代码生成基础设施 | TODO | | |
| P3.1–P3.10 | 自研 IP（逐个） | TODO | | |
| P4.1–P4.6 | 集成 int1–int5 / 一键构建 | TODO | | |
| P5.0 | 板端同步与命令脚本 | DONE | 2026-11-02 | push/check/run通过；bit/hwh/xsa板端SHA256一致；修正Windows CRLF及复合命令shell处理；logs/P5.0_round3.log |
| P5.1 | 平台notebook与LCD验收 | DOING | 2026-11-02 | 网络中断后重启恢复，COM12正常；CPU-only执行notebook及三项基线已取回；新base位流加载和4项寄存器读取通过；独立RF/LCD新位流彩条及顶部动画已由用户确认，DMA部分仍待验收。docs/rf_lcd_bringup.md |
| P5.2 | 基础驱动与自检框架 | DOING | 2026-11-02 | MMIO/Overlay/simple DMA及base自检完成，11项PC测试和板端read-only通过；纠正IRQ_PENDING=0x84；ADI接收DMA已通过4×64KB内部测试音/双通道频率/内存边界验收；完整GPIO/Xilinx DMA/自研IP契约仍待验收；docs/base_driver_status.md |
| P5.3 | AD9361控制库与联调 | DOING | 2026-11-02 | ID/初始化/双TX89.75dB、RX内部测试音及DMA通过；95.8MHz导频/听音和LCD实采频谱已确认。两速率RX时序扫描连续窗口13/16档、恢复设置后PRBS通过；N1已完成统一RF绑定/TxGuard及TX-DMA逐位回环；完整旧版控制API验收仍按后续方案推进。docs/rx_timing_margin.md |
| P5.4 | 应用与LCD实时显示 | DOING | 2026-11-02 | 独立live_z20_lcd位流构建/时序通过；25项软件测试及像素/换帧RTL仿真通过；板端CPU频谱+瀑布图约1.67fps、超过100帧，用户目视确认通过。完整应用/PL处理链仍待完成。docs/lcd_live_display.md |
| P5.5–P5.6 | 教学与阶段验收 | TODO | | |
| G0 | 👤 现状确认（用户已有的 AD9361/LCD 方案、跳线、IP） | DONE | 2026-11-02 | 根据既有用户确认和上板证据补记：ATK-MD0700 V2.4 SSD1963 J22 800×480；J7/J8=2.5V（已测）；RX1A接20–512MHz天线；PYNQ2.7、IP和当前独立工程已记录。见 docs/board_info.md、docs/rf_lcd_bringup.md、docs/lcd_live_display.md |
| G1 | 位流可用（测试源模式） | DONE | 2026-11-03 | x3_g1_acceptance.json及SHA256：独立加载原始NPZ/HEX/位流，单音及三音目标正确、8192功率字零错；仅限既有测试源和回放，不代表宽带射频验收。 |
| G2 | 跳线2.5V、接收与内部TX-DMA数字回环 | DONE | 2026-11-02 | 按80_next N1门禁：既有天线FM接收、RX PRBS/时序窗口通过；第4轮ramp/PN回环和完整原始采样PC独立比对全部零错误，TX读数89.75dB、结束RF复位。用户授权额外归档复核轮次已记录。FM实时耳机监听移至N7，AMC不作为本G2条件；不代表射频发射或空口闭环已通过 |
| G3 | 👤 空口闭环 + 注噪 SNR 扫描 + 全功能 + final_metrics | TODO | | 主线终点，到此即可提交 |
| C1 | 👤（备选）有衰减器时的电缆闭环 | SKIPPED | 2026-11-02 | 按用户本轮要求及80_next.md不使用衰减器，不执行电缆闭环；禁止SMA线直连TX/RX |
| P7.1–P7.8 | 交付 | TODO | | |

## P0.1 执行记录（2026-11-01）

- 实际目录是 `D:\FPGA\ZSS\zss`，不是最初消息中的 `D:\ZSS`；已完整阅读 AGENTS.md、runbook/README.md、本文及 runbook/00_env.md。
- Git 2.53、SSH 9.5、Vivado 2025.2、Z20 器件库均通过检查。默认 Python 3.13.1 不符合要求，已定位并验证本机 Python 3.12.10，仅对本次验收进程调整 PATH。
- `vitis-run --help` 及 XSCT 2025.2.0 均实际运行成功。XSCT 与 Vivado 位于不同安装根目录，P0.4 配置时必须显式处理；未提前生成环境脚本。
- 7-Zip 只有指向失效目录的注册信息，未定位到可运行文件；Etcher、MobaXterm/PuTTY 未在已检查位置找到。按 P0.1 缺工具的人工规则暂停，等待安装结果或有效路径。
- 本目录是交接包，无 Git 元数据；提交姓名和邮箱为空。未执行 git commit，未使用虚构作者；需在满足提交前置条件后补交本步骤记录。P0.2、P0.3 未标 DONE。
- 后续核查：用户提供的开始菜单 7-Zip 文件夹只有快捷方式，程序和帮助文件的目标均已缺失，仍不能运行。用户已提供真实 Git 提交身份，待 P0.2 配置；不在跟踪文档和检查日志中抄录具体姓名、邮箱。
- 新安装验证：`D:\7zip\7-Zip\7z.exe` 为 26.05 x64，信息查询、测试归档及解压均退出 0，解压后 SHA256 一致。7-Zip 问题已解决，剩余 Etcher 和串口终端待人工提供安装结果或有效路径。
- 用户随后提供 `D:\MobaXterm`：已将 Portable v26.6 解压至其 `Portable_v26.6` 子目录（跳过已有文件，不覆盖），找到程序且文件版本为 26.6.0.5560；未启动界面或连接串口。Etcher 2.1.9 安装包已下载，依人工安装规则暂停等待安装结果。
- 用户提供 Etcher 已打开的截图；已核实本机安装目录和程序版本 2.1.9。辅助工具已补齐，P0.1 验收通过；P0.8 再验证实际串口通信和 SD 启动。因初始目录没有 Git 元数据，按顺序在 P0.3 初始化后补交 P0.1、P0.2 记录。
- 产物：`docs/toolchain.md`；日志：`logs/P0.1.log`、`logs/P0.1_extended.log`、`logs/P0.1_vivado.log`。日志只保存在本机，不应加入 Git。
- 本次未访问 FPGA/JTAG/板端网络、未触发任何 TX、未改动 `third_party/` 或 `vendor/atk/`。P0 阶段尚未完成，因此阶段协作总结待阶段验收后写入 `report/llm_logs/`。

## P0.2–P0.4 执行记录（2026-11-01）

- P0.2：使用用户提供的 Git 身份配置并逐项读回验证；长路径开启，自动换行转换关闭。网络地址、板端 Python 和内核等字段保持空白，等待 P0.8 人工回报。
- P0.3：创建 main 仓库和目录骨架；从 Apache 官网获取许可证，验证包含完整条款；git status、目录存在性及忽略规则均通过。第 1 次下载出现 EOF，第 2 次为 Windows CRYPT_E_REVOCATION_OFFLINE，第 3 次使用 curl --ssl-revoke-best-effort 成功；保留证书链验证，仅容忍吊销查询服务离线。P0.1、P0.2 已分别补交，P0.3 已单独提交。
- P0.4：新增 tools/env.ps1，按环境变量或安装目录自动查找同版本工具；XSCT_ROOT 可独立于 XILINX_ROOT。项目 Python 自动优选 3.12/3.11/3.10，不改系统 PATH。
- 第 1 轮发现本机 Python 安装路径含中文，原生输出编码丢失；已改用 ASCII JSON 传输路径，加载及重复加载通过。第 2 轮后台验收发现 Vivado 非零退出；第 3 轮保存完整输出，确认版本为 2025.2、退出码仍为 1。达到重试限制，P0.4 标 FAIL 并停止，不把版本字符串正确当作完整验收通过。尚未执行后续 Python 依赖安装和 ADI 拉取。
- 关键日志：`logs/P0.4.log` 中 `Vivado exit=1`、`Vivado version acceptance failed`；后台验收已结束，无遗留构建任务。本步骤未访问硬件。
- 用户要求继续后已查明并纠正上述误判：本机原版 Vivado/bin/loader.bat 第 549–551 行在 RDI_INVOKE_VERSION_ONLY 分支调用版本程序后明确 exit /b 1，不能据此判断 Vivado 无法运行。恢复后的首轮验收实际执行只读 Tcl，version -short=2025.2、get_parts 唯一匹配 xc7z020clg484-2，并以 exit 0 正常结束；XSCT 打印验证标识后同样退出 0。已恢复 P0.4 为 DONE，未修改 AMD 安装文件，也未访问硬件。

## 镜像等待期间的执行范围

- 用户明确要求“镜像一会给你，正在下载，接着完成后面内容”。因此继续 P1 的电脑端离线步骤；P1.0 本身声明只编译、不需要开发板，P1.1 的前置 P0.7 已满足。
- P0.8 保持 BLOCKED-HUMAN，板端字段保持未知；不把它视为完成。SD 写入、启动拨码、网络登录、射频上板门禁仍需用户实际完成和回报。
- P1.1 发现直接按名称逐项设置会在 Bank 电压尚为默认值时拒绝 1.8V MIO；生成器现先应用 Bank 电压，再原子应用配置字典，排除由外设分配派生的 MIO 方向。第二轮实际 Vivado 内存工程检查通过，未访问硬件。
- P1.8 生成 wrapper 后发现手册示例的 SPI 展开端口实际被 wrapper 包成 IOBUF。顶层改接底层 system BD 的 60 个真实端口，仅 IIC 保留必要双向缓冲，SPI 为独立输出/输入。已逐项比对 60/60 接口并在主综合尚排队时更新独立构建目录的顶层，记录于 logs/P1.8_binding.log。
- P2.1 首轮17项通过，8符号发送滤波器与同长截断接收滤波器叠加时 EVM 约1.60%；检查理想接收参考的收敛性，12/16/24/32符号接收参考均约0.80%。仅将验收接收参考改为32符号，发送端仍为8符号且门槛仍为1%；第二轮18项全部通过。固定噪声的多项式、逐字步进、符号和Q格式已在 params/siggen 明确，尚未与后续RTL比对，不能宣称完成硬件位精确验收。
- P1.6 已视觉核实底板第2/15页及核心板第3/4页；IIC 的真实顺序为 SCL=G21、SDA=G20。图像及源文件 SHA256 记录在本机 logs，未改动原始资料。
- 用户明确要求不修改 third_party/ 文件；因此 P1.7 不采用手册示例中向该目录复制覆盖层并直接构建的写法，而用已固定 HDL 提交创建 build/work/adi_hdl 独立 checkout，在其中同步覆盖层和生成 IP。原 third_party/hdl 和 vendor/atk 保持只读参考状态；构建脚本仍使用相对路径或环境变量。

## 已确认的硬件差异（影响后续显示方案，不代表 G0 已完成）

- 用户明确确认继续使用此前调通的 **ATK-MD0700 V2.4，SSD1963，34 针 8080 并口屏，接 Z20 J22**，而不是 runbook 默认的 J26 RGB 屏。
- 此确认优先于文档中“7 寸 RGB LCD 接 J26 / GT9147”的假设。后续显示接口、驱动和触摸方案必须先按实际屏幕资料核对；不得直接套用 J26 的 `rgb2lcd` 输出方案，也不得猜测触摸芯片。
- 仓库外旧工程尚未导入。G0、G2 等人工门禁保持 TODO；不能把此前的彩条或产品 ID 测试当作本仓库的系统处理、射频接收或自动识别验收。

## RF/LCD 联调进展（2026-11-02）

- 用户明确暂停AMC训练，优先RF/LCD；不再追加模型训练。
- 独立工程fmcomms2_z20_lcd补齐G22电源使能，集成原J22并口LCD彩条；原base/备份未覆盖。79路PL引脚无重复，第三次构建通过最终时序；产物SHA256板端核验成功。
- SPI产品ID十次0x0A，官方no-OS初始化成功，采样率30.72MSPS、ENSM=ALERT、两路TX衰减89.75dB；结束后RF复位GPIO=0。不是完整G2/DMA验收。LCD彩条与顶部变化已由用户目视确认。
- 文档docs/rf_lcd_bringup.md及测量JSON已保存；PC驱动13项测试通过；third_party和vendor未修改。

## 内部RX测试音与DMA（2026-11-02）

- 同一RF/LCD位流，AD9361内部RX注入960kHz测试音，连续4次64KB DMA完成；两通道频率均正确，主频能量占比0.99999765，两侧64字节边界未变。测试结束GPIO=0、无在途缓冲区。
- 原生捕获、归一化双通道SigMF、频谱/波形图及JSON已保存。18项PS测试通过。docs/rx_bist_dma_acceptance.md。
- 不将内部测试音视为天线射频接收，也不将其视为TX-DMA逐位回环或完整G2验收；模型训练保持暂停。

## 天线接收与FM解调（2026-11-02）

- 用户确认RX1A已接天线。98MHz中心、30.72MSPS，8次1MiB接收完成；BBPLL/RX PLL锁定、BIST关闭、TX衰减89.75dB、最后GPIO0。
- 90MHz候选未检出稳定19kHz导频，不记广播FM通过；95.8MHz先4段、后16段均检出稳定导频，后者突出度16.14–27.21dB。生成4.03秒分段试听WAV及频谱图；用户确认可听到人声，但噪声很大，音质未通过；未启用识别模型。
- PYNQ所有权适配器完成三轮1MiB实际分配/释放验证；16次8MiB DMA复用同一物理地址且边界正常。20项PS测试通过。详细证据docs/fm_antenna_acceptance.md。
- 当前显示仍是彩条，实采频谱尚未接到LCD；板载耳机输出/完整G2未通过。

## FM试听质量调试（2026-11-02）

- 用户确认原4秒录音可听到人声，但电流样噪声很大；可听人声通过，音质不通过。
- 保留原IQ/原WAV，增加150–3400Hz语音版、短相位尖峰处理与5ms重叠衔接，生成3.96秒新试听。相对人声频段的低/高频带能量分别降低15.58/29.62dB，不宣称整体SNR提升或电源故障已定位。
- 21项PS测试通过；用户确认新试听有改善但噪声仍大。未改接线/位流、未重新训练。

## 音质排查与天线纠正（2026-11-02）

- 用户确认语音版有改善但噪声仍大。询问实际天线后，用户确认RX1A接的是2.4GHz板状天线；当前FM测试约95.8MHz，频段不匹配。先纠正接收前置条件，不能认定仅靠滤波已解决。
- 新增RX内部PRBS诊断，按固定no-OS的PN9选择、W1C清标志及ADC活动检查。在30.72/3.84MSPS分别检查500ms，四路状态均0、ADC状态0xD、时钟计数非零，结束GPIO0。未运行TX-DMA逐位回环，不宣称全部硬件无故障。
- 证据board/measurements/rx_prbs_rates.json；日志logs/P5.3_rx_prbs_rates.log。等待用户换到已有20–512MHz磁吸天线。

## 换天线后的同参数比较（2026-11-02）

- 用户明确确认已换20–512MHz磁吸天线，原LCD接线和2.5V跳线保持。首轮采集在加载状态检查处停止，未访问RF/DMA；所需位流未加载。重新下载同一已验证位流后连续十次ID=0x0A，未修改硬件代码或重建工程。
- 恢复后95.8MHz、3.84MSPS、1.5MHz带宽采集16次8MiB，DMA与内存边界检查全部通过，结束GPIO0，无在途缓冲；双TX衰减89.75dB。
- 导频突出度中位数17.58→30.80dB，RX1 AGC增益中位数73→59dB。导频16/16通过；新原始解调及语音版WAV已生成，音质待用户确认，不宣称整体音频SNR提升。
- 验收tools/compare_fm_antennas.py通过，SigMF SHA512一致。证据board/measurements/fm_antenna_comparison.json；日志logs/P5.3_fm_antenna_comparison.log。LCD仍为彩条，完整G2未完成。

## LCD黑屏恢复与听音回报（2026-11-02）

- 用户确认round3录音明显改善，仅剩少量噪声；未据此宣称无噪声或完整G2通过。已记录精确WAV哈希和用户回报。
- 用户报告LCD无显示。SSH正常、无RF采集进程；普通账户PYNQ查询先缺XRT环境，补环境后记录为空；管理员查询则确认原联调位流仍登记，故不将普通账户空记录当成位流丢失证据。
- restore_lcd_colorbar.py校验同一bit/hwh及哈希，取得RF独占锁，重新下载原程序并保持RF复位GPIO0。日志logs/P5.1_lcd_restore_round1.log；未修改引脚、HDL或重新构建。
- 用户随后明确确认彩条恢复、顶部色块持续变化，恢复验收通过。证据board/measurements/lcd_restore.json及lcd_restore_confirmation.json。黑屏根因未确定；实时RF频谱上屏和耳机输出仍未实现。

## 实际接收频谱上屏（2026-11-02）

- 用户要求LCD增加实际显示，独立新工程fmcomms2_z20_lcd_live保留原接线/2.5V/旧彩条产物。增加256KiB双页BRAM、帧边界换页和J22显示；板端CPU对AD9361真实接收快照计算FFT并绘制频谱、瀑布和状态。
- 首轮GPIO默认值格式错误，改0x00000000并去除只读MEM_DEPTH设置；第二轮构建成功，setup/hold/pulse +0.471/+0.021/+0.264ns。25项PC测试、像素顺序/双倍显示/换帧仿真通过。
- 用户重接GE_PS后网络恢复；板端首次因BRAM在mem_dict而非ip_dict停止，按实际HWH信息修正，第二次启动成功。十次ID0x0A，采样30.72MSPS，LO97999998Hz，双TX89.75dB，DMA边界正常。
- 保存超过100帧检查点，约1.67fps。用户明确确认绿色频谱、彩色瀑布图和帧计数持续增加，显示验收通过。程序单次900秒后关闭RX并显示RX STOPPED；尚未开机自启。docs/lcd_live_display.md。
- 不将板端CPU快照显示视为连续全带宽PL加速、AMC或完整G2/G3通过。模型仍暂停，耳机和触摸未实现。

## 字体显示优化（2026-11-02）

- 用户报告文字重影；将正文/标题调整为10/14像素粗体、单色字形覆盖，提高对比度、调整底部间距，并将软件预览改为最近邻放大以匹配硬件。未改位流或接线。
- 旧接收进程正常停止后更新软件并重启；4项相关PC测试通过，实际运行90帧、DMA边界正常，标题像素无抗锯齿灰边。
- 用户明确确认“清楚了，重影消失”，字体验收通过。证据board/measurements/lcd_font_confirmation.json及lcd_font_preview.png；不宣称已证明原重影的物理根因。

## 接收时序余量验收（2026-11-02）

- 用户要求继续，推进P5.3的数值时序窗口。先正常停止并确认LCD接收进程退出，再编译项目控制库；避免覆盖正在使用的共享库。编译退出0，保留板端时钟偏差及上游已有警告。
- 按固定no-OS寄存器/PN9逻辑扫描RX时钟和数据延迟16×16，各点稳定5ms、观察10ms；不调用结尾会取消TX静音的官方全时序分析函数。全程TX静音89.75dB，仅内部RX校验，无发射。
- 30.72/3.84MSPS通过点145/153；原clock=0时数据轴连续窗口13/16档，原data=2时时钟轴窗口均4档，满足至少3档门槛。两次均精确恢复0x006=0x02；恢复后500ms PRBS四路均0；关闭GPIO0。
- 验收tools/analyze_rx_timing.py通过，证据board/measurements/rx_timing_margin.json、report/figures/rx_timing_margin.png；不宣称BER、物理眼宽或全温稳定性。
- 测试后已重启优化字体的LCD接收程序，超过60帧、DMA边界正常，约1.67fps。证据board/measurements/lcd_after_timing.json。完整G2/控制API仍未全部完成。


## 后续执行方案 N0–N9（80_next.md 优先）

按 N0→N9 顺序执行，M-A（N0–N5）最优先；旧 P2.9 三轮失败记录保留，N6 作为 P2.9b 独立计数，三轮仍未达标则记录 FAIL 并继续 N7。C1 保持 SKIPPED。

| 步骤 | 内容 | 状态 | 时间 | 备注 |
|---|---|---|---|---|
| N0 | 收尾与实际硬件/文档对齐 | DONE | 2026-11-02 | G0补记DONE、C1为SKIPPED；AGENTS/BOM/README对齐J22 SSD1963；两份训练指标/历史JSON校验并归档，PT本地保留且忽略；N0–N9登记，第三方工作区无修改。验收logs/N0.log，提交后核对git status干净 |
| N1 | TX-DMA数字回环、统一RF封装与TxGuard | DONE | 2026-11-02 | 用户明确授权额外一轮归档复核；第4轮ramp/PN各131072字全部逐位一致，PC从完整NPZ独立重算四通道零错误，归档/样本SHA256匹配。ID0x0A，十次TX读数均[89750,89750]，结束GPIO0、无在途缓冲；前后boot_id一致。34项PC测试及板端原子写入检查通过。board/measurements/tx_loopback.json、tx_loopback_acceptance.json、report/figures/tx_loopback.png；logs/N1_archive_acceptance.log。前三轮记录保留，无第5轮 |
| N2 | 仿真基础设施与spec_front | DONE | 2026-11-02 | 四帧FFT/功率/Welch/dB/560点显示逐位一致，独立随机背压及20000周期暂停、抽帧/带符号最大值通过；完整核心150MHz布局布线WNS+0.135ns、内部保持+0.059ns，3725LUT/5463FF/14.5BRAM/25DSP；重排4BRAM已核实，IP完整性检查通过。sim/results/n2_acceptance.json、docs/n2_spec_front.md；虚拟OOC端口hold不代表板级闭合，N4须验收完整系统。无上板下载 |
| N3 | CFAR、聚类和占用度 | DONE | 2026-11-02 | 13组门限/hit/dB/占用各26624字、目标窗口1664字逐位一致，独立随机/长背压、空帧/溢出、目标AXIS与MMIO、占用饱和清零通过；4项软件驱动测试通过。150MHz布局布线WNS+0.280ns、内部hold+0.127ns；1897LUT/1230FF/15BRAM/2DSP，占用2BRAM实测；IP完整性通过。sim/results/n3_acceptance.json、docs/n3_cfar.md；SSH/PYNQ只读检查通过，无下载。虚拟OOC端口hold留N4闭合 |
| N4 | sentinel_v1、PL频谱/CFAR与SSD1963直驱 | DONE | 2026-11-02 | 限定3.84MSPS仅接收验收：整机WNS+0.086ns/WHS+0.046ns，26625LUT/49BRAM/64DSP；单音0bin、三音3目标、8192字回放零错；七档LCD目视通过，默认3档。两次120秒RF显示中位49.45/49.42fps，211条记录采样FIFO溢出0，目标列表容量告警42/105和43/106须保留；95.8MHz补测频点对应证据41/106。用户确认动态频谱/瀑布和列表正常，58项软件测试通过，退出GPIO0。详见docs/n4_acceptance_summary.md及board/measurements/n4_acceptance_summary.json。30.72MSPS、完整FM带宽、全温/长期稳定性未验收；N5未开始，按用户要求暂停，不提交Git |
| N5 | E1/E10对比与G1验收 | TODO | | M-A收口；实测数据追溯 |
| N6 | 分层调制识别与盲同步（P2.9b） | TODO | | M-B；最多3轮，10dB准确率≥88%，失败后继续N7 |
| N7 | 信道提取、HOC与FM耳机监听 | TODO | | M-B；耳机P1/LINE_OUT，目视与听音需用户确认 |
| N8 | 空口闭环与数字注噪评测 | TODO | | M-C；接天线需人工确认，无电缆直连 |
| N9 | 实验、报告、技能包和交付 | TODO | | M-C；不可裁剪 |

N0 前置条件：新评审及80方案存在，实际显示/跳线/天线已有确认。改动限于文档、忽略规则与既有训练指标归档；不操作硬件，不重新训练，不修改第三方目录。训练 *_metrics.json / *_history.json 保留原始内容，.pt 仅留本地并忽略；不把失败权重当作已通过的部署模型。用户提供的新评审、方案及启动说明一并保留为执行依据。

N0 验收结果：内容检查全部通过（logs/N0.log）；`Select-String AGENTS.md -Pattern "SSD1963"` 命中实际屏幕说明。N1–N9尚未执行，M-A尚未完成；没有触发硬件、射频、Vivado或训练操作。

## 2026-11-02 N4交接

交接包原记录写有“完整构建第1轮后台运行”，但接手本机时已无对应Vivado进程；日志停于place阶段且退出标记为RUNNING。未生成或下载sentinel_v1位流。本机已修复搬迁后的ADI隔离worktree元数据、重建Python 3.12虚拟环境，并启动整机实现第2轮；以本机新日志和最终审计为准。相关PC测试及解析器测试此前已准备，最终审计尚未完成。温度仅查到xadc路径，尚未显示到UI。不得把这些记录视为N4/M-A已完成。

## N4 BUS_PHASE=25 照片复核（2026-11-02）

证据 board/measurements/n4_bench_phase25_visual.jpg、n4_phase25_visual_acceptance.json：三音谱峰/瀑布轨迹静态布局符合预期，没有明显空间错位。72帧/10.010秒=7.193fps。照片无法证实动态无闪烁/偶发错点；human_visual_acceptance 保持 pending。逐档时序、RF仅接收、信号列表与≥15fps目标均未验收，N4保持DOING；用户要求N4完成后暂停并汇报，不推进N5。

## N4 LCD动态验收检查点（2026-11-02）

- 原固定三音瀑布在稳定输入下看起来静止，不能凭此认定显示停止；bench_lcd.py 已在10秒无UI帧率基准测量结束后增加底部PL FRAME计数，人工观察阶段含UI刷新，不能把前段帧率称为完整UI帧率。
- 首次增加UI时，高速CFAR列表在Python读回期间更新而触发一致性保护；失败测量 n4_bench_phase25_ui_r1.json 保留。bench动态检查现只显示帧计数，完整信号列表仍在RF monitor单独验收，不以空列表替代。
- 用户确认25档“计数持续增加、画面正常”，7.1927fps；证据 board/measurements/n4_phase25_ui_acceptance.json。
- 用户确认12档“计数增加、画面正常”，14.5853fps；证据 board/measurements/n4_phase12_ui_acceptance.json。
- 8档基准21.3914fps，目视待确认；6/4/3/2尚未验收。N4保持DOING，完成后按用户要求暂停，不进入N5；不执行git提交/推送。

2026-11-02 N4：用户确认“8档计数增加、画面正常”。BUS_PHASE=8纯频谱/瀑布基准21.3914fps，动态阶段179次UI更新及帧计数推进；证据 board/measurements/n4_phase8_ui_acceptance.json。6/4/3/2及RF显示待验收，N4仍DOING，完成后暂停，不推进N5。

2026-11-02 N4 LCD：用户确认6档、4档均计数增加且画面正常；基准分别27.7720、39.5600fps。证据 board/measurements/n4_phase6_ui_acceptance.json、n4_phase4_ui_acceptance.json。3/2档、默认档RF含UI显示仍待验收，N4保持DOING。

## N4最终收尾（2026-11-02）

3/2档及RF动态画面均已获用户确认。BUS_PHASE=3作为运行默认；2档69.33fps仅为无UI基准。真实RF两次120秒完整显示中位49.45/49.42fps，列表容量告警已如实保留。95.8MHz附近目标补测、退出GPIO0和58项PS测试均有证据。总验收 board/measurements/n4_acceptance_summary.json；完整解释 docs/n4_acceptance_summary.md。已停止板端monitor/bench并暂停，等待用户下一步指示。G1登记与E1/E10留N5；无N5操作、无提交推送。
