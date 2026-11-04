"""把正点原子资料盘中本项目需要的文件抽取到 vendor/atk/（英文文件名），便于整个仓库拷贝到其他设备。
用法：python tools/pack_vendor.py "<正点原子资料盘根目录>"
只需要在原始电脑（有资料盘的那台）上运行一次；其他设备直接使用 vendor/atk/。
"""
import hashlib, json, os, shutil, sys, zipfile, pathlib

atk = pathlib.Path(sys.argv[1])
repo = pathlib.Path(__file__).resolve().parents[1]
out = repo / "vendor" / "atk"
out.mkdir(parents=True, exist_ok=True)

# 1) 原理图、引脚、装配图（重命名为纯英文）
files = {
    "3_开发板原理图/Z20 ZYNQ开发板底板原理图_1V0.pdf": "docs/z20_base_schematic_1v0.pdf",
    "3_开发板原理图/Z20 ZYNQ开发板核心板原理图_1V0.pdf": "docs/z20_core_schematic_1v0.pdf",
    "3_开发板原理图/Z20 ZYNQ_IO.xdc": "docs/z20_io_gbk.xdc",
    "3_开发板原理图/Z20 ZYNQ开发板IO引脚分配表.xlsx": "docs/z20_io_table.xlsx",
    "3_开发板原理图/Z20 ZYNQ结构图&DXF&封装库/Z20 ZYNQ底板/Z20 ZYNQ底板结构图/ZYNQ7020装配图.pdf": "docs/z20_base_assembly.pdf",
    "2_文档教程/6_【正点原子】Z20 ZYNQ之PYNQ开发指南_V1.0 .pdf": "docs/atk_z20_pynq_guide_v1.0.pdf",
    "7_芯片数据手册/09_RGB_LCD触摸屏/GT9147数据手册.pdf": "datasheets/gt9147_datasheet.pdf",
    "7_芯片数据手册/09_RGB_LCD触摸屏/GT9147编程指南.pdf": "datasheets/gt9147_programming_guide.pdf",
    "7_芯片数据手册/10_XADC/ug480_7Series_XADC.pdf": "datasheets/ug480_7series_xadc.pdf",
    "7_芯片数据手册/12_RTC实时时钟芯片/PCF8563.pdf": "datasheets/pcf8563.pdf",
    "7_芯片数据手册/06_EEPROM/AT24C64_datasheet.pdf": "datasheets/at24c64.pdf",
}
manifest = {}
for src, dst in files.items():
    s = atk / src
    d = out / dst
    d.parent.mkdir(parents=True, exist_ok=True)
    if s.exists():
        shutil.copy2(s, d)
        manifest[dst] = hashlib.sha256(d.read_bytes()).hexdigest()
    else:
        print("WARN missing:", src)

# 2) PYNQ 例程：base 工程、IP 仓库、DMA 与 LCD 例程（ready_to_test + notebook）
z = zipfile.ZipFile(atk / "4_Source_Code/6_PYNQ_Design/Z20.zip")
want = ("base/ready_to_test/", "ip_repo/", "4_dma_tutorial/notebook/",
        "4_dma_tutorial/vivado/dma_tutorial/ready_to_test/",
        "6_ov5640_lcd/notebook/", "6_ov5640_lcd/vivado/ov5640_lcd/ready_to_test/")
n = 0
for name in z.namelist():
    if name.startswith(want) and not name.endswith("/"):
        z.extract(name, out / "pynq_ref"); n += 1
manifest["pynq_ref/*"] = f"{n} files from Z20.zip"

(out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf8")
(out / "README.md").write_text(
    "# vendor/atk —— 正点原子 Z20 参考资料（节选）\n\n"
    "来源：正点原子 Z20 ZYNQ 开发板资料盘(A盘)，官方下载入口：http://www.openedv.com/thread-351965-1-1.html\n"
    "由 tools/pack_vendor.py 抽取并改为英文文件名。版权归正点原子所有，仅供本项目开发参考，**不随开源仓库发布**（已在 .gitignore 中排除）。\n\n"
    "| 路径 | 内容 |\n|---|---|\n"
    "| docs/z20_base_schematic_1v0.pdf | 底板原理图（FMC 第 15 页、音频第 12 页、LCD 第 11 页、电源与 J7/J8 第 3 页） |\n"
    "| docs/z20_core_schematic_1v0.pdf | 核心板原理图（Bank13/33 第 3 页、Bank34/35 第 4 页） |\n"
    "| docs/z20_base_assembly.pdf | 底板装配图（第 2 页为丝印面：J7/J8、LINE_OUT、SPEAKER 位置） |\n"
    "| docs/z20_io_gbk.xdc | 官方引脚约束（GBK 编码） |\n"
    "| docs/z20_io_table.xlsx | 官方引脚分配表 |\n"
    "| docs/atk_z20_pynq_guide_v1.0.pdf | PYNQ 开发指南（镜像烧录、启动拨码、登录方式） |\n"
    "| pynq_ref/base/ready_to_test/ | PYNQ base 工程（base.tcl / base.hwh / base.bit / base.xdc），PS7 配置来源 |\n"
    "| pynq_ref/ip_repo/ | 正点原子自定义 IP（rgb2lcd、axi_dynclk、audio_codec_ctrl 等） |\n"
    "| pynq_ref/4_dma_tutorial/, pynq_ref/6_ov5640_lcd/ | DMA 与 LCD 例程（位流 + notebook） |\n"
    "| datasheets/ | GT9147、XADC、PCF8563、AT24C64 手册 |\n", encoding="utf8")
print(f"vendor/atk ready: {len(files)} docs, {n} pynq_ref files")
