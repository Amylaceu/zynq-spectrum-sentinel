# X4 分层识别验收记录

## 结论

X4 为 **FAIL**。已完成三轮，按 `90_plan.md` 的失败处理继续 X5，不追加训练、不降低指标。归档完整性 PASS 只表示文件与 SHA256 可追溯，不代表识别验收通过。

| 正式轮次 | INT8 十类@10dB | 八大类@10dB | QPSK召回 | 8PSK召回 | 板端中位/最大耗时ms | 结论 |
|---|---|---|---|---|---|---|
| 1 | 78.60% | 97.65% | 0% | 94.00% | 53.661 / 790.997 | FAIL |
| 2 | 88.45% | 97.95% | 78.50% | 98.00% | 54.284 / 200.942 | FAIL |
| 3 | 87.65% | 97.85% | 79.50% | 90.50% | 49.265 / 184.668 | FAIL |

第三轮十类低于88%，QPSK低于80%，部分单次推理超过100ms。第二轮虽达到总体十类指标，但QPSK、部分SNR量化下降和单次耗时未通过。第三轮FP32十类87.85%，INT8下降0.20个百分点；每个SNR的下降均不超过1个百分点。各轮独立判定见 `board/measurements/x4_analysis_rN.json`。

## 冻结的实验接口

- 选用第三轮作为 X5 的实验候选，`src/ps/models/weights/amc_v2/selected.json` 明确保留 FAIL；不能将其描述为已验收的十类识别器。
- 模型SHA256：`5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935`。
- 输入4096个复数样本、480kSPS，八类CNN与24维浮点统计特征；高阶PSK/QAM以NumPy盲同步细分。INT8指混合精度权重/激活及INT32累加，缩放、HOC和同步仍含浮点。
- 训练/验证/测试208000/26000/26000段。正式评测采用独立测试集，合成数据的带内SNR不能等同空口SNR。
- 置信度未校准。第三轮合成FM召回99.5%，不能代替X5真实电台识别比例。
- API、数据布局及来源冻结约定见 `docs/amc_v2_interface.md`。X5必须先完成移频、滤波与采样率匹配。

## 验证与证据

- `logs/X4_finalize_r3.log`：`X4_FINALIZE_COMPLETE`。
- `logs/X4_full_regression.log`：252 passed in 6.00s。
- `board/measurements/x4_archive_integrity.json`：28份测量及三轮结论的哈希检查；本次收尾另以只读方式重算全部28份哈希和选定模型/manifest，均一致。
- 三轮逐段预测、混淆矩阵、准确率曲线、板端测量均为JSON/NPZ并配SHA256；冻结源码归档于 `report/results/x4_sources_rN.zip`，E7图位于 `report/figures/e7_x4_rN_*.png`。
- 板端离线推理不使用射频、不加载位流。下一步X5以已通过时序的3.84MSPS工程为基础，新的整机仍须独立时序审计。
