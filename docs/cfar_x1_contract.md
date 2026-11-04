# X1 CFAR契约与离线开发边界

本文件起草于SD备份等待期间。当前X0已完成备份及板测并提交，X1配置A已获用户确认；
整机实现r2及有限板端自检已通过，RF两轮检出率未达标，最终第三轮进行中。以下新文件仅由显式V1b入口导入，
不修改N3/N4已验收模型和寄存器。当前进度以runbook/STATUS.md为准。

## 当前已实现

- sim/golden/cfar_x1.py：带硬屏蔽边界、合并/宽度筛选、功率top32的模型。
- src/regs/cfar_x1.yaml：独立的新版本寄存器草案，VERSION=0x43460002。
- tools/export_cfar_x1_constants.py：从YAML生成Python/C/仿真常量，检查地址冲突。
- src/ps/sentinel/drivers/cfar_x1.py：仅接受新版本的驱动，配置前完整参数校验，
  在FRAME_COUNT前后读取同帧状态/计数/列表并重试；不把实时STATUS当作快照状态。
- src/rtl/cfar_x1/cfar_cluster_x1.v：独立聚类模块、串行插入top32、原子发布记录/计数、
  AXIS反压、帧间配置快照。输入blocked由未来集成层产生；本模块不读取MASK寄存器。

## 记录语义

2048个fftshift后功率bin；参考窗口循环，聚类不跨频谱首尾。
记录继续为16字节小端：uint16 start/stop/peak_bin/flags，uint32 peak_pwr/sum_pwr。
所有端点包含在区间内；同峰值取第一个bin。

MERGE_GAP为命中段间最多缺失bin数量，默认6；MIN_WIDTH为合并后stop-start+1，
默认2，0表示不剔除窄目标。区间的峰值和累加包含未屏蔽的合并间隙，累加饱和到uint32。
mask不仅清零命中，还强制结束当前聚类，任何记录都不能横跨mask。
mask不从CFAR参考窗口中删除功率，也不改变参考均值分母。
显式最多16项，允许重叠/乱序，按并集处理；自动DC范围在16项之外额外生效。
DC_MASK=255禁用自动DC，0..254屏蔽中心±该值。

## 新地址与计数

| 名称 | 地址 | 定义 |
|---|---|---|
| MERGE_GAP | 0x14 | 原GAP位置，新版本默认6 |
| MIN_WIDTH | 0x38 | 0..2048，默认2 |
| MASK_COUNT | 0x3c | 0..16，默认0 |
| STATUS_LATCH | 0x40 | 与发布列表同帧；bit4容量告警，bit2/3保留检测错误/无效配置语义 |
| RAW_COUNT | 0x44 | 屏蔽和合并之后、宽度过滤之前的段数 |
| FILTERED_COUNT | 0x48 | 宽度筛选丢弃数 |
| CANDIDATE_COUNT | 0x4c | RAW_COUNT-FILTERED_COUNT，top32截断前数量 |
| MASK[0..15] | 0x80..0xbc | 每项uint32，start=低16位，stop=高16位，合法bin0..2047 |
| VERSION | 0xfc | 0x43460002；旧0x43460001不可使用新驱动 |

TARGET_COUNT=min(CANDIDATE_COUNT,32)。只有CANDIDATE_COUNT>32才置容量告警，
并在每条保留记录flags bit0置1。先功率降序，同功率按start升序。
HIT_COUNT统计屏蔽后的命中bin数，不是目标宽度之和。
FRAME_COUNT、所有发布计数、STATUS_LATCH和记录须在同一个时钟边沿切换。
STATUS仍为实时状态；STATUS_LATCH不包含实时busy/occupancy clearing位。
配置仅在上游停止、检测/聚类/occupancy清空空闲时进行，首bin锁存整组配置。

## 当前集成状态（RF量化验收仍待完成）

1. X1寄存器、MASK锁存、core/occupancy/告警已集成，18组core仿真逐位通过。
2. sentinel_v1b IP、BD和整链仿真通过；整机r2最终WNS 0.000ns、WHS +0.032ns，审计PASS。失败r1保留且未部署。
3. V1b绑定、monitor_x1、部署与指标脚本已完成；最新部署前165项相关回归通过，旧回归计数仅为历史记录。
4. 用户已确认X1配置A；部署16项文件及有限自检通过，PC独立复核四帧8192功率字零差异。
5. 两轮RF电台检出率66.02%/59.22%，均低于80%；容量告警/采样溢出均0。第三轮仅降低门限系数，不改评分。旧v1保留用于回退。

独立cluster的blocked输入假定已按帧固定；bin_index/TLAST假定由已校验的检测器提供。
候选排序时会暂停输入；不能把当前模块仿真当成X2的30.72MSPS零丢样证明。
独立OOC通过（如果通过）也不能替代整机WNS/WHS或板测。

## 复现

从仓库根目录运行：

~~~powershell
./.venv/Scripts/python.exe tools/export_cfar_x1_constants.py
./.venv/Scripts/python.exe -m pytest sim/golden/tests/test_cfar_x1.py sim/golden/tests/test_cfar.py src/ps/tests tools/tests/test_verify_sd_image.py -q
# 长任务后台运行；Attempt限1..3，已有同名证据不覆盖。
./tools/test_cfar_cluster_x1.ps1 -Attempt 1
./tools/synth_cfar_cluster_x1.ps1 -Attempt 1
~~~

已有r1结果的仓库直接阅读结果；需要重跑时使用下一轮编号。
新向量位于data/reference/cfar/x1_rN，模型结果与清单SHA256一起保留。
