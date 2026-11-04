`timescale 1ns/1ps
// Finite Welch frames, capture CDC, and CFAR publication must stay paired.
module tb_x1_diagnostic;
    reg clk=0,cpu=0; always #3.333 clk=~clk; always #10 cpu=~cpu;
    reg resetn=0,arm=0,valid=0,last=0; reg [31:0] data=0;
    wire ready,pv,pr,pl,we,ce,done,error,welch_error;
    wire [31:0] pd,ma,md; wire [3:0] mw;
    reg [10:0] bin=0;
    reg [31:0] memory[0:2047],stimulus[0:16383],expected[0:16383],stats[0:47];
    integer frame,i,cycle=0,writes=0;
    wire thr_ready=(cycle%11)<7,hit_ready=(cycle%13)<9;
    always @(posedge clk) begin
        cycle<=cycle+1;
        if(pv && pr) bin<=bin+1'b1;
        if(ce) begin
            if(mw!==4'hf || ma[31:13]!==0) $fatal(1,"capture write invalid");
            memory[ma[12:2]]<=md;writes<=writes+1;
        end
    end
    spec_welch welch(.aclk(clk),.aresetn(resetn),.avg_shift(5'd3),
        .s_axis_tdata(data),.s_axis_tvalid(valid),.s_axis_tready(ready),.s_axis_tlast(last),
        .m_axis_tdata(pd),.m_axis_tvalid(pv),.m_axis_tready(pr),.m_axis_tlast(pl),.framing_error(welch_error));
    sentinel_capture capture(.dsp_clk(clk),.dsp_aresetn(resetn),.cpu_clk(cpu),.cpu_aresetn(resetn),
        .arm_toggle(arm),.power_data(pd),.power_bin(bin),.power_valid(pv),.power_ready(pr),.power_last(pl),
        .mem_addr(ma),.mem_data(md),.mem_we(mw),.mem_en(ce),.done_toggle(done),.error_sticky(error));
    cfar_core_x1 cfar(.aclk(clk),.aresetn(resetn),.s_axis_pwr_tdata(pd),.s_axis_pwr_tvalid(pv),
        .s_axis_pwr_tready(pr),.s_axis_pwr_tlast(pl),.m_axis_thr_tready(thr_ready),
        .m_axis_hit_tready(hit_ready),.m_axis_tgt_tready(1'b1),
        .s_axi_awaddr(14'b0),.s_axi_awvalid(1'b0),.s_axi_wdata(32'b0),.s_axi_wstrb(4'b0),
        .s_axi_wvalid(1'b0),.s_axi_bready(1'b1),.s_axi_araddr(14'b0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1));
    initial begin
        $readmemh("diag_input.hex",stimulus);$readmemh("diag_power.hex",expected);$readmemh("diag_stats.hex",stats);
        repeat(12) @(negedge clk);resetn=1;
        force cfar.registers.reg_ctrl=1;
        wait(!cfar.occ_clearing);
        for(frame=0;frame<8;frame=frame+1) begin
            @(negedge cpu);arm=~arm;repeat(20) @(negedge clk);
            for(i=0;i<2048;i=i+1) begin
                if(i%37==0) repeat(5) @(negedge clk);
                @(negedge clk);valid=1;data=stimulus[frame*2048+i];last=(i==2047);
                do @(posedge clk);while(!ready);
                @(negedge clk);valid=0;last=0;
            end
            wait(done==arm && cfar.frames==frame+1);repeat(120) @(negedge clk);
            if(error || welch_error || cfar.detect_error || cfar.cluster_busy || bin!=0 || writes!=(frame+1)*2048)
                $fatal(1,"finite frame not drained");
            for(i=0;i<2048;i=i+1)
                if(memory[i]!==expected[frame*2048+i]) $fatal(1,"paired power mismatch frame%0d bin%0d",frame,i);
            if(cfar.targets!==stats[frame*6] || cfar.hits!==stats[frame*6+1] ||
               cfar.raw_count!==stats[frame*6+2] || cfar.filtered_count!==stats[frame*6+3] ||
               cfar.candidate_count!==stats[frame*6+4] || cfar.status_latch!==stats[frame*6+5])
                $fatal(1,"CFAR counters do not match captured frame%0d",frame);
        end
        $display("TB_RESULT: PASS 8 finite IIR frames,16384 exact captured powers,48 exact CFAR counters,CDC and backpressure");
        $finish;
    end
    initial begin #15000000;$fatal(1,"diagnostic simulation timeout");end
endmodule
