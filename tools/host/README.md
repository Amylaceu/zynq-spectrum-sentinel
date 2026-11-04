# SentinelHost 使用说明

Windows 10/11 x64。开发版使用 Python 3.12；发行版不需要 Python。

## 从源码启动

在仓库根目录运行：

```powershell
.venv/Scripts/python.exe -m pip install -r tools/host/requirements.txt
.venv/Scripts/python.exe tools/host/run_host.py --connect 192.168.2.99
.venv/Scripts/python.exe tools/host/run_host.py --replay data/sessions/A_monitor.zsr
```

IP以开发板实际局域网地址为准。板端先在项目目录启动：

```sh
sudo sh release/v2/scripts/sentinel.sh monitor --hostlink --ui v3
```

配置A：20–512MHz天线接RX1A，TX1A空。结束使用正式stop入口，关电前sync/shutdown。

## 独立程序

保留整个 `SentinelHost` 目录，不能只复制exe。双击 `SentinelHost.exe`，输入板卡IP后点Connect。同目录下有会话时，可点Replay选择相应 `.zsr` 文件夹，无需连接开发板。

```powershell
./SentinelHost.exe --replay sessions/A_monitor.zsr
```

无会话时不自动生成假数据。合成预览明确标注OFFLINE/SYNTHETIC；只用于开发检查。B组真实会话在G5确认接线并彩排后补入，不能把预览作为B组实测。

## 操作

当前默认是三栏中文界面。左侧导航切换监测、识别、音频、闭环评测、全景、系统、回放；中间 LCD 孪生始终保留，末项可打开原分析视图。
画布自动按窗口空间放大，最近邻缩放；按 `F` 或双击孪生标题聚焦，`F11` 全屏演示，`Tab` 切页。
界面中的未验收功能会显示说明或禁用按钮；当前 PC 音频/录音还未启用，不能把合成音频预览当作 FM 板测。
详细实施范围和限制见 `docs/g4plus_host_v2.md`。下列旧版按钮名称对应新版中文操作及回放页中的功能。

- Record开始录制，选择一个不存在的 `.zsr` 目录；再次点击Record或正常关闭窗口后生成校验清单。未完成的录制不接受回放。
- Replay选择已校验的会话目录。Pause暂停/继续，1x/2x切换速度；回放不向板端发送命令。
- PNG保存整窗图像；CSV导出当前目标表；IQ导出最后收到的512点 `.npy` 和小端complex64 `.cf32`。
- 点目标行请求板端选择同一key并切到TGT页。若目标已消失，板端返回错误，不自动选择其他目标。
- Matrix PNG仅在每个识别采样明确携带已知发送类别时可用；普通接收不计算准确率。
- Alerts载入 `alarms.yaml`，按指定频段最近10秒CFAR检出比例提示事件和弹窗；不是校准的信道占用率。冷却时间可防止重复弹窗。
- F11全屏/退出全屏；段标题与倒计时由板端demo消息提供。工具栏在全屏时隐藏。
- 可选token仅在密码输入框输入，不进入录制和日志。不提供发射、TX衰减或任意Shell命令。

## 数据含义

频谱为2048点PL功率快照相邻最大值抽取后的1024点；纵轴dB相对原始整数1，不是dBm/dBFS。目标功率保持原始值。灰黄色线为峰值保持，三角标记是CFAR目标；瀑布只在收到新频谱时推进。

频段占用度使用最近10秒检出快照，掉线后保留最后状态，不能把过时数据当作仍在线。网络状态栏显示实时/断线/回放。识别模型保留历史未达标结论；直方图是预测计数。

会话目录包含session.jsonl、blobs.npz、manifest.json和SHA256；不使用pickle。回放验证摘要和消息长度，原始来源写在manifest.source中。工具栏录制可以记录回放，其来源标明replay。

PC接收至Qt绘图更新耗时不代表ADC→屏幕端到端延迟；精确PL帧映射尚未认证。性能实测和限制见仓库 `docs/g4_sentinel_host.md` 及验收JSON。

## 构建

在仓库根目录后台执行并将日志保存到logs/G4_build.log：

```powershell
.venv/Scripts/python.exe tools/host/build_host.py
```

输出dist/SentinelHost；构建器拒绝覆盖现有发行目录。完整目录及其files_sha256.json一起交付。


## H1全景与手机监看（源码版本）

全景页可打开实际扫频result.json，校验全部分段和拼接文件SHA256；横轴MHz、纵轴dBFS/Hz，有限快照且未经射频功率标定。全景页使用全幅曲线视图，其他页面仍保留LCD孪生。

实时扫描由电脑端tools/f4_scan.py启动，--profile fast默认保存65536点IQ计算得到的PSD，--keep-iq可选同时保存IQ。该工具独占板端资源，扫描时不要再启动monitor。全景上位机使用--panorama-live指向该次输出目录的pano_tiles.jsonl，并用--panorama-final指向raw/result.json；只有取回结果和独立停止证据均通过后才显示已验证完成。没有频段点击启动接收功能，该功能等待常驻服务控制台集成。

顶部电脑图标打开“手机监看二维码”，地址来自IP输入框。手机和板卡需同一路由器，二维码不启动服务或检查连通性。安装本目录requirements.txt后使用；旧G4plus发行版不含本轮全景和二维码，暂未重新打包。
