module z20_lcd_test_2v5(
 input wire sys_clk,
 output reg [15:0] lcd_data=0,
 output wire lcd_cs_n,
 output reg lcd_rs=0,
 output reg lcd_wr_n=1,
 output wire lcd_rd_n,
 output reg lcd_reset_n=0,
 output wire fmc_pwr_gd, ad9361_resetb, ad9361_enable, ad9361_txnrx,
 output wire spi_csn,spi_clk,spi_mosi,
 output wire hdmi_in_reset_n
);
 assign hdmi_in_reset_n=1'b0;
 assign lcd_cs_n=1'b0;
 assign lcd_rd_n=1'b1;
 assign fmc_pwr_gd=1'b1;
 assign ad9361_resetb=1'b1;
 assign ad9361_enable=1'b0;
 assign ad9361_txnrx=1'b0;
 assign spi_csn=1'b1;
 assign spi_clk=1'b0;
 assign spi_mosi=1'b0;
 function [31:0] rom;
 input [7:0] address;
 begin
   case(address)
        0: rom = 32'h000000e2;
        1: rom = 32'h4000001d;
        2: rom = 32'h40000002;
        3: rom = 32'h40000004;
        4: rom = 32'h80001388;
        5: rom = 32'h000000e0;
        6: rom = 32'h40000001;
        7: rom = 32'h8007a120;
        8: rom = 32'h000000e0;
        9: rom = 32'h40000003;
        10: rom = 32'h800927c0;
        11: rom = 32'h00000001;
        12: rom = 32'h8007a120;
        13: rom = 32'h000000e6;
        14: rom = 32'h4000002f;
        15: rom = 32'h400000ff;
        16: rom = 32'h400000ff;
        17: rom = 32'h000000b0;
        18: rom = 32'h40000020;
        19: rom = 32'h40000000;
        20: rom = 32'h40000003;
        21: rom = 32'h4000001f;
        22: rom = 32'h40000001;
        23: rom = 32'h400000df;
        24: rom = 32'h40000000;
        25: rom = 32'h000000b4;
        26: rom = 32'h40000004;
        27: rom = 32'h4000001f;
        28: rom = 32'h40000000;
        29: rom = 32'h4000002e;
        30: rom = 32'h40000000;
        31: rom = 32'h40000000;
        32: rom = 32'h40000000;
        33: rom = 32'h40000000;
        34: rom = 32'h000000b6;
        35: rom = 32'h40000002;
        36: rom = 32'h4000000c;
        37: rom = 32'h40000000;
        38: rom = 32'h40000017;
        39: rom = 32'h40000016;
        40: rom = 32'h40000000;
        41: rom = 32'h40000000;
        42: rom = 32'h000000f0;
        43: rom = 32'h40000003;
        44: rom = 32'h00000029;
        45: rom = 32'h000000d0;
        46: rom = 32'h40000000;
        47: rom = 32'h000000be;
        48: rom = 32'h40000005;
        49: rom = 32'h400000fe;
        50: rom = 32'h40000001;
        51: rom = 32'h40000000;
        52: rom = 32'h40000000;
        53: rom = 32'h40000000;
        54: rom = 32'h000000b8;
        55: rom = 32'h40000003;
        56: rom = 32'h40000001;
        57: rom = 32'h000000ba;
        58: rom = 32'h40000001;
        59: rom = 32'h00000036;
        60: rom = 32'h40000000;
        61: rom = 32'h0000002a;
        62: rom = 32'h40000000;
        63: rom = 32'h40000000;
        64: rom = 32'h40000003;
        65: rom = 32'h4000001f;
        66: rom = 32'h0000002b;
        67: rom = 32'h40000000;
        68: rom = 32'h40000000;
        69: rom = 32'h40000001;
        70: rom = 32'h400000df;
        71: rom = 32'h0000002c;
   default: rom=0;
   endcase
 end
 endfunction
 localparam LAST=71;
 reg [3:0] state=0;
 reg [31:0] wait_count=0;
 reg [7:0] index=0;
 reg [5:0] phase_count=0;
 reg pixels=0;
 reg [9:0] x=0;
 reg [8:0] y=0;
 reg [3:0] frame=0;
 wire [31:0] instruction=rom(index);
 reg [15:0] color;
 always @* begin
   if(y<32) color=frame[1] ? 16'hffff : 16'h07e0;
   else if(x<100) color=16'hffff;
   else if(x<200) color=16'hffe0;
   else if(x<300) color=16'h07ff;
   else if(x<400) color=16'h07e0;
   else if(x<500) color=16'hf81f;
   else if(x<600) color=16'hf800;
   else if(x<700) color=16'h001f;
   else color=16'h0000;
 end
 always @(posedge sys_clk) begin
   case(state)
   0: begin
      if(wait_count==999999) begin wait_count<=0;lcd_reset_n<=1;state<=1;end
      else wait_count<=wait_count+1;
   end
   1: begin
      if(wait_count==4999999) begin wait_count<=0;state<=2;end
      else wait_count<=wait_count+1;
   end
   2: begin
      if(!pixels && instruction[31:30]==2) begin wait_count<=instruction[29:0];state<=7;end
      else begin
         lcd_rs<=pixels ? 1'b1 : instruction[30];
         lcd_data<=pixels ? color : instruction[15:0];
         phase_count<=0;state<=3;
      end
   end
   3: if(phase_count==24) begin phase_count<=0;lcd_wr_n<=0;state<=4;end
      else phase_count<=phase_count+1;
   4: if(phase_count==24) begin phase_count<=0;lcd_wr_n<=1;state<=5;end
      else phase_count<=phase_count+1;
   5: if(phase_count==24) begin phase_count<=0;state<=6;end
      else phase_count<=phase_count+1;
   6: begin
      if(pixels) begin
        if(x==799) begin x<=0;
          if(y==479) begin y<=0;frame<=frame+1;pixels<=0;index<=61;end
          else y<=y+1;
        end else x<=x+1;
      end else if(index==LAST) begin pixels<=1;x<=0;y<=0;end
      else index<=index+1;
      state<=2;
   end
   7: if(wait_count==0) begin index<=index+1;state<=2;end
      else wait_count<=wait_count-1;
   default: state<=0;
   endcase
 end
endmodule
