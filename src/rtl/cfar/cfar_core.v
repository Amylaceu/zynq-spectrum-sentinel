module cfar_core (
    input wire aclk,input wire aresetn,
    input wire [31:0] s_axis_pwr_tdata,input wire s_axis_pwr_tvalid,
    output wire s_axis_pwr_tready,input wire s_axis_pwr_tlast,
    output wire [15:0] m_axis_thr_tdata,output wire [10:0] m_axis_thr_tuser,
    output wire m_axis_thr_tlast,output wire m_axis_thr_tvalid,input wire m_axis_thr_tready,
    output wire [7:0] m_axis_hit_tdata,output wire [10:0] m_axis_hit_tuser,
    output wire m_axis_hit_tlast,output wire m_axis_hit_tvalid,input wire m_axis_hit_tready,
    output wire [127:0] m_axis_tgt_tdata,output wire m_axis_tgt_tlast,
    output wire m_axis_tgt_tvalid,input wire m_axis_tgt_tready,
    output wire irq_list_ready,
    output wire [31:0] dbg_threshold,output wire [31:0] dbg_power,
    output wire [13:0] unused_debug,
    input wire [13:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [13:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,
    input wire s_axi_rready,output wire [1:0] s_axi_rresp
);
    wire [31:0] ctrl,n_shift,guard_bins,alpha,dc_mask,gap,alarm_limit,clear_token;
    wire [31:0] frames,occ_frames;
    wire [5:0] targets;
    wire [11:0] hits;
    wire alarm,overflow,detect_error,detect_idle,cluster_busy,cluster_ready,occ_clearing;
    wire [6:0] list_addr;
    wire [10:0] occ_index;
    wire [31:0] list_data;
    wire [15:0] occ_data;
    reg [31:0] clear_seen;
    reg [7:0] frame_gap;
    reg [11:0] frame_alarm_limit;
    wire clear_request=clear_token!=clear_seen && detect_idle && !cluster_busy;
    wire [92:0] detected,hit_payload,thr_payload;
    wire detected_valid,detected_ready,broadcast_ready;
    wire accept=detected_valid && detected_ready;
    wire valid_config=(n_shift<=6 && guard_bins<=31 && alpha<=65535 && dc_mask<=255 && gap<=255 && alarm_limit<=4095 && ctrl[2:1]<3);
    wire enable=ctrl[0] && valid_config && !occ_clearing && !clear_request && !cluster_busy;
    assign unused_debug={12'b0,detect_idle,cluster_busy};
    cfar_ctrl_regs registers(.aclk(aclk),.aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_ctrl(ctrl),.reg_n_shift(n_shift),.reg_guard(guard_bins),.reg_alpha(alpha),.reg_dc_mask(dc_mask),.reg_gap(gap),
        .reg_alarm_limit(alarm_limit),.reg_occ_clear_token(clear_token),
        .target_count({26'b0,targets}),.frame_count(frames),.hit_count({20'b0,hits}),.alarm({31'b0,alarm}),
        .occ_frames(occ_frames),.status({27'b0,overflow,!valid_config,detect_error,occ_clearing,!detect_idle || cluster_busy}),
        .target_word_addr(list_addr),.target_data(list_data),.occ_index(occ_index),.occ_data(occ_data));
    cfar_detect detector(.aclk(aclk),.aresetn(aresetn),.enable(enable),
        .cfg_mode(ctrl[2:1]),.cfg_nshift(n_shift[2:0]),.cfg_guard(guard_bins[4:0]),.cfg_alpha(alpha[15:0]),.cfg_dc_mask(dc_mask[7:0]),
        .s_axis_tdata(s_axis_pwr_tdata),.s_axis_tvalid(s_axis_pwr_tvalid),.s_axis_tready(s_axis_pwr_tready),.s_axis_tlast(s_axis_pwr_tlast),
        .m_axis_tdata(detected),.m_axis_tvalid(detected_valid),.m_axis_tready(detected_ready),.error_sticky(detect_error),.idle(detect_idle));
    assign detected_ready=broadcast_ready && cluster_ready;
    axis_broadcast2 #(.WIDTH(93)) outputs(.aclk(aclk),.aresetn(aresetn),.s_axis_tdata(detected),
        .s_axis_tvalid(detected_valid && cluster_ready),.s_axis_tready(broadcast_ready),
        .m0_axis_tdata(hit_payload),.m0_axis_tvalid(m_axis_hit_tvalid),.m0_axis_tready(m_axis_hit_tready),
        .m1_axis_tdata(thr_payload),.m1_axis_tvalid(m_axis_thr_tvalid),.m1_axis_tready(m_axis_thr_tready));
    assign m_axis_hit_tdata={7'b0,hit_payload[0]};assign m_axis_hit_tuser=hit_payload[91:81];assign m_axis_hit_tlast=hit_payload[92];
    assign dbg_threshold=hit_payload[64:33];assign dbg_power=hit_payload[32:1];
    assign m_axis_thr_tdata=thr_payload[80:65];assign m_axis_thr_tuser=thr_payload[91:81];assign m_axis_thr_tlast=thr_payload[92];
    cfar_cluster clusters(.aclk(aclk),.aresetn(aresetn),.cfg_gap(frame_gap),.alarm_limit(frame_alarm_limit),
        .power(detected[32:1]),.hit(detected[0]),.bin_index(detected[91:81]),.last(detected[92]),.valid(accept),.ready(cluster_ready),
        .busy(cluster_busy),.irq_list_ready(irq_list_ready),.target_count(targets),.frame_count(frames),.frame_hits(hits),.alarm(alarm),.overflow(overflow),
        .mmio_word_addr(list_addr),.mmio_data(list_data),.m_axis_tdata(m_axis_tgt_tdata),.m_axis_tvalid(m_axis_tgt_tvalid),
        .m_axis_tready(m_axis_tgt_tready),.m_axis_tlast(m_axis_tgt_tlast));
    cfar_occupancy occupancy(.aclk(aclk),.aresetn(aresetn),.clear_request(clear_request),
        .bin_index(detected[91:81]),.hit(detected[0]),.valid(accept),.last(detected[92]),
        .mmio_index(occ_index),.mmio_data(occ_data),.clearing(occ_clearing),.frame_count(occ_frames));
    always @(posedge aclk) begin
        if(!aresetn) begin clear_seen<=0;frame_gap<=2;frame_alarm_limit<=1;end
        else begin
            if(clear_request) clear_seen<=clear_token;
            if(detect_idle && s_axis_pwr_tvalid && s_axis_pwr_tready) begin frame_gap<=gap[7:0];frame_alarm_limit<=alarm_limit[11:0];end
        end
    end
endmodule
