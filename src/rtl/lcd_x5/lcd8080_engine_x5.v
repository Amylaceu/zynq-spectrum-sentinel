module lcd8080_engine_x5 #(
    parameter RESET_CYCLES=1000000,parameter STARTUP_CYCLES=5000000,parameter DELAY_SHIFT=0
)(
    input wire aclk,input wire aresetn,input wire dsp_clk,input wire dsp_aresetn,
    input wire [15:0] s_axis_spec_tdata,input wire [9:0] s_axis_spec_tuser,
    input wire s_axis_spec_tvalid,input wire s_axis_spec_tlast,output wire s_axis_spec_tready,
    input wire [15:0] s_axis_thr_tdata,input wire [10:0] s_axis_thr_tuser,
    input wire s_axis_thr_tvalid,input wire s_axis_thr_tlast,output wire s_axis_thr_tready,
    output wire [31:0] ui_addr,input wire [31:0] ui_data,
    output wire [15:0] lcd_data,output wire lcd_cs_n,lcd_rs,lcd_wr_n,lcd_rd_n,lcd_reset_n,
    output wire irq_frame_done,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,input wire s_axi_rready,output wire [1:0] s_axi_rresp
);
    wire [31:0] ctrl,phase,ui_epoch,ui_applied,frame_count,frame_id,drop_count,drop_gray;
    wire [31:0] status,drop_binary;
    wire initialized,render_busy,snapshot_error,reduce_error,region_error;
    (* ASYNC_REG="TRUE" *) reg [1:0] snapshot_error_sync,reduce_error_sync;
    (* ASYNC_REG="TRUE" *) reg [31:0] drop_meta,drop_sync;
    wire [15:0] reduced_thr;
    wire [9:0] reduced_thr_col,read_column;
    wire reduced_thr_valid,reduced_thr_last,frame_available,accept_frame;
    wire [15:0] spec_db,thr_db;
    wire [1:0] op_kind;
    wire [15:0] p0,p1,p2,p3,fill,pixel;
    wire op_valid,op_ready,op_done,pixel_valid,pixel_ready,pixel_last;
    wire [16:0] cmd_data;
    wire cmd_valid,cmd_ready;
    wire [31:0] frame_gray;
    reg [31:0] previous_frames;
    assign irq_frame_done=frame_count!=previous_frames;
    assign s_axis_spec_tready=1;
    assign status={27'b0,region_error,reduce_error_sync[1],snapshot_error_sync[1],render_busy,initialized};
    genvar bit_index;
    generate for(bit_index=0;bit_index<32;bit_index=bit_index+1) begin:decode_gray
        assign drop_binary[bit_index]=^drop_sync[31:bit_index];
    end endgenerate
    always @(posedge aclk) begin
        if(!aresetn) begin drop_meta<=0;drop_sync<=0;snapshot_error_sync<=0;reduce_error_sync<=0;previous_frames<=0;end
        else begin
            drop_meta<=drop_gray;drop_sync<=drop_meta;
            snapshot_error_sync<={snapshot_error_sync[0],snapshot_error};
            reduce_error_sync<={reduce_error_sync[0],reduce_error};previous_frames<=frame_count;
        end
    end
    lcd_ctrl_regs_x5 registers(.aclk(aclk),.aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_ctrl(ctrl),.reg_bus_phase(phase),.reg_ui_epoch(ui_epoch),
        .ro_frame_count(frame_count),.ro_ui_applied(ui_applied),.ro_status(status),.ro_dropped(drop_binary),.ro_frame_id(frame_id));
    spec_display_reduce thr_reduce(.aclk(dsp_clk),.aresetn(dsp_aresetn),.frame_decim(16'd1),
        .s_axis_tdata(s_axis_thr_tdata),.s_axis_tvalid(s_axis_thr_tvalid),.s_axis_tready(s_axis_thr_tready),.s_axis_tlast(s_axis_thr_tlast),
        .m_axis_tdata(reduced_thr),.m_axis_tuser(reduced_thr_col),.m_axis_tvalid(reduced_thr_valid),.m_axis_tready(1'b1),
        .m_axis_tlast(reduced_thr_last),.framing_error(reduce_error));
    lcd_snapshot snapshots(.dsp_clk(dsp_clk),.dsp_aresetn(dsp_aresetn),
        .s_spec_tdata(s_axis_spec_tdata),.s_spec_tuser(s_axis_spec_tuser),.s_spec_tvalid(s_axis_spec_tvalid),.s_spec_tlast(s_axis_spec_tlast),
        .s_thr_tdata(reduced_thr),.s_thr_tuser(reduced_thr_col),.s_thr_tvalid(reduced_thr_valid),.s_thr_tlast(reduced_thr_last),
        .dropped_frames(drop_count),.dropped_gray(drop_gray),.error_sticky(snapshot_error),
        .lcd_clk(aclk),.lcd_aresetn(aresetn),.frame_available(frame_available),.accept_frame(accept_frame),
        .frame_id(frame_id),.read_column(read_column),.spec_data(spec_db),.threshold_data(thr_db));
    lcd_render_scheduler_x5 scheduler(.sys_clk(aclk),.aresetn(aresetn),.initialized(initialized),.enable(ctrl[0]),
        .frame_available(frame_available),.accept_frame(accept_frame),.read_column(read_column),.spec_db(spec_db),.threshold_db(thr_db),
        .ui_epoch(ui_epoch),.ui_applied_epoch(ui_applied),.ui_address(ui_addr),.ui_word(ui_data),
        .op_kind(op_kind),.op_p0(p0),.op_p1(p1),.op_p2(p2),.op_p3(p3),.fill_color(fill),.op_valid(op_valid),.op_ready(op_ready),.op_done(op_done),
        .pixel_data(pixel),.pixel_valid(pixel_valid),.pixel_ready(pixel_ready),.pixel_last(pixel_last),
        .frame_count(frame_count),.frame_gray(frame_gray),.busy(render_busy));
    lcd8080_region regions(.sys_clk(aclk),.aresetn(aresetn),.op_kind(op_kind),.op_p0(p0),.op_p1(p1),.op_p2(p2),.op_p3(p3),
        .fill_color(fill),.op_valid(op_valid),.op_ready(op_ready),.s_axis_pixel_tdata(pixel),.s_axis_pixel_tvalid(pixel_valid),
        .s_axis_pixel_tready(pixel_ready),.s_axis_pixel_tlast(pixel_last),.m_axis_cmd_tdata(cmd_data),.m_axis_cmd_tvalid(cmd_valid),
        .m_axis_cmd_tready(cmd_ready),.done(op_done),.error_sticky(region_error));
    lcd8080_bus #(.RESET_CYCLES(RESET_CYCLES),.STARTUP_CYCLES(STARTUP_CYCLES),.DELAY_SHIFT(DELAY_SHIFT))
        bus(.sys_clk(aclk),.aresetn(aresetn),.bus_phase_cycles(phase[7:0]),
        .s_axis_tdata(cmd_data),.s_axis_tvalid(cmd_valid),.s_axis_tready(cmd_ready),.initialized(initialized),
        .lcd_data(lcd_data),.lcd_cs_n(lcd_cs_n),.lcd_rs(lcd_rs),.lcd_wr_n(lcd_wr_n),.lcd_rd_n(lcd_rd_n),.lcd_reset_n(lcd_reset_n));
endmodule
