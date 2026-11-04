// Sequential vectoring CORDIC: IQ16 -> frequency in signed Q0.24 turns/sample.
// No RF, clock-domain crossing or output interpolation. Configure while reset.
// Removing residual phase increment is algebraically equivalent to mixing by
// an NCO before phase differencing, without four continuous complex products.
module fm_phase_y3 #(
    parameter ATAN_FILE="y3_atan.hex"
) (
    input wire aclk, input wire aresetn,
    input wire [31:0] cfg_fcw,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready,
    output reg [23:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready,
    output reg [31:0] zero_samples
);
    localparam IDLE=0, ROTATE=1, EMIT=2;
    reg [1:0] state;
    reg [4:0] iteration;
    reg signed [39:0] x,y;
    reg signed [25:0] angle;
    reg signed [25:0] atan_table[0:19];
    reg [23:0] previous;
    reg have_previous,zero_input;
    wire signed [15:0] in_i=$signed(s_axis_tdata[15:0]);
    wire signed [15:0] in_q=$signed(s_axis_tdata[31:16]);
    wire signed [39:0] scaled_i={{8{in_i[15]}},in_i,16'b0};
    wire signed [39:0] scaled_q={{8{in_q[15]}},in_q,16'b0};
    initial $readmemh(ATAN_FILE,atan_table);
    assign s_axis_tready=aresetn && state==IDLE && (!m_axis_tvalid || m_axis_tready);
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=IDLE;iteration<=0;x<=0;y<=0;angle<=0;previous<=0;
            have_previous<=0;zero_input<=0;m_axis_tvalid<=0;m_axis_tdata<=0;
            zero_samples<=0;
        end else begin
            if(m_axis_tvalid && m_axis_tready) m_axis_tvalid<=0;
            if(s_axis_tvalid && s_axis_tready) begin
                if(in_i<0) begin
                    x<=-scaled_i;y<=-scaled_q;
                    angle<=in_q<0 ? -26'sd8388608 : 26'sd8388608;
                end else begin x<=scaled_i;y<=scaled_q;angle<=0;end
                zero_input<=s_axis_tdata==0;iteration<=0;state<=ROTATE;
                if(s_axis_tdata==0 && zero_samples!=32'hffffffff)
                    zero_samples<=zero_samples+1'b1;
            end
            if(state==ROTATE) begin
                if(y>0) begin
                    x<=x+(y>>>iteration);y<=y-(x>>>iteration);
                    angle<=angle+atan_table[iteration];
                end else if(y<0) begin
                    x<=x-(y>>>iteration);y<=y+(x>>>iteration);
                    angle<=angle-atan_table[iteration];
                end
                if(iteration==19) state<=EMIT;else iteration<=iteration+1'b1;
            end
            if(state==EMIT) begin
                // 24-bit modular subtraction unwraps one sample interval.
                // A zero input invalidates the pair; never fabricate its angle.
                m_axis_tdata<=have_previous && !zero_input ?
                    angle[23:0]-previous-cfg_fcw[31:8] : 24'b0;
                previous<=angle[23:0];have_previous<=!zero_input;
                m_axis_tvalid<=1;state<=IDLE;
            end
        end
    end
endmodule
