`timescale 1ns/1ps
module tb_sentinel_chain;
    reg clk=0,lc=0;always #3.333 clk=~clk;always #10 lc=~lc;
    reg resetn=0,input_valid=0,input_last=0;reg [31:0] input_data=0;
    wire input_ready;
    wire [31:0] pwr_data,power_data,frame_count;wire [10:0] pwr_bin;
    wire pwr_valid,pwr_last,pwr_ready,db_valid,db_last,db_full_valid,error_sticky;
    wire [15:0] db_data,db_full;wire [9:0] db_pixel;wire db_ready=1;
    wire [47:0] fft_data;wire fft_valid,power_valid;
    reg [7:0] awaddr=0;reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0;wire awready,wready,bvalid;wire [1:0] bresp;
    reg [31:0] stimulus[0:8191],expected[0:8191];reg [15:0] expected_pixel[0:2239],expected_thr[0:559];
    integer sent,n=0,tn=0,i,cycle=0,input_frames=0,output_frames=0;
    integer input_cycle[0:15],output_cycle[0:15];
    wire [15:0] threshold,reduced_thr,read_spec,read_thr;
    wire [10:0] thr_bin;wire [9:0] thr_col;
    wire thr_valid,thr_ready,thr_last,rtv,rtl,reduce_error,cfar_irq;
    wire snapshot_ready,snapshot_error;reg accept_frame=0;reg [9:0] read_column=0;
    wire [31:0] snapshot_id,dropped,drop_gray;
    spec_front dut(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(input_data),.s_axis_tvalid(input_valid),.s_axis_tready(input_ready),.s_axis_tlast(input_last),
        .m_axis_pwr_tdata(pwr_data),.m_axis_pwr_tuser(pwr_bin),.m_axis_pwr_tvalid(pwr_valid),.m_axis_pwr_tready(pwr_ready),.m_axis_pwr_tlast(pwr_last),
        .m_axis_db_tdata(db_data),.m_axis_db_tuser(db_pixel),.m_axis_db_tvalid(db_valid),.m_axis_db_tready(db_ready),.m_axis_db_tlast(db_last),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'b1111),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
        .s_axi_araddr(8'b0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1),
        .dbg_fft_tdata(fft_data),.dbg_fft_valid(fft_valid),.dbg_power_shifted(power_data),.dbg_power_valid(power_valid),
        .dbg_db_full(db_full),.dbg_db_valid(db_full_valid),.frame_count(frame_count),.error_sticky(error_sticky));

    cfar_core cfar(.aclk(clk),.aresetn(resetn),.s_axis_pwr_tdata(pwr_data),.s_axis_pwr_tvalid(pwr_valid),
        .s_axis_pwr_tready(pwr_ready),.s_axis_pwr_tlast(pwr_last),
        .m_axis_thr_tdata(threshold),.m_axis_thr_tuser(thr_bin),.m_axis_thr_tvalid(thr_valid),.m_axis_thr_tready(thr_ready),.m_axis_thr_tlast(thr_last),
        .m_axis_hit_tready(1'b1),.m_axis_tgt_tready(1'b1),.irq_list_ready(cfar_irq),
        .s_axi_awaddr(14'b0),.s_axi_awvalid(1'b0),.s_axi_wdata(32'b0),.s_axi_wstrb(4'b0),.s_axi_wvalid(1'b0),
        .s_axi_bready(1'b1),.s_axi_araddr(14'b0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1));
    spec_display_reduce reduce_thr(.aclk(clk),.aresetn(resetn),.frame_decim(16'd1),
        .s_axis_tdata(threshold),.s_axis_tvalid(thr_valid),.s_axis_tready(thr_ready),.s_axis_tlast(thr_last),
        .m_axis_tdata(reduced_thr),.m_axis_tuser(thr_col),.m_axis_tvalid(rtv),.m_axis_tlast(rtl),.m_axis_tready(1'b1),.framing_error(reduce_error));
    lcd_snapshot snap(.dsp_clk(clk),.dsp_aresetn(resetn),.s_spec_tdata(db_data),.s_spec_tuser(db_pixel),.s_spec_tvalid(db_valid),.s_spec_tlast(db_last),
        .s_thr_tdata(reduced_thr),.s_thr_tuser(thr_col),.s_thr_tvalid(rtv),.s_thr_tlast(rtl),.dropped_frames(dropped),.dropped_gray(drop_gray),.error_sticky(snapshot_error),
        .lcd_clk(lc),.lcd_aresetn(resetn),.frame_available(snapshot_ready),.accept_frame(accept_frame),.frame_id(snapshot_id),
        .read_column(read_column),.spec_data(read_spec),.threshold_data(read_thr));
    task automatic write_bus(input [7:0] addr,input [31:0] value);
        @(negedge clk);awaddr=addr;wdata=value;awvalid=1;wvalid=1;
        do @(posedge clk);while(!(awready && wready));
        @(negedge clk);awvalid=0;wvalid=0;bready=1;
        do @(posedge clk);while(!bvalid);
        if(bresp!=0) $fatal(1,"AXI write failed");
        @(negedge clk);bready=0;
    endtask

    always @(posedge clk) if(resetn) begin
        cycle=cycle+1;
        if(input_valid && input_ready && input_last) begin input_cycle[input_frames]=cycle;input_frames=input_frames+1;end
        if(cfar_irq) begin output_cycle[output_frames]=cycle;output_frames=output_frames+1;end
        if(pwr_valid && pwr_ready) begin
            if((n<8192 && pwr_data!==expected[n]) || pwr_bin!==(n%2048) || pwr_last!==(n%2048==2047)) $fatal(1,"chain power/frame mismatch at %d",n);
            n=n+1;
        end
        if(rtv) begin if(tn<560) expected_thr[tn]=reduced_thr;tn=tn+1;end
    end
    initial begin
        $readmemh("in_axis32.hex",stimulus);$readmemh("exp_welch.hex",expected);$readmemh("n2_display_expected.hex",expected_pixel);
        repeat(12) @(negedge clk);resetn=1;
        // CFAR AXI transport is covered independently; this test holds its default numeric configuration enabled.
        force cfar.registers.reg_ctrl=1;
        write_bus(4,3);write_bus(8,1);write_bus(0,1);
        for(sent=0;sent<32768;sent=sent+1) begin
            @(negedge clk);input_data=stimulus[sent%8192];input_valid=1;input_last=sent%2048==2047;
            do @(posedge clk);while(!input_ready);
        end
        @(negedge clk);input_valid=0;
        wait(cfar.frames==16 && tn==8960);repeat(30) @(negedge lc);
        if(!snapshot_ready || n!=32768 || error_sticky || reduce_error || snapshot_error || cfar.detect_error) $fatal(1,"chain framing/clock error");
        @(negedge lc);accept_frame=1;@(negedge lc);accept_frame=0;
        if(snapshot_id!==0) $fatal(1,"first frame id");
        for(i=0;i<560;i=i+1) begin
            read_column=i;repeat(2) @(negedge lc);
            if(read_spec!==expected_pixel[i] || read_thr!==expected_thr[i]) $fatal(1,"mixed snapshot column%d",i);
        end
        $display("CHAIN_STEADY input_cycles=%0d output_cycles=%0d frames=7 dsp_hz=150000000",input_cycle[15]-input_cycle[8],output_cycle[15]-output_cycle[8]);
        $display("TB_RESULT: PASS integrated FFT/Welch->CFAR->LCD pairing,first8192 exact power words,16frames stress,8960 threshold pixels,frame0 coherent560-point snapshot");$finish;
    end
    initial begin #10000000;$fatal(1,"chain timeout n%d tn%d",n,tn);end
endmodule
