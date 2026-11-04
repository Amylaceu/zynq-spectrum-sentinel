"""Fail-closed Y3 routed-image checks; never authorizes RF or playback itself."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

from accept_sentinel_v1 import BASES, timing_summary, utilization
from accept_sentinel_v1b import bus_skew_summary

ROOT = Path(__file__).resolve().parents[1]
AUDIO_PINS = {'aud_mclk': 'U9', 'aud_bclk': 'AA11', 'aud_lrc': 'U6',
              'aud_dacdat': 'AB11', 'audio_iic_scl': 'A18', 'audio_iic_sda': 'A19'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def hwh_contract(path, dsp_mhz=150):
    root = ET.parse(path).getroot()
    system = root.find('SYSTEMINFO')
    if system is None or tuple(system.get(k) for k in ('DEVICE', 'PACKAGE', 'SPEEDGRADE')) != ('7z020', 'clg484', '-2'):
        raise ValueError('Wrong FPGA device')
    ps = root.find(".//MODULE[@INSTANCE='sys_ps7']")
    if ps is None:
        raise ValueError('Missing PS7')
    windows = {e.get('INSTANCE'): (int(e.get('BASEVALUE'), 0), int(e.get('HIGHVALUE'), 0))
               for e in ps.findall('./MEMORYMAP/MEMRANGE')}
    bases = dict(BASES, axi_lcd_ui=0x42100000, x5_ctrl=0x41230000,
                 x5_meta=0x41240000, x5_status=0x41250000,
                 y3_audio_ctrl=0x41260000, y3_audio_state=0x41270000,
                 y3_audio_counts=0x41280000, axi_iic_audio=0x41630000)
    for name, base in bases.items():
        if name not in windows or windows[name][0] != base:
            raise ValueError('Wrong/missing address '+name)
    for name, size in (('axi_lcd_ui', 131072), ('axi_power_capture', 8192), ('cfar_core_0', 16384)):
        lo, hi = windows[name]
        if hi-lo+1 != size:
            raise ValueError('Wrong window size '+name)
    # Overlap would corrupt unrelated UI/power/capture registers.
    selected = sorted((windows[name][0], windows[name][1], name) for name in bases)
    for (_, end, name), (start, _, other) in zip(selected, selected[1:]):
        if end >= start:
            raise ValueError('Overlapping address windows '+name+' / '+other)
    def parameters(instance, kind=None):
        module = root.find(".//MODULE[@INSTANCE='%s']" % instance)
        if module is None or kind is not None and module.get('MODTYPE') != kind:
            raise ValueError('Wrong/missing module '+instance)
        return {p.get('NAME'): p.get('VALUE') for p in module.findall('./PARAMETERS/PARAMETER')}
    parameters('cfar_core_0', 'cfar_core_v2' if dsp_mhz == 100 else 'cfar_core_x5')
    parameters('lcd_engine', 'lcd8080_engine_x5')
    parameters('x5_frontend_0', 'y3_frontend')
    parameters('axi_iic_audio', 'axi_iic')
    clock = parameters('dsp_clock')
    if float(clock['C_CLKOUT0_ACTUAL_FREQ']) != dsp_mhz or float(clock['C_PRIM_IN_FREQ']) != 50:
        raise ValueError('Wrong DSP clock')
    audio_clock = parameters('audio_clock')
    audio_mhz = float(audio_clock['C_CLKOUT0_ACTUAL_FREQ'])
    if not 12.28 <= audio_mhz <= 12.30 or float(audio_clock['C_PRIM_IN_FREQ']) != 50:
        raise ValueError('Wrong 48kHz/256Fs audio clock')
    dma = parameters('axi_dma_replay', 'axi_dma')
    for name, value in (('C_INCLUDE_SG', 0), ('C_INCLUDE_S2MM', 1),
                        ('C_INCLUDE_MM2S', 1), ('C_S_AXIS_S2MM_TDATA_WIDTH', 32),
                        ('C_SG_LENGTH_WIDTH', 23), ('C_INCLUDE_S2MM_DRE', 0)):
        if int(dma[name], 0) != value:
            raise ValueError('DMA parameter mismatch '+name)
    return {name: hex(windows[name][0]) for name in bases}


def check_audio_io(report):
    rows = {}
    for line in report.splitlines():
        if line.startswith('|'):
            columns = [part.strip() for part in line.split('|')]
            if len(columns) > 6:
                rows[columns[2]] = (columns[1], columns[6])
    for signal, pin in AUDIO_PINS.items():
        if rows.get(signal) != (pin, 'LVCMOS33'):
            raise ValueError('Wrong audio pin/voltage: '+signal+' '+str(rows.get(signal)))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--attempt', type=int, choices=(1, 2, 3), required=True)
    args = parser.parse_args()
    reports = ROOT/'build/reports/sentinel_y3'
    bundle = ROOT/'board/overlay/sentinel_y3'
    if any((d/'acceptance.json').exists() for d in (reports, bundle)):
        raise FileExistsError('Preserve existing acceptance')
    from freeze_y3_build import verify
    prepath, pre = verify(args.attempt)
    timing = timing_summary((reports/'final_timing.rpt').read_text(errors='replace'))
    resources = utilization((reports/'final_utilization.rpt').read_text(errors='replace'))
    skew = bus_skew_summary((reports/'final_bus_skew.rpt').read_text(errors='replace'))
    check_audio_io((reports/'final_io.rpt').read_text(errors='replace'))
    manifest = {line.split()[1]: line.split()[0].lower() for line in
                (bundle/'sha256.txt').read_text(encoding='utf-8-sig').splitlines() if line.strip()}
    for suffix in ('bit', 'hwh', 'xsa'):
        path = bundle/('sentinel_y3.'+suffix)
        if sha(path) != manifest.get(path.name):
            raise ValueError('Artifact digest mismatch '+path.name)
    addresses = hwh_contract(bundle/'sentinel_y3.hwh')
    audio_module = ET.parse(bundle/'sentinel_y3.hwh').getroot().find(".//MODULE[@INSTANCE='audio_clock']")
    audio_params = {p.get('NAME'): p.get('VALUE') for p in audio_module.findall('./PARAMETERS/PARAMETER')}
    audio_mhz = float(audio_params['C_CLKOUT0_ACTUAL_FREQ'])
    result = dict(status='PASS', image='sentinel_y3',
                  recorded_at_pc=datetime.now(timezone.utc).isoformat(),
                  scope='PC routed implementation only; no board RF, audio, or visual claim',
                  final_timing=timing, resources=resources, bus_skew=skew, addresses=addresses,
                  audio_io_pins=AUDIO_PINS,
                  audio_clock_reported_mhz=audio_mhz,
                  derived_pcm_rate_hz=audio_mhz*1e6/256,
                  clock_scope='Vivado nominal generated clock; actual board drift is not measured here',
                  artifacts_sha256=manifest, prebuild_manifest_sha256=sha(prepath),
                  report_sha256={p.name: sha(p) for p in reports.glob('final_*.rpt')},
                  cdc_review='Explicit DSP/CPU AXI and AXIS converters; retained final CDC report')
    for directory in (reports, bundle):
        path = directory/'acceptance.json'
        path.write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
        Path(str(path)+'.sha256').write_text(sha(path)+'  '+path.name+'\n', encoding='ascii')
    print('SENTINEL_Y3_IMPLEMENTATION_ACCEPTANCE_PASS')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

