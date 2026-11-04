"""Create an independent Y3 audio overlay from the frozen v1d source layer.

Only creates a new destination; does not edit v1d/Z2/vendor/ADI inputs.
"""
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    source = ROOT / 'src/hw/sentinel_v1d'
    destination = ROOT / 'src/hw/sentinel_y3'
    if destination.exists():
        raise FileExistsError('Preserve existing Y3 source overlay')
    shutil.copytree(source, destination)
    for name in ('Makefile', 'system_project.tcl'):
        path = destination / name
        path.write_text(path.read_text().replace('sentinel_v1d', 'sentinel_y3'), encoding='utf-8')
    project = destination / 'system_project.tcl'
    text = project.read_text().replace('src/rtl/x5/x5_frontend.v', 'src/rtl/audio_y3/y3_frontend.v')
    text = text.replace('src/rtl/nco_capture/x5_channel_capture.v',
        'src/rtl/audio_y3/audio_sink_y3.v src/rtl/audio_y3/fm_phase_y3.v\n'
        '    src/rtl/audio_y3/fm_audio_filter_y3.v src/rtl/audio_y3/i2s_tx_y3.v')
    text = text.replace('lcd_j22.xdc adc_tap_cdc.xdc', 'lcd_j22.xdc adc_tap_cdc.xdc audio_y3.xdc')
    project.write_text(text, encoding='utf-8')
    bd = destination / 'system_bd.tcl'
    text = bd.read_text().replace('src/rtl/nco_capture/x5_nco_sine.hex}',
        'src/rtl/nco_capture/x5_nco_sine.hex src/rtl/audio_y3/rom/y3_atan.hex\n'
        '    src/rtl/audio_y3/rom/y3_audio_fir.hex}')
    bd.write_text(text, encoding='utf-8')
    bd = destination / 'sentinel_bd.tcl'
    text = bd.read_text().replace('-reference x5_frontend', '-reference y3_frontend')
    text = text.replace('# Persist concrete connections',
        'source [file join [file dirname [info script]] audio_y3_bd.tcl]\n\n# Persist concrete connections')
    text = text.replace('logs/X5_v1d_bd_addresses.txt', 'logs/Y3_bd_addresses.txt')
    bd.write_text(text, encoding='utf-8')
    top = destination / 'system_top.v'
    text = top.read_text().replace('  output hdmi_in_reset_n',
        '  inout audio_iic_scl, audio_iic_sda,\n'
        '  output aud_mclk, aud_bclk, aud_lrc, aud_dacdat,\n'
        '  output hdmi_in_reset_n')
    text = text.replace('  system i_system (',
        '  wire audio_scl_i,audio_scl_o,audio_scl_t;\n'
        '  wire audio_sda_i,audio_sda_o,audio_sda_t;\n'
        '  IOBUF audio_scl_buf(.IO(audio_iic_scl),.I(audio_scl_o),.O(audio_scl_i),.T(audio_scl_t));\n'
        '  IOBUF audio_sda_buf(.IO(audio_iic_sda),.I(audio_sda_o),.O(audio_sda_i),.T(audio_sda_t));\n'
        '  system i_system (\n'
        '    .audio_iic_scl_i(audio_scl_i),.audio_iic_scl_o(audio_scl_o),.audio_iic_scl_t(audio_scl_t),\n'
        '    .audio_iic_sda_i(audio_sda_i),.audio_iic_sda_o(audio_sda_o),.audio_iic_sda_t(audio_sda_t),\n'
        '    .aud_mclk(aud_mclk),.aud_bclk(aud_bclk),.aud_lrc(aud_lrc),.aud_dacdat(aud_dacdat),')
    top.write_text(text, encoding='utf-8')
    rom = ROOT / 'src/rtl/audio_y3/rom'
    rom.mkdir(exist_ok=False)
    for name in ('y3_atan.hex', 'y3_audio_fir.hex'):
        shutil.copyfile(ROOT / 'build/work/y3_fm_vectors_r3' / name, rom / name)
    print('Y3_SOURCE_OVERLAY_CREATED')


if __name__ == '__main__':
    main()
