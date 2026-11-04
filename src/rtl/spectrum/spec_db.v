module spec_db (
    input wire aclk, input wire aresetn,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output reg [15:0] m_axis_tdata, output reg m_axis_tvalid,
    input wire m_axis_tready, output reg m_axis_tlast
);
    (* rom_style="distributed" *) reg [31:0] log_rom[0:255];
    initial $readmemh("spec_log_mantissa.hex",log_rom);
    reg [1:0] state;
    reg [4:0] exponent,normalize_exponent;
    reg [7:0] mantissa;
    reg [31:0] normalized,shifted,sum;
    reg zero,last;
    always @* begin
        normalized=s_axis_tdata; normalize_exponent=0;
        if(normalized>=65536) begin normalized=normalized>>16; normalize_exponent=16; end
        if(normalized>=256) begin normalized=normalized>>8; normalize_exponent=normalize_exponent+8; end
        if(normalized>=16) begin normalized=normalized>>4; normalize_exponent=normalize_exponent+4; end
        if(normalized>=4) begin normalized=normalized>>2; normalize_exponent=normalize_exponent+2; end
        if(normalized>=2) normalize_exponent=normalize_exponent+1;
        if(normalize_exponent>=8) shifted=s_axis_tdata>>(normalize_exponent-8);
        else shifted=s_axis_tdata<<(8-normalize_exponent);
    end
    wire [31:0] rounded=sum+32'd128;
    assign s_axis_tready=state==0;
    always @(posedge aclk) begin
        if(!aresetn) begin state<=0; m_axis_tvalid<=0; m_axis_tdata<=0; m_axis_tlast<=0; end
        else begin
            case(state)
                0: if(s_axis_tvalid) begin
                    exponent<=normalize_exponent; mantissa<=shifted[7:0];
                    zero<=s_axis_tdata==0; last<=s_axis_tlast; state<=1;
                end
                1: begin sum<=exponent*32'd197283+log_rom[mantissa]; state<=2; end
                2: begin
                    m_axis_tdata<=zero ? 16'h8000 : rounded[23:8];
                    m_axis_tlast<=last; m_axis_tvalid<=1; state<=3;
                end
                3: if(m_axis_tready) begin m_axis_tvalid<=0; state<=0; end
            endcase
        end
    end
endmodule
