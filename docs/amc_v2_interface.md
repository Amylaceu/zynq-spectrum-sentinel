# AMC v2 接口与验收约定

## 数据接口

- 公共入口：`sentinel.amc.infer_np.Predictor(model_path, precision='int8')`。
- 调用：`predict(iq, fs=480000)`。接收复数 `[4096]` / `[B,4096]`，或实数 I/Q `[2,4096]` / `[B,2,4096]`；I 在前、Q 在后。无效长度、非有限值和零功率输入必须拒绝。
- 训练和部署共同使用 `sentinel/amc/contract.py` 与 `features.py`；`sim/golden/params.py` 中的 `AMC_FS=480000`、`CAPTURE_LEN_AMC=4096` 与之对应。输入必须先完成目标移频和抗混叠滤波，不能直接把 3.84 MSPS 原始采样当作 480 kSPS 输入。
- 第一层为八大类 CNN + 24 维浮点统计特征。第二层为纯 NumPy 的盲符号率、频偏校正、RRC/Gardner 及 PSK/QAM 阶数判断。
- 返回每段的 `label`、`class_index`、`coarse`、`coarse_index`、`confidence`、`detail`。`confidence` 是启发式分数，尚未经过概率校准；`detail['symbols']` 为盲同步后的复数符号，可用于星座显示。非 PSK/QAM 类的 `detail` 为 `None`。
- 导入和推理不会初始化 AD9361、访问 MMIO、开启 TX 或加载位流。X5 负责捕获、调度、投票及界面集成。

## 量化含义

导出采用 BN 融合、逐输出通道 INT8 权重、每段独立的动态 INT8 激活及 INT32 累加。缩放、偏置、全局池化、softmax 和统计特征仍为浮点计算，因此报告称为“混合精度 INT8”，不称为全整数推理。导出文件同时保留 FP32 权重供一致性复核。

## 数据与轮次

正式数据为十类、13 个 SNR 档，每个 class/SNR 2000 段，共 260000 段；分层划分为 train/val/test = 208000/26000/26000。沿用 v1 的种子和分组划分规则，4096 点波形与原 1024 点数据不同，不宣称为同输入的严格配对比较。测试数据不参加梯度更新、归一化参数估计或 checkpoint 选择。

`data/synthetic/amc_v2/manifest.json` 保存各数组与生成源码的 SHA256。每轮源码冻结于 `build/work/x4_pc_rN/source/`，训练日志写入 `logs/X4_pc_rN_*.log`。SMOKE 数据仅验证流程，不消耗正式准确率轮次，也不计入性能达标结论。

正式轮次最多三轮。指标不变：10 dB 下十类 ≥88%、大类 ≥95%、QPSK/8PSK 召回率各 ≥80%、量化准确率下降 ≤1 个百分点、板端完整单次推理 ≤100 ms。独立分析器从保存的逐段预测重算指标，不能只采信训练脚本的 PASS 字段。

## 板端验收和部署

`tools/bench_x4_board.py` 将每轮冻结的 runtime、导出模型和 50 段独立测试样本上传至独立 setup 目录。普通 SSH 用户离线运行，无 sudo、无射频操作、无已部署文件替换。包含前端和第二层的耗时与单独第二层耗时分别记录。

模型在 `build/work/` 中完成评测后，必须把选定的导出、metadata、SHA256 与验收结论一起归档至 `src/ps/models/weights/`，才能由 X5 复用。未通过的模型允许作为显式标记的实验候选，不能描述为已验收的自动调制识别成品。

## 可追溯产物

- `board/measurements/x4_pc_rN.json`：执行记录、冻结源码与日志摘要。
- `board/measurements/x4_pc_rN_evaluation.json/.npz`：完整测试曲线、混淆矩阵与逐段预测。
- `board/measurements/x4_board_rN.json`：板端离线推理测量。
- `board/measurements/x4_analysis_rN.json`：独立复核结论。
- `report/figures/e7_x4_rN_*.png`：带明确数据差异说明的 E7 历史对照。

以上 JSON/NPZ 配套 SHA256；最终状态以 `runbook/STATUS.md` 和各轮分析为准。
