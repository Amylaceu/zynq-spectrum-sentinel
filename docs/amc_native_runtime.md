# X4 可选本地符号同步加速（2026-11-03）

## 结论

这是 CPU 推理耗时优化，不修改模型、训练集、判决阈值或正式 X4 FAIL。旧调用 `Predictor(model)` 继续使用原 NumPy 路径；需要显式实例化 `NativePredictor` 才启用本地库。板上既有部署没有被覆盖。

首轮板测：13 个 SNR 档、260 段合成测试样本，原版、新默认接口及本地版完整输出精确一致（标签、置信度、同步符号及诊断值）；36 个符号同步边界/随机用例也零差异。容差预设为符号绝对1e-6、标量绝对1e-10，实际误差均为0。未宣称全部26000段或所有未来输入均逐位等价。

配对计时使用10类各5段SNR10样本，3次重复，旋转原版/本地版次序：

| 指标 | 冻结原版 | 本地符号同步 |
|---|---:|---:|
| 完整预测次数 | 150 | 150 |
| 中位 ms | 49.334 | 49.364 |
| P95 ms | 126.029 | 98.456 |
| 最大 ms | 140.669 | 134.450 |
| >100ms 次数 | 60 | 3 |

P95降低约21.88%；高阶PSK/QAM类别中位从约118.5–121.0ms降至92.6–95.8ms。六个直接分类类别不使用符号同步，整体中位因此变化很小。偶发最大值仍>100ms，**不能宣布时延硬指标或X4通过**。保持原十类87.65%、QPSK79.5%的失败结论。

## 实现

- `native/gardner.c` 用双精度标量运算执行串行反馈循环，保持原计算顺序；编译禁用fast-math及FMA合并。没有访问硬件或引入推理线程。
- `infer_native.py` 保留NumPy相位搜索；相同整数偏移的重复打分只计算一次，保持首次最大值规则。
- `fine.refine(..., timing_recovery=...)`、`Predictor(..., refiner=...)` 是向后兼容的显式注入点。默认行为不变，模块导入不加载动态库。
- 动态库路径必须显式提供，ABI版本为1；缺文件、ABI不符、非法输入会报错，不静默降级。
- 原模型 SHA256：`5e752f90523ea92d95bbd0ac3fe40ff70c12d9f0023373c36c22acd495508935`。

## 另一台设备/后续agent使用

不要把Windows或x86编译的库搬到ARM板。先在目标PYNQ板复制本仓库的源码，使用板上的gcc编译；不需要sudo、不操作RF。以实际仓库根目录执行：

```sh
sh tools/build_amc_native.sh "$PWD/build/native/libsentinel_gardner.so"
```

输出已存在时脚本拒绝覆盖，使用新目录存放新版本。输入仍为4096点、480kSPS、复数数组或INT16 I/Q[2,4096]，不改变X5捕获接口。示例从仓库根目录启动Python：

```python
from pathlib import Path
import sys
root = Path.cwd()
sys.path.insert(0, str(root / 'src/ps'))
from sentinel.amc.infer_native import NativePredictor
predictor = NativePredictor(
    root / 'src/ps/models/weights/amc_v2/round_3/model.npz',
    root / 'build/native/libsentinel_gardner.so',
)
# result = predictor.predict(iq, fs=480000)
```

启用前重新核对库与C源码哈希；先离线与原版比较，再进入捕获/显示集成。不要未经验证自动替换X5实例。

## 证据与轮次

`board/measurements/x4_native_board_r1.json`及SHA256包含300条计时、260条样本标签、36个核心用例、编译器/参数/库和源码哈希、boot_id。冻结原版从提交`cb2c15d`提取，并核对上一轮记录的源码哈希，因此不是用已改动的新默认路径冒充旧基线。

板端隔离目录为`/home/xilinx/sentinel/setup/x4_native_board_r1`；本地可复核包在`build/work/x4_native_board_r1/`。脚本`tools/bench_x4_native_board.py --attempt 1`为已完成的一轮，拒绝覆盖；后续新实验最多3轮，不能通过重跑挑选最好结果。正式训练三轮不变。

PC测试`src/ps/tests`为176 passed；完整默认与原版等价还在板端260段上复核。未做真实RF准确率、UI、长时间稳定性或实时调度验收。
