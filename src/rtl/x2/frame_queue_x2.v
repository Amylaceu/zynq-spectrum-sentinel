// Two complete-frame banks. Input NEVER waits for the detector. Ownership is
// decided at bin0 and held through bin2047, even if a bank becomes free midway.
// Malformed TLAST sets a sticky error; framing is fixed at 2048 accepted bins.
// Counters saturate, rather than silently wrapping during long measurements.
module frame_queue_x2 (
    input wire aclk, input wire aresetn,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output wire m_axis_tlast,
    output reg [31:0] frames_in, output reg [31:0] frames_out,
    output reg [31:0] frame_drop, output reg framing_error
);
    (* ram_style="block" *) reg [31:0] memory[0:4095];
    reg [1:0] full;
    reg write_bank,read_bank,drop_current;
    reg [10:0] write_index,read_index;
    wire dropping=write_index==0 ? full[write_bank] : drop_current;
    wire [10:0] next_index=read_index+11'd1;
    wire read_enable=(!m_axis_tvalid && full[read_bank]) ||
                     (m_axis_tvalid && m_axis_tready && read_index!=2047);
    assign s_axis_tready=aresetn;
    assign m_axis_tlast=read_index==2047;
    always @(posedge aclk) if(aresetn) begin
        if(s_axis_tvalid && !dropping) memory[{write_bank,write_index}]<=s_axis_tdata;
        if(read_enable) m_axis_tdata<=memory[{read_bank,m_axis_tvalid ? next_index : read_index}];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            full<=0;write_bank<=0;read_bank<=0;drop_current<=0;
            write_index<=0;read_index<=0;m_axis_tvalid<=0;
            frames_in<=0;frames_out<=0;frame_drop<=0;framing_error<=0;
        end else begin
            if(s_axis_tvalid) begin
                if(s_axis_tlast!=(write_index==2047)) framing_error<=1;
                if(write_index==0) drop_current<=dropping;
                write_index<=write_index+1'b1;
                if(write_index==2047) begin
                    if(frames_in!=32'hffffffff) frames_in<=frames_in+1'b1;
                    if(dropping) begin
                        if(frame_drop!=32'hffffffff) frame_drop<=frame_drop+1'b1;
                    end else begin full[write_bank]<=1;write_bank<=!write_bank;end
                end
            end
            if(!m_axis_tvalid) begin
                if(full[read_bank]) m_axis_tvalid<=1;
            end else if(m_axis_tready) begin
                if(read_index==2047) begin
                    full[read_bank]<=0;read_bank<=!read_bank;read_index<=0;m_axis_tvalid<=0;
                    if(frames_out!=32'hffffffff) frames_out<=frames_out+1'b1;
                end else read_index<=next_index;
            end
        end
    end
endmodule
