`timescale 1ns/1ps
module tb_cfar_guard8;
    localparam CASES=18,WORDS=CASES*2048;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] input_data=0;
    reg input_valid=0,input_last=0;
    wire input_ready;
    wire [15:0] thr_data;
    wire [7:0] hit_data;
    wire [10:0] thr_bin,hit_bin;
    wire thr_valid,thr_last,hit_valid,hit_last;
    reg thr_ready=0,hit_ready=0,tgt_ready=0;
    wire [127:0] tgt_data;
    wire tgt_valid,tgt_last,irq;
    wire [31:0] threshold,power;
    reg [13:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;
    reg [3:0] wstrb=15;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [31:0] rdata;
    wire [1:0] bresp,rresp;
    reg [31:0] inputs[0:WORDS-1],exp_thr[0:WORDS-1],exp_hit[0:WORDS-1],exp_db[0:WORDS-1];
    reg [31:0] exp_occ[0:WORDS-1],config_words[0:CASES*24-1],stats[0:CASES*7-1],counts[0:CASES-1];
    reg [127:0] records[0:CASES*32-1];
    integer current_case=0,nhit=0,nthr=0,ntgt=0,nirq=0,cycles=0,send_index,lane,r;
    integer fthr,fhit,fdb,focc,ftarget,fstats;
    reg checking=1;
    reg [31:0] random_state=32'hcfa2e08b;
    reg hit_stall=0,thr_stall=0,tgt_stall=0;
    reg [83:0] held_hit;
    reg [27:0] held_thr;
    reg [128:0] held_tgt;
    reg [31:0] temp;
    cfar_core_x1 dut(.aclk(clk),.aresetn(resetn),
        .s_axis_pwr_tdata(input_data),.s_axis_pwr_tvalid(input_valid),.s_axis_pwr_tready(input_ready),.s_axis_pwr_tlast(input_last),
        .m_axis_thr_tdata(thr_data),.m_axis_thr_tuser(thr_bin),.m_axis_thr_tvalid(thr_valid),.m_axis_thr_tready(thr_ready),.m_axis_thr_tlast(thr_last),
        .m_axis_hit_tdata(hit_data),.m_axis_hit_tuser(hit_bin),.m_axis_hit_tvalid(hit_valid),.m_axis_hit_tready(hit_ready),.m_axis_hit_tlast(hit_last),
        .m_axis_tgt_tdata(tgt_data),.m_axis_tgt_tvalid(tgt_valid),.m_axis_tgt_tready(tgt_ready),.m_axis_tgt_tlast(tgt_last),.irq_list_ready(irq),
        .dbg_threshold(threshold),.dbg_power(power),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(wstrb),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
        .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.s_axi_rresp(rresp));
    // Verify wrap, borrow and full-width carry independent of the CFAR vectors.
    initial begin : check_add_sub40
        reg [39:0] edges_a[0:5];
        reg [31:0] edges_b[0:3];
        reg [39:0] a,expected,actual;
        reg [31:0] b,c,rng;
        integer i,j,k;
        edges_a[0]=0;edges_a[1]=1;edges_a[2]=40'hffffffffff;
        edges_a[3]=40'h00ffffffff;edges_a[4]=40'h0100000000;edges_a[5]=40'h8000000000;
        edges_b[0]=0;edges_b[1]=1;edges_b[2]=32'hffffffff;edges_b[3]=32'h80000000;
        for(i=0;i<6;i=i+1) for(j=0;j<4;j=j+1) for(k=0;k<4;k=k+1) begin
            expected=edges_a[i]+{8'b0,edges_b[j]}-{8'b0,edges_b[k]};
            actual=dut.detector.add_sub40(edges_a[i],edges_b[j],edges_b[k]);
            if(actual!==expected) $fatal(1,"carry-save edge mismatch %0d/%0d/%0d",i,j,k);
        end
        rng=32'h57a1cfa2;
        for(i=0;i<10000;i=i+1) begin
            rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);a={rng[7:0],rng};
            rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);b=rng;
            rng=rng^(rng<<13);rng=rng^(rng>>17);rng=rng^(rng<<5);c=rng;
            expected=a+{8'b0,b}-{8'b0,c};actual=dut.detector.add_sub40(a,b,c);
            if(actual!==expected) $fatal(1,"carry-save random mismatch %0d",i);
        end
        $display("X1_ADD_SUB40_PASS 10096");
    end
    task automatic wr(input [13:0] addr,input [31:0] value,input [3:0] enables=15);
        fork
            begin @(negedge clk);if(addr[2]) repeat(3) @(negedge clk);
                awaddr=addr;awvalid=1;do @(posedge clk);while(!awready);@(negedge clk);awvalid=0;end
            begin @(negedge clk);if(!addr[2]) repeat(3) @(negedge clk);
                wdata=value;wstrb=enables;wvalid=1;do @(posedge clk);while(!wready);@(negedge clk);wvalid=0;end
        join
        wait(bvalid);repeat(2) begin @(posedge clk);#1;if(!bvalid || bresp!=0) $fatal(1,"B response");end
        @(negedge clk);bready=1;@(posedge clk);@(negedge clk);bready=0;
    endtask
    task automatic rd(input [13:0] addr,output [31:0] value);
        @(negedge clk);araddr=addr;arvalid=1;do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;wait(rvalid);#1;value=rdata;
        repeat(2) begin @(posedge clk);#1;if(!rvalid || rdata!==value || rresp!=0) $fatal(1,"R response changed");end
        @(negedge clk);rready=1;@(posedge clk);@(negedge clk);rready=0;
    endtask
    initial begin
        $readmemh("input.hex",inputs);$readmemh("threshold.hex",exp_thr);$readmemh("hit.hex",exp_hit);$readmemh("db.hex",exp_db);
        $readmemh("stats.hex",stats);$readmemh("config.hex",config_words);$readmemh("targets.hex",records);$readmemh("count.hex",counts);$readmemh("occupancy.hex",exp_occ);
        fthr=$fopen("x1_guard8_threshold_out.hex","w");fhit=$fopen("x1_guard8_hit_out.hex","w");fdb=$fopen("x1_guard8_db_out.hex","w");
        focc=$fopen("x1_guard8_occupancy_out.hex","w");ftarget=$fopen("x1_guard8_targets_out.hex","w");
        fstats=$fopen("x1_guard8_stats_out.hex","w");
        repeat(12) @(negedge clk);resetn=1;
        rd('hfc,temp);if(temp!==32'h43460002) $fatal(1,"VERSION");
        // Independent AW/W, WSTRB and RO writes are checked before data path starts.
        wr('hc,32'hdeadbeef);wr('hc,32'h11223344,4'b0101);rd('hc,temp);
        if(temp!==32'hde22be44) $fatal(1,"WSTRB");
        wr('hfc,0);rd('hfc,temp);if(temp!==32'h43460002) $fatal(1,"RO VERSION");
        // Mask-window WSTRB, read-only snapshot and invalid configuration guards.
        wr('h80,32'hdeadbeef);wr('h80,32'h11223344,4'b0101);rd('h80,temp);
        if(temp!==32'hde22be44) $fatal(1,"mask WSTRB");
        wr('h40,32'hffffffff);rd('h40,temp);if(temp!==0) $fatal(1,"RO snapshot");
        wait(!dut.occ_clearing);
        wr('h3c,17);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"invalid mask count accepted");
        wr(0,0);wr('h3c,1);wr('h80,32'h00030004);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"reversed mask accepted");
        wr(0,0);wr('h80,32'h08000000);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"out of range mask accepted");
        wr(0,0);wr('h3c,0);wr('h38,2049);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"invalid width accepted");
        wr(0,0);wr('h38,2);
        for(current_case=0;current_case<CASES;current_case=current_case+1) begin
            ntgt=0;
            for(r=1;r<6;r=r+1) wr(r*4,config_words[current_case*24+r]);
            wr('h38,config_words[current_case*24+6]);wr('h3c,config_words[current_case*24+7]);
            for(r=0;r<16;r=r+1) wr('h80+r*4,config_words[current_case*24+8+r]);
            wr(0,config_words[current_case*24]);
            for(send_index=0;send_index<2048;send_index=send_index+1) begin
                @(negedge clk);input_data=inputs[current_case*2048+send_index];input_valid=1;input_last=send_index==2047;
                do @(posedge clk);while(!input_ready);
                if(send_index==20) begin
                    @(negedge clk);input_valid=0;
                    // Current frame must retain the original mask/DC/gap/width.
                    wr('h14,0);wr('h38,2048);wr('h80,32'h07ff0000);wr('h3c,1);wr('h10,255);
                end
                if(random_state[3:2]==0) begin @(negedge clk);input_valid=0;end
            end
            @(negedge clk);input_valid=0;
            wait(nirq==current_case+1 && nhit==(current_case+1)*2048 && nthr==(current_case+1)*2048 && ntgt==counts[current_case]);
            wr(0,0); // Freeze new frames for a coherent occupancy/list read.
            rd('h18,temp);if(temp!==counts[current_case]) $fatal(1,"TARGET_COUNT");
            rd('h1c,temp);if(temp!==current_case+1) $fatal(1,"FRAME_COUNT");
            rd('h30,temp);if(temp!==current_case+1) $fatal(1,"OCC_FRAMES");
            wait(!dut.cluster_busy);
            rd('h34,temp);if(temp[3:0]!==0) $fatal(1,"STATUS %h",temp);
            rd('h18,temp);$fdisplay(fstats,"%08x",temp);
            rd('h44,temp);if(temp!==stats[current_case*7+1]) $fatal(1,"RAW_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h48,temp);if(temp!==stats[current_case*7+2]) $fatal(1,"FILTERED_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h4c,temp);if(temp!==stats[current_case*7+3]) $fatal(1,"CANDIDATE_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h20,temp);if(temp!==stats[current_case*7+4]) $fatal(1,"HIT_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h40,temp);if(temp!==stats[current_case*7+5]) $fatal(1,"STATUS_LATCH");$fdisplay(fstats,"%08x",temp);
            rd('h28,temp);if(temp!==stats[current_case*7+6]) $fatal(1,"ALARM");$fdisplay(fstats,"%08x",temp);
            for(r=0;r<32;r=r+1) for(lane=0;lane<4;lane=lane+1) begin
                if(r<counts[current_case]) begin
                    rd('h200+16*r+4*lane,temp);
                    if(temp!==records[current_case*32+r][lane*32+:32]) $fatal(1,"MMIO target case=%0d record=%0d lane=%0d got=%h exp=%h",current_case,r,lane,temp,records[current_case*32+r][lane*32+:32]);
                end else temp=0;
                $fdisplay(ftarget,"%08x",temp);
            end
            for(r=0;r<2048;r=r+1) begin
                rd('h1000+4*r,temp);
                if(temp!==exp_occ[current_case*2048+r]) $fatal(1,"occupancy case=%0d bin=%0d got=%h expected=%h",current_case,r,temp,exp_occ[current_case*2048+r]);
                $fdisplay(focc,"%08x",temp);
            end
            $display("X1_CORE_CASE_PASS %0d targets=%0d",current_case,counts[current_case]);
        end
        wr('h2c,1);wait(dut.occ_clearing);wait(!dut.occ_clearing);
        rd('h30,temp);if(temp!==0) $fatal(1,"clear frames");
        for(r=0;r<2048;r=r+1) begin rd('h1000+4*r,temp);if(temp!==0) $fatal(1,"clear occupancy");end
        $fclose(fthr);$fclose(fhit);$fclose(fdb);$fclose(focc);$fclose(ftarget);$fclose(fstats);
        // Framing errors are visible both live and in the published frame.
        checking=0;wr('h3c,0);wr('h38,2);wr('h10,255);wr('hc,1974);wr(0,1);
        for(send_index=0;send_index<2048;send_index=send_index+1) begin
            @(negedge clk);input_data=0;input_valid=1;input_last=(send_index==100 || send_index==2047);
            do @(posedge clk);while(!input_ready);
        end
        @(negedge clk);input_valid=0;wait(nirq==CASES+1);wait(!dut.cluster_busy);
        wr(0,0);rd('h40,temp);if(!temp[2]) $fatal(1,"framing error not latched");
        rd('h34,temp);if(!temp[2]) $fatal(1,"framing error not live");
        @(negedge clk);resetn=0;repeat(5) @(negedge clk);resetn=1;
        rd('h1c,temp);if(temp!==0) $fatal(1,"reset sequence");
        rd('h40,temp);if(temp!==0) $fatal(1,"reset snapshot");
        $display("TB_RESULT: PASS X1_CORE 18 cases, modes/masks/frame_config/atomic_stats/AXI/occupancy/framing");$finish;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        hit_ready=random_state[0] || random_state[8];thr_ready=random_state[4] || random_state[20];
        tgt_ready=random_state[9] && random_state[17];
        if(nhit>=60 && cycles<9000) hit_ready=0;
    end
    always @(posedge clk) if(resetn) begin
        cycles=cycles+1;
        if(irq) begin
            nirq=nirq+1;
            if(checking && (dut.frames!==current_case+1 || dut.targets!==stats[current_case*7] ||
                dut.raw_count!==stats[current_case*7+1] || dut.filtered_count!==stats[current_case*7+2] ||
                dut.candidate_count!==stats[current_case*7+3] || dut.hits!==stats[current_case*7+4] ||
                dut.status_latch!==stats[current_case*7+5] || dut.alarm!==stats[current_case*7+6]))
                $fatal(1,"non-atomic frame publication");
        end
        if(hit_stall && (!hit_valid || {hit_last,hit_bin,hit_data,threshold,power}!==held_hit)) $fatal(1,"hit payload unstable");
        if(thr_stall && (!thr_valid || {thr_last,thr_bin,thr_data}!==held_thr)) $fatal(1,"threshold payload unstable");
        if(tgt_stall && (!tgt_valid || {tgt_last,tgt_data}!==held_tgt)) $fatal(1,"target payload unstable");
        hit_stall=hit_valid && !hit_ready;held_hit={hit_last,hit_bin,hit_data,threshold,power};
        thr_stall=thr_valid && !thr_ready;held_thr={thr_last,thr_bin,thr_data};
        tgt_stall=tgt_valid && !tgt_ready;held_tgt={tgt_last,tgt_data};
        if(checking && hit_valid && hit_ready) begin
            if(threshold!==exp_thr[nhit] || hit_data!==exp_hit[nhit][7:0] || power!==inputs[nhit] || hit_bin!==nhit%2048 || hit_last!==((nhit%2048)==2047))
                $fatal(1,"threshold/hit idx=%0d got=%h/%h exp=%h/%h",nhit,threshold,hit_data,exp_thr[nhit],exp_hit[nhit]);
            $fdisplay(fthr,"%08x",threshold);$fdisplay(fhit,"%08x",hit_data);nhit=nhit+1;
        end
        if(checking && thr_valid && thr_ready) begin
            if(thr_data!==exp_db[nthr][15:0] || thr_bin!==nthr%2048 || thr_last!==((nthr%2048)==2047)) $fatal(1,"dB idx=%0d got=%h exp=%h",nthr,thr_data,exp_db[nthr]);
            $fdisplay(fdb,"%08x",{16'b0,thr_data});nthr=nthr+1;
        end
        if(checking && tgt_valid && tgt_ready) begin
            if(tgt_data!==records[current_case*32+ntgt] || tgt_last!==(ntgt==counts[current_case]-1)) $fatal(1,"AXIS target %0d case%0d got=%h expected=%h",ntgt,current_case,tgt_data,records[current_case*32+ntgt]);
            ntgt=ntgt+1;
        end
    end
    initial begin repeat(1000000) @(posedge clk);$fatal(1,"CFAR timeout case=%0d nhit=%0d nthr=%0d irq=%0d targets=%0d",current_case,nhit,nthr,nirq,ntgt);end
endmodule
