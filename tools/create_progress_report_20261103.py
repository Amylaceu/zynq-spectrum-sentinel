"""Create the project progress and directory handoff report; no board access."""
from pathlib import Path
import hashlib
import json

from docx import Document
from docx.shared import Cm, Inches, Pt, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'report/FPGA项目进度与文件目录说明_20261103.docx'


def verified(relative):
    p = ROOT/relative
    assert hashlib.sha256(p.read_bytes()).hexdigest() == Path(str(p)+'.sha256').read_text().split()[0]
    return json.loads(p.read_text(encoding='utf-8'))


def main():
    stability = verified('board/measurements/y3_noise_stability_human.json')
    timing = verified('board/overlay/sentinel_v2_100m/acceptance.json')
    software = verified('sim/results/y3_noise_quality_software.json')
    doc = Document()
    section = doc.sections[0]
    section.page_width, section.page_height = Inches(8.5), Inches(11)
    section.top_margin = section.bottom_margin = Cm(1.8)
    section.left_margin = section.right_margin = Cm(2)
    section.header_distance = section.footer_distance = Cm(.8)
    for name in ('Normal', 'Body Text', 'List Bullet', 'List Number', 'Title', 'Heading 1', 'Heading 2'):
        s = doc.styles[name]
        s.font.name = 'Calibri'
        s.element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), '微软雅黑')
    normal = doc.styles['Normal']
    normal.font.size = Pt(10.5)
    normal.paragraph_format.line_spacing = 1.12
    normal.paragraph_format.space_after = Pt(6)
    for name, size in [('Heading 1', 17), ('Heading 2', 12)]:
        s = doc.styles[name]
        s.font.size = Pt(size)
        s.font.color.rgb = RGBColor.from_string('17365D')
        s.paragraph_format.space_before = Pt(8)
        s.paragraph_format.space_after = Pt(7)
    doc.styles['Title'].font.size = Pt(23)
    doc.styles['Title'].font.color.rgb = RGBColor(0, 0, 0)
    header = section.header.paragraphs[0]
    header.text = 'zynq-spectrum-sentinel  |  项目进度与交接记录'
    header.runs[0].font.size = Pt(8)
    header.runs[0].font.color.rgb = RGBColor.from_string('666666')
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run('2026年11月3日  ·  第 ')
    field = OxmlElement('w:fldSimple'); field.set(qn('w:instr'), 'PAGE'); footer._p.append(field)
    footer.add_run(' 页')
    for r in footer.runs:
        r.font.size = Pt(8)

    def p(text, bold=False):
        para = doc.add_paragraph()
        para.add_run(text).bold = bold
        return para

    def h(text):
        doc.add_heading(text, 2)

    def page(title):
        doc.add_page_break()
        doc.add_heading(title, 1)

    def table(headers, rows, widths):
        t = doc.add_table(rows=1, cols=len(headers))
        t.alignment = WD_TABLE_ALIGNMENT.CENTER
        t.autofit = False
        for col, w in zip(t.columns, widths): col.width = Cm(w)
        for c, txt, width in zip(t.rows[0].cells, headers, widths):
            c.text = txt; c.width = Cm(width)
        for row in rows:
            cells = t.add_row().cells
            for c, txt, width in zip(cells, row, widths):
                c.text = str(txt); c.width = Cm(width)
        for i, row in enumerate(t.rows):
            pr = row._tr.get_or_add_trPr()
            pr.append(OxmlElement('w:cantSplit'))
            if i == 0: pr.append(OxmlElement('w:tblHeader'))
            for cell in row.cells:
                cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
                tc = cell._tc.get_or_add_tcPr()
                borders = OxmlElement('w:tcBorders')
                for edge in ('top', 'left', 'bottom', 'right'):
                    e = OxmlElement('w:'+edge)
                    for k, v in [('val','single'), ('sz','4'), ('color','D9D9D9')]: e.set(qn('w:'+k), v)
                    borders.append(e)
                tc.append(borders)
                margins = OxmlElement('w:tcMar')
                for edge, value in [('top','70'), ('bottom','70'), ('left','95'), ('right','95')]:
                    e = OxmlElement('w:'+edge); e.set(qn('w:w'), value); e.set(qn('w:type'),'dxa'); margins.append(e)
                tc.append(margins)
                fill = OxmlElement('w:shd'); fill.set(qn('w:fill'), 'E8EFF6' if i == 0 else ('F7F9FC' if i%2 == 0 else 'FFFFFF')); tc.append(fill)
                for para in cell.paragraphs:
                    para.paragraph_format.space_after = Pt(1)
                    para.paragraph_format.line_spacing = 1.05
                    for r in para.runs:
                        r.font.size = Pt(9.5); r.bold = i == 0
        doc.add_paragraph().paragraph_format.space_after = Pt(0)

    doc.add_paragraph('FPGA项目进度与文件目录说明', 'Title')
    p('基于 Zynq 7000 与 AD9361 的实时频谱智能监测与自动调制识别终端', True)
    p('编制：Codex 执行代理　｜　接收人：项目负责人　｜　记录日期：2026年11月3日')
    h('文档目的与当前结论')
    p('本文件汇总当前已实现功能、真实板测结果、噪声诊断结论、代码与数据目录、版本保存情况及后续任务，便于本人或另一台电脑上的执行代理接续开发。记录以仓库和测量回执为依据，不把“功能可运行”写成“全部竞赛指标已通过”。')
    p('项目已具备真实射频接收、实时频谱与瀑布显示、信号检测、IQ捕获、识别结果上屏和清楚的FM广播监听。识别准确率、部分性能指标及最终演示交付仍未完成。当前使用100MHz开发基线，先完成功能闭环，再优化指标。')
    h('当前硬件与运行参数')
    table(['项目', '实际配置'], [
        ('FPGA与开发板','XC7Z020，正点原子Z20'), ('射频前端','AD-FMCOMMS3-EBZ / AD9361'),
        ('处理时钟与接收率','100MHz；3.84MSPS'), ('子信道与音频采样率','480kSPS；48kHz'),
        ('显示','J22，SSD1963，800×480'), ('音频','ES8388 ROUT2 → MD8002A → J36板载喇叭'),
        ('当前接线','配置A：20–512MHz天线接RX1A，TX1A空着'),
        ('FMC电压','J7/J8保持2.5V'), ('最近FM设置','电台95.8MHz；LO 96.05MHz；接收RF带宽1.5MHz'),
        ('最近播放设置','BUS_PHASE=2，模拟输出−15dB；下次按用户要求小幅提高'),
    ], [4.1,13.4])
    p('LO是接收窗口中心，不是被监听电台频率。最近测试仅接收，双路TX衰减89.75dB，没有使用衰减器，也没有进行SMA收发直连。')
    h('文档范围')
    p('本文件只整理既有成果，不启动射频、不播放音频、不改变板端系统。最后一次测试回执确认已静音并停止GPIO/SRC/audio；这不等同于本文件生成时再次查询了实时硬件状态。')

    page('一 已完成功能与开发基线')
    table(['模块', '已完成内容', '验收边界'], [
        ('数字处理','单音0bin误差；三音3目标；8192字回放一致','不代表全带宽板测通过'),
        ('接收接口','PN检查及延迟窗口扫描通过','3.84MSPS；非全温签核'),
        ('频谱与显示','真实频谱、瀑布、信号列表已上屏','不同应用模式帧率不同'),
        ('CFAR检测','检测与定位链路可运行','原检出率指标仍未达标'),
        ('PFB与捕获','信道化和IQ捕获可用；191份回归捕获校验通过','当前按3.84MSPS推进'),
        ('调制识别','捕获、推理、列表与点图显示已接通','准确率未达标，不等同识别可靠'),
        ('喇叭输出','1kHz测试音及FM广播听音通过','接收质量仍可能波动'),
        ('质量保护','导频与相位质量检查、静音保护和状态提示','适用已确认的立体声FM'),
    ], [2.6,8.8,6.1])
    h('100MHz实现结果')
    t = timing['final_timing']; r = timing['resources']
    table(['指标','实测值'], [('WNS / WHS',f"+{t['WNS_ns']:.3f} / +{t['WHS_ns']:.3f} ns"),
        ('TNS / THS','0 / 0'), ('LUT / 寄存器',f"{r['Slice LUTs']:,.0f} / {r['Slice Registers']:,.0f}"),
        ('BRAM / DSP',f"{r['Block RAM Tile']:.0f} / {r['DSPs']:.0f}")], [5.2,12.3])
    p('当前依据用户批准的“非负时序裕量开发门槛”使用。原定WNS≥+1ns仍是后续优化目标；CDC、板外全PVT和板线预算等限制保留在development_review.json中。未把开发审计PASS当作全部竞赛指标PASS。')
    h('迁移到100MHz后的真实接收回归')
    p('120.467秒真实接收，191份IQ捕获校验通过；94条遥测无采样连续性故障。用户确认FRAME增加、频谱瀑布更新、列表和点图正常。接收接口扫描153/256点通过，原设置数据窗口16档、时钟窗口4档，恢复原寄存器设置。')
    p('识别与点图同时运行的回归中，显示中位28.988fps、最低27.711fps，仍未达30fps。FM监听模式的40fps以上结果不能替代识别模式的性能验收。150MHz旧位流与历史测试结果保留。')

    page('二 FM噪声诊断与最新板测')
    h('问题定位范围')
    p('部分原始ADC IQ已经存在明显噪声，使用此前能正常工作的电脑端解调算法也不能恢复良好内容。接线、位流不变时，后续数据又恢复清楚的FM导频。PN9四路无错误；LCD开启和关闭时都出现过好坏两种状态，不能认定屏幕就是干扰源。')
    table(['对照','19kHz导频突出度'], [('历史正常原始IQ','约29.31 / 32.48dB'),
        ('当前诊断r1原始IQ','约4.81 / 3.64dB'), ('r2前两块 LCD开与关','约3.91 / 5.94dB'),
        ('r2后两块 LCD开与关','约36.77 / 38.81dB'), ('r2后续PFB输出8块','约27.33–36.53dB')], [9,8.5])
    p('导频突出度不是校准SNR。原始ADC与PFB快照有间隙，不是同一时刻逐样本配对。具体干扰源以及供电、外部设备、增益等因素尚未确定；不能把此次恢复全部归功于代码。')
    h('新增软件保护与修正')
    p('对4096点IQ检查导频位置、突出度、异常相位跳变和幅度；连续3次可信后解除静音，连续2次差则静音，显示WEAK FM: MUTED。保存检测时间和实际放音区间。该保护不替代调制识别，不能用导频缺失否定单声道FM。')
    p('修正了阻塞IQ采集后仍使用旧时间戳、导致采样率虚高的问题；验收增加实际遥测间隔覆盖检查。首次失败及旧样本数门槛导致的FAIL回执均保留，独立复核不覆盖历史证据。')
    table(['最终稳定性项目','结果'], [
        ('数字链路运行',f"{stability['duration_s']:.4f}秒"), ('实际连续放音',f"{stability['audible_seconds']:.4f}秒；初始静音约1.0522秒"),
        ('质量快照','665/665可信；导频突出度最低26.545dB'), ('下溢与最低显示帧率','0次；40.3784fps'),
        ('温度与软件回归','64.35–65.58°C；85项针对性测试通过'), ('人工反馈','广播清楚、只有轻微底噪、没有明显断音'),
    ], [5.1,12.4])
    p('300秒数字链路通过；严格300秒全程解除静音仍差约0.95秒，旧Y3 FAIL保留。测试结束已静音并关闭接收。本轮未修改RTL或位流、未重新综合布线。')

    page('三 文件夹目录与保存位置')
    p('当前实际开发仓库：F:\\.zss\\zss。F:\\project为启动上下文中的早期规划与资料目录；当前代码、板测结果和Git提交均以实际仓库为准。下表路径均相对仓库根目录。', True)
    table(['目录或文件','用途'], [
        ('AGENTS.md','执行规则、硬件事实、安全约束'), ('runbook/','执行策划、步骤、STATUS进度；95_final.md优先'),
        ('docs/','技术说明、验收总结、故障分析'), ('src/hw/','Vivado工程覆盖层、Block Design和约束'),
        ('src/rtl/','FPGA硬件逻辑，包括PFB、音频及ADC接口'), ('src/ps/sentinel/','板端Python驱动、算法、应用和质量保护'),
        ('src/ps/libad9361_pynq/','AD9361控制库'), ('src/ps/models/ 与 tests/','模型相关文件与PS测试'),
        ('board/overlay/','可部署bit/HWH/XSA及验收文件'), ('board/scripts/','在开发板执行的入口脚本'),
        ('board/measurements/','板测JSON、IQ数据及SHA256'), ('tools/','电脑端构建、部署、分析、验收脚本'),
        ('sim/golden/ 与 sim/tb/','软件参考模型与RTL测试平台'), ('sim/scripts/ 与 sim/results/','仿真脚本与仿真软件验收结果'),
        ('build/scripts/','Vivado构建、导出及审计Tcl'), ('build/reports/ 与 build/work/','时序资源报告及构建中间文件'),
        ('data/','历史录波、参考和合成数据'), ('report/results/ 与 figures/','分析产物、WAV、归档包及图表'),
        ('report/llm_logs/','大模型协作记录'), ('logs/','构建、部署、测试日志，不提交Git'),
        ('skill/','竞赛技能包'), ('third_party/ 与 vendor/atk/','第三方依赖及厂商原理图、例程、IP；只读'),
        ('.venv/','本机Python环境；跨设备时重新建立'),
    ], [6.2,11.3])
    p('原理图与厂商资料以vendor/atk/中的实际资料及README索引为准。本报告没有重新检索全部原理图，不把历史附件目录误称为当前源码目录。')

    page('四 常用文件与板端部署')
    p('以下为后续开发最常用的相对路径，均可从F:\\.zss\\zss进入。阅读旧记录时注意日期和历史说明；旧的“尚未上板”等描述不覆盖最新检查点。')
    table(['文件或路径','查阅用途'], [
        ('runbook/STATUS.md','当前进度与历史验收'), ('runbook/95_final.md','Y0–Y7与Z增补最终策划'),
        ('docs/antenna_sd_guide.md','天线配置和SD卡规则'), ('docs/y3_noise_diagnosis.md','本次噪声定位、修正和复现说明'),
        ('src/ps/sentinel/fm_quality.py','FM质量判断与门控'), ('board/scripts/run_y3_audio.py','板端FM监听与安全退出'),
        ('tools/run_y3_board.py','电脑端部署和验收入口'), ('board/scripts/diagnose_y3_iq.py','原始ADC/PFB快照诊断'),
        ('tools/analyze_y3_iq_diagnostic.py','离线IQ及数学音频对比'), ('board/measurements/y3_noise_stability_human.json','最终量化与人工反馈'),
        ('board/measurements/y3_v2_audio_r3_quality/result.json','300秒测试完整遥测'),
        ('sim/results/y3_noise_quality_software.json','85项测试与源码哈希'),
        ('report/llm_logs/Y3_noise_diagnosis.md','本轮协作记录'),
    ], [11.7,5.8])
    h('当前位流包')
    p('board/overlay/sentinel_v2_100m/包含sentinel_v2_100m.bit、同名.hwh和.xsa、acceptance.json、development_review.json及SHA256清单。bit供FPGA配置，hwh供PYNQ识别硬件，xsa为硬件平台导出。原sentinel_v1、v1b、v1d包保留，不能随意混配不同版本的bit/HWH。')
    h('开发板上的隔离部署副本')
    p('最近成功测试目录：')
    p('/home/xilinx/sentinel/setup/y3_v2_audio_r3_quality_runtime/')
    p('内部ps/保存本次板端软件，scripts/保存运行脚本，overlay/保存使用的位流，measurements/保存结果。每轮runtime为可追溯的隔离测试副本；电脑仓库是代码主位置。当前尚未整理成最终一键启动发布目录，也未宣称开机自启已完成。')

    page('五 未完成项与后续执行顺序')
    table(['阶段','当前情况','后续处理'], [
        ('N0–N4 / X0','基础功能及归档完成','保留原验收与SD备份'),
        ('X1 检测率','95.8MHz检出约73.58%，未达80%','保留FAIL，不追加原调参'),
        ('X2 全带宽','宽带实现时序失败','本阶段保持3.84MSPS，写入展望'),
        ('X3 时延','历史中位629.90µs，未达200µs','保留测量定义与失败结果'),
        ('X4 识别','第三轮十类@10dB约87.65%，综合未达标','不重新训练；保留失败候选用途'),
        ('Y2 识别上屏','显示链路可用，准确率和模式帧率未达标','完成体验整合，不宣称指标通过'),
        ('Y3 FM音频','清楚出声，300秒链路测试通过','严格连续300秒出声仍待完整覆盖'),
        ('Y4 空口闭环','尚未完成','先确认配置B或C再允许发射'),
        ('Y5–Y7','尚未完成本阶段整体验收','扫频稳定性、技能包、报告、演示交付'),
        ('Z1 Z2及建议增强','一键演示与UI整合未全部完成','按最终策划推进，不新增触摸双通道'),
    ], [3.1,7.7,6.7])
    h('推荐接续顺序')
    p('先整理当前可运行代码、位流及证据，使跨设备交接完整；再按用户要求提高下次试听音量，并将严格连续播放计时放在首次质量放行之后。随后完成一键演示与界面整合，再进入空口闭环、扫频稳定性、实验对比、技能包、报告和最终交付。')
    p('当前音量保护上限是−15dB。下次拟小幅提高时，需同步修改并测试保护范围，不能只改命令参数。本次未实际调高。具体干扰源未定位，噪声复发时优先保存IQ、增益/RSSI及外部设备状态，不先重新构建位流。')
    h('继续开发时保持的约束')
    p('不使用衰减器；不以SMA线直接连接TX和RX；配置A仅接收。发射前按策划确认天线配置和ISM频段，保留TxGuard与RSSI中止保护。测试中不复位、不拔SD卡；断电前先sync与shutdown。third_party/和vendor/atk/保持只读。')

    page('六 版本保存与跨设备交接说明')
    h('已保存的本地提交')
    table(['提交','内容'], [('cc8a1d3','本轮噪声诊断、质量保护、测试与证据，119个文件变更'),
        ('ca475a9','测试音通过、原FM失败听音及安全退出记录')], [3.5,14])
    p('本轮已提交不等于整个工程已全部提交。前次汇报核对时，仍有33个已跟踪但未提交的文件改动，以及208个未跟踪条目（部分条目是目录，不等同文件数）。包含100MHz工程、位流、驱动、脚本和测量成果。数字为生成本报告之前的基线快照；新增报告及生成脚本会改变工作区条目数。')
    p('现有成果仍保留在工作区；仅复制Git提交或重新clone不能完整恢复当前可运行工程。未发布或推送GitHub。')
    h('已有备份')
    p('F:\\.zss\\backup_before_inplace_20261103_175628')
    p('该备份目录经核对仍存在，是此前修改前的备份，不包含之后所有最新改动。最新成果以F:\\.zss\\zss工作区及测量回执为准，不把旧备份当作最新完整交付包。')
    h('迁移到另一台电脑时')
    for text in [
        '交接前核对未提交和未跟踪内容，保存完整工作区快照；不能只依赖Git仓库。',
        '包含源码、tools、runbook、docs、位流包、JSON/SHA256及必要IQ/归档数据，同时单独带上vendor/atk厂商资料。',
        '若需要重现构建，还要带上冻结输入/相关归档并核对工具链；不要把build/work直接当成可跨设备运行的最终工程。',
        '新设备使用短英文路径，重新建立Python环境并配置Vivado/工具环境；不要复用旧电脑.venv。',
        '重新验证新设备SSH连接和密钥，按当前硬件接线确认后才启动射频；板端密码不写入交接文档。',
        '读取AGENTS、95_final、antenna_sd_guide、STATUS及最新噪声诊断，保留历史FAIL，勿重复已完成步骤或覆盖测量证据。',
    ]:
        doc.add_paragraph(text, style='List Number')
    h('本文件与证据来源')
    p('本文件保存于report/FPGA项目进度与文件目录说明_20261103.docx。关键数值来自board/overlay/sentinel_v2_100m/acceptance.json、board/measurements/y3_noise_stability_human.json和sim/results/y3_noise_quality_software.json；生成时核验相应SHA256。完整过程见docs/y3_noise_diagnosis.md与runbook/STATUS.md。')
    p('本文件是阶段性进度与交接说明，不替代正式竞赛报告或完整最终验收。')
    doc.core_properties.title = 'FPGA项目进度与文件目录说明'
    doc.core_properties.subject = 'Zynq频谱终端进度、实测、目录与交接'
    doc.core_properties.author = 'Codex 执行代理'
    doc.save(OUT)
    Path(str(OUT)+'.sha256').write_text(hashlib.sha256(OUT.read_bytes()).hexdigest()+'  '+OUT.name+'\n', encoding='utf-8')
    print(OUT)


if __name__ == '__main__':
    main()
