// Atomic token/ack snapshot. ADC counter has already crossed via registered
// Gray coding; all inputs here are synchronous to the 150 MHz DSP clock.
module stream_stats_x2 (
    input wire aclk,input wire aresetn,
    input wire [31:0] sample_drop,frame_drop,frames_in,frames_out,
    input wire overflow_sticky,mismatch_sticky,queue_error,
    input wire [12:0] fifo_level,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,input wire s_axi_rready,output wire [1:0] s_axi_rresp
);
    wire [31:0] token;
    reg [31:0] ack,sd,fd,fi,fo,status,level;
    stream_x2_regs regs(.aclk(aclk),.aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_snap_token(token),.ro_snap_ack(ack),.ro_sample_drop(sd),.ro_frame_drop(fd),
        .ro_frames_in(fi),.ro_frames_out(fo),.ro_status(status),.ro_fifo_level(level));
    always @(posedge aclk) begin
        if(!aresetn) begin ack<=0;sd<=0;fd<=0;fi<=0;fo<=0;status<=0;level<=0;end
        else if(token!=ack) begin
            ack<=token;sd<=sample_drop;fd<=frame_drop;fi<=frames_in;fo<=frames_out;
            status<={29'b0,queue_error,mismatch_sticky,overflow_sticky};level<={19'b0,fifo_level};
        end
    end
endmodule
