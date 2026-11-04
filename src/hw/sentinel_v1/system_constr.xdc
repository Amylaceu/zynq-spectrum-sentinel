# ad9361 on Z20 FMC LPC (J31). Bank33/34 VCCO must be 2.5V (J7/J8).
set_property -dict {PACKAGE_PIN Y18  IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports rx_clk_in_p]      ; ## G6  LA00_CC_P
set_property -dict {PACKAGE_PIN AA18 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports rx_clk_in_n]      ; ## G7  LA00_CC_N
set_property -dict {PACKAGE_PIN W17  IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports rx_frame_in_p]    ; ## D8  LA01_CC_P
set_property -dict {PACKAGE_PIN W18  IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports rx_frame_in_n]    ; ## D9  LA01_CC_N
set_property -dict {PACKAGE_PIN Y14  IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[0]}] ; ## H7  LA02_P
set_property -dict {PACKAGE_PIN AA14 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[0]}] ; ## H8  LA02_N
set_property -dict {PACKAGE_PIN AB19 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[1]}] ; ## G9  LA03_P
set_property -dict {PACKAGE_PIN AB20 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[1]}] ; ## G10 LA03_N
set_property -dict {PACKAGE_PIN Y13  IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[2]}] ; ## H10 LA04_P
set_property -dict {PACKAGE_PIN AA13 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[2]}] ; ## H11 LA04_N
set_property -dict {PACKAGE_PIN AA17 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[3]}] ; ## D11 LA05_P
set_property -dict {PACKAGE_PIN AB17 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[3]}] ; ## D12 LA05_N
set_property -dict {PACKAGE_PIN AA22 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[4]}] ; ## C10 LA06_P
set_property -dict {PACKAGE_PIN AB22 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[4]}] ; ## C11 LA06_N
set_property -dict {PACKAGE_PIN AA16 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_p[5]}] ; ## H13 LA07_P
set_property -dict {PACKAGE_PIN AB16 IOSTANDARD LVDS_25 DIFF_TERM TRUE} [get_ports {rx_data_in_n[5]}] ; ## H14 LA07_N
set_property -dict {PACKAGE_PIN V18  IOSTANDARD LVDS_25} [get_ports tx_clk_out_p]                    ; ## G12 LA08_P
set_property -dict {PACKAGE_PIN V19  IOSTANDARD LVDS_25} [get_ports tx_clk_out_n]                    ; ## G13 LA08_N
set_property -dict {PACKAGE_PIN AB14 IOSTANDARD LVDS_25} [get_ports tx_frame_out_p]                  ; ## D14 LA09_P
set_property -dict {PACKAGE_PIN AB15 IOSTANDARD LVDS_25} [get_ports tx_frame_out_n]                  ; ## D15 LA09_N
set_property -dict {PACKAGE_PIN U17  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[0]}]              ; ## H16 LA11_P
set_property -dict {PACKAGE_PIN V17  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[0]}]              ; ## H17 LA11_N
set_property -dict {PACKAGE_PIN U15  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[1]}]              ; ## G15 LA12_P
set_property -dict {PACKAGE_PIN U16  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[1]}]              ; ## G16 LA12_N
set_property -dict {PACKAGE_PIN V14  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[2]}]              ; ## D17 LA13_P
set_property -dict {PACKAGE_PIN V15  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[2]}]              ; ## D18 LA13_N
set_property -dict {PACKAGE_PIN P16  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[3]}]              ; ## C14 LA10_P (Bank34)
set_property -dict {PACKAGE_PIN R16  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[3]}]              ; ## C15 LA10_N (Bank34)
set_property -dict {PACKAGE_PIN T21  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[4]}]              ; ## C18 LA14_P
set_property -dict {PACKAGE_PIN U21  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[4]}]              ; ## C19 LA14_N
set_property -dict {PACKAGE_PIN V13  IOSTANDARD LVDS_25} [get_ports {tx_data_out_p[5]}]              ; ## H19 LA15_P
set_property -dict {PACKAGE_PIN W13  IOSTANDARD LVDS_25} [get_ports {tx_data_out_n[5]}]              ; ## H20 LA15_N

set_property -dict {PACKAGE_PIN N22  IOSTANDARD LVCMOS25} [get_ports {gpio_status[0]}]   ; ## G21 LA20_P
set_property -dict {PACKAGE_PIN P22  IOSTANDARD LVCMOS25} [get_ports {gpio_status[1]}]   ; ## G22 LA20_N
set_property -dict {PACKAGE_PIN P20  IOSTANDARD LVCMOS25} [get_ports {gpio_status[2]}]   ; ## H25 LA21_P
set_property -dict {PACKAGE_PIN P21  IOSTANDARD LVCMOS25} [get_ports {gpio_status[3]}]   ; ## H26 LA21_N
set_property -dict {PACKAGE_PIN K19  IOSTANDARD LVCMOS25} [get_ports {gpio_status[4]}]   ; ## G24 LA22_P
set_property -dict {PACKAGE_PIN K20  IOSTANDARD LVCMOS25} [get_ports {gpio_status[5]}]   ; ## G25 LA22_N
set_property -dict {PACKAGE_PIN R19  IOSTANDARD LVCMOS25} [get_ports {gpio_status[6]}]   ; ## D23 LA23_P
set_property -dict {PACKAGE_PIN T19  IOSTANDARD LVCMOS25} [get_ports {gpio_status[7]}]   ; ## D24 LA23_N
set_property -dict {PACKAGE_PIN J15  IOSTANDARD LVCMOS25} [get_ports {gpio_ctl[0]}]      ; ## H28 LA24_P
set_property -dict {PACKAGE_PIN K15  IOSTANDARD LVCMOS25} [get_ports {gpio_ctl[1]}]      ; ## H29 LA24_N
set_property -dict {PACKAGE_PIN N17  IOSTANDARD LVCMOS25} [get_ports {gpio_ctl[2]}]      ; ## G27 LA25_P
set_property -dict {PACKAGE_PIN N18  IOSTANDARD LVCMOS25} [get_ports {gpio_ctl[3]}]      ; ## G28 LA25_N
set_property -dict {PACKAGE_PIN N15  IOSTANDARD LVCMOS25} [get_ports gpio_en_agc]        ; ## H22 LA19_P
set_property -dict {PACKAGE_PIN P15  IOSTANDARD LVCMOS25} [get_ports gpio_sync]          ; ## H23 LA19_N
set_property -dict {PACKAGE_PIN L17  IOSTANDARD LVCMOS25} [get_ports gpio_resetb]        ; ## H31 LA28_P
set_property -dict {PACKAGE_PIN R18  IOSTANDARD LVCMOS25} [get_ports enable]             ; ## G18 LA16_P
set_property -dict {PACKAGE_PIN T18  IOSTANDARD LVCMOS25} [get_ports txnrx]              ; ## G19 LA16_N

set_property -dict {PACKAGE_PIN J21  IOSTANDARD LVCMOS25 PULLTYPE PULLUP} [get_ports spi_csn] ; ## D26 LA26_P
set_property -dict {PACKAGE_PIN J22  IOSTANDARD LVCMOS25} [get_ports spi_clk]            ; ## D27 LA26_N
set_property -dict {PACKAGE_PIN J20  IOSTANDARD LVCMOS25} [get_ports spi_mosi]           ; ## C26 LA27_P
set_property -dict {PACKAGE_PIN K21  IOSTANDARD LVCMOS25} [get_ports spi_miso]           ; ## C27 LA27_N

create_clock -name rx_clk -period 4 [get_ports rx_clk_in_p]
