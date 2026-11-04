# P2.8 硬件参考向量

生成命令：在仓库根目录加载 tools/env.ps1，执行 `python -m sim.golden.export_refs --out data/reference`。

manifest.json 记录各文件 SHA256、尺寸、数组形状、字长和生成配置；数据与安装目录无关，但 FFT 运行需要本机 AMD C 模型。AMD DLL 不在此数据集中，也不随仓库分发。

- npy 为小端整数，hex 为 C 顺序展平、每行一个二进制补码整数，具体字长看 manifest。
- `in_iq` 为 N×2 标量 I/Q；`in_axis32` 为已打包 AXIS 字，I在低16位、Q在高16位，不能将前者的hex直接作为32位总线文件读取。
- spectrum FFT 为自然序 N×2、24位左对齐整数；power/welch/db 已做fftshift。功率和dB的标度见 docs/spectrum_numeric.md。
- CFAR `exp_tgt_*` 是目标列表的连续小端字节流，每16字节一个记录，布局 HH HH II。RTL 128位记录消费端须每16字节按小端组装，不能把每行字节误当成一个完整目标。
- PFB 输出 [frames,16,2]，帧端点 n×8，初始历史为零；不是已丢弃启动段的数据。
- HOC 矩按 manifest 的顺序每项实、虚两路，hex为48位，npy使用int64保存，比较时取48位补码。count=1024，右移量见manifest。
- NCO捕获和解调重采样使用已注明的参考数值算法；后续对应RTL按其规定的SQNR/延迟对齐验收，不虚称目前已完成硬件逐位一致。
- render 输入和输出均已保存，参考画面为800×480，不是默认RGB屏的1024×600。

这里的数据都是确定性仿真数据，未包含真实接收或上板测量结果。
