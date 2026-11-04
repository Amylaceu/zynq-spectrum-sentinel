`timescale 1ns/1ps
// Verifies the functional premise of audio_edges_y3.xdc independently of data values.
module tb_audio_edge_contract;
    reg clk=0; always #40.6905 clk=~clk;
    reg resetn=0,enable=0,valid=0;
    reg [31:0] data=0;
    wire ready,bclk,lrck,dacdat;
    wire [31:0] frames,underflows;
    realtime last_fall=-1000, last_rise=-1000;
    integer transitions=0, cycles=0;
    i2s_tx_y3 dut(.mclk(clk),.aresetn(resetn),.enable(enable),
        .s_axis_tdata(data),.s_axis_tvalid(valid),.s_axis_tready(ready),
        .bclk(bclk),.lrck(lrck),.dacdat(dacdat),.frames(frames),.underflows(underflows));
    always @(negedge bclk) begin
        if(resetn && last_rise>0 && $realtime-last_rise<162.7)
            $fatal(1,"BCLK high pulse too short");
        last_fall=$realtime;
    end
    always @(posedge bclk) begin
        if(resetn && last_fall>0 && $realtime-last_fall<162.7)
            $fatal(1,"BCLK low pulse too short");
        last_rise=$realtime;
    end
    always @(lrck or dacdat) if(resetn) begin
        #0.001;
        if($realtime-last_fall>0.002)
            $fatal(1,"Audio output changed away from BCLK falling edge");
        transitions=transitions+1;
    end
    initial begin
        repeat(5) @(negedge clk);
        resetn=1;
        repeat(18000) begin
            @(negedge clk);
            cycles=cycles+1;
            // Includes enable/disable, missing input, and arbitrary sample data.
            enable=(cycles%791)>37;
            valid=(cycles%113)>11;
            data=$random;
        end
        if(transitions<500) $fatal(1,"Insufficient output transition coverage");
        $display("TB_RESULT: PASS phase-qualified I2S edges, transitions=%0d",transitions);
        $finish;
    end
    initial begin #2000000; $fatal(1,"Timeout"); end
endmodule
