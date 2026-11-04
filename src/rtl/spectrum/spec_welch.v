module spec_welch (
    input wire aclk, input wire aresetn, input wire [4:0] avg_shift,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tlast,
    output reg framing_error
);
    (* ram_style="block" *) reg [31:0] history[0:2047];
    reg [1:0] state;
    reg [10:0] index,address;
    reg [4:0] frame_shift,shift;
    reg initialized,first,last;
    reg [31:0] current,previous;
    wire signed [32:0] old_power=first ? 33'sd0 : $signed({1'b0,previous});
    wire signed [32:0] new_power=$signed({1'b0,current});
    reg signed [32:0] difference;
    reg [31:0] old_for_update;
    // The exact uint32 difference fits signed33; all higher reference bits are sign copies.
    wire signed [32:0] updated=$signed({1'b0,old_for_update})+(difference >>> shift);
    assign s_axis_tready=state==0;
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=0; index<=0; initialized<=0; frame_shift<=3;
            m_axis_tvalid<=0; m_axis_tdata<=0; m_axis_tlast<=0; framing_error<=0;
        end else begin
            case(state)
                0: if(s_axis_tvalid) begin
                    previous<=history[index]; current<=s_axis_tdata; address<=index;
                    first<=!initialized; last<=index==2047;
                    shift<=index==0 ? avg_shift : frame_shift;
                    if(index==0) frame_shift<=avg_shift;
                    if(s_axis_tlast!=(index==2047)) framing_error<=1;
                    if(index==2047) initialized<=1;
                    index<=index+1'b1; state<=1;
                end
                1: begin
                    difference<=new_power-old_power;old_for_update<=old_power[31:0];state<=2;
                end
                2: begin
                    history[address]<=updated[31:0]; m_axis_tdata<=updated[31:0];
                    m_axis_tlast<=last; m_axis_tvalid<=1; state<=3;
                end
                3: if(m_axis_tready) begin m_axis_tvalid<=0; state<=0; end
                default: state<=0;
            endcase
        end
    end
endmodule
