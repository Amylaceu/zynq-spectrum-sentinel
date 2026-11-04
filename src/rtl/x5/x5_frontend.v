// Independent lossless source fork. Each branch acknowledges a word exactly
// once; simply ANDing READY and fanning out VALID would duplicate samples.
module x5_frontend (
    input wire aclk,input wire aresetn,
    input wire [31:0] control,fcw,source_id,
    output wire [31:0] status,
    input wire [31:0] s_axis_tdata,input wire s_axis_tvalid,input wire s_axis_tlast,
    output wire s_axis_tready,
    output wire [31:0] m_axis_spec_tdata,output wire m_axis_spec_tvalid,
    output wire m_axis_spec_tlast,input wire m_axis_spec_tready,
    output wire [31:0] m_axis_capture_tdata,output wire [3:0] m_axis_capture_tkeep,
    output wire m_axis_capture_tvalid,output wire m_axis_capture_tlast,
    input wire m_axis_capture_tready
);
    reg [31:0] data;
    reg last;
    reg [1:0] pending;
    reg [63:0] cycles;
    wire pfb_ready;
    wire local_resetn=aresetn && !control[2];
    wire [1:0] consumed={pfb_ready,m_axis_spec_tready};
    assign s_axis_tready=local_resetn && !(|(pending & ~consumed));
    assign m_axis_spec_tdata=data;
    assign m_axis_spec_tvalid=local_resetn && pending[0];
    assign m_axis_spec_tlast=last;
    always @(posedge aclk) begin
        if(!aresetn) cycles<=0;else cycles<=cycles+1;
        if(!local_resetn) begin data<=0;last<=0;pending<=0;end
        else if(s_axis_tvalid && s_axis_tready) begin
            data<=s_axis_tdata;last<=s_axis_tlast;pending<=2'b11;
        end else pending<=pending & ~consumed;
    end
    wire capture_busy,done_toggle,pfb_error;
    wire [3:0] capture_error;
    wire [12:0] captured_count;
    assign status={3'b0,captured_count,7'b0,pfb_error,capture_error,2'b0,done_toggle,capture_busy};
    x5_channel_capture channelizer(.aclk(aclk),.aresetn(local_resetn),
        .s_axis_tdata(data),.s_axis_tvalid(local_resetn && pending[1]),.s_axis_tready(pfb_ready),
        .arm_toggle(control[0]),.clear_errors(control[1]),.cfg_ch_sel(control[7:4]),
        .cfg_fcw(fcw),.cfg_dec(control[11:8]),.cfg_len(control[28:16]),
        .cfg_src(source_id),.timestamp(cycles),.busy(capture_busy),.done_toggle(done_toggle),
        .error_sticky(capture_error),.captured_count(captured_count),.pfb_error(pfb_error),
        .m_axis_tdata(m_axis_capture_tdata),.m_axis_tkeep(m_axis_capture_tkeep),
        .m_axis_tvalid(m_axis_capture_tvalid),.m_axis_tready(m_axis_capture_tready),
        .m_axis_tlast(m_axis_capture_tlast));
endmodule
