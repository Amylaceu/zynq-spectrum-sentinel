###############################################################################
## Derived from ADI projects/common/zed/zed_system_bd.tcl (2014-2025 ADI).
### SPDX-License-Identifier: ADIBSD
###############################################################################

set CACHE_COHERENCY false
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:ddrx_rtl:1.0 ddr
create_bd_intf_port -mode Master -vlnv xilinx.com:display_processing_system7:fixedio_rtl:1.0 fixed_io
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:iic_rtl:1.0 iic_fmc
create_bd_port -dir I -from 63 -to 0 gpio_i
create_bd_port -dir O -from 63 -to 0 gpio_o
create_bd_port -dir O -from 63 -to 0 gpio_t

ad_ip_instance processing_system7 sys_ps7
source [file join [file dirname [info script]] z20_ps7_preset.tcl]
z20_apply_ps7_preset sys_ps7

# Apply fabric settings after the vendor board preset.
foreach {key value} {
    PCW_TTC0_PERIPHERAL_ENABLE 0
    PCW_EN_CLK0_PORT 1
    PCW_EN_RST0_PORT 1
    PCW_EN_CLK1_PORT 1
    PCW_EN_RST1_PORT 1
    PCW_FPGA0_PERIPHERAL_FREQMHZ 100.0
    PCW_FPGA1_PERIPHERAL_FREQMHZ 200.0
    PCW_USE_FABRIC_INTERRUPT 1
    PCW_USE_S_AXI_HP0 1
    PCW_IRQ_F2P_INTR 1
    PCW_IRQ_F2P_MODE REVERSE
    PCW_GPIO_EMIO_GPIO_ENABLE 1
    PCW_GPIO_EMIO_GPIO_IO 64
    PCW_SPI0_PERIPHERAL_ENABLE 0
    PCW_SPI1_PERIPHERAL_ENABLE 0
    PCW_I2C0_PERIPHERAL_ENABLE 0
    PCW_I2C1_PERIPHERAL_ENABLE 0
    PCW_CAN0_PERIPHERAL_ENABLE 0
    PCW_CAN1_PERIPHERAL_ENABLE 0
    PCW_USE_DMA0 0
    PCW_USE_DMA1 0
    PCW_USE_DMA2 0
} {
    ad_ip_parameter sys_ps7 CONFIG.$key $value
}

ad_ip_instance ilconcat sys_concat_intc [list NUM_PORTS 16]
ad_ip_instance proc_sys_reset sys_rstgen [list C_EXT_RST_WIDTH 1]
ad_ip_instance proc_sys_reset sys_200m_rstgen [list C_EXT_RST_WIDTH 1]
ad_ip_instance axi_iic axi_iic_fmc

ad_connect sys_cpu_clk sys_ps7/FCLK_CLK0
ad_connect sys_200m_clk sys_ps7/FCLK_CLK1
ad_connect sys_cpu_reset sys_rstgen/peripheral_reset
ad_connect sys_cpu_resetn sys_rstgen/peripheral_aresetn
ad_connect sys_cpu_clk sys_rstgen/slowest_sync_clk
ad_connect sys_rstgen/ext_reset_in sys_ps7/FCLK_RESET0_N
ad_connect sys_200m_reset sys_200m_rstgen/peripheral_reset
ad_connect sys_200m_resetn sys_200m_rstgen/peripheral_aresetn
ad_connect sys_200m_clk sys_200m_rstgen/slowest_sync_clk
ad_connect sys_200m_rstgen/ext_reset_in sys_ps7/FCLK_RESET1_N

set sys_cpu_clk [get_bd_nets sys_cpu_clk]
set sys_dma_clk [get_bd_nets sys_cpu_clk]
set sys_iodelay_clk [get_bd_nets sys_200m_clk]
set sys_cpu_reset [get_bd_nets sys_cpu_reset]
set sys_cpu_resetn [get_bd_nets sys_cpu_resetn]
set sys_dma_reset [get_bd_nets sys_cpu_reset]
set sys_dma_resetn [get_bd_nets sys_cpu_resetn]
set sys_iodelay_reset [get_bd_nets sys_200m_reset]
set sys_iodelay_resetn [get_bd_nets sys_200m_resetn]

ad_connect ddr sys_ps7/DDR
ad_connect fixed_io sys_ps7/FIXED_IO
ad_connect gpio_i sys_ps7/GPIO_I
ad_connect gpio_o sys_ps7/GPIO_O
ad_connect gpio_t sys_ps7/GPIO_T
ad_connect iic_fmc axi_iic_fmc/iic
ad_connect GND sys_ps7/USB0_VBUS_PWRFAULT
# HP0 is reserved for later integration; no unused AXI interconnect is created.
ad_connect sys_cpu_clk sys_ps7/S_AXI_HP0_ACLK

ad_ip_instance axi_sysid axi_sysid_0
ad_ip_instance sysid_rom rom_sys_0
ad_connect axi_sysid_0/rom_addr rom_sys_0/rom_addr
ad_connect axi_sysid_0/sys_rom_data rom_sys_0/rom_data
ad_connect sys_cpu_clk rom_sys_0/clk

ad_connect sys_concat_intc/dout sys_ps7/IRQ_F2P
for {set index 0} {$index < 16} {incr index} {
    if {$index == 11} {
        ad_connect sys_concat_intc/In$index axi_iic_fmc/iic2intc_irpt
    } else {
        ad_connect sys_concat_intc/In$index GND
    }
}
ad_cpu_interconnect 0x45000000 axi_sysid_0
ad_cpu_interconnect 0x41620000 axi_iic_fmc

# PL MMIO control; GPIO reset value holds AD9361 RESETB low and TX controls low.
ad_ip_instance axi_quad_spi axi_ad9361_spi [list \
    C_SPI_MODE 0 C_NUM_SS_BITS 1 C_SCK_RATIO 16 C_USE_STARTUP 0 \
    C_FIFO_DEPTH 16 C_NUM_TRANSFER_BITS 8]
ad_ip_instance axi_gpio axi_ad9361_gpio [list \
    C_IS_DUAL 1 C_GPIO_WIDTH 16 C_ALL_OUTPUTS 1 C_DOUT_DEFAULT 0x00000000 \
    C_GPIO2_WIDTH 8 C_ALL_INPUTS_2 1]
ad_connect sys_cpu_clk axi_ad9361_spi/ext_spi_clk
create_bd_intf_port -mode Master -vlnv xilinx.com:interface:spi_rtl:1.0 spi_ad9361
ad_connect spi_ad9361 axi_ad9361_spi/SPI_0
create_bd_port -dir O -from 15 -to 0 ad9361_gpio_o
create_bd_port -dir I -from 7 -to 0 ad9361_gpio_i
ad_connect ad9361_gpio_o axi_ad9361_gpio/gpio_io_o
ad_connect ad9361_gpio_i axi_ad9361_gpio/gpio2_io_i
ad_cpu_interconnect 0x41E00000 axi_ad9361_spi
ad_cpu_interconnect 0x41200000 axi_ad9361_gpio
ad_cpu_interrupt ps-10 mb-10 axi_ad9361_spi/ip2intc_irpt
