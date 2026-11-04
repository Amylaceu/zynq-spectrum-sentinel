# Base schematic p2 CN2: FMC_LPC_IIC_SCL -> B35_L22_N -> G21.
# Base schematic p2 CN2: FMC_LPC_IIC_SDA -> B35_L22_P -> G20.
# Core schematic p4 confirms Bank35; base p15 shows the 3.3V level shifters.
set_property -dict {PACKAGE_PIN G21 IOSTANDARD LVCMOS33 PULLUP true} [get_ports iic_scl]
set_property -dict {PACKAGE_PIN G20 IOSTANDARD LVCMOS33 PULLUP true} [get_ports iic_sda]
set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]
