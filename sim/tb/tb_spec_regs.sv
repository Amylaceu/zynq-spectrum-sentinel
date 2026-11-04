`timescale 1ns/1ps
module tb_spec_regs;
    `include "spec_ctrl_defs.vh"
    reg clk=0; always #3.333 clk=~clk;
    reg resetn=0;
    reg [7:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0,frame_count=42;
    reg [3:0] wstrb=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [1:0] bresp,rresp;
    wire [31:0] rdata,ctrl,avg,decim;
    spec_ctrl_regs dut(.aclk(clk),.aresetn(resetn),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
        .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.s_axi_rresp(rresp),
        .reg_ctrl(ctrl),.reg_avg_shift(avg),.reg_disp_decim(decim),.ro_frame_cnt(frame_count));
    task automatic write_bus(input [7:0] addr,input [31:0] value,input [3:0] enables,input bit w_first);
        fork
            begin
                @(negedge clk);if(w_first) repeat(3) @(negedge clk);
                awaddr=addr;awvalid=1;do @(posedge clk);while(!awready);
                @(negedge clk);awvalid=0;
            end
            begin
                @(negedge clk);if(!w_first) repeat(3) @(negedge clk);
                wdata=value;wstrb=enables;wvalid=1;do @(posedge clk);while(!wready);
                @(negedge clk);wvalid=0;
            end
        join
        wait(bvalid);
        repeat(4) begin @(posedge clk);#1;if(!bvalid || bresp!=0) $fatal(1,"Write response not held");end
        @(negedge clk);bready=1;@(posedge clk);@(negedge clk);bready=0;
    endtask
    task automatic read_bus(input [7:0] addr,input [31:0] expected);
        @(negedge clk);araddr=addr;arvalid=1;do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;
        wait(rvalid);
        if(addr==SPEC_CTRL_FRAME_CNT) frame_count=frame_count+1;
        repeat(4) begin
            @(posedge clk);#1;
            if(!rvalid || rdata!==expected || rresp!=0) $fatal(1,"Read mismatch/response instability addr=%h got=%h expected=%h",addr,rdata,expected);
        end
        @(negedge clk);rready=1;@(posedge clk);@(negedge clk);rready=0;
    endtask
    initial begin
        repeat(10) @(negedge clk);resetn=1;
        read_bus(SPEC_CTRL_VERSION,32'h53500001);
        read_bus(SPEC_CTRL_CTRL,0);read_bus(SPEC_CTRL_AVG_SHIFT,3);read_bus(SPEC_CTRL_DISP_DECIM,1);
        write_bus(SPEC_CTRL_CTRL,32'hdeadbeef,4'b1111,0);
        read_bus(SPEC_CTRL_CTRL,32'hdeadbeef);
        write_bus(SPEC_CTRL_CTRL,32'h11223344,4'b0101,1);
        read_bus(SPEC_CTRL_CTRL,32'hde22be44);
        write_bus(SPEC_CTRL_AVG_SHIFT,31,4'b0001,0);read_bus(SPEC_CTRL_AVG_SHIFT,31);
        write_bus(SPEC_CTRL_VERSION,0,4'b1111,1);read_bus(SPEC_CTRL_VERSION,32'h53500001);
        write_bus(SPEC_CTRL_FRAME_CNT,0,4'b1111,0);read_bus(SPEC_CTRL_FRAME_CNT,42);
        read_bus(SPEC_CTRL_FRAME_CNT,43);
        $display("TB_RESULT: PASS AXI-Lite skewed AW/W, WSTRB, RO, delayed B/R responses");$finish;
    end
    initial begin repeat(3000) @(posedge clk);$fatal(1,"Register interface timeout");end
endmodule
