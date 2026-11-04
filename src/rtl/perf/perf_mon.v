module perf_mon (
    input wire aclk,input wire aresetn,
    input wire sample_valid,input wire sample_ready,
    input wire fft_valid,input wire fft_ready,input wire fft_last,
    input wire hit_valid,input wire hit_ready,input wire hit_value,
    input wire list_ready,input wire overflow_sticky,input wire error_sticky,
    input wire [12:0] fifo_level,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,input wire s_axi_rready,output wire [1:0] s_axi_rresp
);
    wire [31:0] clear_token,snap_token,arm_token;
    reg [31:0] clear_seen,snap_seen,arm_seen;
    reg [63:0] samples,cycles;
    reg [31:0] frames,hits,lists,latency,markers,marker_start;
    reg arm_wait,marker_pending,latency_valid,overflow_seen,error_seen;
    reg [31:0] snap_samples_lo,snap_samples_hi,snap_frames,snap_hits,snap_lists;
    reg [31:0] snap_cycles_lo,snap_cycles_hi,snap_latency,snap_markers,snap_status,snap_fifo;
    perf_ctrl_regs registers(.aclk(aclk),.aresetn(aresetn),
.s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),.s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),.s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),.s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),.s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_clear_token(clear_token),.reg_snap_token(snap_token),.reg_arm_token(arm_token),
        .ro_snap_ack(snap_seen),.ro_samples_lo(snap_samples_lo),.ro_samples_hi(snap_samples_hi),
        .ro_fft_frames(snap_frames),.ro_hits(snap_hits),.ro_lists(snap_lists),
        .ro_cycles_lo(snap_cycles_lo),.ro_cycles_hi(snap_cycles_hi),.ro_latency_cycles(snap_latency),
        .ro_markers_done(snap_markers),.ro_status(snap_status),.ro_fifo_level(snap_fifo));
    // All observed events are in aclk. Counter snapshots are atomic and remain stable until a new token.
    // A marker is the first accepted IQ sample after ARM_TOKEN, measured to the next list-ready pulse.
    // Callers arm only after draining the previous pipeline; no claim of per-target RF latency.
    always @(posedge aclk) begin
        if(!aresetn) begin
            clear_seen<=0;snap_seen<=0;arm_seen<=0;samples<=0;cycles<=0;frames<=0;hits<=0;lists<=0;
            latency<=0;markers<=0;marker_start<=0;arm_wait<=0;marker_pending<=0;latency_valid<=0;
            overflow_seen<=0;error_seen<=0;
            snap_samples_lo<=0;snap_samples_hi<=0;snap_frames<=0;snap_hits<=0;snap_lists<=0;
            snap_cycles_lo<=0;snap_cycles_hi<=0;snap_latency<=0;snap_markers<=0;snap_status<=0;snap_fifo<=0;
        end else begin
            cycles<=cycles+1'b1;
            if(clear_token!=clear_seen) begin
                clear_seen<=clear_token;samples<=0;cycles<=0;frames<=0;hits<=0;lists<=0;markers<=0;
                latency<=0;arm_wait<=0;marker_pending<=0;latency_valid<=0;overflow_seen<=0;error_seen<=0;
                arm_seen<=arm_token;
            end else begin
                if(sample_valid && sample_ready) samples<=samples+1'b1;
                if(fft_valid && fft_ready && fft_last) frames<=frames+1'b1;
                if(hit_valid && hit_ready && hit_value) hits<=hits+1'b1;
                if(list_ready) lists<=lists+1'b1;
                if(overflow_sticky) overflow_seen<=1;
                if(error_sticky) error_seen<=1;
                if(arm_token!=arm_seen) begin
                    arm_seen<=arm_token;
                    if(marker_pending || arm_wait) error_seen<=1;
                    else begin arm_wait<=1;latency_valid<=0;end
                end
                if(arm_wait && sample_valid && sample_ready) begin
                    marker_start<=cycles[31:0];marker_pending<=1;arm_wait<=0;
                end
                if(marker_pending && list_ready) begin
                    latency<=cycles[31:0]-marker_start;markers<=markers+1'b1;marker_pending<=0;latency_valid<=1;
                end
            end
            if(snap_token!=snap_seen) begin
                snap_seen<=snap_token;snap_samples_lo<=samples[31:0];snap_samples_hi<=samples[63:32];
                snap_frames<=frames;snap_hits<=hits;snap_lists<=lists;
                snap_cycles_lo<=cycles[31:0];snap_cycles_hi<=cycles[63:32];snap_latency<=latency;snap_markers<=markers;
                snap_status<={27'b0,arm_wait,marker_pending,latency_valid,error_seen,overflow_seen};snap_fifo<={19'b0,fifo_level};
            end
        end
    end
endmodule
