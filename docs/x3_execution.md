# X3 执行与交接

本阶段使用通过整机时序的 `sentinel_v1b`，3.84 MSPS。用户已确认配置 A，仅接收；TX1A 空着、RX1A 接当前比较选出的 20–512 MHz 天线。未加载 X2 时序失败位流。

## 环境与文件

- PC：仓库根目录，PowerShell，`.venv` Python 3.12，NumPy/SciPy/matplotlib/pytest，OpenSSH。
- 板：PYNQ 2.7，Python 3.8，`/usr/local/share/pynq-venv/bin/python3`。地址/用户从 `docs/board_info.md` 读取。
- 测量模块：`src/ps/sentinel/app/perf_x3.py`；板端入口：`board/scripts/run_x3_perf.py`。
- PC 执行器：`tools/run_x3_board.py`；只原子发布以上两个新增文件，逐字节核对依赖与 bit/HWH/XSA，不替换既有驱动或共享库。
- 分析：`tools/analyze_x3.py`；图表：`tools/render_x3_report.py`；防错误验收测试：`tools/tests/test_analyze_x3.py`。

## 已完成命令及重现入口

以下编号均已占用，**不要原样重跑已有测量**。执行器拒绝覆盖既有证据。只有新的必要实验、符合重试限制且获对应天线确认时才使用新编号；本阶段无需再板测。

```powershell
# CPU + 1000 次数字标记 + 独立连续吞吐 + 接收，历史 r3
python tools/run_x3_board.py --attempt 3 --confirm-configuration-a --sudo-stdin
# 只重测接收子项，历史 receive_r2；不会重复 1000 次数字标记
python tools/run_x3_board.py --attempt 2 --section receive --confirm-configuration-a --sudo-stdin
```

`python` 应使用 `.venv` 解释器；`--sudo-stdin` 从私密 stdin 读入一次密码并只传给 sudo。不要把密码写入命令参数、脚本、环境文件或日志。没有该参数则要求板端 sudo -n 可用。长任务须由后台进程运行，stdout/stderr 写入 `logs/X3_host_*.log`；实际远程测量写入 `logs/X3_*.log`，限制 240 秒。

PC 分析与报告无需接板；下面分析命令的默认产物已存在，因此使用新输出路径才可重算（例如临时目录，且应与默认测量同级，以便生成 G1 文件）。图表可基于同一分析重新生成：

```powershell
.\.venv\Scripts\python tools/analyze_x3.py
.\.venv\Scripts\python tools/render_x3_report.py
.\.venv\Scripts\python -m pytest tools/tests/test_analyze_x3.py -q
```

## 轮次账本与问题纠正

| 尝试 | 实际执行 | 结果 |
|---|---|---|
| preparation_r1 | 导入依赖准备 | namespace package 无 __file__，未启动硬件；已修正 |
| perf_r2 | 数字子项第 1 轮 | 2 帧后停止：额外目标使旧的“恰好一个目标”断言失败；主峰/计数正确；未进入 RF |
| perf_r3 | 数字第 2 轮 + 接收第 1 轮 | 1000 次数字测量与独立吞吐均完整；接收首条状态 1，立即停止，整次执行保留 FAIL |
| receive_r2 | 接收第 2 轮 | 补充初始化后清零与清零前后证据，零起始；30 秒通过，未用数字第 3 轮 |

`perf_r3` 的数字子项可用，不能据此把整次执行的 FAIL 改成 PASS。`x3_sources/` 保留旧测量模块原文，SHA 与各 execution receipt 对应。

RX 新窗口记录清零前 status=1、samples=0；清零后/启动前 status/samples/fft_frames/lists 全 0。RTL 的 perf_mon 会锁存历史错误；adc_tap 上游标志若持续为 1，清零后会重新置位，脚本将拒绝启动。复测不在测量期间清零，不掩盖实际溢出。证据支持“初始化阶段历史锁存影响本次入口”，未追溯到初始化期间具体哪一个周期。

## 验收口径

- 1000 次逐次验证样本 +2048、功率帧/列表 +1、标记序号、主峰和错误状态；独立连续 3 秒测试计算吞吐。
- CPU CA 输出与仓库黄金模型重新比对；CA 基准不含聚类/top-32，不能将组合吞吐比写成 FFT 单项加速或独立 CFAR 时延。
- 30 秒接收记录约 1 Hz 文字/列表刷新，250 ms 安全检查；不代表长时稳定性或新一轮人工目视验收。
- 执行前后 boot_id 一致、共享库 SHA 不变、GPIO=0、source enable=0。退出已停止接收，继续保持供电，关机仍按安全流程。
- 所有新增测量/分析 JSON 有 SHA256。报告清单对图、表、分析输入建立 SHA256；失败原始数据保留。

结果见 `docs/x3_acceptance_summary.md`、`report/opt_tables.md`。X1/X2/X3 的原指标未全部达标，不能据阶段归档声称完整 M-A 通过。
