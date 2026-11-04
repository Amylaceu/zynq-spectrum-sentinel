# AMC 三轮验收失败记录

| 轮次 | 方法 | 10 dB测试准确率 | 门槛 | 结论 |
|---|---|---:|---:|---|
| 1 | Raw IQ baseline | 77.00% | 88% | 未通过 |
| 2 | Differential IQ | 67.15% | 88% | 未通过 |
| 3 | Raw IQ curriculum + phase augmentation | 75.90% | 88% | 未通过 |

三轮均为同一26万段合成数据、同一独立划分、40轮训练。检查验证集后调整实验方法，没有调整样本标签、验收数据或88%门槛。

日志关键错误：`RuntimeError: P2.9 accuracy acceptance failed: SNR10=75.9000%, required>=88%`（第三轮）。

已达到用户及AGENTS.md第4.5条的三轮上限：停止新增训练与功能推进，等待人工决定下一步。P2.9=FAIL；P2.10未开始，INT8及CNN-only正式基线未完成。

后续可评估接收同步/带宽匹配预处理，或在明确批准后调整分类模型方案；这些是待审查方向，不是已查明的唯一根因。

最好首轮权重只作为失败实验保留，不作为可部署的amc_v1成品。三轮指标位于report/results/amc_attempts.json，曲线位于report/figures/amc_attempts_failed.png。
