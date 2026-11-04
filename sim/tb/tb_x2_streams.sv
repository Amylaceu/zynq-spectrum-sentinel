`timescale 1ns/1ps
// Deterministic scoreboards: arithmetic extremes, frame-latched shift, stalls,
// full-rate Welch, and complete-frame queue dropping under prolonged stalls.
module tb_x2_streams;
    reg clk=0; always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] wd=0,qd=0;
    reg wv=0,wl=0,qr=0,qv=0,ql=0,wr=0;
    reg [4:0] shift=0;
    wire ws,wov,wol,we,qs,qov,qol,qe;
    wire [31:0] wo,qo,fi,fo,fd;
    integer wn=0,qn=0,sent,bin,f,cycles=0,keep_count=0;
    integer expected_frames[0:39];
    reg [31:0] wh[0:2047],expected[0:16383];
    reg signed [32:0] delta,updated;
    reg [31:0] old_value,random_state=32'h782931a5;
    reg random_stalls=0,welch_stalled=0,queue_stalled=0;
    reg [32:0] welch_held,queue_held;
    integer previous_output=-1,continuous_count=0;
    spec_welch_x2 welch(.aclk(clk),.aresetn(resetn),.avg_shift(shift),
        .s_axis_tdata(wd),.s_axis_tvalid(wv),.s_axis_tready(ws),.s_axis_tlast(wl),
        .m_axis_tdata(wo),.m_axis_tvalid(wov),.m_axis_tready(wr),.m_axis_tlast(wol),.framing_error(we));
    frame_queue_x2 queue(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(qd),.s_axis_tvalid(qv),.s_axis_tready(qs),.s_axis_tlast(ql),
        .m_axis_tdata(qo),.m_axis_tvalid(qov),.m_axis_tready(qr),.m_axis_tlast(qol),
        .frames_in(fi),.frames_out(fo),.frame_drop(fd),.framing_error(qe));
    function [31:0] value(input integer n);
        case(n%4)
          0:value=32'hffffffff;
          1:value=0;
          2:value=n*32'h98765431;
          3:value=32'h80000000;
        endcase
    endfunction
    always @(negedge clk) if(random_stalls) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        wr=random_state[0] || random_state[4];
        qr=random_state[2] && random_state[11];
    end
    always @(posedge clk) if(resetn) begin
        cycles=cycles+1;
        if(welch_stalled && (!wov || {wol,wo}!==welch_held)) $fatal(1,"Welch stall instability");
        welch_stalled=wov && !wr;welch_held={wol,wo};
        if(queue_stalled && (!qov || {qol,qo}!==queue_held)) $fatal(1,"queue stall instability");
        queue_stalled=qov && !qr;queue_held={qol,qo};
        if(wov && wr) begin
            if(wo!==expected[wn] || wol!==(wn%2048==2047)) $fatal(1,"Welch word %d got %h expected %h",wn,wo,expected[wn]);
            if(wn>0 && wn<8192) begin
                if(cycles!=previous_output+1) $fatal(1,"Welch bubble");
                continuous_count=continuous_count+1;
            end
            previous_output=cycles;wn=wn+1;
        end
        if(qv && qs && queue.write_index==0 && !queue.dropping) begin
            expected_frames[keep_count]=qd>>11;keep_count=keep_count+1;
        end
        if(qov && qr) begin
            if(qo!==(expected_frames[qn/2048]*2048+qn%2048) || qol!==(qn%2048==2047))
                $fatal(1,"queue reordered/mixed word %d got %h",qn,qo);
            qn=qn+1;
        end
        if(qv && !qs) $fatal(1,"queue backpressured input");
    end
    initial begin
        for(bin=0;bin<2048;bin=bin+1) wh[bin]=0;
        for(sent=0;sent<16384;sent=sent+1) begin
            f=sent/2048;bin=sent%2048;
            old_value=wh[bin];delta=$signed({1'b0,value(sent)})-$signed({1'b0,old_value});
            updated=$signed({1'b0,old_value})+(delta >>> (f<4 ? 3 : (f==4 ? 0 : (f==5 ? 31 : 5))));
            expected[sent]=updated[31:0];wh[bin]=updated[31:0];
        end
        repeat(12) @(negedge clk);resetn=1;wr=1;
        for(sent=0;sent<16384;sent=sent+1) begin
            if(sent==8192) begin
                @(negedge clk);wv=0;wait(wn==8192);random_stalls=1;
            end
            @(negedge clk);wd=value(sent);wv=1;wl=sent%2048==2047;
            f=sent/2048;
            shift=sent%2048==0 ? (f<4 ? 3 : (f==4 ? 0 : (f==5 ? 31 : 5))) : 17;
            do @(posedge clk);while(!ws);
        end
        @(negedge clk);wv=0;
        wait(wn==16384);random_stalls=0;wr=1;qr=0;
        // Fill both banks, drop whole frames, then release midway through a
        // dropped frame. The rest of that frame must still be discarded.
        for(sent=0;sent<40*2048;sent=sent+1) begin
            @(negedge clk);qv=1;qd=sent;ql=sent%2048==2047;
            if(sent==5*2048+1024) qr=1;
            if(sent==10*2048) random_stalls=1;
        end
        @(negedge clk);qv=0;random_stalls=0;qr=1;wr=1;
        wait(qn==keep_count*2048);repeat(10) @(negedge clk);
        if(fi!=40 || fo!=keep_count || fd!=40-keep_count || fd==0 || we || qe || continuous_count!=8191)
            $fatal(1,"counters/errors fi%0d fo%0d drop%0d kept%0d",fi,fo,fd,keep_count);
        $display("X2_STREAMS welch_words=%0d consecutive=%0d frames_in=%0d frames_out=%0d frame_drop=%0d",wn,continuous_count+1,fi,fo,fd);
        $display("TB_RESULT: PASS bit-exact Welch and whole-frame queue under backpressure");$finish;
    end
    initial begin #10000000;$fatal(1,"timeout");end
endmodule
