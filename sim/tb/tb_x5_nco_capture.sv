`timescale 1ns/1ps
module tb_x5_nco_capture;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0,arm=0,clear_errors=0;
    reg [3:0] channel=5,dec=1;
    reg [31:0] fcw=0,src=32'ha55a0042;
    reg [12:0] length=4096;
    reg [63:0] timestamp=64'hfedcba98fffffff0,first_timestamp;
    wire busy,done;wire [3:0] errors;wire [12:0] count;
    reg [31:0] in_data=0;reg [3:0] in_user=0;reg in_valid=0,in_last=0;wire in_ready;
    wire [31:0] out_data;wire [3:0] out_keep;wire out_valid,out_last;reg out_ready=0;
    reg [31:0] stimulus[0:4095],expected[0:4512];
    integer received=0,packet_index=0,offset=0,cycles=0,case_no,k,bin;
    reg capture_first=0,stalled=0;reg [31:0] held_data,rng=32'h51ac9461;reg held_last;
    reg request_level;
    nco_capture dut(.aclk(clk),.aresetn(resetn),.arm_toggle(arm),.clear_errors(clear_errors),
        .cfg_ch_sel(channel),.cfg_fcw(fcw),.cfg_dec(dec),.cfg_len(length),.cfg_src(src),.timestamp(timestamp),
        .busy(busy),.done_toggle(done),.error_sticky(errors),.captured_count(count),
        .s_axis_tdata(in_data),.s_axis_tuser(in_user),.s_axis_tvalid(in_valid),.s_axis_tready(in_ready),.s_axis_tlast(in_last),
        .m_axis_tdata(out_data),.m_axis_tkeep(out_keep),.m_axis_tvalid(out_valid),.m_axis_tready(out_ready),.m_axis_tlast(out_last));
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};out_ready=resetn && rng[3:0]>5;
    end
    always @(posedge clk) begin
        timestamp<=timestamp+1'b1;
        if(resetn) begin
            cycles<=cycles+1;if(cycles>300000) $fatal(1,"NCO timeout");
            if(in_valid && !in_ready) $fatal(1,"Capture stopped draining");
            if(capture_first && in_valid && in_user==5) begin first_timestamp<=timestamp;capture_first<=0;end
            if(stalled && (!out_valid || out_data!==held_data || out_last!==held_last)) $fatal(1,"Capture AXIS instability");
            stalled<=out_valid && !out_ready;held_data<=out_data;held_last<=out_last;
            if(out_valid && out_ready) begin
                if(received>=4513) $fatal(1,"Extra NCO output");
                if(packet_index==1) begin
                    if(out_data!==first_timestamp[31:0]) $fatal(1,"NCO timestamp low");
                end else if(packet_index==2) begin
                    if(out_data!==first_timestamp[63:32]) $fatal(1,"NCO timestamp high");
                end else if(out_data!==expected[received])
                    $fatal(1,"NCO mismatch at %0d got %h expected %h",received,out_data,expected[received]);
                if(out_keep!==4'hf || out_last!==(packet_index==length-1+8)) $fatal(1,"NCO framing");
                received<=received+1;packet_index<=packet_index+1;
            end
        end
    end
    task tick;begin @(negedge clk);end endtask
    task clear_faults;begin tick;clear_errors=1;tick;clear_errors=0;tick;if(errors) $fatal(1,"Clear errors failed");end endtask
    task reject_config(input [3:0] bad_dec,input [12:0] bad_len);
        begin
            tick;dec=bad_dec;length=bad_len;tick;arm=!arm;
            repeat(5) tick;
            if(busy || out_valid || !errors[0]) $fatal(1,"Invalid config accepted");
            clear_faults;
        end
    endtask
    initial begin
        $readmemh("x5_nco_input.hex",stimulus);$readmemh("x5_nco_expected.hex",expected);
        repeat(20) tick;resetn=1;
        reject_config(2,4096);reject_config(1,0);reject_config(1,4097);
        for(case_no=0;case_no<4;case_no=case_no+1) begin
            tick;dec=1;channel=5;src=32'ha55a0042;packet_index=0;
            case(case_no)
                0:begin length=4096;fcw=32'h12345678;end
                1:begin length=257;fcw=32'hf1234567;end
                2:begin length=1;fcw=0;end
                3:begin length=127;fcw=32'h20000000;end
            endcase
            tick;arm=!arm;request_level=arm;capture_first=1;
            repeat(3) tick;
            for(k=0;k<length;k=k+1) begin
                for(bin=0;bin<16;bin=bin+1) begin
                    tick;in_valid=1;in_user=bin;in_last=bin==15;in_data=stimulus[k];
                end
                tick;in_valid=0;
                if(case_no==0 && k==0) begin
                    // Config mutation must not alter the latched capture. Busy ARM rejected.
                    channel=9;fcw=32'hdeadbeef;src=0;dec=8;
                    arm=!arm;repeat(3) tick;arm=!arm;repeat(3) tick;
                    if(!errors[1]) $fatal(1,"Busy rearm not rejected");
                end
            end
            wait(!busy);tick;
            if(done!==request_level || count!==length || packet_index!=length+8) $fatal(1,"NCO completion mismatch");
            if(errors & 4'hd) $fatal(1,"Unexpected capture error %h",errors);
            clear_faults;
        end
        if(received!=4513) $fatal(1,"NCO total word count");
        // A broken sequence after the first selected bin must abort without output.
        tick;channel=5;dec=1;length=2;arm=!arm;repeat(3) tick;
        tick;in_valid=1;in_user=5;in_last=0;
        tick;in_user=7;
        tick;in_valid=0;repeat(10) tick;
        if(busy || out_valid || !errors[2]) $fatal(1,"Framing fault not aborted");
        clear_faults;
        // Reset an incomplete acquisition; no stale packet may escape.
        tick;arm=!arm;repeat(3) tick;
        tick;in_valid=1;in_user=5;in_last=0;
        tick;in_valid=0;resetn=0;arm=0;repeat(20) tick;resetn=1;
        repeat(100) tick;
        if(busy || out_valid || done || errors || count) $fatal(1,"Reset retained capture state");
        $display("TB_RESULT: PASS X5 NCO 4513 exact words, positive/negative/zero FCW, saturation, four lengths, config/rearm/framing/reset");
        $finish;
    end
endmodule
