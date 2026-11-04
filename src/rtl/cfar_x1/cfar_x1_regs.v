// X1 AXI-Lite bank: src/regs/cfar_x1.yaml. Old v1 bank remains unchanged.
module cfar_x1_regs (
    input wire aclk,input wire aresetn,
    input wire [13:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output reg s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [13:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output reg [31:0] s_axi_rdata,output reg s_axi_rvalid,
    input wire s_axi_rready,output wire [1:0] s_axi_rresp,
    output reg [31:0] reg_ctrl,reg_n_shift,reg_guard,reg_alpha,reg_dc_mask,reg_gap,
    output reg [31:0] reg_alarm_limit,reg_occ_clear_token,reg_min_width,reg_mask_count,
    output reg [511:0] reg_masks,
    input wire [31:0] target_count,frame_count,hit_count,alarm,occ_frames,status,
    input wire [31:0] status_latch,raw_count,filtered_count,candidate_count,
    output wire [6:0] target_word_addr,input wire [31:0] target_data,
    output wire [10:0] occ_index,input wire [15:0] occ_data
);
    reg aw_pending,w_pending,read_pending;
    reg [13:0] aw_address,read_address;
    reg [31:0] w_data;
    reg [3:0] strobes;
    integer lane;
    assign s_axi_awready=!aw_pending && !s_axi_bvalid;
    assign s_axi_wready=!w_pending && !s_axi_bvalid;
    assign s_axi_arready=!read_pending && !s_axi_rvalid;
    assign s_axi_bresp=0;assign s_axi_rresp=0;
    // The X1 target window is combinational and uses the captured address.
    assign target_word_addr=read_address[8:2];
    assign occ_index=s_axi_araddr[12:2]-11'd1024;
    always @(posedge aclk) begin
        if(!aresetn) begin
            aw_pending<=0;w_pending<=0;read_pending<=0;s_axi_bvalid<=0;s_axi_rvalid<=0;s_axi_rdata<=0;
            reg_ctrl<=0;reg_n_shift<=4;reg_guard<=2;reg_alpha<=1974;reg_dc_mask<=3;reg_gap<=6;
            reg_alarm_limit<=1;reg_occ_clear_token<=0;
            reg_min_width<=2;reg_mask_count<=0;reg_masks<=0;
        end else begin
            if(s_axi_bvalid && s_axi_bready) s_axi_bvalid<=0;
            if(s_axi_rvalid && s_axi_rready) s_axi_rvalid<=0;
            if(s_axi_awvalid && s_axi_awready) begin aw_pending<=1;aw_address<=s_axi_awaddr;end
            if(s_axi_wvalid && s_axi_wready) begin w_pending<=1;w_data<=s_axi_wdata;strobes<=s_axi_wstrb;end
            if(aw_pending && w_pending && !s_axi_bvalid) begin
                aw_pending<=0;w_pending<=0;s_axi_bvalid<=1;
                for(lane=0;lane<4;lane=lane+1) if(strobes[lane]) begin
                    case(aw_address)
                        'h00:reg_ctrl[lane*8+:8]<=w_data[lane*8+:8];
                        'h04:reg_n_shift[lane*8+:8]<=w_data[lane*8+:8];
                        'h08:reg_guard[lane*8+:8]<=w_data[lane*8+:8];
                        'h0c:reg_alpha[lane*8+:8]<=w_data[lane*8+:8];
                        'h10:reg_dc_mask[lane*8+:8]<=w_data[lane*8+:8];
                        'h14:reg_gap[lane*8+:8]<=w_data[lane*8+:8];
                        'h24:reg_alarm_limit[lane*8+:8]<=w_data[lane*8+:8];
                        'h2c:reg_occ_clear_token[lane*8+:8]<=w_data[lane*8+:8];
                        'h38:reg_min_width[lane*8+:8]<=w_data[lane*8+:8];
                        'h3c:reg_mask_count[lane*8+:8]<=w_data[lane*8+:8];
                        default:if(aw_address>='h80 && aw_address<'hc0 && aw_address[1:0]==0)
                            reg_masks[(aw_address[5:2]*32)+(lane*8)+:8]<=w_data[lane*8+:8];
                    endcase
                end
            end
            if(s_axi_arvalid && s_axi_arready) begin read_address<=s_axi_araddr;read_pending<=1;end
            if(read_pending) begin
                read_pending<=0;s_axi_rvalid<=1;
                if(read_address>='h200 && read_address<'h400) s_axi_rdata<=target_data;
                else if(read_address>='h1000 && read_address<'h3000) s_axi_rdata<={16'b0,occ_data};
                else if(read_address>='h80 && read_address<'hc0 && read_address[1:0]==0)
                    s_axi_rdata<=reg_masks[read_address[5:2]*32+:32];
                else case(read_address)
                    'h00:s_axi_rdata<=reg_ctrl;
                    'h04:s_axi_rdata<=reg_n_shift;
                    'h08:s_axi_rdata<=reg_guard;
                    'h0c:s_axi_rdata<=reg_alpha;
                    'h10:s_axi_rdata<=reg_dc_mask;
                    'h14:s_axi_rdata<=reg_gap;
                    'h18:s_axi_rdata<=target_count;
                    'h1c:s_axi_rdata<=frame_count;
                    'h20:s_axi_rdata<=hit_count;
                    'h24:s_axi_rdata<=reg_alarm_limit;
                    'h28:s_axi_rdata<=alarm;
                    'h2c:s_axi_rdata<=reg_occ_clear_token;
                    'h30:s_axi_rdata<=occ_frames;
                    'h34:s_axi_rdata<=status;
                    'h38:s_axi_rdata<=reg_min_width;
                    'h3c:s_axi_rdata<=reg_mask_count;
                    'h40:s_axi_rdata<=status_latch;
                    'h44:s_axi_rdata<=raw_count;
                    'h48:s_axi_rdata<=filtered_count;
                    'h4c:s_axi_rdata<=candidate_count;
                    'hfc:s_axi_rdata<=32'h43460002;
                    default:s_axi_rdata<=0;
                endcase
            end
        end
    end
endmodule
