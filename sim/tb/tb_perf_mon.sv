`timescale 1ns/1ps
module tb_perf_mon;
    reg clk=0;
    `ifdef DSP_100MHZ
    always #5 clk=~clk;
    `else
    always #3.333 clk=~clk;
    `endif
    reg resetn=0,sv=0,sr=0,fv=0,fr=0,fl=0,hv=0,hr=0,hit=0,lr=0,ov=0,err=0;
    reg [7:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0,value;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [31:0] rdata;
    integer n,expected_samples=0,expected_frames=0,expected_hits=0,expected_lists=0;
    integer marker_cycle,list_cycle,sim_cycle=0;
    reg marker_started=0;
    perf_mon dut(.aclk(clk),.aresetn(resetn),.sample_valid(sv),.sample_ready(sr),
        .fft_valid(fv),.fft_ready(fr),.fft_last(fl),.hit_valid(hv),.hit_ready(hr),.hit_value(hit),
        .list_ready(lr),.overflow_sticky(ov),.error_sticky(err),.fifo_level(13'd1234),
        .s_axi_awaddr(awaddr),
        .s_axi_awvalid(awvalid),
        .s_axi_awready(awready),
        .s_axi_wdata(wdata),
        .s_axi_wstrb(4'b1111),
        .s_axi_wvalid(wvalid),
        .s_axi_wready(wready),
        .s_axi_bvalid(bvalid),
        .s_axi_bready(bready),
        .s_axi_bresp(bresp),
        .s_axi_araddr(araddr),
        .s_axi_arvalid(arvalid),
        .s_axi_arready(arready),
        .s_axi_rdata(rdata),
        .s_axi_rvalid(rvalid),
        .s_axi_rready(rready),
        .s_axi_rresp(rresp));
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

    always @(posedge clk) begin
        sim_cycle=sim_cycle+1;
        if(resetn) begin
            if(sv&&sr) expected_samples=expected_samples+1;
            if(fv&&fr&&fl) expected_frames=expected_frames+1;
            if(hv&&hr&&hit) expected_hits=expected_hits+1;
            if(lr) expected_lists=expected_lists+1;
            if(dut.arm_wait && sv&&sr) begin marker_cycle=sim_cycle;marker_started=1;end
            if(dut.marker_pending && lr) list_cycle=sim_cycle;
        end
    end
    initial begin
        repeat(8) @(negedge clk);resetn=1;
        read_bus('hfc,value);if(value!==32'h50460001) $fatal(1,"version");
        write_bus(8,1);
        for(n=0;n<1000;n=n+1) begin
            @(negedge clk);sv=n%2==0;sr=n%3!=0;fv=n%5==0;fr=n%7!=0;fl=n%10==0;
            hv=n%3==0;hr=n%4!=0;hit=n%8!=0;lr=n==70 || n==700;ov=n==500;err=n==600;
        end
        @(negedge clk);sv=0;sr=0;fv=0;hv=0;lr=0;ov=0;err=0;
        write_bus(4,1);read_bus(12,value);if(value!==1) $fatal(1,"snapshot ack");
        read_bus(16,value);if(value!==expected_samples) $fatal(1,"sample handshake");
        read_bus(20,value);if(value!==0) $fatal(1,"sample high");
        read_bus(24,value);if(value!==expected_frames) $fatal(1,"fft handshake");
        read_bus(28,value);if(value!==expected_hits) $fatal(1,"hit handshake");
        read_bus(32,value);if(value!==expected_lists) $fatal(1,"list count");
        read_bus(44,value);if(!marker_started || value!==(list_cycle-marker_cycle)) $fatal(1,"latency got%0d expected%0d",value,list_cycle-marker_cycle);
        read_bus(48,value);if(value!==1) $fatal(1,"marker complete");
        read_bus(52,value);if(value!==7) $fatal(1,"sticky flags and valid");
        read_bus(56,value);if(value!==1234) $fatal(1,"fifo");
        // Events after snapshot must not change the published counters.
        @(negedge clk);sv=1;sr=1;repeat(20) @(negedge clk);sv=0;
        read_bus(16,value);if(value!==(expected_samples-20)) $fatal(1,"snapshot tearing");
        write_bus(0,1);repeat(4) @(negedge clk);write_bus(4,2);
        read_bus(16,value);if(value!==0) $fatal(1,"clear sample");
        read_bus(52,value);if(value!==0) $fatal(1,"clear flags");
        $display("TB_RESULT: PASS perf handshake counts, atomic snapshot, first-sample marker latency, sticky flags and clear");$finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
