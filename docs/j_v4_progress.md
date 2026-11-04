# J v4 十页上位机候选进展

日期：2026-11-04。当前阶段是离线候选开发，尚未发布正式 v3，也未验收本轮新界面的真板操作。

## 已完成

- 核对用户提供的更新包：七个成员与当前文件逐字节相同，不需要再覆盖。核对结果和包摘要见 `board/measurements/j_v4_update.json` 及其 SHA256。
- 十页中文界面与 63 个独立入口，包含 49a–g、52a–f。开发历程页的卡片可以跳转到对应页和按键，跳转本身不发硬件命令。
- 前九页保留大孪生，第十页改为成果目录和小孪生。离线 1920×1080 预览前九页孪生视口约 1160px，小窗 320px；这不是当前电脑真板窗口的实测尺寸。
- 复用已实现的 check/fm/listen/perf/idle 场景，严格检查实时连接、请求序号、场景名称与板端 READY。未实现命令明确拒绝，不通过改名冒充已接入。
- 历史资料浏览器支持 JSON、文档、原尺寸图片和 WAV 波形/本地播放，展示 SHA256 与原始日期。没有原摘要的资料仅建立当前快照；缺失原始日期时明确标注，绝不以拷贝时间代替。
- 已校验的 ZSR 会话可回放、暂停、0.5/1/2 倍速；开始回放前先等待板端 idle 成功确认，结束后恢复原实时连接。实时窗口关闭前也必须收到 idle 确认，失败时保持窗口。
- `report/host_coverage.md` 逐项列出当前方式、来源与待验收内容。入口可点击、资料可读取和动态功能通过是不同结论。

## 文件结构与运行

所有命令在实际 Git 仓库根目录执行，脚本不依赖固定盘符。

```powershell
# 离线打开候选界面；不会自动连接开发板
.venv\Scripts\python.exe tools/host/product.py

# 经十页风格确认后，才可用于真板界面测试；只连接，不自动启动场景
.venv\Scripts\python.exe tools/host/product.py --connect 192.168.2.99

# 来源核对与覆盖清单生成（不访问开发板）
.venv\Scripts\python.exe tools/host/inventory_v4.py

# 全范围回归；Windows Tcl 测试需要 -s
.venv\Scripts\python.exe -u -m pytest src/ps/tests tools/host/tests tools/tests -q -s
```

| 文件/目录 | 用途 |
|---|---|
| `tools/host/product.py` | 独立候选入口和十页截图生成 |
| `tools/host/sentinel_host/product.py` | 十页布局、命令状态与回放门禁 |
| `tools/host/sentinel_host/catalog.py` | 63 项入口、页面、按键和来源映射 |
| `tools/host/sentinel_host/evidence.py` | 只读资料浏览与摘要/日期展示 |
| `tools/host/inventory_v4.py` | 生成覆盖清单及来源 JSON/SHA256 |
| `tools/host/tests/test_product.py` | 导航、场景关联、回放/关闭门禁测试 |
| `report/figures/host_j_v4_r3/` | 本轮十页合成预览、总览和截图摘要 |
| `board/measurements/j_v4_*.json` | 更新核对、来源清单、离线验收及 SHA256 |

## 本轮验证

完整回归：842 passed、19 skipped，日志 `logs/J2_regression_r1.log` 和对应 stderr。十页预览无数据错误，明确标为 OFFLINE_SYNTHETIC_NOT_BOARD_MEASUREMENT。本轮没有 SSH、射频、音频板测或位流加载；没有更改冻结的 LCD/twin、模型、third_party 或 vendor。

## 待完成

1. 用户确认十页截图风格后，才能进行新布局真板逐页操作。
2. 按 P0 优先接入三音、F3 原始采集回放及推理、参考全景补扫、自动选台/门控状态；所需新常驻场景尚未实现，不能发送不存在的命令。
3. ZSR 拖动定位、SigMF 黄金模型复算与 FM 解调播放、全景逐段动画、F3 逐类回放和语谱图待接入。现有资料浏览不计为这些动态功能通过。
4. 现场参数演示须离页恢复默认并读回；自动 A/B、CPU/推理计时、板端回放/数字注噪仍待集成。
5. 正式 v3、可配置 7200 秒上限、一键入口、各页专用兜底、真实按钮三次就绪、每场景十次 P90、讲稿走查及 SD 备份待执行。已有通用 FM 回放不当作专用素材。

历史 FAIL 和热点 INCONCLUSIVE 全部保留；只读显示历史测量不代表重新通过原指标。
