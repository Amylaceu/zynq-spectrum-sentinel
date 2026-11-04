`timescale 1ns/1ps
module tb_x5_pfb;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] in_data=0;reg in_valid=0;wire in_ready;
    wire [31:0] pfb_data;wire [3:0] pfb_user;
    wire pfb_valid,pfb_last,pfb_error,cap_ready;
    reg gate_ready=0;
    wire pfb_ready=cap_ready && gate_ready;
    reg arm=0;
    wire cap_busy,cap_done;wire [3:0] cap_error;
    wire [12:0] cap_count;wire [31:0] cap_data;wire [3:0] cap_keep;
    wire cap_valid,cap_last;reg dma_ready=0;
    reg [63:0] timestamp=64'h12345678ffff0000,first_timestamp;
    reg [31:0] stimulus[0:32768],expected[0:65551],packet[0:4103];
    integer received=0,packet_received=0,cycles=0,epoch=0,sent,gap;
    integer stalls=0,cap_stalls=0;
    reg [31:0] rng=32'h1234abcd;
    reg stalled=0,packet_stalled=0;
    reg [31:0] held_data,held_packet;
    reg [3:0] held_user;reg held_last,held_packet_last;
    pfb_os2 dut(.aclk(clk),.aresetn(resetn),.s_axis_tdata(in_data),.s_axis_tvalid(in_valid),.s_axis_tready(in_ready),
        .m_axis_tdata(pfb_data),.m_axis_tuser(pfb_user),.m_axis_tvalid(pfb_valid),
        .m_axis_tready(pfb_ready),.m_axis_tlast(pfb_last),.error_sticky(pfb_error));
    nco_capture capture(.aclk(clk),.aresetn(resetn),.arm_toggle(arm),.clear_errors(1'b0),
        .cfg_ch_sel(4'd3),.cfg_fcw(32'h12345678),.cfg_dec(4'd1),.cfg_len(13'd4096),
        .cfg_src(32'h13579bdf),.timestamp(timestamp),.busy(cap_busy),.done_toggle(cap_done),
        .error_sticky(cap_error),.captured_count(cap_count),
        .s_axis_tdata(pfb_data),.s_axis_tuser(pfb_user),.s_axis_tvalid(pfb_valid && gate_ready),
        .s_axis_tready(cap_ready),.s_axis_tlast(pfb_last),.m_axis_tdata(cap_data),
        .m_axis_tkeep(cap_keep),.m_axis_tvalid(cap_valid),.m_axis_tready(dma_ready),.m_axis_tlast(cap_last));
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        gate_ready=resetn && rng[3:0]>2 && !(epoch==1 && cycles>=500 && cycles<3000);
        // Intentionally block DMA until acquisition is complete, then randomize.
        dma_ready=resetn && cap_count==4096 && rng[7:4]>3;
    end
    always @(posedge clk) begin
        timestamp<=timestamp+1'b1;
        if(!resetn) begin received<=0;packet_received<=0;cycles<=0;stalled<=0;packet_stalled<=0;end
        else begin
            cycles<=cycles+1;
            if(cycles>2500000) $fatal(1,"X5 chain timeout epoch %0d received %0d packets %0d",epoch,received,packet_received);
            if(pfb_error || cap_error) $fatal(1,"X5 error PFB=%h capture=%h",pfb_error,cap_error);
            if(epoch==0 && in_valid && !in_ready) $fatal(1,"3.84 MSPS baseline input stalled at %0d",sent);
            if(in_valid && !in_ready) stalls<=stalls+1;
            if(stalled && (!pfb_valid || pfb_data!==held_data || pfb_user!==held_user || pfb_last!==held_last))
                $fatal(1,"PFB payload changed under backpressure");
            stalled<=pfb_valid && !pfb_ready;held_data<=pfb_data;held_user<=pfb_user;held_last<=pfb_last;
            if(pfb_valid && pfb_ready) begin
                if(received>=(epoch==0 ? 65552 : 2048)) $fatal(1,"Unexpected PFB word");
                if(pfb_data!==expected[received]) $fatal(1,"PFB mismatch word %0d got %h expected %h",received,pfb_data,expected[received]);
                if(pfb_user!==(received%16) || pfb_last!==((received%16)==15)) $fatal(1,"PFB bin/TLAST mismatch %0d",received);
                if(epoch==0 && received==3) first_timestamp<=timestamp;
                received<=received+1;
                if(epoch==0 && received%16384==16383)
                    $display("X5_PROGRESS: %0d / 65552 exact PFB IQ words at cycle %0d",received+1,cycles);
            end
            if(packet_stalled && (!cap_valid || cap_data!==held_packet || cap_last!==held_packet_last))
                $fatal(1,"SCAP payload changed under backpressure");
            packet_stalled<=cap_valid && !dma_ready;held_packet<=cap_data;held_packet_last<=cap_last;
            if(cap_valid && !dma_ready) cap_stalls<=cap_stalls+1;
            if(cap_valid && dma_ready) begin
                if(packet_received>=4104 || epoch!=0) $fatal(1,"Unexpected SCAP packet");
                if(packet_received==1) begin
                    if(cap_data!==first_timestamp[31:0]) $fatal(1,"Timestamp low mismatch");
                end else if(packet_received==2) begin
                    if(cap_data!==first_timestamp[63:32]) $fatal(1,"Timestamp high mismatch");
                end else if(cap_data!==packet[packet_received])
                    $fatal(1,"SCAP mismatch word %0d got %h expected %h",packet_received,cap_data,packet[packet_received]);
                if(cap_keep!==4'hf || cap_last!==(packet_received==4103)) $fatal(1,"SCAP KEEP/TLAST mismatch");
                packet_received<=packet_received+1;
            end
        end
    end
    initial begin
        $readmemh("x5_input.hex",stimulus);$readmemh("x5_pfb_expected.hex",expected);$readmemh("x5_chain_expected.hex",packet);
        repeat(20) @(negedge clk);resetn=1;arm=1;
        for(sent=0;sent<32769;sent=sent+1) begin
            @(negedge clk);in_valid=1;in_data=stimulus[sent];
            do @(posedge clk);while(!in_ready);
            @(negedge clk);in_valid=0;
            gap=(sent%16)==15 ? 40 : 39;
            repeat(gap-2) @(negedge clk);
        end
        wait(received==65552 && packet_received==4104 && !cap_busy && cap_done);
        if(cap_count!=4096) $fatal(1,"Capture length mismatch");
        $display("X5_BASELINE_PASS: 32769 inputs at 3.84 MSPS, 4097 frames / 65552 exact PFB IQ, 4104 exact SCAP words");
        @(negedge clk);resetn=0;arm=0;epoch=1;
        repeat(20) @(negedge clk);resetn=1;
        // Reset must restore zero prehistory and rotation. Burst plus long stall.
        for(sent=0;sent<1024;sent=sent+1) begin
            @(negedge clk);in_valid=1;in_data=stimulus[sent];
            do @(posedge clk);while(!in_ready);
        end
        @(negedge clk);in_valid=0;
        wait(received==2048);repeat(100) @(posedge clk);
        if(stalls==0 || cap_stalls==0) $fatal(1,"Backpressure coverage missing");
        $display("TB_RESULT: PASS X5 PFB+NCO exact, reset/replay 128 frames, input stall cycles=%0d DMA stalls=%0d",stalls,cap_stalls);
        $finish;
    end
endmodule
