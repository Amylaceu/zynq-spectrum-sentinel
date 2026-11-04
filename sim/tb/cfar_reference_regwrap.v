// Identical registered boundary; CPU/FPGA deployment unchanged.
module cfar_reference_regwrap (
    input wire  aclk,
    input wire  aresetn,
    input wire [31:0] s_axis_pwr_tdata,
    input wire  s_axis_pwr_tvalid,
    output wire  s_axis_pwr_tready,
    input wire  s_axis_pwr_tlast,
    output wire [15:0] m_axis_thr_tdata,
    output wire [10:0] m_axis_thr_tuser,
    output wire  m_axis_thr_tlast,
    output wire  m_axis_thr_tvalid,
    input wire  m_axis_thr_tready,
    output wire [7:0] m_axis_hit_tdata,
    output wire [10:0] m_axis_hit_tuser,
    output wire  m_axis_hit_tlast,
    output wire  m_axis_hit_tvalid,
    input wire  m_axis_hit_tready,
    output wire [127:0] m_axis_tgt_tdata,
    output wire  m_axis_tgt_tlast,
    output wire  m_axis_tgt_tvalid,
    input wire  m_axis_tgt_tready,
    output wire  irq_list_ready,
    output wire [31:0] dbg_threshold,
    output wire [31:0] dbg_power,
    output wire [13:0] unused_debug,
    input wire [13:0] s_axi_awaddr,
    input wire  s_axi_awvalid,
    output wire  s_axi_awready,
    input wire [31:0] s_axi_wdata,
    input wire [3:0] s_axi_wstrb,
    input wire  s_axi_wvalid,
    output wire  s_axi_wready,
    output wire  s_axi_bvalid,
    input wire  s_axi_bready,
    output wire [1:0] s_axi_bresp,
    input wire [13:0] s_axi_araddr,
    input wire  s_axi_arvalid,
    output wire  s_axi_arready,
    output wire [31:0] s_axi_rdata,
    output wire  s_axi_rvalid,
    input wire  s_axi_rready,
    output wire [1:0] s_axi_rresp
);
    reg  q_aresetn;
    always @(posedge aclk) q_aresetn <= aresetn;
    reg [31:0] q_s_axis_pwr_tdata;
    always @(posedge aclk) q_s_axis_pwr_tdata <= s_axis_pwr_tdata;
    reg  q_s_axis_pwr_tvalid;
    always @(posedge aclk) q_s_axis_pwr_tvalid <= s_axis_pwr_tvalid;
    reg  q_s_axis_pwr_tready;
    wire  d_s_axis_pwr_tready;
    always @(posedge aclk) q_s_axis_pwr_tready <= d_s_axis_pwr_tready;
    assign s_axis_pwr_tready = q_s_axis_pwr_tready;
    reg  q_s_axis_pwr_tlast;
    always @(posedge aclk) q_s_axis_pwr_tlast <= s_axis_pwr_tlast;
    reg [15:0] q_m_axis_thr_tdata;
    wire [15:0] d_m_axis_thr_tdata;
    always @(posedge aclk) q_m_axis_thr_tdata <= d_m_axis_thr_tdata;
    assign m_axis_thr_tdata = q_m_axis_thr_tdata;
    reg [10:0] q_m_axis_thr_tuser;
    wire [10:0] d_m_axis_thr_tuser;
    always @(posedge aclk) q_m_axis_thr_tuser <= d_m_axis_thr_tuser;
    assign m_axis_thr_tuser = q_m_axis_thr_tuser;
    reg  q_m_axis_thr_tlast;
    wire  d_m_axis_thr_tlast;
    always @(posedge aclk) q_m_axis_thr_tlast <= d_m_axis_thr_tlast;
    assign m_axis_thr_tlast = q_m_axis_thr_tlast;
    reg  q_m_axis_thr_tvalid;
    wire  d_m_axis_thr_tvalid;
    always @(posedge aclk) q_m_axis_thr_tvalid <= d_m_axis_thr_tvalid;
    assign m_axis_thr_tvalid = q_m_axis_thr_tvalid;
    reg  q_m_axis_thr_tready;
    always @(posedge aclk) q_m_axis_thr_tready <= m_axis_thr_tready;
    reg [7:0] q_m_axis_hit_tdata;
    wire [7:0] d_m_axis_hit_tdata;
    always @(posedge aclk) q_m_axis_hit_tdata <= d_m_axis_hit_tdata;
    assign m_axis_hit_tdata = q_m_axis_hit_tdata;
    reg [10:0] q_m_axis_hit_tuser;
    wire [10:0] d_m_axis_hit_tuser;
    always @(posedge aclk) q_m_axis_hit_tuser <= d_m_axis_hit_tuser;
    assign m_axis_hit_tuser = q_m_axis_hit_tuser;
    reg  q_m_axis_hit_tlast;
    wire  d_m_axis_hit_tlast;
    always @(posedge aclk) q_m_axis_hit_tlast <= d_m_axis_hit_tlast;
    assign m_axis_hit_tlast = q_m_axis_hit_tlast;
    reg  q_m_axis_hit_tvalid;
    wire  d_m_axis_hit_tvalid;
    always @(posedge aclk) q_m_axis_hit_tvalid <= d_m_axis_hit_tvalid;
    assign m_axis_hit_tvalid = q_m_axis_hit_tvalid;
    reg  q_m_axis_hit_tready;
    always @(posedge aclk) q_m_axis_hit_tready <= m_axis_hit_tready;
    reg [127:0] q_m_axis_tgt_tdata;
    wire [127:0] d_m_axis_tgt_tdata;
    always @(posedge aclk) q_m_axis_tgt_tdata <= d_m_axis_tgt_tdata;
    assign m_axis_tgt_tdata = q_m_axis_tgt_tdata;
    reg  q_m_axis_tgt_tlast;
    wire  d_m_axis_tgt_tlast;
    always @(posedge aclk) q_m_axis_tgt_tlast <= d_m_axis_tgt_tlast;
    assign m_axis_tgt_tlast = q_m_axis_tgt_tlast;
    reg  q_m_axis_tgt_tvalid;
    wire  d_m_axis_tgt_tvalid;
    always @(posedge aclk) q_m_axis_tgt_tvalid <= d_m_axis_tgt_tvalid;
    assign m_axis_tgt_tvalid = q_m_axis_tgt_tvalid;
    reg  q_m_axis_tgt_tready;
    always @(posedge aclk) q_m_axis_tgt_tready <= m_axis_tgt_tready;
    reg  q_irq_list_ready;
    wire  d_irq_list_ready;
    always @(posedge aclk) q_irq_list_ready <= d_irq_list_ready;
    assign irq_list_ready = q_irq_list_ready;
    reg [31:0] q_dbg_threshold;
    wire [31:0] d_dbg_threshold;
    always @(posedge aclk) q_dbg_threshold <= d_dbg_threshold;
    assign dbg_threshold = q_dbg_threshold;
    reg [31:0] q_dbg_power;
    wire [31:0] d_dbg_power;
    always @(posedge aclk) q_dbg_power <= d_dbg_power;
    assign dbg_power = q_dbg_power;
    reg [13:0] q_unused_debug;
    wire [13:0] d_unused_debug;
    always @(posedge aclk) q_unused_debug <= d_unused_debug;
    assign unused_debug = q_unused_debug;
    reg [13:0] q_s_axi_awaddr;
    always @(posedge aclk) q_s_axi_awaddr <= s_axi_awaddr;
    reg  q_s_axi_awvalid;
    always @(posedge aclk) q_s_axi_awvalid <= s_axi_awvalid;
    reg  q_s_axi_awready;
    wire  d_s_axi_awready;
    always @(posedge aclk) q_s_axi_awready <= d_s_axi_awready;
    assign s_axi_awready = q_s_axi_awready;
    reg [31:0] q_s_axi_wdata;
    always @(posedge aclk) q_s_axi_wdata <= s_axi_wdata;
    reg [3:0] q_s_axi_wstrb;
    always @(posedge aclk) q_s_axi_wstrb <= s_axi_wstrb;
    reg  q_s_axi_wvalid;
    always @(posedge aclk) q_s_axi_wvalid <= s_axi_wvalid;
    reg  q_s_axi_wready;
    wire  d_s_axi_wready;
    always @(posedge aclk) q_s_axi_wready <= d_s_axi_wready;
    assign s_axi_wready = q_s_axi_wready;
    reg  q_s_axi_bvalid;
    wire  d_s_axi_bvalid;
    always @(posedge aclk) q_s_axi_bvalid <= d_s_axi_bvalid;
    assign s_axi_bvalid = q_s_axi_bvalid;
    reg  q_s_axi_bready;
    always @(posedge aclk) q_s_axi_bready <= s_axi_bready;
    reg [1:0] q_s_axi_bresp;
    wire [1:0] d_s_axi_bresp;
    always @(posedge aclk) q_s_axi_bresp <= d_s_axi_bresp;
    assign s_axi_bresp = q_s_axi_bresp;
    reg [13:0] q_s_axi_araddr;
    always @(posedge aclk) q_s_axi_araddr <= s_axi_araddr;
    reg  q_s_axi_arvalid;
    always @(posedge aclk) q_s_axi_arvalid <= s_axi_arvalid;
    reg  q_s_axi_arready;
    wire  d_s_axi_arready;
    always @(posedge aclk) q_s_axi_arready <= d_s_axi_arready;
    assign s_axi_arready = q_s_axi_arready;
    reg [31:0] q_s_axi_rdata;
    wire [31:0] d_s_axi_rdata;
    always @(posedge aclk) q_s_axi_rdata <= d_s_axi_rdata;
    assign s_axi_rdata = q_s_axi_rdata;
    reg  q_s_axi_rvalid;
    wire  d_s_axi_rvalid;
    always @(posedge aclk) q_s_axi_rvalid <= d_s_axi_rvalid;
    assign s_axi_rvalid = q_s_axi_rvalid;
    reg  q_s_axi_rready;
    always @(posedge aclk) q_s_axi_rready <= s_axi_rready;
    reg [1:0] q_s_axi_rresp;
    wire [1:0] d_s_axi_rresp;
    always @(posedge aclk) q_s_axi_rresp <= d_s_axi_rresp;
    assign s_axi_rresp = q_s_axi_rresp;
    cfar_core_x1 core(.aclk(aclk),.aresetn(q_aresetn),.s_axis_pwr_tdata(q_s_axis_pwr_tdata),.s_axis_pwr_tvalid(q_s_axis_pwr_tvalid),.s_axis_pwr_tready(d_s_axis_pwr_tready),.s_axis_pwr_tlast(q_s_axis_pwr_tlast),.m_axis_thr_tdata(d_m_axis_thr_tdata),.m_axis_thr_tuser(d_m_axis_thr_tuser),.m_axis_thr_tlast(d_m_axis_thr_tlast),.m_axis_thr_tvalid(d_m_axis_thr_tvalid),.m_axis_thr_tready(q_m_axis_thr_tready),.m_axis_hit_tdata(d_m_axis_hit_tdata),.m_axis_hit_tuser(d_m_axis_hit_tuser),.m_axis_hit_tlast(d_m_axis_hit_tlast),.m_axis_hit_tvalid(d_m_axis_hit_tvalid),.m_axis_hit_tready(q_m_axis_hit_tready),.m_axis_tgt_tdata(d_m_axis_tgt_tdata),.m_axis_tgt_tlast(d_m_axis_tgt_tlast),.m_axis_tgt_tvalid(d_m_axis_tgt_tvalid),.m_axis_tgt_tready(q_m_axis_tgt_tready),.irq_list_ready(d_irq_list_ready),.dbg_threshold(d_dbg_threshold),.dbg_power(d_dbg_power),.unused_debug(d_unused_debug),.s_axi_awaddr(q_s_axi_awaddr),.s_axi_awvalid(q_s_axi_awvalid),.s_axi_awready(d_s_axi_awready),.s_axi_wdata(q_s_axi_wdata),.s_axi_wstrb(q_s_axi_wstrb),.s_axi_wvalid(q_s_axi_wvalid),.s_axi_wready(d_s_axi_wready),.s_axi_bvalid(d_s_axi_bvalid),.s_axi_bready(q_s_axi_bready),.s_axi_bresp(d_s_axi_bresp),.s_axi_araddr(q_s_axi_araddr),.s_axi_arvalid(q_s_axi_arvalid),.s_axi_arready(d_s_axi_arready),.s_axi_rdata(d_s_axi_rdata),.s_axi_rvalid(d_s_axi_rvalid),.s_axi_rready(q_s_axi_rready),.s_axi_rresp(d_s_axi_rresp));
endmodule
