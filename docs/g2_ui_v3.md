# LCD界面第三版：离线预览与接入检查点

用户已确认采用预览风格。界面已接入监测、听音、自检、三音及A/B演示，默认v3，可用`--ui v2`回退。第三轮600秒板测已完成，功能通过、耗时指标未达标，最终指标如下。

预览命令（仓库根目录，主机Python环境）：

```powershell
python tools/preview_ui_v3.py
python -m pytest src/ps/tests/test_ui_v3.py -q
```

图像输出到`report/figures/ui_v3/`：SIG信号卡、TGT选中目标和星座、STAT统计、OTA发送高亮/闪烁暗相、自检。`overview.png`为六种画面总览。所有示例频率、计数、置信度、星座、温度、帧率和准确率均为合成展示数据，左侧明确标注OFFLINE/SYNTHETIC；不是新的射频实测结果。`preview_manifest.json`和SHA256记录图像摘要。

文件职责：

- `src/ps/sentinel/ui_v3/theme.py`：固定调色板、字号、字体缓存及调制类型文字标记。
- `src/ps/sentinel/ui_v3/widgets.py`：限宽文字、进度条、反色徽章、有限幅星座散点。
- `src/ps/sentinel/ui_v3/layout.py`：三个页面、底栏、段标题、倒计时、TX闪烁、最近三条事件。
- `tools/preview_ui_v3.py`：确定性合成数据与预览图，绝不访问开发板。
- `src/ps/tests/test_ui_v3.py`：区域/调色板契约、TX限制、闪烁、缺失数据和旧打包器兼容性。

界面只生成400×240右栏和80×800底栏数组，交给原`pack_ui/X5LCD`；原实现保持不变。卡片标明功率为原始值，不伪称dBFS；置信度低于0.5显示问号。调制类别用A/D/问号和文字共同表达，未仅依赖颜色。TX开启采用黄色反色块，1Hz闪烁暗相仍保留黄色边框和文字。标题20像素、正文14像素、辅助12像素；目标类别24像素。板端沿用已有DejaVuSansMono-Bold，不安装字体包；PC预览查找现有虚拟环境中的matplotlib字体文件。

实际TX ON目视留G5配置B；G2仅接收。三个调优轮次已结束，未达标耗时保留，不追加调优。


## 接入与运行

板端运行环境为PYNQ 2.7 / Python 3.8 / Pillow 7.0，使用现有字体，无新增依赖。

```sh
sudo sh release/v2/scripts/sentinel.sh monitor --ui v3 --seconds 600
sudo sh release/v2/scripts/sentinel.sh listen 95.8 --ui v3
sudo sh release/v2/scripts/sentinel.sh demo A --ui v3 --cycles 1
sudo sh release/v2/scripts/sentinel.sh monitor --ui v2
sudo sh release/v2/scripts/sentinel.sh stop
```

以上从`/home/xilinx/sentinel`运行；仓库主机命令保持相对路径。监听/演示仍使用配置A。B组须在G5按规则重新确认接线，G2没有发射测试。发射亮相与暗相目前只有离线验证，不能以TX OFF目视确认代替实际TX ON验收。

`ui_v3/presenter.py`统一管理5Hz右栏、2Hz底栏的最高刷新频率；调用者计算/采集较慢时实际刷新会降低，不宣称固定5Hz。只有实际像素变化才交换整组双缓冲bank，原硬件接口必须整体提交，不能宣称实现独立局部bank写入。模型投票、识别计数、事件与当前IQ由真实采集循环提供。STAT计数不冒充准确率；B组在有已知发送类别时才显示发送/预测对比。未实际呈现的目标不记录为已完成显示延迟。PC标志在数据服务接入前保持OFF。

自检演示按0.5秒间隔显示四项已验证检查；普通不驻留自检直接显示最终结果。字体缓存只保存有界的ASCII单色字形和文本掩模，兼容板上的旧Pillow。原`lcd_x5.py`、`pack_ui`、`X5LCD`及位流保持不变。

## 测量口径与过程

`result.json`中的`ui.timing_samples_ms`测量绘制、四色打包、MMIO提交总耗时；硬件APPLIED等待单独记录。它不是ADC到屏幕端到端延迟。保留首次冷绘制及全部页面，不剔除慢样本以美化P95。评价脚本`tools/g2_evaluate.py`从原始样本重算分位数，并核对完整时长、帧率、错误、正式进程退出及停止状态。

第一次测试在首次绘字时因Pillow 7不支持`ImageDraw.textlength`退出，用户观察到画面卡住；正式停止检查通过，失败原始数据已保留。第二次修正兼容后可显示，但完整UI中位耗时约162ms，提前受控停止，不能计作10分钟通过。第三次采用缓存字形，预热后离线单页绘制约4–6ms，原打包器单独约25ms；用户确认“画面没问题”。G2第三轮600.929秒完成，785次提交零错误，最低38.965fps；用户确认画面正常。UI总耗时中位36.108ms/P95 165.069ms，未达25/40ms，记FAIL（功能PASS），不增加第四轮。最终停止GPIO/SRC/audio=0，冻结LCD驱动/位流未变。证据board/measurements/g2_acceptance_final.json及SHA256，原始目录g2_monitor_r3_raw。

原始数据按`board/measurements/g2_monitor_r*_raw/`保存；部署、开始、兼容检查与验收汇总JSON均带SHA256。取回工具先检查进程已停止，再比较远端文件全集及每个文件的摘要。发布包位于本机`build/g2_package*/`，不加入Git；部署记录保留包摘要及旧版回退目录。
