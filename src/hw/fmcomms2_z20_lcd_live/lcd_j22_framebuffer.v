`timescale 1ns/1ps
module lcd_j22_framebuffer #(
 parameter RESET_CYCLES=1000000, STARTUP_CYCLES=5000000,
 parameter BUS_PHASE_CYCLES=25, DELAY_SHIFT=0,
 parameter FRAME_WIDTH=800, FRAME_HEIGHT=480
)(
 input wire sys_clk,
 input wire [31:0] mem_data,
 output wire [31:0] mem_addr,
 input wire page_request,
 output reg page_active=0,
 output reg ready=0,
 output wire [13:0] frame_gray,
 output reg [15:0] lcd_data=0,
 output wire lcd_cs_n,
 output reg lcd_rs=0, lcd_wr_n=1,
 output wire lcd_rd_n,
 output reg lcd_reset_n=0,
 output wire hdmi_in_reset_n
);
 assign hdmi_in_reset_n=1'b0;
 assign lcd_cs_n=1'b0;
 assign lcd_rd_n=1'b1;
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
 reg [7:0] phase_count=0;
 reg pixels=0;
 reg [9:0] x=0;
 reg [8:0] y=0;
 reg [13:0] frame=0;
 (* ASYNC_REG="TRUE" *) reg page_meta=0, page_sync=0;
 wire [31:0] instruction=rom(index);
 wire [16:0] word_address = {page_active,15'b0} + (y>>1)*100 + (x>>3);
 assign mem_addr={13'b0, word_address,2'b0};
 wire [7:0] pixel=mem_data >> ({x[2:1],3'b0});
 wire [15:0] rgb565={pixel[7:5],pixel[7:6],pixel[4:2],pixel[4:2],pixel[1:0],pixel[1:0],pixel[1]};
 assign frame_gray=(frame>>1)^frame;
 always @(posedge sys_clk) begin
   page_meta<=page_request; page_sync<=page_meta;
   case(state)
   0: begin
      if(wait_count==RESET_CYCLES-1) begin wait_count<=0;lcd_reset_n<=1;state<=1;end
      else wait_count<=wait_count+1;
   end
   1: begin
      if(wait_count==STARTUP_CYCLES-1) begin wait_count<=0;state<=2;end
      else wait_count<=wait_count+1;
   end
   2: begin
      if(!pixels && instruction[31:30]==2) begin
        wait_count<=instruction[29:0]>>DELAY_SHIFT;state<=7;
      end else if(pixels) begin state<=8; end
      else begin
         lcd_rs<=instruction[30];lcd_data<=instruction[15:0];
         phase_count<=0;state<=3;
      end
   end
   8: begin
      lcd_rs<=1; lcd_data<=rgb565; phase_count<=0;state<=3;
   end
   3: if(phase_count==BUS_PHASE_CYCLES-1) begin phase_count<=0;lcd_wr_n<=0;state<=4;end
      else phase_count<=phase_count+1;
   4: if(phase_count==BUS_PHASE_CYCLES-1) begin phase_count<=0;lcd_wr_n<=1;state<=5;end
      else phase_count<=phase_count+1;
   5: if(phase_count==BUS_PHASE_CYCLES-1) begin phase_count<=0;state<=6;end
      else phase_count<=phase_count+1;
   6: begin
      if(pixels) begin
        if(x==FRAME_WIDTH-1) begin x<=0;
          if(y==FRAME_HEIGHT-1) begin
            y<=0; frame<=frame+1; pixels<=0;index<=61;page_active<=page_sync;
          end else y<=y+1;
        end else x<=x+1;
      end else if(index==LAST) begin pixels<=1;x<=0;y<=0;ready<=1;end
      else index<=index+1;
      state<=2;
   end
   7: if(wait_count==0) begin index<=index+1;state<=2;end
      else wait_count<=wait_count-1;
   default: state<=0;
   endcase
 end
endmodule
