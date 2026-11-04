# Z20 base ES8388, schematic-confirmed; Bank35, 3.3V.
set_property -dict {PACKAGE_PIN U9 IOSTANDARD LVCMOS33} [get_ports aud_mclk]
set_property -dict {PACKAGE_PIN AA11 IOSTANDARD LVCMOS33} [get_ports aud_bclk]
set_property -dict {PACKAGE_PIN U6 IOSTANDARD LVCMOS33} [get_ports aud_lrc]
set_property -dict {PACKAGE_PIN AB11 IOSTANDARD LVCMOS33} [get_ports aud_dacdat]
set_property -dict {PACKAGE_PIN A18 IOSTANDARD LVCMOS33} [get_ports audio_iic_scl]
set_property -dict {PACKAGE_PIN A19 IOSTANDARD LVCMOS33} [get_ports audio_iic_sda]
set_property PULLUP true [get_ports {audio_iic_scl audio_iic_sda}]
set_property -dict {SLEW SLOW DRIVE 8} [get_ports {aud_mclk aud_bclk aud_lrc aud_dacdat}]
# BCLK and LRCK are explicit divided outputs of the 256Fs clock. DAC data and
# LRCK change on BCLK falling edges; codec samples rising edges. ES8388 v5
# requires >=10ns data setup/hold. audio_edges_y3.xdc supplies the explicit
# phase-qualified physical bounds; these coarse cycle checks are not signoff.
create_generated_clock -name y3_audio_bclk -source [get_pins -hier -regexp {.*audio/serializer/phase_reg\[1\]/C}] -divide_by 4 [get_ports aud_bclk]
# LRCK is data sampled on BCLK, not another launch clock on the same port.
# The PS GPIO control is synchronized in system_top before it reaches the IOBUF.
# Exclude only the asynchronous input to the first synchronizer stage.
set_false_path -to [get_pins -hier -regexp {.*audio_drive_meta_reg/D}]
# LRCK is data sampled by BCLK. Vivado may infer LRCK as a generated clock;
# ignore only the resulting self clock-to-clock check. Output delays below
# still constrain LRCK and DACDAT relative to BCLK.
set_false_path -from [get_clocks y3_audio_lrck] -to [get_clocks y3_audio_bclk]
set_output_delay -clock y3_audio_bclk -max 20 [get_ports {aud_lrc aud_dacdat}]
set_output_delay -clock y3_audio_bclk -min -5 [get_ports {aud_lrc aud_dacdat}]
# Open-drain codec control pins are asynchronous to all audio/data clocks.
set_false_path -from [get_ports {audio_iic_scl audio_iic_sda}]
set_false_path -to [get_ports {audio_iic_scl audio_iic_sda}]
