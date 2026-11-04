# P0 环境准备与仓库初始化（目标设备）

> 目标：在一台新的 Windows 电脑上准备好全部工具，并让仓库、第三方源码、Python 环境、板端连接都处于可用状态。
> 前提：本仓库已经完整拷贝或克隆到目标设备，其中包含 `vendor/atk/`（约 83 MB 的正点原子参考资料）。
> 所有命令都在 **PowerShell**（不需要管理员权限，除非特别注明）中，于**仓库根目录**下执行。

---

## P0.1 检查并安装工具

**运行环境**：目标设备 Windows，PowerShell
**操作**：
```powershell
$checks = [ordered]@{
  git    = { git --version }
  python = { python --version }
  ssh    = { ssh -V 2>&1 }
}
foreach ($k in $checks.Keys) { try { "{0,-7} {1}" -f $k, (& $checks[$k] | Select-Object -First 1) } catch { "{0,-7} MISSING" -f $k } }
# 查找 Vivado
$cands = "C:\AMDDesignTools","C:\Xilinx","D:\Xilinx","D:\AMDDesignTools","E:\Xilinx","F:\Vivado","F:\Xilinx"
$viv = foreach ($c in $cands) { Get-ChildItem $c -Recurse -Depth 3 -Filter vivado.bat -ErrorAction SilentlyContinue | Where-Object FullName -match '\\Vivado\\bin\\vivado\.bat$' }
$viv | Select-Object -ExpandProperty FullName
```
**缺少工具时**：标记 `BLOCKED-HUMAN`，把 AGENTS.md §3.3 中对应的下载链接和安装要求告诉用户。

👤 **HUMAN（如果缺少 Vivado）**：
1. 打开 <https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2025-2.html>，登录 AMD 账号，下载 "AMD Unified Installer for FPGAs & Adaptive SoCs 2025.2: Windows Self Extracting Web Installer"。
2. 运行安装程序：选择产品 **Vitis**（会同时包含 Vivado）；器件只勾选 **Zynq-7000**；安装路径用短路径，例如 `C:\AMDDesignTools`。
3. 完成后告诉代理安装路径。

**验收**：git、python（3.10–3.12）、ssh 都存在，并且找到了 `vivado.bat`。

---

## P0.2 git 全局配置

```powershell
git config --global core.longpaths true
git config --global core.autocrlf false
git config --global user.name  2>$null; if (-not $?) { "BLOCKED-HUMAN: 需要用户提供 git user.name / user.email" }
```
👤 **HUMAN**：如果还没有配置 git 身份，执行下面两行（替换成你自己的信息）：
```powershell
git config --global user.name  "<姓名>"
git config --global user.email "<邮箱>"
```
GitHub 仓库地址（用于 P7.7 开源发布）写入 `docs/board_info.md` 中的 `repo_url=` 一行，现在可以先留空。

---

## P0.3 仓库骨架（补全缺失目录）

**产出**：完整的目录结构、`.gitignore`、`LICENSE`、`README.md`（初版）
```powershell
if (-not (Test-Path .git)) { git init -b main }
$dirs = "src/hw","src/rtl/common","src/hls","src/regs","src/ip_repo","src/constraints","src/ps/sentinel","src/ps/libad9361_pynq","src/ps/models","src/ps/tests",
        "sim/golden/tests","sim/tb","sim/results","sim/scripts","build/scripts","build/reports",
        "board/overlay","board/notebooks","board/scripts","board/measurements",
        "data/synthetic","data/captured/samples","data/reference","skill","report/llm_logs","report/figures",
        "third_party","tools","logs","docs"
$dirs | ForEach-Object { New-Item -ItemType Directory -Force $_ | Out-Null }
```
`.gitignore`（写入或补全）：
```
.venv/
logs/
build/work/
*.jou
*.str
.Xil/
*.cache/
*.runs/
*.hw/
*.ip_user_files/
*.sim/
*.gen/
data/synthetic/
data/captured/**/*.sigmf-data
!data/captured/samples/**
vendor/atk/
__pycache__/
*.pyc
.ipynb_checkpoints/
```
`LICENSE`：下载 MIT 全文：
```powershell
Invoke-WebRequest https://www.apache.org/licenses/LICENSE-2.0.txt -OutFile LICENSE
```
`README.md` 初版：项目名称、器件声明（xc7z020clg484-2 / 正点原子 Z20 / AD-FMCOMMS3-EBZ）、⚠️ 上电检查清单（J7/J8 设为 2.5V；没有衰减器时禁止 TX→RX 直连）、指向 `AGENTS.md` 和 `runbook/README.md` 的链接。

**验收**：`git status` 能正常运行；上面列出的目录都存在。

---

## P0.4 生成 `tools/env.ps1`（自动探测，不写死路径）

**产出**：`tools/env.ps1`
```powershell
# 用法：在仓库根目录执行  . .\tools\env.ps1
$ErrorActionPreference = "Stop"
$env:REPO = (Resolve-Path "$PSScriptRoot\..").Path
Set-Location $env:REPO
if (-not $env:XILINX_ROOT -or -not (Test-Path "$env:XILINX_ROOT\Vivado\bin\vivado.bat")) {
  $cands = "C:\AMDDesignTools","C:\Xilinx","D:\Xilinx","D:\AMDDesignTools","E:\Xilinx","F:\Vivado","F:\Xilinx"
  $hit = foreach ($c in $cands) {
    Get-ChildItem $c -Recurse -Depth 3 -Filter vivado.bat -ErrorAction SilentlyContinue |
      Where-Object FullName -match '\\(\d{4}\.\d)\\Vivado\\bin\\vivado\.bat$' }
  if (-not $hit) { throw "Vivado not found. Set `$env:XILINX_ROOT to <install>\<version> (folder containing Vivado\ and Vitis\)" }
  $env:XILINX_ROOT = ($hit | Sort-Object FullName -Descending | Select-Object -First 1).Directory.Parent.Parent.FullName
}
$env:PATH = "$env:XILINX_ROOT\Vivado\bin;$env:XILINX_ROOT\Vitis\bin;$env:PATH"
$env:ADI_IGNORE_VERSION_CHECK = "1"
$env:VIVADO_VER = (Split-Path $env:XILINX_ROOT -Leaf)
if (Test-Path "$env:REPO\docs\board_info.md") {
  $m = Select-String "$env:REPO\docs\board_info.md" -Pattern "^board_ip=(\S+)" | Select-Object -First 1
  if ($m) { $env:BOARD_IP = $m.Matches[0].Groups[1].Value }
}
if (Test-Path "$env:REPO\.venv\Scripts\Activate.ps1") { . "$env:REPO\.venv\Scripts\Activate.ps1" }
$ErrorActionPreference = "Continue"
Write-Host "REPO=$env:REPO  XILINX_ROOT=$env:XILINX_ROOT  VIVADO=$env:VIVADO_VER  BOARD_IP=$env:BOARD_IP" -ForegroundColor Green
```
**验收**：
```powershell
. .\tools\env.ps1
vivado -version | Select-Object -First 1
"vivado: $env:VIVADO_VER" | Out-File docs/toolchain.md -Encoding utf8
"python: $(python --version)" | Out-File docs/toolchain.md -Append -Encoding utf8
"git: $(git --version)" | Out-File docs/toolchain.md -Append -Encoding utf8
```

> **全局约定**：之后所有分册中提到的 `$env:REPO` 都指仓库根目录；Tcl 脚本中用 `$::env(REPO)` 获取；Python 脚本中用 `pathlib.Path(__file__).resolve().parents[N]` 获取。**不要写死盘符**。

---

## P0.5 Python 虚拟环境

**产出**：`.venv/`（不提交）、`requirements.txt`、`requirements-board.txt`

`requirements.txt`（PC 端）：
```
numpy>=1.26,<2.2
scipy>=1.11
matplotlib>=3.8
torch>=2.2
tqdm
pyyaml
jinja2
sigmf>=1.2
pillow
pandas
jupyter
pytest
pymupdf
openpyxl
```
`requirements-board.txt`（板端，PYNQ 2.7 / Python 3.8）：
```
sigmf==1.1.1
pyyaml
```
**命令**：
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
# 国内网络较慢时：pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
# torch 只需要 CPU 版：pip install torch --index-url https://download.pytorch.org/whl/cpu
```
**验收**：
```powershell
python -c "import numpy, scipy, torch, sigmf, yaml, fitz; print('ok', numpy.__version__, torch.__version__)"
```

---

## P0.6 拉取 ADI HDL 与 no-OS（git submodule）

**ADI 分支与 Vivado 版本的对应关系**（执行前先确认实际版本）：

| 已安装的 Vivado | ADI hdl 分支 | 说明 |
|---|---|---|
| 2025.2 | `hdl_2026_r1`（要求 2025.1） | 设置 `ADI_IGNORE_VERSION_CHECK=1`，IP 会自动升级 |
| 2026.1 | `main`（要求 2026.1） | 版本完全匹配，推荐 |

```powershell
. .\tools\env.ps1
$branch = if ($env:VIVADO_VER -like "2026.*") { "main" } else { "hdl_2026_r1" }
git ls-remote --heads https://github.com/analogdevicesinc/hdl.git $branch     # 确认分支存在
git submodule add -b $branch https://github.com/analogdevicesinc/hdl.git third_party/hdl
git submodule add https://github.com/analogdevicesinc/no-OS.git third_party/no-OS
git -C third_party/no-OS submodule update --init --recursive
@"
hdl:   $(git -C third_party/hdl rev-parse HEAD) (branch $branch)
no-OS: $(git -C third_party/no-OS rev-parse HEAD)
required_vivado (adi_env.tcl): $((Select-String third_party/hdl/scripts/adi_env.tcl -Pattern 'required_vivado_version "([^"]+)"').Matches[0].Groups[1].Value)
"@ | Out-File docs/third_party_versions.md -Encoding utf8
```
如果 `third_party/hdl` 已经存在（比如仓库是带子模块克隆下来的），改为执行 `git submodule update --init --recursive`。

**验收**：
```powershell
Test-Path third_party/hdl/projects/fmcomms2/zed/system_bd.tcl, third_party/hdl/library/axi_ad9361, third_party/no-OS/drivers/rf-transceiver/ad9361
```
**排错**：
- 出现 `Filename too long`：确认已执行 `git config --global core.longpaths true`，并且仓库路径足够短（AGENTS.md §3.5）。
- 分支不存在：执行 `git ls-remote --heads https://github.com/analogdevicesinc/hdl.git "hdl_*"`，选择版本要求最接近已安装 Vivado 的分支，并记录下来。
- 国内网络慢：用 `--depth 1` 浅克隆；或者先通过镜像（例如 `https://gitclone.com/github.com/...`）克隆，再执行 `git remote set-url origin` 改回官方地址。

---

## P0.7 校验正点原子参考资料（`vendor/atk/`）

`vendor/atk/` 已经由原始设备上的 `tools/pack_vendor.py` 生成，并随仓库拷贝过来。这一步只做检查：
```powershell
$need = "vendor/atk/docs/z20_base_schematic_1v0.pdf","vendor/atk/docs/z20_core_schematic_1v0.pdf",
        "vendor/atk/docs/z20_base_assembly.pdf","vendor/atk/docs/z20_io_gbk.xdc",
        "vendor/atk/pynq_ref/base/ready_to_test/base.hwh","vendor/atk/pynq_ref/base/ready_to_test/base.tcl",
        "vendor/atk/pynq_ref/ip_repo/rgb2lcd","vendor/atk/pynq_ref/ip_repo/axi_dynclk_v1_0",
        "vendor/atk/pynq_ref/6_ov5640_lcd/vivado/ov5640_lcd/ready_to_test/ov5640_lcd.tcl"
$need | ForEach-Object { "{0,-6} {1}" -f (Test-Path $_), $_ }
```
**如果缺失**：👤 HUMAN。请用户从正点原子官方资料下载入口 <http://www.openedv.com/thread-351965-1-1.html> 获取"Z20 ZYNQ 开发板资料盘(A盘)"，然后运行：
```powershell
python tools/pack_vendor.py "<资料盘根目录>"
```
> 全文约定：之后 runbook 中凡是提到 `third_party/atk_ref/...` 的地方，一律对应 `vendor/atk/pynq_ref/...`；`$ATK\3_开发板原理图\...` 一律对应 `vendor/atk/docs/...`。

---

## P0.8 👤 HUMAN 板端准备

PYNQ 镜像不在仓库中（约 1.9 GB）。

1. 获取镜像：正点原子资料盘 `4_Source_Code\6_PYNQ_Design\ATK-Z20-2.7.0.zip`（下载入口同 P0.7）。**如果用户已经在原设备上烧好 SD 卡，直接把卡插到板上即可，可以跳过 1–3。**
2. 用 7-Zip 解压得到 `ATK-Z20-2.7.0.img`。
3. 用 balenaEtcher 把镜像写入 ≥ 16 GB 的 MicroSD 卡。
4. 启动拨码设为 SD 启动：底板 BOOT_CFG（J19）设为 **BOOT_MODE0 = OFF，BOOT_MODE1 = OFF**（底板丝印表格中 "SD Card" 一行）。
5. 连接：网线接 **GE_PS** 网口（不是 GE_PL）；USB 线接 **USB_UART**；12V 电源。
6. 串口：115200 8N1。登录后执行：
```bash
ip -4 addr show eth0 | grep inet
uname -a
python3 -V
pip3 list 2>/dev/null | grep -i pynq
which python3; ls /usr/local/share/pynq-venv/bin/python3 2>/dev/null
df -h /
```
7. 在 PC 上执行 `ssh xilinx@<板子IP>`（密码 `xilinx`），确认能登录。
8. 配置免密登录（在 PC 上执行）：
```powershell
if (-not (Test-Path $env:USERPROFILE\.ssh\id_ed25519)) { ssh-keygen -t ed25519 -N '""' -f $env:USERPROFILE\.ssh\id_ed25519 }
Get-Content $env:USERPROFILE\.ssh\id_ed25519.pub | ssh xilinx@<板子IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

**代理接下来要做的**：把用户回报的信息写入 `docs/board_info.md`，格式如下（`tools/env.ps1` 和 `tools/board.ps1` 都从这个文件读取）：
```
board_ip=192.168.x.x
board_user=xilinx
board_python=/usr/local/share/pynq-venv/bin/python3
kernel=<uname -a>
pynq_version=<2.7.x>
lcd_model=<屏背型号>  lcd_res=<1024x600|800x480>
repo_url=
```
**验收**：`ssh xilinx@$env:BOARD_IP "echo ok"` 能免密输出 `ok`。

---

## P0 阶段验收

```powershell
. .\tools\env.ps1
vivado -version | Select-Object -First 1
python -c "import numpy, scipy, torch; print('py ok')"
Test-Path third_party/hdl/projects/fmcomms2/zed, vendor/atk/pynq_ref/base/ready_to_test/base.hwh, docs/board_info.md
git add -A; git commit -m "[P0] environment ready on target machine"
```
