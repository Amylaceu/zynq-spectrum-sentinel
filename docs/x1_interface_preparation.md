# X1接口预研：备份等待期间

历史预研记录。用户随后授权在备份期间推进PC端，当前已开始X1模型/驱动/独立cluster实现；最新契约和未完成范围见docs/cfar_x1_contract.md。板测与部署仍待X0。

## 已核实的改动范围

| 层 | 文件 | 当前行为及后续工作 |
|---|---|---|
| 黄金模型 | sim/golden/cfar.py | gap=2，从左向右截前32项；增加宽度、gap=6、屏蔽和top32 |
| 聚类RTL | src/rtl/cfar/cfar_cluster.v | 双bank列表发布，保留前32项；新增宽度筛选和top32 |
| 检测/集成 | src/rtl/cfar/cfar_detect.v、cfar_core.v | 帧配置、命中、状态发布需同步调整 |
| 寄存器 | src/regs/cfar_ctrl.yaml、src/rtl/regs/cfar_ctrl_regs.v | GAP=0x14、STATUS=0x34、VERSION=0x43460001；先定义新寄存器再生成 |
| PS驱动 | src/ps/sentinel/drivers/cfar.py | targets用FRAME_COUNT前后比对；需加入同帧状态 |
| 遥测 | src/ps/sentinel/app/monitor.py | 列表与list_overflow另读，必须改为同一序号快照 |
| 仿真 | tools/export_cfar_rtl_vectors.py、sim/tb/tb_cfar_core.sv | 原脚本覆盖固定N3目录，X1必须用独立目录保留原证据 |
| 构建 | tools/build_sentinel_v1.ps1及相关脚本 | 新建sentinel_v1b；保留已验收v1，不覆盖 |

## 待落实的契约

1. 宽度建议定义为stop-start+1，合并后过滤，默认2。窄单音回归须显式设置兼容参数，不能静默改变旧验收标准。
2. gap仍为两段间未命中bin数，小于或等于配置值合并；峰值含间隙，累加uint32饱和，保持原契约。
3. mask最多16个fftshift后0..2047闭区间；明确是否为聚类硬边界，不能让短屏蔽区被gap合并后重新报告。黄金模型/RTL同义。
4. top32按功率降序，同功率按起始bin升序。容量告警依据过滤后、截断前候选数>32；不能用输出恒<=32隐藏告警。
5. STATUS_LATCH、数量、序号、目标记录同帧发布；读回仍验证前后序号并有限重试。新增寄存器名称本身不等于原子快照。
6. 显式区分新旧IP版本；不能在旧位流写新寄存器。位流/HWH/生成寄存器/驱动/管理入口一起版本化。

## 仿真与验收准备

- width 0/1/2、末bin结束；gap 0/6边界；合并间隙内更强的未命中峰值。
- 空mask、16项、越界、重叠、DC/谱边缘、屏蔽区不可穿越的明确语义测试。
- 32/33/大量目标、最强目标在右侧、同功率排序、累加饱和。
- 连续两帧不同overflow，在MMIO拷贝中切换发布；列表/状态/序号必须一致。
- AXI反压/复位；新向量独立归档；黄金模型和RTL逐位比较并保存JSON/SHA256。

## 板测口径

- 98MHz/3.84MSPS/120秒对比容量告警；原40%是遥测记录比例，不是所有处理帧比例。
- 95.8MHz检测率另用96.4MHz窗口120秒；98MHz/3.84MSPS不包含95.8MHz。
- 记录实际RF滤波带宽（当前runtime设为1.5MHz），不能以采样率冒充模拟通带。
- 目标：同帧遥测容量告警率<5%，95.8MHz±25kHz检出率>=80%；目标数中位数、WNS/WHS>=0。
- 去重遥测序号，保存参数/原始记录/分母定义；未统计每个处理帧时不得称为全帧告警率。
- X0通过并取得配置A确认后才执行；人工目视确认电台频率不能由仿真替代。
