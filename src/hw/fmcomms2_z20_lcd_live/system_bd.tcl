# SPDX-License-Identifier: ADIBSD
# Z20 overlay; referenced ADI files remain unchanged.
source [file join [file dirname [info script]] z20_system_bd.tcl]
source [file join [file dirname [info script]] fmcomms2_z20_bd.tcl]
source $ad_hdl_dir/projects/scripts/adi_pd.tcl

ad_ip_parameter axi_sysid_0 CONFIG.ROM_ADDR_BITS 9
ad_ip_parameter rom_sys_0 CONFIG.PATH_TO_FILE "$mem_init_sys_file_path/mem_init_sys.txt"
ad_ip_parameter rom_sys_0 CONFIG.ROM_ADDR_BITS 9
sysid_gen_sys_init_file

# Initial value only; board interface tuning is required at G2.
ad_ip_parameter axi_ad9361 CONFIG.ADC_INIT_DELAY 23
ad_ip_parameter axi_ad9361 CONFIG.TDD_DISABLE 1

# Two 128KiB pages; each holds a 400x240 RGB332 image, doubled by the LCD engine.
ad_ip_instance axi_bram_ctrl axi_lcd_bram [list DATA_WIDTH 32 SINGLE_PORT_BRAM 1]
ad_ip_instance blk_mem_gen lcd_framebuffer [list \
    Memory_Type True_Dual_Port_RAM Use_Byte_Write_Enable true Byte_Size 8 \
    Write_Width_A 32 Read_Width_A 32 Write_Depth_A 65536 \
    Write_Width_B 32 Read_Width_B 32 Enable_B Use_ENB_Pin \
    Register_PortA_Output_of_Memory_Primitives false \
    Register_PortB_Output_of_Memory_Primitives false \
    Use_RSTA_Pin true Use_RSTB_Pin true]
ad_connect axi_lcd_bram/BRAM_PORTA lcd_framebuffer/BRAM_PORTA
create_bd_intf_port -mode Slave -vlnv xilinx.com:interface:bram_rtl:1.0 lcd_bram
ad_connect lcd_bram lcd_framebuffer/BRAM_PORTB
ad_cpu_interconnect 0x42000000 axi_lcd_bram
set lcd_segment [get_bd_addr_segs -of_objects [get_bd_addr_spaces sys_ps7/Data] -filter {NAME =~ *axi_lcd_bram*}]
if {[llength $lcd_segment] != 1} {error "Ambiguous LCD framebuffer address segment"}
set_property range 256K $lcd_segment

ad_ip_instance axi_gpio axi_lcd_control [list \
    C_GPIO_WIDTH 1 C_ALL_OUTPUTS 1 C_DOUT_DEFAULT 0x00000000 \
    C_IS_DUAL 1 C_GPIO2_WIDTH 32 C_ALL_INPUTS_2 1]
create_bd_port -dir O lcd_page_request
create_bd_port -dir I -from 31 -to 0 lcd_status
ad_connect lcd_page_request axi_lcd_control/gpio_io_o
ad_connect lcd_status axi_lcd_control/gpio2_io_i
ad_cpu_interconnect 0x41210000 axi_lcd_control
