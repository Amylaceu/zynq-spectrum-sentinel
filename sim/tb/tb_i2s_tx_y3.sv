`timescale 1ns/1ps
module tb_i2s_tx_y3;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0,enable=0,valid=0;
    reg [31:0] data=32'h00800001;
    wire ready,bclk,lrck,dacdat;
    wire [31:0] frames,underflows;
    integer accepted=0,completed=0,edges=0,slot_edges=0;
    reg [23:0] expected=0,received=0;
    reg previous_lrck=0,started=0;
    integer bits=0;
    i2s_tx_y3 dut(.mclk(clk),.aresetn(resetn),.enable(enable),
        .s_axis_tdata(data),.s_axis_tvalid(valid),.s_axis_tready(ready),
        .bclk(bclk),.lrck(lrck),.dacdat(dacdat),.frames(frames),.underflows(underflows));
    always @(posedge clk) if(resetn) begin
        if(!enable) expected=0;
        else if(ready) begin
            expected=valid ? data[23:0] : 0;
            if(valid) accepted=accepted+1;
        end
    end
    // Independent I2S receiver: transitions indicate a dummy bit, then24 MSBs.
    always @(posedge bclk) if(resetn) begin
        #1;edges=edges+1;slot_edges=slot_edges+1;
        if(lrck!=previous_lrck) begin
            if(started && slot_edges!=32) $fatal(1,"LRCK slot not32 clocks");
            previous_lrck=lrck;started=1;bits=0;received=0;slot_edges=0;
            if(dacdat!==0) $fatal(1,"I2S delay bit not zero");
        end else if(started) begin
            if(bits<24) begin
                received={received[22:0],dacdat};bits=bits+1;
                if(bits==24) begin
                    if(received!==expected) $fatal(1,"I2S data mismatch got%h expected%h",received,expected);
                    completed=completed+1;
                end
            end else if(dacdat!==0) $fatal(1,"slot padding not zero");
        end
    end
    initial begin
        repeat(5) @(negedge clk);resetn=1;
        repeat(300) @(negedge clk);
        if(ready || frames || underflows) $fatal(1,"disabled channel consumed input");
        // Start exactly at a frame boundary, providing stereo sample continuity.
        wait(dut.phase==255);@(negedge clk);enable=1;valid=1;
        wait(accepted==3);@(negedge clk);data=32'h007fffff;
        wait(accepted==6);@(negedge clk);data=32'h00abcdef;
        wait(accepted==9);@(negedge clk);valid=0;
        wait(underflows==3);@(negedge clk);valid=1;data=32'h00000001;
        wait(accepted==12);
        wait(dut.phase==255);@(negedge clk);enable=0;valid=0;
        repeat(260) @(negedge clk);
        if(underflows!=3 || accepted!=12 || frames!=15 || completed<28)
            $fatal(1,"I2S totals underflow%0d accepted%0d frames%0d words%0d",underflows,accepted,frames,completed);
        resetn=0;repeat(3) @(negedge clk);
        if(dacdat || lrck || underflows || frames) $fatal(1,"reset did not mute");
        $display("TB_RESULT: PASS I2S24 mono stereo, one-bit delay,32-bit slots, padding,3 counted underruns, disabled/reset mute");$finish;
    end
    initial begin #2000000;$fatal(1,"I2S test timeout");end
endmodule
