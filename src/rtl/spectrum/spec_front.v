module spec_front (
    input wire aclk,input wire aresetn,
    input wire [31:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,input wire s_axis_tlast,
    output wire [31:0] m_axis_pwr_tdata,output wire [10:0] m_axis_pwr_tuser,
    output wire m_axis_pwr_tvalid,input wire m_axis_pwr_tready,output wire m_axis_pwr_tlast,
    output wire [15:0] m_axis_db_tdata,output wire [9:0] m_axis_db_tuser,
    output wire m_axis_db_tvalid,input wire m_axis_db_tready,output wire m_axis_db_tlast,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,input wire s_axi_rready,output wire [1:0] s_axi_rresp,
    output wire [47:0] dbg_fft_tdata,output wire dbg_fft_valid,
    output wire [31:0] dbg_power_shifted,output wire dbg_power_valid,
    output wire [15:0] dbg_db_full,output wire dbg_db_valid,
    output reg [31:0] frame_count,output reg error_sticky
);
    wire [31:0] ctrl,avg_shift,disp_decim;
    spec_ctrl_regs regs(.aclk(aclk),.aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_ctrl(ctrl),.reg_avg_shift(avg_shift),.reg_disp_decim(disp_decim),.ro_frame_cnt(frame_count));
    wire [31:0] win_data,fft_data,power_data,shift_data,avg_data;
    wire win_valid,win_ready,win_last,fft_valid,fft_ready,fft_last;
    wire power_valid,power_ready,power_last,shift_valid,shift_ready,shift_last,avg_valid,avg_ready,avg_last;
    wire [7:0] fft_user,status_data;
    wire status_valid,overflow,unexpected,missing;
    wire window_error,shift_error,welch_error,display_error;
    reg config_done;
    wire config_ready;
    reg [10:0] input_index,average_index;
    wire input_enabled=config_done && (ctrl[0] || input_index!=0);
    wire win_input_ready;
    assign s_axis_tready=win_input_ready && input_enabled;
    spec_window windowing(.aclk(aclk),.aresetn(aresetn),.win_sel(ctrl[2:1]),
        .s_axis_tdata(s_axis_tdata),.s_axis_tvalid(s_axis_tvalid && input_enabled),.s_axis_tready(win_input_ready),.s_axis_tlast(s_axis_tlast),
        .m_axis_tdata(win_data),.m_axis_tvalid(win_valid),.m_axis_tready(win_ready),.m_axis_tlast(win_last),.framing_error(window_error));
    spec_fft_2048 fft(.aclk(aclk),.aresetn(aresetn),
        .s_axis_config_tdata(16'h0d55),.s_axis_config_tvalid(!config_done),.s_axis_config_tready(config_ready),
        .s_axis_data_tdata(win_data),.s_axis_data_tvalid(win_valid),.s_axis_data_tready(win_ready),.s_axis_data_tlast(win_last),
        .m_axis_data_tdata(fft_data),.m_axis_data_tuser(fft_user),.m_axis_data_tvalid(fft_valid),.m_axis_data_tready(fft_ready),.m_axis_data_tlast(fft_last),
        .m_axis_status_tdata(status_data),.m_axis_status_tvalid(status_valid),.m_axis_status_tready(1'b1),
        .event_fft_overflow(overflow),.event_tlast_unexpected(unexpected),.event_tlast_missing(missing));
    assign dbg_fft_tdata={fft_data[31:16],8'b0,fft_data[15:0],8'b0};
    assign dbg_fft_valid=fft_valid && fft_ready;
    spec_power power_calc(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(fft_data),.s_axis_tvalid(fft_valid),.s_axis_tready(fft_ready),.s_axis_tlast(fft_last),
        .m_axis_tdata(power_data),.m_axis_tvalid(power_valid),.m_axis_tready(power_ready),.m_axis_tlast(power_last));
    spec_fftshift reorder(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(power_data),.s_axis_tvalid(power_valid),.s_axis_tready(power_ready),.s_axis_tlast(power_last),
        .m_axis_tdata(shift_data),.m_axis_tvalid(shift_valid),.m_axis_tready(shift_ready),.m_axis_tlast(shift_last),.framing_error(shift_error));
    assign dbg_power_shifted=shift_data;assign dbg_power_valid=shift_valid && shift_ready;
    spec_welch welch(.aclk(aclk),.aresetn(aresetn),.avg_shift(avg_shift[4:0]),
        .s_axis_tdata(shift_data),.s_axis_tvalid(shift_valid),.s_axis_tready(shift_ready),.s_axis_tlast(shift_last),
        .m_axis_tdata(avg_data),.m_axis_tvalid(avg_valid),.m_axis_tready(avg_ready),.m_axis_tlast(avg_last),.framing_error(welch_error));
    wire [43:0] pwr_payload,db_payload;
    wire db_input_valid,db_input_ready;
    axis_fork2 #(.WIDTH(44)) outputs_fork(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata({average_index,avg_last,avg_data}),.s_axis_tvalid(avg_valid),.s_axis_tready(avg_ready),
        .m0_axis_tdata(pwr_payload),.m0_axis_tvalid(m_axis_pwr_tvalid),.m0_axis_tready(m_axis_pwr_tready),
        .m1_axis_tdata(db_payload),.m1_axis_tvalid(db_input_valid),.m1_axis_tready(db_input_ready));
    assign m_axis_pwr_tdata=pwr_payload[31:0];assign m_axis_pwr_tlast=pwr_payload[32];assign m_axis_pwr_tuser=pwr_payload[43:33];
    wire [15:0] db_full;
    wire db_full_valid,db_full_ready,db_full_last;
    spec_db logarithm(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(db_payload[31:0]),.s_axis_tvalid(db_input_valid),.s_axis_tready(db_input_ready),.s_axis_tlast(db_payload[32]),
        .m_axis_tdata(db_full),.m_axis_tvalid(db_full_valid),.m_axis_tready(db_full_ready),.m_axis_tlast(db_full_last));
    assign dbg_db_full=db_full;assign dbg_db_valid=db_full_valid && db_full_ready;
    spec_display_reduce display_reduce(.aclk(aclk),.aresetn(aresetn),.frame_decim(disp_decim[15:0]),
        .s_axis_tdata(db_full),.s_axis_tvalid(db_full_valid),.s_axis_tready(db_full_ready),.s_axis_tlast(db_full_last),
        .m_axis_tdata(m_axis_db_tdata),.m_axis_tuser(m_axis_db_tuser),.m_axis_tvalid(m_axis_db_tvalid),.m_axis_tready(m_axis_db_tready),
        .m_axis_tlast(m_axis_db_tlast),.framing_error(display_error));
    always @(posedge aclk) begin
        if(!aresetn) begin config_done<=0;input_index<=0;average_index<=0;frame_count<=0;error_sticky<=0;end
        else begin
            if(config_ready) config_done<=1;
            if(s_axis_tvalid && s_axis_tready) input_index<=input_index+1'b1;
            if(avg_valid && avg_ready) average_index<=average_index+1'b1;
            if(m_axis_pwr_tvalid && m_axis_pwr_tready && m_axis_pwr_tlast) frame_count<=frame_count+1'b1;
            if(window_error || shift_error || welch_error || display_error || overflow || unexpected || missing ||
               (status_valid && status_data[0])) error_sticky<=1;
        end
    end
endmodule
