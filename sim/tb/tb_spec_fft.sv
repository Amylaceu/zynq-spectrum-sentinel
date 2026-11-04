`timescale 1ns/1ps
module tb_spec_fft;
    reg clk=0; always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] input_data=0;
    reg input_valid=0,input_last=0;
    wire input_ready;
    wire [31:0] win_data;
    wire win_valid,win_ready,win_last,framing_error;
    reg config_valid=0;
    wire config_ready;
    wire [31:0] fft_data;
    wire [7:0] fft_user,status_data;
    wire fft_valid,fft_last,status_valid,overflow,unexpected,missing;
    reg fft_ready=0;
    reg [31:0] random_state=32'h71ac45e9;
    reg [31:0] stimulus[0:8191];
    reg [23:0] expected[0:16383];
    integer sent,received=0,cycles=0,output_file;
    reg stalled=0;
    reg [31:0] held_data;
    reg held_last;
    spec_window windowing(.aclk(clk),.aresetn(resetn),.win_sel(2'd0),
        .s_axis_tdata(input_data),.s_axis_tvalid(input_valid),.s_axis_tready(input_ready),.s_axis_tlast(input_last),
        .m_axis_tdata(win_data),.m_axis_tvalid(win_valid),.m_axis_tready(win_ready),.m_axis_tlast(win_last),
        .framing_error(framing_error));
    // Config bits[12:1]: [2,2,2,2,2,1] from first to last FFT stage; bit0=forward.
    spec_fft_2048 fft(.aclk(clk),.aresetn(resetn),
        .s_axis_config_tdata(16'h0d55),.s_axis_config_tvalid(config_valid),.s_axis_config_tready(config_ready),
        .s_axis_data_tdata(win_data),.s_axis_data_tvalid(win_valid),.s_axis_data_tready(win_ready),.s_axis_data_tlast(win_last),
        .m_axis_data_tdata(fft_data),.m_axis_data_tuser(fft_user),.m_axis_data_tvalid(fft_valid),
        .m_axis_data_tready(fft_ready),.m_axis_data_tlast(fft_last),
        .m_axis_status_tdata(status_data),.m_axis_status_tvalid(status_valid),.m_axis_status_tready(1'b1),
        .event_fft_overflow(overflow),.event_tlast_unexpected(unexpected),.event_tlast_missing(missing));
    initial begin
        $readmemh("in_axis32.hex",stimulus); $readmemh("exp_fft.hex",expected);
        output_file=$fopen("spec_fft_out.hex","w");
        repeat(12) @(negedge clk); resetn=1; config_valid=1;
        do @(posedge clk); while(!config_ready);
        @(negedge clk); config_valid=0;
        for(sent=0;sent<8192;sent=sent+1) begin
            @(negedge clk); input_valid=1; input_data=stimulus[sent]; input_last=(sent%2048)==2047;
            do @(posedge clk); while(!input_ready);
        end
        @(negedge clk); input_valid=0;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        fft_ready=resetn && random_state[3:0]>2;
    end
    always @(posedge clk) if(resetn) begin
        cycles<=cycles+1;
        if(cycles>500000) $fatal(1,"FFT timeout");
        if(overflow || unexpected || missing || framing_error) $fatal(1,"FFT event or framing error");
        if(stalled && (!fft_valid || fft_data!==held_data || fft_last!==held_last))
            $fatal(1,"FFT changed payload under backpressure");
        stalled<=fft_valid && !fft_ready; held_data<=fft_data; held_last<=fft_last;
        if(fft_valid && fft_ready) begin
            if(received>=8192) $fatal(1,"Unexpected extra FFT output");
            if({fft_data[15:0],8'b0}!==expected[2*received] ||
               {fft_data[31:16],8'b0}!==expected[2*received+1])
                $fatal(1,"FFT mismatch at %0d got %h,%h expected %h,%h",received,
                    {fft_data[15:0],8'b0},{fft_data[31:16],8'b0},expected[2*received],expected[2*received+1]);
            if(fft_last!==((received%2048)==2047)) $fatal(1,"FFT TLAST mismatch");
            $fwrite(output_file,"%06x\n%06x\n",{fft_data[15:0],8'b0},{fft_data[31:16],8'b0});
            received<=received+1;
        end
    end
    initial begin
        wait(received==8192);
        repeat(12) @(posedge clk);
        $fclose(output_file);
        $display("TB_RESULT: PASS 4 FFT frames, 16384 words, randomized output backpressure");
        $finish;
    end
endmodule
