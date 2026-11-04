`timescale 1ns/1ps
module tb_audio_sink_y3;
    reg clk=0;always #3.333333 clk=~clk;
    // Deliberately +80ppm audio clock: finite FIFO is not a drift eliminator.
    reg mclk=0;always #40.686849 mclk=~mclk;
    reg resetn=0,enable=0;
    reg [31:0] iq_data=0;
    reg [3:0] iq_channel=0;
    reg transfer=0;
    wire bclk,lrck,dacdat;
    wire [31:0] status,frames,underflows,pcm_samples;
    reg [31:0] iq[0:49152],golden[0:4915];
    integer sent=0,words=0,samples=0,cycles=0,next_at=0;
    integer bits=0;
    reg previous_lrck=0,started=0;
    reg [23:0] received=0;
    audio_sink_y3 #(.PCM_DEPTH(8192),.PCM_COUNT_WIDTH(14),.PREFILL(4096)) dut(.aclk(clk),.aresetn(resetn),
        .mclk(mclk),.mresetn(resetn),.enable(enable),.tone_mode(1'b0),.channel(4'd6),
        .fcw(32'h28000000),.iq_data(iq_data),.iq_channel(iq_channel),
        .iq_transfer(transfer),.bclk(bclk),.lrck(lrck),.dacdat(dacdat),
        .status(status),.frames(frames),.underflows(underflows),.pcm_samples(pcm_samples));
    // 150MHz/480kHz alternates 312/313 cycles. Also inject unrelated bins.
    always @(negedge clk) begin
        transfer=0;
        if(resetn && enable) begin
            cycles=cycles+1;
            if(cycles>=next_at && sent<49153) begin
                iq_data=iq[sent];iq_channel=6;transfer=1;
                sent=sent+1;next_at=next_at+(sent%2 ? 312 : 313);
            end else if(cycles%19==0) begin
                iq_data=32'hffff1234;iq_channel=7;transfer=1;
            end
        end
    end
    // Independently reconstruct each stereo I2S word from external signals.
    always @(posedge bclk) if(resetn) begin
        #1;
        if(lrck!=previous_lrck) begin
            previous_lrck=lrck;bits=0;received=0;
            if(!lrck && dut.playback) started=1;
            if(dacdat!==0) $fatal(1,"nonzero I2S delay bit");
        end else if(started && bits<24) begin
            received={received[22:0],dacdat};bits=bits+1;
            if(bits==24) begin
                if(samples>=4916 || received!==golden[samples][23:0])
                    $fatal(1,"PCM[%0d] ch%0d got%h expected%h",samples,lrck,received,golden[samples][23:0]);
                words=words+1;
                if(lrck) samples=samples+1;
            end
        end
    end
    initial begin
        $readmemh("y3_fm_input.hex",iq);
        $readmemh("y3_audio_expected.hex",golden);
        repeat(100) @(negedge clk);resetn=1;
        repeat(100) @(negedge clk);enable=1;next_at=100;
        wait(samples==800);
        @(negedge clk);
        if(status[2:1]!=0 || underflows!=0 || pcm_samples<800 || words!=1600)
            $fatal(1,"status%h underruns%0d produced%0d words%0d",status,underflows,pcm_samples,words);
        if(status[17:4]<4090 || status[17:4]>4110)
            $fatal(1,"production FIFO prefill/drift level unexpected %0d",status[17:4]);
        // Stop before finite test-vector exhaustion. A real receiver is continuous.
        enable=0;resetn=0;started=0;
        repeat(200) @(negedge clk);
        if(dacdat!==0 || lrck!==0) $fatal(1,"reset must mute");
        $display("TB_RESULT: PASS Y3 audio sink: production8192/prefill4096, 800 stereo PCM frames exact, +80ppm audio clock, unrelated-channel rejection, no underrun, reset mute");
        $finish;
    end
    initial begin #120000000;$fatal(1,"audio sink timeout sent%0d samples%0d",sent,samples);end
endmodule
