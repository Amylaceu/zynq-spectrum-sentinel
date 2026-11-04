`timescale 1ns/1ps
module tb_lcd_j22_framebuffer;
reg clk=0;always #10 clk=~clk;
wire [31:0] addr;reg [31:0] data=0;reg request=0;
wire active,ready;wire [13:0] gray;
wire [15:0] lcd;wire cs,rs,wr,rd,rst,hdmi;
lcd_j22_framebuffer #(.RESET_CYCLES(4),.STARTUP_CYCLES(4),
 .BUS_PHASE_CYCLES(2),.DELAY_SHIFT(20),.FRAME_WIDTH(16),.FRAME_HEIGHT(8)) dut(
 .sys_clk(clk),.mem_addr(addr),.mem_data(data),.page_request(request),
 .page_active(active),.ready(ready),.frame_gray(gray),.lcd_data(lcd),
 .lcd_cs_n(cs),.lcd_rs(rs),.lcd_wr_n(wr),.lcd_rd_n(rd),.lcd_reset_n(rst),.hdmi_in_reset_n(hdmi));
function [7:0] px(input integer p,input integer x,input integer y);
 px=(p*73+x*7+y*13)&255;
endfunction
function [15:0] rgb(input [7:0] v);
 rgb={v[7:5],v[7:6],v[4:2],v[4:2],v[1:0],v[1:0],v[1]};
endfunction
integer a,p,row,col;
always @(posedge clk) begin
 a=addr>>2;p=a/32768;a=a%32768;row=a/100;col=(a%100)*4;
 data<={px(p,col+3,row),px(p,col+2,row),px(p,col+1,row),px(p,col,row)};
end
integer count=0,frames=0;reg pixels=0;reg [15:0] expected;
always @(posedge wr) if(rst) begin
 if(!rs && lcd==16'h2c) begin pixels=1;count=0;end
 else if(pixels && rs) begin
   expected=rgb(px(frames==0?0:1,(count%16)/2,(count/16)/2));
   if(lcd!==expected) $fatal(1,"pixel mismatch frame=%0d pixel=%0d got=%h expected=%h",frames,count,lcd,expected);
   if(frames==0 && count==5) request=1;
   if(frames==0 && active!==0) $fatal(1,"page changed inside frame");
   count=count+1;
   if(count==128) begin
     pixels=0;frames=frames+1;
     if(frames==2) begin $display("LCD_PIXEL_AND_PAGE_SWAP_PASS");$finish;end
   end
 end
end
initial begin #1000000;$fatal(1,"timeout");end
endmodule
