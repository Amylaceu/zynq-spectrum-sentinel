`timescale 1ns/1ps
module tb_cfar_cluster_x1;
    localparam CASES=20, WORDS=CASES*2048;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [7:0] gap=6;
    reg [11:0] width=2;
    reg [31:0] power=0;
    reg hit=0,blocked=0,last=0,valid=0;
    reg [10:0] bin_index=0;
    wire ready,busy,irq;
    wire [31:0] frame_seq,status_latch;
    wire [5:0] target_count;
    wire [11:0] frame_hits,raw_count,filtered_count,candidate_count;
    reg [6:0] word_addr=0;
    wire [31:0] word_data;
    wire [127:0] target;
    wire target_valid,target_last;
    reg target_ready=0;
    reg [31:0] powers[0:WORDS-1],hits[0:WORDS-1],blocks[0:WORDS-1];
    reg [31:0] configs[0:CASES*2-1],stats[0:CASES*6-1];
    reg [127:0] expected[0:CASES*32-1];
    reg [31:0] random_state=32'h18ac7e61;
    reg stalled=0;
    reg [128:0] held;
    integer current_case=0,received=0,publications=0,cycles=0,total_records=0;
    integer i,j,lane,output_file;
    reg [31:0] before_sequence;
    cfar_cluster_x1 dut(.aclk(clk),.aresetn(resetn),.cfg_gap(gap),.cfg_min_width(width),
        .cfg_alarm_limit(12'd1),.frame_error(2'b0),.alarm(),
        .power(power),.hit(hit),.blocked(blocked),.bin_index(bin_index),.last(last),.valid(valid),
        .ready(ready),.busy(busy),.irq_list_ready(irq),.frame_count(frame_seq),.target_count(target_count),
        .frame_hits(frame_hits),.raw_count(raw_count),.filtered_count(filtered_count),.candidate_count(candidate_count),
        .status_latch(status_latch),.mmio_word_addr(word_addr),.mmio_data(word_data),
        .m_axis_tdata(target),.m_axis_tvalid(target_valid),.m_axis_tready(target_ready),.m_axis_tlast(target_last));

    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        target_ready=resetn && random_state[0];
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if(cycles>2000000) $fatal(1,"timeout case=%0d state=%0d",current_case,dut.state);
        if(!resetn) stalled=0;
        else begin
            if(stalled && (!target_valid || {target_last,target}!==held)) $fatal(1,"AXIS changed during stall");
            stalled=target_valid && !target_ready;held={target_last,target};
            if(irq) begin
                publications=publications+1;
                if(frame_seq!==publications || target_count!==stats[current_case*6] ||
                   raw_count!==stats[current_case*6+1] || filtered_count!==stats[current_case*6+2] ||
                   candidate_count!==stats[current_case*6+3] || frame_hits!==stats[current_case*6+4] ||
                   status_latch!==stats[current_case*6+5])
                    $fatal(1,"publish stats mismatch case=%0d seq=%0d count=%0d raw=%0d filtered=%0d candidates=%0d hits=%0d status=%h",
                        current_case,frame_seq,target_count,raw_count,filtered_count,candidate_count,frame_hits,status_latch);
            end
            if(target_valid && target_ready) begin
                if(received>=stats[current_case*6] || target!==expected[current_case*32+received])
                    $fatal(1,"target mismatch case=%0d idx=%0d got=%h exp=%h",current_case,received,target,expected[current_case*32+received]);
                if(target_last!==(received==stats[current_case*6]-1)) $fatal(1,"TLAST mismatch");
                $fdisplay(output_file,"%032h",target);
                received=received+1;total_records=total_records+1;
            end
        end
    end

    initial begin
        $readmemh("power.hex",powers);$readmemh("hit.hex",hits);$readmemh("blocked.hex",blocks);
        $readmemh("config.hex",configs);$readmemh("stats.hex",stats);$readmemh("targets.hex",expected);
        output_file=$fopen("x1_cluster_targets_out.hex","w");
        repeat(10) @(negedge clk);resetn=1;
        for(current_case=0;current_case<CASES;current_case=current_case+1) begin
            received=0;gap=configs[current_case*2];width=configs[current_case*2+1];
            before_sequence=frame_seq;
            for(i=0;i<2048;i=i+1) begin
                @(negedge clk);
                valid=1;power=powers[current_case*2048+i];hit=hits[current_case*2048+i][0];
                blocked=blocks[current_case*2048+i][0];bin_index=i;last=i==2047;
                do @(posedge clk);while(!ready);
                if(i<2047 && frame_seq!==before_sequence) $fatal(1,"published partial frame");
                // Config changes after first handshake must not alter this frame.
                if(i==5) begin @(negedge clk);valid=0;gap=0;width=2048;end
                if(random_state[3:2]==0) begin @(negedge clk);valid=0;end
            end
            @(negedge clk);valid=0;
            wait(publications==current_case+1 && received==stats[current_case*6]);
            wait(ready);
            for(j=0;j<32;j=j+1) for(lane=0;lane<4;lane=lane+1) begin
                @(negedge clk);word_addr=j*4+lane;#1;
                if(word_data!==expected[current_case*32+j][lane*32+:32])
                    $fatal(1,"MMIO mismatch case=%0d record=%0d lane=%0d",current_case,j,lane);
            end
            $display("X1_CASE_PASS %0d targets=%0d raw=%0d candidates=%0d status=%h",current_case,target_count,raw_count,candidate_count,status_latch);
        end
        $fclose(output_file);
        @(negedge clk);valid=1;hit=1;blocked=0;power=100;last=0;bin_index=0;
        @(posedge clk);@(negedge clk);valid=0;resetn=0;
        repeat(3) @(negedge clk);resetn=1;
        repeat(3) @(negedge clk);
        if(frame_seq!==0 || target_count!==0 || status_latch!==0 || target_valid || irq || !ready)
            $fatal(1,"reset did not discard unfinished frame");
        $display("TB_RESULT: PASS X1_CLUSTER cases=%0d records=%0d cycles=%0d",CASES,total_records,cycles);
        $finish;
    end
endmodule
