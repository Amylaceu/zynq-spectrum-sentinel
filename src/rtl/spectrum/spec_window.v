module spec_window (
    input wire aclk, input wire aresetn,
    input wire [1:0] win_sel,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tlast,
    output reg framing_error
);
    (* rom_style="block" *) reg signed [17:0] bh4 [0:2047];
    (* rom_style="block" *) reg signed [17:0] hann [0:2047];
    (* rom_style="block" *) reg signed [17:0] rect [0:2047];
    initial begin
        $readmemh("spec_window_bh4.hex", bh4);
        $readmemh("spec_window_hann.hex", hann);
        $readmemh("spec_window_rect.hex", rect);
    end
    reg [1:0] state, frame_window;
    reg [10:0] index;
    reg signed [15:0] sample_i, sample_q;
    reg signed [17:0] coefficient;
    reg signed [33:0] product_i, product_q;
    reg last;
    wire [1:0] selection = index==0 ? win_sel : frame_window;
    assign s_axis_tready = state==0;
    always @(posedge aclk) begin
        if (!aresetn) begin
            state<=0; index<=0; frame_window<=0;
            m_axis_tvalid<=0; m_axis_tdata<=0; m_axis_tlast<=0; framing_error<=0;
        end else begin
            case (state)
                0: if (s_axis_tvalid) begin
                    sample_i <= s_axis_tdata[15:0]; sample_q <= s_axis_tdata[31:16];
                    case(selection)
                        0: coefficient<=bh4[index];
                        1: coefficient<=hann[index];
                        default: coefficient<=rect[index];
                    endcase
                    if(index==0) frame_window<=win_sel;
                    last<=index==2047;
                    if(s_axis_tlast!=(index==2047)) framing_error<=1;
                    index<=index+1'b1;
                    state<=1;
                end
                1: begin
                    product_i<=sample_i*coefficient; product_q<=sample_q*coefficient;
                    state<=2;
                end
                2: begin
                    m_axis_tdata<={product_q[32:17],product_i[32:17]};
                    m_axis_tlast<=last; m_axis_tvalid<=1; state<=3;
                end
                3: if(m_axis_tready) begin m_axis_tvalid<=0; state<=0; end
            endcase
        end
    end
endmodule
