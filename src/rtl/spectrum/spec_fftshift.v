module spec_fftshift (
    input wire aclk,input wire aresetn,
    input wire [31:0] s_axis_tdata,input wire s_axis_tvalid,
    output wire s_axis_tready,input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata,output reg m_axis_tvalid,
    input wire m_axis_tready,output wire m_axis_tlast,
    output reg framing_error
);
    (* ram_style="block" *) reg [31:0] frame_ram[0:4095];
    reg [1:0] full;
    reg write_bank,read_bank;
    reg [10:0] write_index,read_index;
    wire [10:0] shifted_address=write_index^11'd1024;
    wire [10:0] next_read_index=read_index+11'd1;
    wire read_enable=(!m_axis_tvalid && full[read_bank]) ||
                     (m_axis_tvalid && m_axis_tready && read_index!=2047);
    wire [11:0] read_address={read_bank,m_axis_tvalid ? next_read_index : read_index};
    assign s_axis_tready=!full[write_bank];
    assign m_axis_tlast=read_index==2047;
    // One syntactic read port and one write port infer a simple dual-port BRAM.
    always @(posedge aclk) if(aresetn) begin
        if(s_axis_tvalid && s_axis_tready) frame_ram[{write_bank,shifted_address}]<=s_axis_tdata;
        if(read_enable) m_axis_tdata<=frame_ram[read_address];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            full<=0;write_bank<=0;read_bank<=0;write_index<=0;read_index<=0;
            m_axis_tvalid<=0;framing_error<=0;
        end else begin
            if(s_axis_tvalid && s_axis_tready) begin
                if(s_axis_tlast!=(write_index==2047)) framing_error<=1;
                write_index<=write_index+1'b1;
                if(write_index==2047) begin full[write_bank]<=1;write_bank<=!write_bank;end
            end
            if(!m_axis_tvalid) begin
                if(full[read_bank]) begin
                    m_axis_tvalid<=1;
                end
            end else if(m_axis_tready) begin
                if(read_index==2047) begin
                    full[read_bank]<=0;read_bank<=!read_bank;read_index<=0;m_axis_tvalid<=0;
                end else begin
                    read_index<=next_read_index;
                end
            end
        end
    end
endmodule
