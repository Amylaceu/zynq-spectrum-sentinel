`timescale 1ns/1ps
// Isolate the lossless fork from channelizer arithmetic (verified separately).
module x5_channel_capture (
 input wire aclk,aresetn,input wire [31:0] s_axis_tdata,
 input wire s_axis_tvalid,output reg s_axis_tready,
 input wire arm_toggle,clear_errors,input wire [3:0] cfg_ch_sel,cfg_dec,
 input wire [31:0] cfg_fcw,cfg_src,input wire [12:0] cfg_len,
 input wire [63:0] timestamp,output wire busy,done_toggle,
 output wire [3:0] error_sticky,output wire [12:0] captured_count,
 output wire pfb_error,output wire [31:0] m_axis_tdata,
 output wire [3:0] m_axis_tkeep,output wire m_axis_tvalid,m_axis_tlast,
 input wire m_axis_tready
);
 assign busy=0;assign done_toggle=0;assign error_sticky=0;
 assign captured_count=0;assign pfb_error=0;assign m_axis_tdata=0;
 assign m_axis_tkeep=15;assign m_axis_tvalid=0;assign m_axis_tlast=0;
 initial s_axis_tready=0;
endmodule

module tb_x5_fork;
 reg clk=0;always #3.333 clk=~clk;
 reg resetn=0,valid=0,last=0,ready=0,accepted=0;
 reg [31:0] data=0;wire in_ready,out_valid,out_last;
 wire [31:0] out_data;
 integer sent=0,spec=0,pfb=0,cycles=0;
 integer seed=32'h78123235;
 reg [31:0] random_value;
 x5_frontend dut(.aclk(clk),.aresetn(resetn),.control(32'b0),.fcw(32'b0),
   .source_id(32'b0),.status(),.s_axis_tdata(data),.s_axis_tvalid(valid),
   .s_axis_tlast(last),.s_axis_tready(in_ready),.m_axis_spec_tdata(out_data),
   .m_axis_spec_tvalid(out_valid),.m_axis_spec_tlast(out_last),
   .m_axis_spec_tready(ready),.m_axis_capture_tdata(),.m_axis_capture_tkeep(),
   .m_axis_capture_tvalid(),.m_axis_capture_tlast(),.m_axis_capture_tready(1'b1));
 initial begin
   repeat(20) @(negedge clk);resetn=1;
   while(spec<4000 || pfb<4000) begin
     @(negedge clk);
     random_value=$random(seed);
     // Long asymmetric stalls must neither duplicate nor lose a branch word.
     ready=(cycles>=300 && cycles<900)?0:random_value[0];
     dut.channelizer.s_axis_tready=(cycles>=1000 && cycles<1700)?0:random_value[2];
     if(!valid || accepted) begin
       valid=(sent<4000) && random_value[5];data=sent;last=(sent%2048==2047);
     end
     @(posedge clk);
     if(out_valid && ready) begin
       if(out_data!==spec || out_last!==(spec%2048==2047)) $fatal(1,"spec duplicate/loss %d %d",out_data,spec);
       spec=spec+1;
     end
     if(dut.channelizer.s_axis_tvalid && dut.channelizer.s_axis_tready) begin
       if(dut.channelizer.s_axis_tdata!==pfb) $fatal(1,"PFB duplicate/loss");
       pfb=pfb+1;
     end
     accepted=valid && in_ready;
     if(accepted) sent=sent+1;
     cycles=cycles+1;
     if(cycles>60000) $fatal(1,"fork timeout");
   end
   @(negedge clk);valid=0;ready=1;dut.channelizer.s_axis_tready=1;
   repeat(30) begin @(posedge clk);if(out_valid || dut.channelizer.s_axis_tvalid) $fatal(1,"extra word");end
   $display("TB_RESULT: PASS X5 fork 4000 words both consumers; asymmetric random and long stalls");$finish;
 end
endmodule
