module spec_power (
    input wire aclk, input wire aresetn,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [31:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tlast
);
    reg [31:0] square_i,square_q;
    reg valid1,last1;
    wire advance=!m_axis_tvalid || m_axis_tready;
    assign s_axis_tready=!valid1 || advance;
    wire signed [15:0] real_word=s_axis_tdata[15:0];
    wire signed [15:0] imag_word=s_axis_tdata[31:16];
    // Native FFT words left-shifted8, squared then right-shifted16,
    // are exactly the sum of these two native signed16 squares.
    always @(posedge aclk) begin
        if(!aresetn) begin valid1<=0; m_axis_tvalid<=0; m_axis_tdata<=0; m_axis_tlast<=0; end
        else begin
            if(advance) begin
                m_axis_tvalid<=valid1;
                if(valid1) begin m_axis_tdata<=square_i+square_q; m_axis_tlast<=last1; end
            end
            if(s_axis_tready) begin
                valid1<=s_axis_tvalid;
                if(s_axis_tvalid) begin
                    square_i<=real_word*real_word; square_q<=imag_word*imag_word;
                    last1<=s_axis_tlast;
                end
            end
        end
    end
endmodule
