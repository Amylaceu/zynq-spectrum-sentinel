// X5 independent register contract; offsets match LCD v1, version differs.
module lcd_ctrl_regs_z2 (
    input wire aclk,
    input wire aresetn,
    input wire [7:0] s_axi_awaddr,
    input wire s_axi_awvalid,
    output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,
    output wire s_axi_wready,
    output reg s_axi_bvalid,
    input wire s_axi_bready,
    output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,
    input wire s_axi_arvalid,
    output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,
    output reg s_axi_rvalid,
    input wire s_axi_rready,
    output wire [1:0] s_axi_rresp,
    output reg [31:0] reg_ctrl,
    output reg [31:0] reg_bus_phase,
    output reg [31:0] reg_ui_epoch,
    input wire [31:0] ro_frame_count,
    input wire [31:0] ro_ui_applied,
    input wire [31:0] ro_status,
    input wire [31:0] ro_dropped,
    input wire [31:0] ro_frame_id
);
reg aw_pending, w_pending;
reg [7:0] aw_address;
reg [31:0] w_data;
reg [3:0] w_strobes;
integer lane;
assign s_axi_awready=!aw_pending && !s_axi_bvalid;
assign s_axi_wready=!w_pending && !s_axi_bvalid;
assign s_axi_arready=!s_axi_rvalid;
assign s_axi_bresp=2'b00; assign s_axi_rresp=2'b00;
always @(posedge aclk) begin
if (!aresetn) begin
aw_pending<=0; w_pending<=0; s_axi_bvalid<=0; s_axi_rvalid<=0; s_axi_rdata<=0;
reg_ctrl<=32'h00000000;
reg_bus_phase<=32'h00000019;
reg_ui_epoch<=32'h00000000;
end else begin
if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
if(s_axi_awvalid && s_axi_awready) begin aw_pending<=1; aw_address<=s_axi_awaddr; end
if(s_axi_wvalid && s_axi_wready) begin w_pending<=1; w_data<=s_axi_wdata; w_strobes<=s_axi_wstrb; end
if(aw_pending && w_pending && !s_axi_bvalid) begin
aw_pending<=0; w_pending<=0; s_axi_bvalid<=1;
case(aw_address)
8'h00: for(lane=0;lane<4;lane=lane+1) if(w_strobes[lane]) reg_ctrl[lane*8+:8]<=w_data[lane*8+:8];
8'h04: for(lane=0;lane<4;lane=lane+1) if(w_strobes[lane]) reg_bus_phase[lane*8+:8]<=w_data[lane*8+:8];
8'h08: for(lane=0;lane<4;lane=lane+1) if(w_strobes[lane]) reg_ui_epoch[lane*8+:8]<=w_data[lane*8+:8];
default: begin end
endcase
end
if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
if(s_axi_arvalid && s_axi_arready) begin s_axi_rvalid<=1;
case(s_axi_araddr)
8'h00: s_axi_rdata<=reg_ctrl;
8'h04: s_axi_rdata<=reg_bus_phase;
8'h08: s_axi_rdata<=reg_ui_epoch;
8'h0c: s_axi_rdata<=ro_frame_count;
8'h10: s_axi_rdata<=ro_ui_applied;
8'h14: s_axi_rdata<=ro_status;
8'h18: s_axi_rdata<=ro_dropped;
8'h1c: s_axi_rdata<=ro_frame_id;
8'hfc: s_axi_rdata<=32'h4c430006;
default: s_axi_rdata<=0;
endcase
end
end
end
endmodule
