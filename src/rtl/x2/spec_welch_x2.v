// One sample per clock, with a globally stalled three-stage elastic pipeline.
// History is read synchronously and written two stages later. A bin is revisited
// only after 2048 accepted samples, so no same-address forwarding is needed.
module spec_welch_x2 (
    input wire aclk, input wire aresetn, input wire [4:0] avg_shift,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tlast,
    output reg framing_error
);
    (* ram_style="block" *) reg [31:0] history[0:2047];
    reg [10:0] index, address0, address1;
    reg [4:0] frame_shift, shift0, shift1;
    reg initialized, first0, last0, last1, valid0, valid1;
    reg [31:0] current0, previous0, old1;
    reg signed [32:0] difference1;
    wire advance=!m_axis_tvalid || m_axis_tready;
    wire signed [32:0] old0=first0 ? 33'sd0 : $signed({1'b0,previous0});
    wire signed [32:0] update1=$signed({1'b0,old1})+(difference1 >>> shift1);
    assign s_axis_tready=advance && aresetn;
    // No reset on the RAM or its read register: preserve BRAM inference.
    always @(posedge aclk) begin
        if(aresetn && advance) begin
            if(s_axis_tvalid) previous0<=history[index];
            if(valid1) history[address1]<=update1[31:0];
        end
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            index<=0;initialized<=0;frame_shift<=3;valid0<=0;valid1<=0;
            m_axis_tvalid<=0;m_axis_tlast<=0;m_axis_tdata<=0;framing_error<=0;
        end else if(advance) begin
            valid0<=s_axis_tvalid;
            valid1<=valid0;
            m_axis_tvalid<=valid1;
            if(s_axis_tvalid) begin
                current0<=s_axis_tdata;address0<=index;first0<=!initialized;
                last0<=index==2047;shift0<=index==0 ? avg_shift : frame_shift;
                if(index==0) frame_shift<=avg_shift;
                if(s_axis_tlast!=(index==2047)) framing_error<=1;
                if(index==2047) initialized<=1;
                index<=index+1'b1;
            end
            if(valid0) begin
                difference1<=$signed({1'b0,current0})-old0;
                old1<=old0[31:0];address1<=address0;shift1<=shift0;last1<=last0;
            end
            if(valid1) begin m_axis_tdata<=update1[31:0];m_axis_tlast<=last1;end
        end
    end
endmodule
