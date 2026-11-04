"""Derive the X2 integration project, preserving both accepted overlays."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("Unexpected anchor: " + old)
    return text.replace(old, new, 1)


def main():
    source = ROOT / "src/hw/sentinel_v1b"
    destination = ROOT / "src/hw/sentinel_v1c"
    if destination.exists():
        raise FileExistsError(destination)
    outputs = {p.name: p.read_text() for p in source.iterdir() if p.is_file()}
    for name in ("system_project.tcl", "Makefile"):
        outputs[name] = outputs[name].replace("sentinel_v1b", "sentinel_v1c")
    reference_files = " \\\n".join((
        "src/rtl/x2/adc_tap_x2.v]",
        "    [file normalize $::env(REPO)/src/rtl/x2/stream_stats_x2.v]",
        "    [file normalize $::env(REPO)/src/rtl/x2/stream_x2_regs.v]"))
    outputs["system_project.tcl"] = once(outputs["system_project.tcl"],
        "src/rtl/adc_tap/adc_tap.v]", reference_files)
    outputs["system_bd.tcl"] = once(outputs["system_bd.tcl"], "set extra_repositories [list",
        "set extra_repositories [list [file normalize $::env(REPO)/build/work/x2_packaged_ip]")
    bd = outputs["sentinel_bd.tcl"].replace("Sentinel v1b", "Sentinel v1c")
    bd = once(bd, "{adc_tap adc_tap_0", "{adc_tap_x2 adc_tap_0 stream_stats_x2 stream_stats_0")
    bd = once(bd, "ad_ip_instance spec_front spec_front_0", "ad_ip_instance spec_front_x2 spec_front_0")
    bd = once(bd, "ad_ip_instance cfar_core_x1 cfar_core_0", "ad_ip_instance cfar_core_x2 cfar_core_0")
    bd = once(bd, "cfar_core_0 perf_mon_0}", "cfar_core_0 perf_mon_0 stream_stats_0}")
    bd = once(bd, "n4_connect spec_front_0/m_axis_db lcd_engine/s_axis_spec", """n4_connect VCC spec_front_0/m_axis_db_tready
n4_connect cfar_core_0/m_axis_db lcd_engine/s_axis_spec""")
    bd = once(bd, "sentinel_axi 0x43C70000 perf_mon_0 $dsp_clk $dsp_resetn", """sentinel_axi 0x43C70000 perf_mon_0 $dsp_clk $dsp_resetn
sentinel_axi 0x43C80000 stream_stats_0 $dsp_clk $dsp_resetn
foreach pin {sample_drop overflow_sticky mismatch_sticky fifo_level} {
    n4_connect adc_tap_0/$pin stream_stats_0/$pin
}
foreach pin {frames_in frames_out frame_drop queue_error} {
    n4_connect cfar_core_0/$pin stream_stats_0/$pin
}""")
    outputs["sentinel_bd.tcl"] = bd.replace("logs/X1_v1b_bd_addresses.txt", "logs/X2_v1c_bd_addresses.txt")
    outputs["adc_tap_cdc.xdc"] += r"""
# Registered Gray source: constrain every bit to the first synchronizer stage.
# 8ns is shorter than the minimum receive-clock period used by these tests.
# Fail closed if hierarchy changes; never false-path the binary counter bus.
set drop_q [get_pins -hier -regexp {.*adc_tap_0/inst/drop_gray_reg\[[0-9]+\]/Q}]
set drop_d [get_pins -hier -regexp {.*adc_tap_0/inst/drop_sync0_reg\[[0-9]+\]/D}]
if {[llength $drop_q]!=32 || [llength $drop_d]!=32} {error "Missing X2 Gray CDC endpoints"}
set_max_delay -datapath_only 8.0 -from $drop_q -to $drop_d
set_bus_skew 8.0 -from $drop_q -to $drop_d
"""
    destination.mkdir()
    for name, text in outputs.items():
        (destination / name).write_bytes(text.encode())
    print("SENTINEL_V1C_PROJECT_PREPARED", len(outputs))


if __name__ == "__main__":
    main()
