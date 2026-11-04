`timescale 1ns/1ps
// Lockstep observable equivalence, including stalls, reset and publication.
module tb_x2_timing_candidates;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0,valid=0,hit=0,blocked=0,last=0,output_ready=0;
    reg [31:0] power=0,rng=32'h5d38a71c;
    reg [10:0] bin_index=0;
    reg [7:0] gap=6;
    reg [11:0] min_width=2,alarm_limit=5;
    reg [1:0] frame_error=0;
    reg [6:0] mmio_addr=0;
    wire [1:0] ready,busy,irq,alarm,tvalid,tlast;
    wire [31:0] frame_count[0:1],status[0:1],mmio[0:1];
    wire [5:0] targets[0:1];
    wire [11:0] hits[0:1],raws[0:1],filtered[0:1],candidates[0:1];
    wire [127:0] stream[0:1];
    integer cycle=0,frame,b,publications=0,stream_words=0;
`define PORTS(N) .aclk(clk),.aresetn(resetn),.cfg_gap(gap),.cfg_min_width(min_width), \
        .cfg_alarm_limit(alarm_limit),.frame_error(frame_error),.power(power),.hit(hit), \
        .blocked(blocked),.bin_index(bin_index),.last(last),.valid(valid), \
        .ready(ready[N]),.busy(busy[N]),.irq_list_ready(irq[N]),.frame_count(frame_count[N]), \
        .target_count(targets[N]),.frame_hits(hits[N]),.raw_count(raws[N]), \
        .filtered_count(filtered[N]),.candidate_count(candidates[N]),.status_latch(status[N]), \
        .alarm(alarm[N]),.mmio_word_addr(mmio_addr),.mmio_data(mmio[N]), \
        .m_axis_tdata(stream[N]),.m_axis_tvalid(tvalid[N]),.m_axis_tready(output_ready),.m_axis_tlast(tlast[N])
    cfar_cluster_x1 baseline(`PORTS(0));
    cfar_cluster_timing_x2 candidate(`PORTS(1));
`undef PORTS
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};
        output_ready=(cycle%311<280) && (rng[0] || rng[5]);
        mmio_addr=mmio_addr+1'b1;
    end
    always @(posedge clk) begin
        cycle=cycle+1;
        #1;
        if(resetn) begin
            if({ready[0],busy[0],irq[0],alarm[0],tvalid[0],tlast[0],
                frame_count[0],targets[0],hits[0],raws[0],filtered[0],candidates[0],status[0]} !==
               {ready[1],busy[1],irq[1],alarm[1],tvalid[1],tlast[1],
                frame_count[1],targets[1],hits[1],raws[1],filtered[1],candidates[1],status[1]})
                $fatal(1,"control/publication mismatch at cycle %0d",cycle);
            // The original list memories are uninitialized before first publish.
            if(publications>0 && mmio[0]!==mmio[1]) $fatal(1,"MMIO list mismatch");
            if(tvalid[0] && stream[0]!==stream[1]) $fatal(1,"AXIS record mismatch");
            if(irq[0]) publications=publications+1;
            if(tvalid[0] && output_ready) stream_words=stream_words+1;
        end
        if(cycle>1000000) $fatal(1,"timeout");
    end
    initial begin
        repeat(5) @(negedge clk);resetn=1;
        for(frame=0;frame<32;frame=frame+1) begin
            gap=frame%9;min_width=(frame%4)+1;frame_error=frame%4;
            for(b=0;b<2048;b=b+1) begin
                if(b%37==0) repeat(3) @(negedge clk);
                @(negedge clk);
                valid=1;bin_index=b;last=(b==2047);power=rng;
                case(frame%8)
                    0:hit=0;
                    1:hit=1;
                    2:hit=(b%12)<3;
                    3:hit=(b==2047);
                    4:hit=(b%2)==0;
                    5:hit=(b<8 || b>2042);
                    default:hit=rng[1];
                endcase
                blocked=frame%8>=5 && (b%71==0 || rng[9:6]==0);
                if(frame%8==4) power=32'hffffffff;
                @(posedge clk);while(!ready[0]) @(posedge clk);
                @(negedge clk);valid=0;
            end
            wait(irq[0]);wait(ready[0]);repeat(3) @(negedge clk);
        end
        if(publications!=32 || stream_words<100) $fatal(1,"insufficient coverage");
        // Reset in the middle of an open cluster; published outputs must clear.
        @(negedge clk);valid=1;hit=1;blocked=0;bin_index=0;last=0;
        repeat(8) @(negedge clk);resetn=0;valid=0;
        repeat(4) @(negedge clk);resetn=1;repeat(4) @(negedge clk);
        if(frame_count[0]!=0 || targets[0]!=0) $fatal(1,"reset failed");
        $display("TB_RESULT: PASS X2 cluster cycle-exact 32 frames, %0d stream words, randomized stalls, masks, top32, reset",stream_words);
        $finish;
    end
endmodule
