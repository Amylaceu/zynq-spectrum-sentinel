module adc_tap_v2 #(parameter FIFO_DEPTH=4096,parameter FIFO_COUNT_WIDTH=13) (
    input wire adc_clk,input wire adc_reset,
    input wire [15:0] adc_i,input wire [15:0] adc_q,
    input wire adc_valid_i,input wire adc_valid_q,
    input wire dsp_clk,input wire dsp_aresetn,
    output wire [31:0] m_axis_tdata,output wire m_axis_tvalid,
    input wire m_axis_tready,output wire m_axis_tlast,
    output wire overflow_sticky,output wire mismatch_sticky,
    output wire [FIFO_COUNT_WIDTH-1:0] fifo_level
);
    // AXI ADC control0x51: signed12 right-aligned, sign-extended to16.
    // Shift exactly once here into the project's signed16 Q1.15 transport.
    wire [31:0] normalized={adc_q[11:0],4'b0,adc_i[11:0],4'b0};
    // Assert reset in both domains when either producer or consumer resets.
    // XPM provides domain-local synchronous release. Never bypass it with
    // reset_request at an ordinary D pin: that recreates an unsafe DSP->ADC
    // crossing. The FIFO reset synchronizer initializes asserted through GSR
    // and samples only the ADC-domain reset; both FIFO reset edges use wr_clk.
    wire reset_request=adc_reset || !dsp_aresetn;
    wire adc_domain_reset,dsp_domain_reset;
    xpm_cdc_async_rst #(.DEST_SYNC_FF(3),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) adc_reset_cdc (
        .src_arst(reset_request),.dest_clk(adc_clk),.dest_arst(adc_domain_reset));
    xpm_cdc_async_rst #(.DEST_SYNC_FF(3),.INIT_SYNC_FF(1),.RST_ACTIVE_HIGH(1)) dsp_reset_cdc (
        .src_arst(reset_request),.dest_clk(dsp_clk),.dest_arst(dsp_domain_reset));
    wire fifo_reset;
    xpm_cdc_sync_rst #(.DEST_SYNC_FF(3),.INIT(1),.INIT_SYNC_FF(1),
        .SIM_ASSERT_CHK(1)) fifo_reset_cdc (
        .src_rst(adc_domain_reset),.dest_clk(adc_clk),.dest_rst(fifo_reset));
    wire full,empty,wr_busy,rd_busy;
    wire input_valid=adc_valid_i && adc_valid_q;
    wire fifo_write=input_valid && !full && !wr_busy && !adc_domain_reset && !fifo_reset;
    reg overflow_adc,mismatch_adc;
    (* ASYNC_REG="TRUE" *) reg [1:0] overflow_sync,mismatch_sync;
    reg [10:0] output_index;
    assign overflow_sticky=overflow_sync[1];assign mismatch_sticky=mismatch_sync[1];
    assign m_axis_tvalid=!empty && !rd_busy && !dsp_domain_reset;
    assign m_axis_tlast=output_index==2047;
    xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.ECC_MODE("no_ecc"),.RELATED_CLOCKS(0),
        .FIFO_WRITE_DEPTH(FIFO_DEPTH),.WRITE_DATA_WIDTH(32),.READ_DATA_WIDTH(32),
        .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(2),
        .WR_DATA_COUNT_WIDTH(FIFO_COUNT_WIDTH),.RD_DATA_COUNT_WIDTH(FIFO_COUNT_WIDTH),.USE_ADV_FEATURES("0404"),
        .SIM_ASSERT_CHK(1)) fifo (
        .rst(fifo_reset),.wr_clk(adc_clk),.rd_clk(dsp_clk),.din(normalized),.wr_en(fifo_write),
        .rd_en(m_axis_tvalid && m_axis_tready),.dout(m_axis_tdata),.full(full),.empty(empty),
        .wr_rst_busy(wr_busy),.rd_rst_busy(rd_busy),.rd_data_count(fifo_level),
        .sleep(1'b0),.injectsbiterr(1'b0),.injectdbiterr(1'b0));
    always @(posedge adc_clk) begin
        if(fifo_reset) begin overflow_adc<=0;mismatch_adc<=0;end
        else begin
            if(input_valid && full && !wr_busy) overflow_adc<=1;
            if(adc_valid_i!=adc_valid_q) mismatch_adc<=1;
        end
    end
    always @(posedge dsp_clk) begin
        if(dsp_domain_reset) begin output_index<=0;overflow_sync<=0;mismatch_sync<=0;end
        else begin
            overflow_sync<={overflow_sync[0],overflow_adc};mismatch_sync<={mismatch_sync[0],mismatch_adc};
            if(m_axis_tvalid && m_axis_tready) output_index<=output_index+1'b1;
        end
    end
endmodule
