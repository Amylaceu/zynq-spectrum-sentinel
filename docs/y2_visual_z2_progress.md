# Y2 人工目视与 Z2 独立界面修订

## 原 v1d 目视：PASS

用户原话：“计数增加，列表和点图可见，画面正常”。运行的是原 station_r3
隔离部署，未改模型、CFAR参数或位流；已正常停止，取回115份捕获。

- 执行收据：`board/measurements/y2_visual_1_execution.json`，状态
  `PASS_EXECUTION_AWAITING_HUMAN`。原收据不回写。
- 独立人工确认：`board/measurements/y2_visual_confirmation_1.json`，状态
  `PASS_VISUAL`；与开始收据的 SHA256 关联。
- 关联汇总：`board/measurements/y2_visual_link_1.json` 及 SHA256。
- 原 Y2 量化 FAIL 不变：28.992fps、95.8MHz完整五票FM为3/9。
  人工目视不能替代识别真值、帧率统计、新配色或音频验收。

## Z2：组件通过，整机尚未通过

独立 `sentinel_z2` 工程将 LCD 界面页改为每字10像素、每像素3位八色；
每页64000字节，仍使用原双页128KiB BRAM。版本为0x4c430006，拒绝旧格式。
状态栏、五类调制配色、最近五条UTC事件记录均在此修订中。

- RTL r1通过完整滚动、双bank、背压和padding检查。
- IP打包与BD连接验证r1通过；PC相关回归343项通过。
- `sim/results/z2_pc_r1.json`、`report/results/z2_pc_r1.zip`均有SHA256。
- `docs/z2_prebuild_r1.json`冻结299项；构建过程中不修改冻结输入。
- 整机第1次运行在顶层综合开始后退出，无顶层DCP，无明确RTL报错；
  原因未确定。2200文件归档在`report/results/z2_implementation_r1.zip`。
- 第2次实际综合在诊断脚本中成功，生成`system_top.dcp`。Tcl停止条件把
  方括号误作glob，导致本想只检查前置语句的脚本实际执行了综合；日志尾部
  “no synthesis invoked”标记错误，以`z2_synthesis_recovery_r2.json`为准。
- 第3次重复诊断又启动综合，已中止且没有覆盖第2次DCP；不再启动第4次。
- 第1次仅链接恢复在`open_project`后`open_checkpoint`中触发Vivado
  `TclStackFree`/`EXCEPTION_BREAKPOINT`。无成功链接、实现或位流，不能上板。
  崩溃日志和dump已封存为`report/results/z2_link_failure_1.zip`，
  测量入口`board/measurements/z2_link_failure_1.json`及SHA256。
- 第2次非工程链接成功打开顶层DCP，但第一次向`adc_tap_0`插入OOC DCP时
  触发`EXCEPTION_ACCESS_VIOLATION`；尚有大量未解析黑盒，没有整机DCP。
  两次崩溃各自有JSON/SHA和ZIP归档，原因尚未确定。
- 停止Z2链接恢复，不再综合；保留已通过时序的v1d基线继续音频。
  这是新UI硬件未完成，不是原PFB失败，不因此额外重做Y2-L的DDC。
  Z2八色/事件区未上板，不以旧画面冒充新功能完成。
- `report/figures/z2_ui_preview.png`仅为合成布局预览，不是板测照片。

原 v1d 位流、实测数据与冻结文件保持原样。Z2不算追加FM调参或模型训练。
新界面必须单独上板并获得新的人工确认。
