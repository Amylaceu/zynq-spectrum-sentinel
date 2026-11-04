// Copyright (C) 2014-2023 Analog Devices, Inc. All rights reserved.
// Z20 derivative of ADI fmcomms2/zed/system_top.v.
// SPDX-License-Identifier: LicenseRef-ADIBSD
// ADI license terms: third_party/hdl/LICENSE_ADIBSD.
`timescale 1ns/100ps

module system_top (
  inout [14:0] ddr_addr,
  inout [2:0] ddr_ba,
  inout ddr_cas_n, ddr_ck_n, ddr_ck_p, ddr_cke, ddr_cs_n,
  inout [3:0] ddr_dm,
  inout [31:0] ddr_dq,
  inout [3:0] ddr_dqs_n, ddr_dqs_p,
  inout ddr_odt, ddr_ras_n, ddr_reset_n, ddr_we_n,
  inout fixed_io_ddr_vrn, fixed_io_ddr_vrp,
  inout [53:0] fixed_io_mio,
  inout fixed_io_ps_clk, fixed_io_ps_porb, fixed_io_ps_srstb,
  inout iic_scl, iic_sda,
  input rx_clk_in_p, rx_clk_in_n,
  input rx_frame_in_p, rx_frame_in_n,
  input [5:0] rx_data_in_p, rx_data_in_n,
  output tx_clk_out_p, tx_clk_out_n,
  output tx_frame_out_p, tx_frame_out_n,
  output [5:0] tx_data_out_p, tx_data_out_n,
  output txnrx, enable,
  output gpio_resetb, gpio_sync, gpio_en_agc,
  output [3:0] gpio_ctl,
  input [7:0] gpio_status,
  output spi_csn, spi_clk, spi_mosi,
  input spi_miso,
  input sys_clk,
  output fmc_pwr_gd,
  output [15:0] lcd_data,
  output lcd_cs_n, lcd_rs, lcd_wr_n, lcd_rd_n, lcd_reset_n,
  output hdmi_in_reset_n
);

  // PG_C2M enables FMCOMMS3 U301 (ADP2164), schematic sheets 3/4.
  assign fmc_pwr_gd = 1'b1;
  assign hdmi_in_reset_n = 1'b0;
  wire [15:0] ad9361_gpio_o;
  wire iic_scl_i, iic_scl_o, iic_scl_t;
  wire iic_sda_i, iic_sda_o, iic_sda_t;
  assign gpio_resetb = ad9361_gpio_o[0];
  assign gpio_sync = ad9361_gpio_o[1];
  assign gpio_en_agc = ad9361_gpio_o[2];
  assign gpio_ctl = ad9361_gpio_o[6:3];

  // The generated wrapper inserts SPI IOBUFs. Use the underlying BD module
  // so standard four-wire SPI remains explicitly output/output/output/input.
  IOBUF i_iic_scl (.IO(iic_scl), .I(iic_scl_o), .O(iic_scl_i), .T(iic_scl_t));
  IOBUF i_iic_sda (.IO(iic_sda), .I(iic_sda_o), .O(iic_sda_i), .T(iic_sda_t));
  system i_system (
    .lcd_clk(sys_clk), .lcd_data(lcd_data), .lcd_cs_n(lcd_cs_n),
    .lcd_rs(lcd_rs), .lcd_wr_n(lcd_wr_n), .lcd_rd_n(lcd_rd_n), .lcd_reset_n(lcd_reset_n),
    .ddr_addr(ddr_addr), .ddr_ba(ddr_ba),
    .ddr_cas_n(ddr_cas_n), .ddr_ck_n(ddr_ck_n), .ddr_ck_p(ddr_ck_p),
    .ddr_cke(ddr_cke), .ddr_cs_n(ddr_cs_n), .ddr_dm(ddr_dm),
    .ddr_dq(ddr_dq), .ddr_dqs_n(ddr_dqs_n), .ddr_dqs_p(ddr_dqs_p),
    .ddr_odt(ddr_odt), .ddr_ras_n(ddr_ras_n),
    .ddr_reset_n(ddr_reset_n), .ddr_we_n(ddr_we_n),
    .fixed_io_ddr_vrn(fixed_io_ddr_vrn), .fixed_io_ddr_vrp(fixed_io_ddr_vrp),
    .fixed_io_mio(fixed_io_mio), .fixed_io_ps_clk(fixed_io_ps_clk),
    .fixed_io_ps_porb(fixed_io_ps_porb), .fixed_io_ps_srstb(fixed_io_ps_srstb),
    .gpio_i(64'b0), .gpio_o(), .gpio_t(),
    .iic_fmc_scl_i(iic_scl_i), .iic_fmc_scl_o(iic_scl_o), .iic_fmc_scl_t(iic_scl_t),
    .iic_fmc_sda_i(iic_sda_i), .iic_fmc_sda_o(iic_sda_o), .iic_fmc_sda_t(iic_sda_t),
    .rx_clk_in_p(rx_clk_in_p), .rx_clk_in_n(rx_clk_in_n),
    .rx_frame_in_p(rx_frame_in_p), .rx_frame_in_n(rx_frame_in_n),
    .rx_data_in_p(rx_data_in_p), .rx_data_in_n(rx_data_in_n),
    .tx_clk_out_p(tx_clk_out_p), .tx_clk_out_n(tx_clk_out_n),
    .tx_frame_out_p(tx_frame_out_p), .tx_frame_out_n(tx_frame_out_n),
    .tx_data_out_p(tx_data_out_p), .tx_data_out_n(tx_data_out_n),
    .txnrx(txnrx), .enable(enable),
    .up_enable(ad9361_gpio_o[7]), .up_txnrx(ad9361_gpio_o[8]),
    .ad9361_gpio_o(ad9361_gpio_o), .ad9361_gpio_i(gpio_status),
    .spi_ad9361_io0_i(1'b0), .spi_ad9361_io0_o(spi_mosi), .spi_ad9361_io0_t(),
    .spi_ad9361_io1_i(spi_miso), .spi_ad9361_io1_o(), .spi_ad9361_io1_t(),
    .spi_ad9361_sck_i(1'b0), .spi_ad9361_sck_o(spi_clk), .spi_ad9361_sck_t(),
    .spi_ad9361_ss_i(1'b1), .spi_ad9361_ss_o(spi_csn), .spi_ad9361_ss_t()
  );
endmodule
