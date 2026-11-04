`timescale 1ns/1ps
module tb_lcd8080_engine;
    reg clk=0;always #10 clk=~clk;
    reg dsp_clk=0;always #3.333 dsp_clk=~dsp_clk;
    reg resetn=0,svalid=0,slast=0,tvalid=0,tlast=0;
    reg [9:0] scol=0;
    reg [10:0] tcol=0;
    wire tready;
    reg [7:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [31:0] rdata,ui_addr;
    wire [15:0] lcd_data;
    wire cs,rs,wr,rd,rst,irq;
    integer i,bus_writes=0;
    reg [31:0] value;
    reg previous_wr=1;
    lcd8080_engine #(.RESET_CYCLES(3),.STARTUP_CYCLES(5),.DELAY_SHIFT(20)) dut(.aclk(clk),.aresetn(resetn),.dsp_clk(dsp_clk),.dsp_aresetn(resetn),
        .s_axis_spec_tdata(16'd1219),.s_axis_spec_tuser(scol),.s_axis_spec_tvalid(svalid),.s_axis_spec_tlast(slast),
        .s_axis_thr_tdata(16'd1024),.s_axis_thr_tuser(tcol),.s_axis_thr_tvalid(tvalid),.s_axis_thr_tlast(tlast),.s_axis_thr_tready(tready),
        .ui_addr(ui_addr),.ui_data(32'b0),.lcd_data(lcd_data),.lcd_cs_n(cs),.lcd_rs(rs),.lcd_wr_n(wr),.lcd_rd_n(rd),.lcd_reset_n(rst),.irq_frame_done(irq),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),.s_axi_wdata(wdata),.s_axi_wstrb(4'b1111),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(rready));
    task automatic write_bus(input [7:0] addr,input [31:0] data);
        @(negedge clk);awaddr=addr;wdata=data;awvalid=1;wvalid=1;
        do @(posedge clk);while(!(awready&&wready));@(negedge clk);awvalid=0;wvalid=0;bready=1;
        do @(posedge clk);while(!bvalid);@(negedge clk);bready=0;
    endtask
    task automatic read_bus(input [7:0] addr,output [31:0] data);
        @(negedge clk);araddr=addr;arvalid=1;do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;rready=1;do @(posedge clk);while(!rvalid);
        data=rdata;@(negedge clk);rready=0;
    endtask
    initial begin
        repeat(12) @(negedge clk);resetn=1;
        write_bus(4,1);read_bus('hfc,value);if(value!==32'h4c430001) $fatal(1,"LCD version");
        write_bus(0,1);
        for(i=0;i<560;i=i+1) begin
            @(negedge dsp_clk);svalid=1;scol=i;slast=i==559;
            @(negedge dsp_clk);svalid=0;
        end
        for(i=0;i<2048;i=i+1) begin
            @(negedge dsp_clk);tvalid=1;tcol=i;tlast=i==2047;
            do @(posedge dsp_clk);while(!tready);
        end
        @(negedge dsp_clk);tvalid=0;
        wait(dut.snapshots.request_toggle!=0);repeat(10) @(negedge clk);
        if(bus_writes<100 || dut.snapshot_error || dut.reduce_error || dut.region_error) $fatal(1,"engine binding/status");
        read_bus('h14,value);if(value[4:2]!=0 || !value[0]) $fatal(1,"engine MMIO status %h",value);
        read_bus('h18,value);if(value!==0) $fatal(1,"unexpected dropped frames");
        $display("TB_RESULT: PASS LCD engine binding,AXI,full threshold reduction,paired snapshot and init/clear bus; not full frame timing");$finish;
    end
    always @(posedge clk) begin
        if(!previous_wr && wr && resetn) bus_writes=bus_writes+1;
        previous_wr=wr;
    end
    initial begin #1000000;$fatal(1,"engine timeout");end
endmodule
