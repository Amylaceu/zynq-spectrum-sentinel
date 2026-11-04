`timescale 1ns/1ps
module tb_stream_stats_x2;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] sd=0,fd=0,fi=0,fo=0;
    reg [7:0] awaddr=0,araddr=0;reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;wire [31:0] rdata;
    wire [1:0] bresp,rresp;
    stream_stats_x2 dut(.aclk(clk),.aresetn(resetn),.sample_drop(sd),.frame_drop(fd),.frames_in(fi),.frames_out(fo),
      .overflow_sticky(1'b0),.mismatch_sticky(1'b0),.queue_error(1'b0),.fifo_level(13'd10),
      .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),.s_axi_wstrb(4'hf),
      .s_axi_wvalid(wvalid),.s_axi_wready(wready),.s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
      .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),.s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.s_axi_rresp(rresp));
    task automatic write_token(input [31:0] token);
      @(negedge clk);awaddr=0;wdata=token;awvalid=1;wvalid=1;
      do @(posedge clk);while(!(awready&&wready));
      @(negedge clk);awvalid=0;wvalid=0;bready=1;
      do @(posedge clk);while(!bvalid);
      if(bresp!=0) $fatal(1,"write response");
      @(negedge clk);bready=0;
    endtask
    task automatic check_read(input [7:0] address,input [31:0] expected);
      @(negedge clk);araddr=address;arvalid=1;
      do @(posedge clk);while(!arready);
      @(negedge clk);arvalid=0;
      wait(rvalid);repeat(4) @(negedge clk);
      if(rdata!==expected || rresp!=0) $fatal(1,"snapshot offset%h expected%h got%h",address,expected,rdata);
      rready=1;@(negedge clk);rready=0;
    endtask
    initial begin
      repeat(10) @(negedge clk);resetn=1;
      sd=3;fd=4;fi=20;fo=15;
      write_token(32'hffffffff);
      check_read(4,32'hffffffff);
      // Counters change while AXI reads are stalled. The whole latched tuple
      // must still describe the old event until a new token is acknowledged.
      sd=100;fd=200;fi=300;fo=400;
      check_read(8,3);check_read(12,4);check_read(16,20);check_read(20,15);
      check_read(24,0);check_read(28,10);check_read(252,32'h58320001);
      write_token(0);check_read(4,0);check_read(8,100);check_read(12,200);
      check_read(16,300);check_read(20,400);
      $display("TB_RESULT: PASS atomic token/ack X2 statistics, stalled AXI reads,token wrap");$finish;
    end
    initial begin #100000;$fatal(1,"snapshot timeout");end
endmodule
