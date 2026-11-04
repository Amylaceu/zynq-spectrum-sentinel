// Optional wiring-only top for standalone synthesis/implementation. The BD may
// instantiate pfb_os2 and nco_capture separately with the same port contract.
module x5_channel_capture (
    input wire aclk,input wire aresetn,
    input wire [31:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
    input wire arm_toggle,input wire clear_errors,
    input wire [3:0] cfg_ch_sel,input wire [31:0] cfg_fcw,
    input wire [3:0] cfg_dec,input wire [12:0] cfg_len,
    input wire [31:0] cfg_src,input wire [63:0] timestamp,
    output wire busy,output wire done_toggle,output wire [3:0] error_sticky,
    output wire [12:0] captured_count,output wire pfb_error,
    output wire [31:0] m_axis_tdata,output wire [3:0] m_axis_tkeep,
    output wire m_axis_tvalid,input wire m_axis_tready,output wire m_axis_tlast
);
    wire [31:0] data;wire [3:0] channel;
    wire valid,ready,last;
    pfb_os2 pfb(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(s_axis_tdata),.s_axis_tvalid(s_axis_tvalid),.s_axis_tready(s_axis_tready),
        .m_axis_tdata(data),.m_axis_tuser(channel),.m_axis_tvalid(valid),.m_axis_tready(ready),
        .m_axis_tlast(last),.error_sticky(pfb_error));
    nco_capture capture(.aclk(aclk),.aresetn(aresetn),.arm_toggle(arm_toggle),.clear_errors(clear_errors),
        .cfg_ch_sel(cfg_ch_sel),.cfg_fcw(cfg_fcw),.cfg_dec(cfg_dec),.cfg_len(cfg_len),
        .cfg_src(cfg_src),.timestamp(timestamp),.busy(busy),.done_toggle(done_toggle),
        .error_sticky(error_sticky),.captured_count(captured_count),
        .s_axis_tdata(data),.s_axis_tuser(channel),.s_axis_tvalid(valid),.s_axis_tready(ready),.s_axis_tlast(last),
        .m_axis_tdata(m_axis_tdata),.m_axis_tkeep(m_axis_tkeep),.m_axis_tvalid(m_axis_tvalid),
        .m_axis_tready(m_axis_tready),.m_axis_tlast(m_axis_tlast));
endmodule
