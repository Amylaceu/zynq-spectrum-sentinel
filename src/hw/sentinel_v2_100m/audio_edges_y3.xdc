# ES8388 v5 pp32-33: LRCK must change within +/-10ns of BCLK falling;
# DAC data needs >=10ns setup/hold at BCLK rising. Serializer changes both
# only on phase[1:0]==3, exactly the BCLK falling launch edge (tested in RTL).
# A generic MCLK-to-BCLK hold check incorrectly assumes changes on EVERY
# MCLK edge and inserts long output-route detours. Use bounded physical
# output paths, plus explicit per-corner edge analysis, for these 3 paths.
# Keep each C-to-pad path within 10ns. Vivado adds the existing 20ns output
# delay to max-delay paths ending at LRCK/DACDAT, so their Tcl limit is 30ns.
# Signoff separately compares the slow/fast physical pin delays and allows
# 1ns launch-clock and 2ns PCB skew; this is not a cycle-based setup claim.
# Data has >150ns stability around BCLK rising (half-period ~162.76ns).
# These bounds do NOT apply to audio-drive OBUFT enables: configure/mute
# protocol must complete before unmuting the codec. No blanket clock cuts.
set_output_delay -clock y3_audio_bclk -min -5 [get_ports {aud_lrc aud_dacdat}]
foreach {signal regex limit} {
    bclk {.*audio/serializer/phase_reg\[1\]/C} 10.0
    lrc {.*audio/serializer/lrck_reg/C} 30.0
    dacdat {.*audio/serializer/dacdat_reg/C} 30.0
} {
    set start [get_pins -hier -regexp $regex]
    if {[llength $start] != 1} {error "Unexpected audio launch pin: $signal"}
    set_max_delay -datapath_only $limit -from $start -to [get_ports aud_$signal]
}
