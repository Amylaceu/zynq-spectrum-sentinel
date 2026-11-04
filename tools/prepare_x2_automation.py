"""Create X2 build/audit entry points from the independently accepted X1 flow."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(name, text):
    path = ROOT / name
    if path.exists():
        raise FileExistsError(path)
    path.write_bytes(text.encode())


def main():
    for old, new in (("tools/build_sentinel_v1b.ps1", "tools/build_sentinel_v1c.ps1"),
                     ("tools/audit_sentinel_v1b.ps1", "tools/audit_sentinel_v1c.ps1"),
                     ("tools/accept_sentinel_v1b.py", "tools/accept_sentinel_v1c.py"),
                     ("build/scripts/audit_sentinel_v1b.tcl", "build/scripts/audit_sentinel_v1c.tcl")):
        text = (ROOT / old).read_text()
        # Keep the parser import from the previous accepted flow, not a
        # self-import accidentally created by the entry-point rename.
        text = text.replace("sentinel_v1b", "sentinel_v1c").replace("SENTINEL_V1B", "SENTINEL_V1C")
        text = text.replace("X1", "X2").replace("x1_", "x2_")
        text = text.replace("X2_v1b", "X2_v1c").replace("x2_v1b", "x2_v1c")
        text = text.replace("v1b Vivado", "v1c Vivado").replace("prior v1b", "prior v1c")
        if new.endswith("accept_sentinel_v1c.py"):
            text = text.replace("cfar_core_x1", "cfar_core_x2")
            text = text.replace("'cfar_version':0x43460002,", "'cfar_version':0x43460002, 'stream_version':0x58320001,")
            text = text.replace("    result = {", """    stats = ET.parse(hwh).getroot().find(".//MODULE[@INSTANCE='stream_stats_0']")
    if stats is None or stats.get('MODTYPE') != 'stream_stats_x2' or addresses.get('stream_stats_0') != '0x43c80000':
        raise ValueError('Missing X2 stream statistics contract')
    gray_skew = bus_skew_summary((reports/'final_gray_bus_skew.rpt').read_text())
    result = {""")
            text = text.replace("'bus_skew':bus_skew,", "'bus_skew':bus_skew, 'gray_bus_skew':gray_skew,")
            text = text.replace("'standalone_cluster_r1_hold_result':'FAIL retained; routed full-system report assessed separately',", "'prior_X1_acceptance':'FAIL RF metric retained; X2 does not repair or relabel X1',")
        if new.endswith("build_sentinel_v1c.ps1"):
            text = text.replace("x2_packaged_ip/cfar_core_x1", "x2_packaged_ip/cfar_core_x2")
            text = text.replace("throw 'Package X2 CFAR first'", "throw 'Package X2 CFAR first'")
            text = text.replace("& (Join-Path $PSScriptRoot 'sync_hw.ps1')", """if(-not(Test-Path sim/results/x2_simulation_acceptance.json)){throw 'X2 simulation acceptance required'}
$simulation=Get-Content sim/results/x2_simulation_acceptance.json -Raw | ConvertFrom-Json
if($simulation.status -ne 'PASS'){throw 'X2 simulation did not pass'}
& $env:ZSS_PYTHON (Join-Path $PSScriptRoot 'freeze_x2_build.py') --attempt $Attempt --verify
if($LASTEXITCODE){throw 'X2 frozen input verification failed'}
& (Join-Path $PSScriptRoot 'sync_hw.ps1')""")
        if new.endswith("audit_sentinel_v1c.tcl"):
            text = text.replace('puts "SENTINEL_FINAL_AUDIT_PASS"', r'''
set drop_q [get_pins -hier -regexp {.*adc_tap_0/inst/drop_gray_reg\[[0-9]+\]/Q}]
set drop_d [get_pins -hier -regexp {.*adc_tap_0/inst/drop_sync0_reg\[[0-9]+\]/D}]
set drop_second [get_cells -hier -regexp {.*adc_tap_0/inst/drop_sync1_reg\[[0-9]+\]}]
if {[llength $drop_q]!=32 || [llength $drop_d]!=32 || [llength $drop_second]!=32} {error "Missing X2 counter CDC endpoints"}
foreach cell $drop_second {
    if {[get_property ASYNC_REG $cell] ne "TRUE"} {error "Counter CDC second stage lacks ASYNC_REG"}
}
report_bus_skew -from $drop_q -to $drop_d -warn_on_violation -file [file join $reports final_gray_bus_skew.rpt]
report_timing -from $drop_q -to $drop_d -max_paths 32 -file [file join $reports final_gray_paths.rpt]
puts "SENTINEL_FINAL_AUDIT_PASS"
''')
        save(new, text)


if __name__ == "__main__":
    main()
