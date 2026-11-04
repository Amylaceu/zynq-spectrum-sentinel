`timescale 1ns/1ps
module tb_spec_stages;
    localparam WORDS=16384;
    reg clk=0; always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] stimulus[0:4*WORDS-1],expected[0:4*WORDS-1];
    reg [31:0] in_data[0:3];
    reg [3:0] in_valid=0,in_last=0,out_ready=0,done=0;
    wire [3:0] in_ready,out_valid,out_last;
    wire [31:0] out_data[0:3];
    wire [15:0] db_data;
    wire window_error,welch_error;
    reg [1:0] win_sel=0;
    reg [4:0] avg_shift=3;
    spec_window w(.aclk(clk),.aresetn(resetn),.win_sel(win_sel),
        .s_axis_tdata(in_data[0]),.s_axis_tvalid(in_valid[0]),.s_axis_tready(in_ready[0]),.s_axis_tlast(in_last[0]),
        .m_axis_tdata(out_data[0]),.m_axis_tvalid(out_valid[0]),.m_axis_tready(out_ready[0]),.m_axis_tlast(out_last[0]),.framing_error(window_error));
    spec_power p(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(in_data[1]),.s_axis_tvalid(in_valid[1]),.s_axis_tready(in_ready[1]),.s_axis_tlast(in_last[1]),
        .m_axis_tdata(out_data[1]),.m_axis_tvalid(out_valid[1]),.m_axis_tready(out_ready[1]),.m_axis_tlast(out_last[1]));
    spec_welch a(.aclk(clk),.aresetn(resetn),.avg_shift(avg_shift),
        .s_axis_tdata(in_data[2]),.s_axis_tvalid(in_valid[2]),.s_axis_tready(in_ready[2]),.s_axis_tlast(in_last[2]),
        .m_axis_tdata(out_data[2]),.m_axis_tvalid(out_valid[2]),.m_axis_tready(out_ready[2]),.m_axis_tlast(out_last[2]),.framing_error(welch_error));
    spec_db d(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(in_data[3]),.s_axis_tvalid(in_valid[3]),.s_axis_tready(in_ready[3]),.s_axis_tlast(in_last[3]),
        .m_axis_tdata(db_data),.m_axis_tvalid(out_valid[3]),.m_axis_tready(out_ready[3]),.m_axis_tlast(out_last[3]));
    assign out_data[3]={16'b0,db_data};
    initial begin
        $readmemh("n2_stages_in.hex",stimulus);$readmemh("n2_stages_expected.hex",expected);
        repeat(12) @(negedge clk);resetn=1;
    end
    for(genvar ch=0;ch<4;ch=ch+1) begin:channels
        integer sent,received=0,fd;
        reg [31:0] random_state=32'h9813ca71+ch;
        reg stalled=0,held_last;
        reg [31:0] held_data;
        initial begin
            fd=$fopen($sformatf("spec_stage%0d_out.hex",ch),"w");
            wait(resetn);
            for(sent=0;sent<WORDS;sent=sent+1) begin
                @(negedge clk);
                in_data[ch]=stimulus[ch*WORDS+sent];in_valid[ch]=1;in_last[ch]=(sent%2048)==2047;
                if(ch==0) begin
                    case(sent/2048)
                        1,4,7: win_sel=1;
                        2,5: win_sel=2;
                        default: win_sel=0;
                    endcase
                end
                if(ch==2) avg_shift=sent/2048==4 ? 0 : sent/2048==5 ? 31 : 3;
                do @(posedge clk);while(!in_ready[ch]);
            end
            @(negedge clk);in_valid[ch]=0;
        end
        always @(negedge clk) begin
            random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
            out_ready[ch]=resetn && random_state[3:0]>2;
        end
        always @(posedge clk) if(resetn) begin
            if(window_error || welch_error) $fatal(1,"Stage framing error");
            if(stalled && (!out_valid[ch] || out_data[ch]!==held_data || out_last[ch]!==held_last))
                $fatal(1,"Backpressure payload change stage %0d",ch);
            stalled<=out_valid[ch] && !out_ready[ch];held_data<=out_data[ch];held_last<=out_last[ch];
            if(out_valid[ch] && out_ready[ch]) begin
                if(received>=WORDS) $fatal(1,"Extra output stage %0d",ch);
                if(out_data[ch]!==expected[ch*WORDS+received])
                    $fatal(1,"Stage %0d mismatch %0d got %h expected %h",ch,received,out_data[ch],expected[ch*WORDS+received]);
                if(out_last[ch]!==((received%2048)==2047)) $fatal(1,"Stage TLAST mismatch");
                $fwrite(fd,"%08x\n",out_data[ch]);received<=received+1;
                if(received==WORDS-1) begin done[ch]<=1;$fclose(fd);end
            end
        end
    end
    initial begin
        wait(&done);repeat(12) @(posedge clk);
        $display("TB_RESULT: PASS window/power/Welch/dB, 65536 words, randomized backpressure");$finish;
    end
    initial begin repeat(400000) @(posedge clk);$fatal(1,"Stage timeout");end
endmodule
