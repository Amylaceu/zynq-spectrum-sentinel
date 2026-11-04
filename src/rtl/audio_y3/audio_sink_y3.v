// Continuous selected-channel tap. Never backpressures the spectrum/PFB chain.
// Configure channel/fcw with enable=0. Any lost IQ/PCM is sticky and invalidates
// continuous-playback acceptance. Top-level FIFO/prefill parameters determine
// drift headroom; independent-clock drift must also be measured on board.
module audio_sink_y3 #(
    parameter integer PCM_DEPTH=2048,
    parameter integer PCM_COUNT_WIDTH=12,
    parameter integer PREFILL=512
) (
    input wire aclk, input wire aresetn,
    input wire mclk, input wire mresetn,
    input wire enable, input wire tone_mode, input wire [3:0] channel, input wire [31:0] fcw,
    input wire [31:0] iq_data, input wire [3:0] iq_channel,
    input wire iq_transfer,
    output wire bclk, output wire lrck, output wire dacdat,
    output wire [31:0] status,
    output wire [31:0] frames,
    output wire [31:0] underflows,
    output wire [31:0] pcm_samples
);
    wire run=aresetn && enable;
    wire iq_full,iq_empty,iq_wbusy,iq_rbusy;
    wire [31:0] phase_input;
    wire phase_ready,phase_valid,phase_output_ready;
    wire [23:0] phase_data;
    wire [31:0] zero_samples;
    wire iq_selected=run && !tone_mode && iq_transfer && iq_channel==channel;
    wire iq_write=iq_selected && !iq_full && !iq_wbusy;
    wire iq_read=!iq_empty && !iq_rbusy && phase_ready && run;
    reg iq_overflow;
    xpm_fifo_sync #(.FIFO_MEMORY_TYPE("distributed"),.ECC_MODE("no_ecc"),
        .FIFO_WRITE_DEPTH(32),.WRITE_DATA_WIDTH(32),.READ_DATA_WIDTH(32),
        .READ_MODE("fwft"),.FIFO_READ_LATENCY(0),.WR_DATA_COUNT_WIDTH(6),
        .RD_DATA_COUNT_WIDTH(6),.USE_ADV_FEATURES("0000"),.SIM_ASSERT_CHK(1)) iq_fifo (
        .rst(!run),.wr_clk(aclk),.din(iq_data),.wr_en(iq_write),
        .rd_en(iq_read),.dout(phase_input),.full(iq_full),.empty(iq_empty),
        .wr_rst_busy(iq_wbusy),.rd_rst_busy(iq_rbusy),.sleep(1'b0),
        .injectsbiterr(1'b0),.injectdbiterr(1'b0));
    always @(posedge aclk) begin
        if(!run) iq_overflow<=0;
        else if(iq_selected && (iq_full || iq_wbusy)) iq_overflow<=1;
    end
    fm_phase_y3 phase_core(.aclk(aclk),.aresetn(run),.cfg_fcw(fcw),
        .s_axis_tdata(phase_input),.s_axis_tvalid(!iq_empty && !iq_rbusy && run),
        .s_axis_tready(phase_ready),.m_axis_tdata(phase_data),
        .m_axis_tvalid(phase_valid),.m_axis_tready(phase_output_ready),
        .zero_samples(zero_samples));
    wire [31:0] pcm_data,filtered_inputs;
    wire pcm_valid,pcm_ready;
    fm_audio_filter_y3 filter_core(.aclk(aclk),.aresetn(run),
        .s_axis_tdata(phase_data),.s_axis_tvalid(phase_valid),
        .s_axis_tready(phase_output_ready),.m_axis_tdata(pcm_data),
        .m_axis_tvalid(pcm_valid),.m_axis_tready(pcm_ready),
        .samples_in(filtered_inputs),.samples_out(pcm_samples));

    wire pcm_full,pcm_empty,pcm_wbusy,pcm_rbusy;
    wire [31:0] playback_data;
    wire [PCM_COUNT_WIDTH-1:0] wr_count,rd_count;
    wire serializer_ready;
    assign pcm_ready=run && !pcm_wbusy && !pcm_full;
    wire tone_audio;
    xpm_fifo_async #(.FIFO_MEMORY_TYPE("block"),.ECC_MODE("no_ecc"),
        .RELATED_CLOCKS(0),.FIFO_WRITE_DEPTH(PCM_DEPTH),
        .WRITE_DATA_WIDTH(32),.READ_DATA_WIDTH(32),.READ_MODE("fwft"),
        .FIFO_READ_LATENCY(0),.CDC_SYNC_STAGES(3),
        .WR_DATA_COUNT_WIDTH(PCM_COUNT_WIDTH),.RD_DATA_COUNT_WIDTH(PCM_COUNT_WIDTH),
        .USE_ADV_FEATURES("0404"),.SIM_ASSERT_CHK(1)) pcm_fifo (
        .rst(!run),.wr_clk(aclk),.rd_clk(mclk),.din(pcm_data),
        .wr_en(pcm_valid && pcm_ready),
        .rd_en(serializer_ready && !tone_audio && !pcm_empty && !pcm_rbusy),
        .dout(playback_data),.full(pcm_full),.empty(pcm_empty),
        .wr_rst_busy(pcm_wbusy),.rd_rst_busy(pcm_rbusy),
        .wr_data_count(wr_count),.rd_data_count(rd_count),.sleep(1'b0),
        .injectsbiterr(1'b0),.injectdbiterr(1'b0));

    wire run_audio;
    xpm_cdc_single #(.DEST_SYNC_FF(3),.SRC_INPUT_REG(0),.SIM_ASSERT_CHK(1)) enable_cdc (
        .src_clk(aclk),.src_in(run),.dest_clk(mclk),.dest_out(run_audio));
    xpm_cdc_single #(.DEST_SYNC_FF(3),.SRC_INPUT_REG(0),.SIM_ASSERT_CHK(1)) tone_cdc (
        .src_clk(aclk),.src_in(tone_mode),.dest_clk(mclk),.dest_out(tone_audio));
    // PS-controlled self-test only: 48 samples/cycle at nominal48kHz = 1kHz.
    // Same I2S serializer and physical codec path as FM; no RF/DMA required.
    // Set tone_mode with enable=0 and leave it fixed until playback stops.
    (* rom_style="distributed" *) reg [23:0] tone_rom[0:47];
    initial $readmemh("y3_tone.hex",tone_rom);
    reg [5:0] tone_index;
    always @(posedge mclk) begin
        if(!mresetn || !run_audio || !tone_audio) tone_index<=0;
        else if(serializer_ready) tone_index<=tone_index==47 ? 0 : tone_index+1'b1;
    end
    reg playback;
    reg [7:0] frame_phase;
    always @(posedge mclk) begin
        if(!mresetn) begin playback<=0;frame_phase<=0;end
        else begin
            frame_phase<=frame_phase+1'b1;
            if(!run_audio || pcm_rbusy) playback<=0;
            else if(frame_phase==255 && (tone_audio || rd_count>=PREFILL)) playback<=1;
        end
    end
    wire [31:0] audio_frames,audio_underflows;
    i2s_tx_y3 serializer(.mclk(mclk),.aresetn(mresetn),.enable(playback && run_audio),
        .s_axis_tdata(tone_audio ? {8'b0,tone_rom[tone_index]} : playback_data),
        .s_axis_tvalid(tone_audio || (!pcm_empty && !pcm_rbusy)),
        .s_axis_tready(serializer_ready),.bclk(bclk),.lrck(lrck),.dacdat(dacdat),
        .frames(audio_frames),.underflows(audio_underflows));
    // Monotonic unit-increment counters, sampled as Gray codes by the XPM.
    // They reset only with the system/audio clock reset, not enable toggling.
    xpm_cdc_gray #(.WIDTH(32),.DEST_SYNC_FF(3),.REG_OUTPUT(1),.SIM_ASSERT_CHK(0)) frame_cdc (
        .src_clk(mclk),.src_in_bin(audio_frames),.dest_clk(aclk),.dest_out_bin(frames));
    xpm_cdc_gray #(.WIDTH(32),.DEST_SYNC_FF(3),.REG_OUTPUT(1),.SIM_ASSERT_CHK(0)) underflow_cdc (
        .src_clk(mclk),.src_in_bin(audio_underflows),.dest_clk(aclk),.dest_out_bin(underflows));
    wire playback_dsp;
    xpm_cdc_single #(.DEST_SYNC_FF(3),.SRC_INPUT_REG(0),.SIM_ASSERT_CHK(1)) playing_cdc (
        .src_clk(mclk),.src_in(playback),.dest_clk(aclk),.dest_out(playback_dsp));
    reg pcm_full_seen;
    always @(posedge aclk) begin
        if(!run) pcm_full_seen<=0;
        else if(pcm_valid && pcm_full && !pcm_wbusy) pcm_full_seen<=1;
    end
    wire [13:0] level=wr_count;
    assign status={14'b0,level,playback_dsp,pcm_full_seen,iq_overflow,run};
endmodule
