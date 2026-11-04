`timescale 1ns/1ps
module tb_audio_tone_y3;
    reg aclk=0; always #3.333333 aclk=~aclk;
    reg mclk=0; always #40.690104 mclk=~mclk;
    reg resetn=0, enable=0, tone_mode=0;
    wire bclk, lrck, dacdat;
    wire [31:0] status, frames, underflows, pcm_samples;
    reg [23:0] expected[0:47];
    reg [23:0] left_samples[0:95], right_samples[0:95];
    integer bits=0, left_count=0, right_count=0, offset, i, match_count=0;
    reg previous_lrck=0, capturing=0;
    reg [23:0] received=0;

    audio_sink_y3 #(.PCM_DEPTH(8192),.PCM_COUNT_WIDTH(14),.PREFILL(4096)) dut(
        .aclk(aclk),.aresetn(resetn),.mclk(mclk),.mresetn(resetn),
        .enable(enable),.tone_mode(tone_mode),.channel(4'd6),.fcw(32'b0),
        .iq_data(32'b0),.iq_channel(4'b0),.iq_transfer(1'b0),
        .bclk(bclk),.lrck(lrck),.dacdat(dacdat),.status(status),
        .frames(frames),.underflows(underflows),.pcm_samples(pcm_samples));

    // Check the pins, not the ROM-to-serializer internal wire. The arbitrary
    // capture phase is resolved against all 48 possible sine offsets below.
    always @(posedge bclk) if(resetn) begin
        #1;
        if(lrck!=previous_lrck) begin
            previous_lrck=lrck;
            bits=0;received=0;
            if(!lrck && dut.playback) capturing=1;
            if(dacdat!==0) $fatal(1,"I2S delay bit is not zero");
        end else if(capturing && bits<24) begin
            received={received[22:0],dacdat};
            bits=bits+1;
            if(bits==24) begin
                if(!lrck && left_count<96) begin
                    left_samples[left_count]=received;
                    left_count=left_count+1;
                end
                if(lrck && right_count<96) begin
                    right_samples[right_count]=received;
                    right_count=right_count+1;
                end
            end
        end
    end
    initial begin
        $readmemh("y3_tone.hex",expected);
        repeat(100) @(negedge aclk); resetn=1;
        // FM mode with no IQ must stay silent and must not underflow.
        repeat(1000) @(negedge mclk);
        if(frames!=0 || underflows!=0) $fatal(1,"unexpected audio without IQ");
        tone_mode=1;enable=1;
        wait(left_count==96 && right_count==96);
        if(underflows!=0 || pcm_samples!=0 || status[2:1]!=0)
            $fatal(1,"tone caused FIFO fault or FM activity");
        match_count=0;
        for(offset=0;offset<48;offset=offset+1) begin
            integer good;
            good=1;
            for(i=0;i<96;i=i+1) begin
                if(left_samples[i]!==expected[(i+offset)%48] ||
                   right_samples[i]!==left_samples[i]) good=0;
            end
            match_count=match_count+good;
        end
        if(match_count!=1) $fatal(1,"1kHz mono duplicated tone mismatch; matches=%0d",match_count);
        enable=0;resetn=0;
        repeat(10) @(negedge mclk);
        if(dacdat!==0 || lrck!==0) $fatal(1,"reset did not silence I2S");
        $display("TB_RESULT: PASS Y3 tone 1kHz/48kHz, 96 stereo frames exact, no FM/IQ, no underflow, mute/reset");
        $finish;
    end
    initial begin #10000000; $fatal(1,"Y3 tone timeout left%0d right%0d",left_count,right_count); end
endmodule
