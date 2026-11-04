`timescale 1ns/1ps
module tb_adc_tap_v2;
    reg adc_clk=0;always #8.138 adc_clk=~adc_clk;
    reg dsp_clk=0;always #5 dsp_clk=~dsp_clk;
    reg adc_reset=1,resetn=0,vi=0,vq=0,ready=0;
    reg [15:0] ai=0,aq=0;
    wire [31:0] data;
    wire valid,last,overflow,mismatch;
    wire [5:0] level;
    integer sent=0,received=0,cycles=0;
    reg compare=1,random_ready=1,stalled=0;
    reg [32:0] held;
    reg [31:0] random_state=32'h73a8470c;
    time adc_edge=0;
    always @(posedge adc_clk) adc_edge=$time;
    always @(dut.fifo_reset) if($time>110 && $time!=adc_edge)
        $fatal(1,"FIFO reset changed outside a write-clock edge");
    adc_tap_v2 #(.FIFO_DEPTH(32),.FIFO_COUNT_WIDTH(6)) dut(.adc_clk(adc_clk),.adc_reset(adc_reset),
        .adc_i(ai),.adc_q(aq),.adc_valid_i(vi),.adc_valid_q(vq),.dsp_clk(dsp_clk),.dsp_aresetn(resetn),
        .m_axis_tdata(data),.m_axis_tvalid(valid),.m_axis_tready(ready),.m_axis_tlast(last),
        .overflow_sticky(overflow),.mismatch_sticky(mismatch),.fifo_level(level));
    function [31:0] expected(input integer index);
        reg [11:0] i,q;
        begin i=index;q=index*37;expected={q,4'b0,i,4'b0};end
    endfunction
    task automatic pulse_sample(input integer index);
        @(negedge adc_clk);ai={{4{index[11]}},index[11:0]};aq=(index*37);
        aq={{4{aq[11]}},aq[11:0]};vi=1;vq=1;
        @(negedge adc_clk);vi=0;vq=0;
    endtask
    initial begin
        repeat(20) @(negedge adc_clk);resetn=1;adc_reset=0;
        wait(!dut.wr_busy && !dut.rd_busy);repeat(8) @(negedge adc_clk);
        for(sent=0;sent<4096;sent=sent+1) begin pulse_sample(sent);repeat(2) @(negedge adc_clk);end
        wait(received==4096);repeat(10) @(negedge dsp_clk);
        if(overflow || mismatch) $fatal(1,"unexpected ADC fault");
        compare=0;random_ready=0;ready=0;
        for(sent=0;sent<128;sent=sent+1) pulse_sample(sent);
        repeat(10) @(negedge dsp_clk);if(!overflow) $fatal(1,"overflow not reported");
        adc_reset=1;resetn=0;repeat(20) @(negedge adc_clk);resetn=1;adc_reset=0;
        wait(!dut.wr_busy && !dut.rd_busy);repeat(8) @(negedge adc_clk);
        if(overflow || mismatch) $fatal(1,"sticky reset failed");
        @(negedge adc_clk);vi=1;vq=0;@(negedge adc_clk);vi=0;
        repeat(10) @(negedge dsp_clk);if(!mismatch) $fatal(1,"I/Q mismatch not reported");
        // Exercise one-sided resets at non-clock-aligned phases. Neither side
        // may leak stale FIFO words or keep a prior frame index after reset.
        #3;adc_reset=1;
        repeat(20) @(negedge adc_clk);#2;adc_reset=0;
        wait(!dut.wr_busy && !dut.rd_busy && !dut.fifo_reset);
        repeat(10) @(negedge dsp_clk);
        if(valid || overflow || mismatch) $fatal(1,"ADC-only reset did not flush");
        received=0;compare=1;random_ready=1;
        for(sent=0;sent<2048;sent=sent+1) begin pulse_sample(sent);repeat(2) @(negedge adc_clk);end
        wait(received==2048);@(negedge dsp_clk);compare=0;random_ready=0;ready=0;
        for(sent=0;sent<8;sent=sent+1) pulse_sample(sent+100);
        #3;resetn=0;repeat(20) @(negedge adc_clk);#2;resetn=1;
        wait(!dut.wr_busy && !dut.rd_busy && !dut.fifo_reset);
        repeat(10) @(negedge dsp_clk);
        if(valid || overflow || mismatch) $fatal(1,"DSP-only reset did not flush");
        received=0;compare=1;random_ready=1;
        for(sent=0;sent<2048;sent=sent+1) begin pulse_sample(sent);repeat(2) @(negedge adc_clk);end
        wait(received==2048);repeat(10) @(negedge dsp_clk);
        if(overflow || mismatch) $fatal(1,"fault after reset recovery");
        $display("TB_RESULT: PASS ADC normalization, async clocks,8192 checked words,stalls,overflow,mismatch,one-sided resets,synchronous FIFO reset");$finish;
    end
    always @(negedge dsp_clk) if(random_ready) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        ready=random_state[3] || random_state[18];
        if(cycles>300 && cycles<350) ready=0;
    end
    always @(posedge dsp_clk) begin
        cycles=cycles+1;
        if(resetn && compare) begin
            if(stalled && (!valid || {last,data}!==held)) $fatal(1,"ADC output unstable");
            stalled=valid && !ready;held={last,data};
            if(valid && ready) begin
                if(data!==expected(received) || last!==((received%2048)==2047)) $fatal(1,"ADC word%0d got=%h expected=%h",received,data,expected(received));
                received=received+1;
            end
        end else stalled=0;
        if(cycles>100000) $fatal(1,"ADC timeout");
    end
endmodule
