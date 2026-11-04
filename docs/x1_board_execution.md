# X1 板测衔接与证据清单

从经 Git 核实的仓库根目录执行，Python 使用 `.venv`。本文件只描述 X1；
实际是否通过，以 `runbook/STATUS.md` 和各验收 JSON 为准。

## 前置条件

- 用户已确认配置 A，授权证据：`docs/x1_board_configuration_a.json`。
- RX1A 接粗长 20–512 MHz 天线，TX1A 空；J22、J7/J8=2.5V 不变。
- 不发射，不换线；测试中不得复位、断电或拔 SD 卡。
- 当前构建轮次为整机 r2。r1 时序失败已归档，禁止加载。
- `tools/audit_sentinel_v1b.ps1 -Attempt 2` 必须通过：最终 setup/hold/pulse、
  bus-skew、时序覆盖、资源、HWH 和产物哈希都满足要求。
- `docs/x1_v1b_prebuild_r2.json` 的全部输入哈希保持一致；电脑端软件检查快照为
  `docs/x1_software_predeployment_r3.json`。旧快照不覆盖、不混用。

## 顺序执行

以下数字 `1` 是尚未使用的板测轮次，与整机实现 r2 分开计数；
如有失败，保留原文件，再使用下一轮编号，最多三轮。

```powershell
. ./tools/env.ps1
./tools/audit_sentinel_v1b.ps1 -Attempt 2 *> logs/X1_final_audit_console_r2.log
if ($LASTEXITCODE) { throw '禁止部署：整机审计未通过' }

& $env:ZSS_PYTHON tools/deploy_x1.py --attempt 1
if ($LASTEXITCODE) { throw '文件部署未通过' }
```

部署工具不加载位流、不初始化射频；保留 v1 基线和原 runtime 备份。
以下板测命令会加载通过审计的 v1b，必须逐项运行并检查退出码。
`--sudo-stdin` 由调用代理通过子进程标准输入安全提供已获授权的凭据，
或交由用户在终端手动输入；不要把凭据写进脚本、日志或仓库。

```powershell
& $env:ZSS_PYTHON tools/run_x1_board.py --mode selftest --attempt 1 --confirm-configuration-a --sudo-stdin
if ($LASTEXITCODE) { throw '自检执行失败，保留本轮证据后停止' }
& $env:ZSS_PYTHON tools/analyze_x1_selftest.py --attempt 1
if ($LASTEXITCODE) { throw '自检独立复核失败，禁止进入RF测试' }

& $env:ZSS_PYTHON tools/run_x1_board.py --mode capacity --attempt 1 --confirm-configuration-a --sudo-stdin
if ($LASTEXITCODE) { throw '容量窗口执行失败，停止并诊断' }
& $env:ZSS_PYTHON tools/run_x1_board.py --mode station --attempt 1 --confirm-configuration-a --sudo-stdin
if ($LASTEXITCODE) { throw '电台窗口执行失败，停止并诊断' }

& $env:ZSS_PYTHON tools/analyze_x1_board.py --capacity board/measurements/x1_capacity_r1.json --station board/measurements/x1_station_r1.json --out board/measurements/x1_rf_metrics_r1.json
if ($LASTEXITCODE) { throw '指标未达标，保留结果并按90_plan诊断' }
```

先看自检独立复核通过，才执行真实接收。两窗口必须使用完全相同的 CFAR/平均参数：
默认 AVG_SHIFT=3、MIN_WIDTH=2、MERGE_GAP=6、ALPHA=1974、DC_MASK=3，
无额外屏蔽。容量窗口 LO=98MHz，电台窗口 LO=96.4MHz；各120秒、3.84MSPS、
RF滤波带宽1.5MHz、BUS_PHASE=3。98MHz窗口本身不覆盖95.8MHz。

## 验收与停止点

1. 自检：单音误差≤1bin、三音3目标、四帧8192功率字逐位零差异；PC独立重算NPZ。
2. 容量告警率<5%；95.8MHz±25kHz电台检出率≥80%；记录目标数中位数。
3. 原始遥测缺失保守计入分母；重复CFAR序号或未推进的帧/输入计数拒绝验收，
   不能删掉失败记录来提高指标。统计的是周期快照比例，不是所有PL帧的比例。
4. 双TX衰减持续89.75dB、RSSI≤−30dBm、温度30–85°C、采样溢出0。
5. 停止后，在独占锁下运行板端 `scripts/x1_postflight.py`，只读确认GPIO=0、SRC停止；
   将输出保存为新的JSON和SHA256，并核对前后boot_id一致。
6. **人工步骤**：向用户说明当前LO、已知95.8MHz条目位置，请用户核对电台频率及动态画面。
   目视结果单独保存并以哈希关联本轮测试；不要复用X0/N4的确认。
7. 指标通过不能替代人工验收。全部通过后更新X1汇总与STATUS，提交 `[X1] ...`；
   才能进入X2。未通过则保留证据，按90_plan诊断，不能标DONE。

每个测量JSON及归档均须有SHA256。长任务日志以 `logs/X1_` 开头。
板端墙上时钟不作为验收时间依据；使用PC时间、单调计时、boot_id和文件哈希。
