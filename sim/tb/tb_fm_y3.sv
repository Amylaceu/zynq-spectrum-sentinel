`timescale 1ns/1ps
module tb_fm_y3;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0,valid=0;
    reg [31:0] data=0;
    wire ready,phase_valid,phase_ready,audio_valid;
    wire [23:0] phase_data;
    wire [31:0] audio_data,zeros,inputs,outputs;
    reg audio_ready=1;
    reg [31:0] input_words[0:8192],audio_expected[0:819];
    reg [23:0] phase_expected[0:8192];
    integer sent=0,phase_count=0,audio_count=0,cycle=0,hold_left=0;
    reg [31:0] rng=32'h91573a;
    reg held=0;
    reg [31:0] held_data;
    fm_phase_y3 phase_core(.aclk(clk),.aresetn(resetn),.cfg_fcw(32'h28000000),
        .s_axis_tdata(data),.s_axis_tvalid(valid),.s_axis_tready(ready),
        .m_axis_tdata(phase_data),.m_axis_tvalid(phase_valid),
        .m_axis_tready(phase_ready),.zero_samples(zeros));
    fm_audio_filter_y3 filter_core(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(phase_data),.s_axis_tvalid(phase_valid),.s_axis_tready(phase_ready),
        .m_axis_tdata(audio_data),.m_axis_tvalid(audio_valid),.m_axis_tready(audio_ready),
        .samples_in(inputs),.samples_out(outputs));
    always @(negedge clk) if(resetn) begin
        cycle=cycle+1;
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        // Deliberate long stall plus randomized downstream backpressure.
        audio_ready=!(cycle>=700000 && cycle<707000) && rng[2:0]!=0;
        if(!valid && sent<8193 && cycle%313==0) begin
            valid=1;data=input_words[sent];
        end
    end
    always @(posedge clk) if(resetn) begin
        if(valid && ready) begin sent=sent+1;valid<=0;end
        if(phase_valid && phase_ready) begin
            if(phase_count>=8193 || phase_data!==phase_expected[phase_count])
                $fatal(1,"phase[%0d] got%h expected%h",phase_count,phase_data,phase_expected[phase_count]);
            phase_count=phase_count+1;
        end
        if(held && (!audio_valid || audio_data!==held_data)) $fatal(1,"AXIS changed under stall");
        held=audio_valid && !audio_ready;held_data=audio_data;
        if(audio_valid && audio_ready) begin
            if(audio_count>=820 || audio_data!==audio_expected[audio_count])
                $fatal(1,"audio[%0d] got%h expected%h",audio_count,audio_data,audio_expected[audio_count]);
            audio_count=audio_count+1;
        end
    end
    initial begin
        $readmemh("y3_fm_input.hex",input_words);
        $readmemh("y3_phase_expected.hex",phase_expected);
        $readmemh("y3_audio_expected.hex",audio_expected);
        repeat(5) @(negedge clk);resetn=1;
        wait(audio_count==820 && phase_count==8193 && sent==8193);
        repeat(50) @(negedge clk);
        if(sent!=8193 || phase_count!=8193 || inputs!=8193 || outputs!=820 || zeros!=3)
            $fatal(1,"counts sent%0d phase%0d inputs%0d outputs%0d zero%0d",sent,phase_count,inputs,outputs,zeros);
        resetn=0;repeat(3) @(negedge clk);
        if(audio_valid || phase_valid || outputs || zeros) $fatal(1,"reset not clear");
        $display("TB_RESULT: PASS Y3 FM 8193 IQ/820 PCM exact, CORDIC residual, zero pairs, FIR/deemphasis, AXIS stall/reset");
        $finish;
    end
    initial begin #40000000;$fatal(1,"FM timeout");end
endmodule
