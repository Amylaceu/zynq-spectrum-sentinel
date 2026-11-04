// 161-tap Q1.17 lowpass BEFORE /10 decimation; then 75us deemphasis at48k.
// History is dual-port synchronous RAM; snapshot readers may coexist with up
// to nine younger writes. Output backpressure halts the next decimation start.
module fm_audio_filter_y3 #(
    parameter COEFF_FILE="y3_audio_fir.hex",
    parameter integer DEEMPH_BETA=63579
) (
    input wire aclk,input wire aresetn,
    input wire [23:0] s_axis_tdata,input wire s_axis_tvalid,
    output wire s_axis_tready,
    output reg [31:0] m_axis_tdata,output reg m_axis_tvalid,
    input wire m_axis_tready,
    output reg [31:0] samples_in,output reg [31:0] samples_out
);
    localparam IDLE=0,READ=1,MULT=2,ACC=3,DEEMPH=4,UPDATE=5,GAIN=6,EMIT=7,DEEMPH_MULT=8;
    reg [3:0] state;
    (* ram_style="block" *) reg signed [23:0] history[0:255];
    (* rom_style="distributed" *) reg signed [17:0] coeff[0:160];
    initial $readmemh(COEFF_FILE,coeff);
    reg [7:0] write_index,snapshot_index,tap,valid_history,snapshot_history;
    reg [3:0] decimate;
    reg signed [23:0] history_read;
    reg signed [17:0] coeff_read;
    reg read_zero;
    reg signed [41:0] product;
    reg signed [49:0] accumulator;
    reg signed [31:0] filtered,deemphasis;
    reg signed [32:0] deemph_delta;
    (* use_dsp="yes" *) reg signed [50:0] deemph_product;
    reg signed [48:0] gain_product;
    wire signed [49:0] next_sum=accumulator+{{8{product[41]}},product};
    wire [7:0] read_index=snapshot_index-tap;
    wire accept=s_axis_tvalid && s_axis_tready;
    assign s_axis_tready=aresetn && (decimate!=0 ||
        (state==IDLE && (!m_axis_tvalid || m_axis_tready)));
    always @(posedge aclk) begin
        if(accept) history[write_index]<=s_axis_tdata;
        history_read<=history[read_index];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=IDLE;write_index<=0;snapshot_index<=0;tap<=0;
            valid_history<=0;snapshot_history<=0;decimate<=0;coeff_read<=0;read_zero<=1;
            product<=0;accumulator<=0;filtered<=0;deemphasis<=0;
            deemph_delta<=0;deemph_product<=0;gain_product<=0;m_axis_tdata<=0;m_axis_tvalid<=0;
            samples_in<=0;samples_out<=0;
        end else begin
            if(m_axis_tvalid && m_axis_tready) m_axis_tvalid<=0;
            if(accept) begin
                write_index<=write_index+1'b1;
                if(valid_history<160) valid_history<=valid_history+1'b1;
                decimate<=decimate==9 ? 0 : decimate+1'b1;
                if(samples_in!=32'hffffffff) samples_in<=samples_in+1'b1;
                if(decimate==0) begin
                    snapshot_index<=write_index;snapshot_history<=valid_history;
                    tap<=0;accumulator<=0;state<=READ;
                end
            end
            case(state)
                READ:begin coeff_read<=coeff[tap];read_zero<=tap>snapshot_history;state<=MULT;end
                MULT:begin product<=read_zero ? 42'sd0 : history_read*coeff_read;state<=ACC;end
                ACC:begin
                    accumulator<=next_sum;
                    if(tap==160) begin filtered<=next_sum>>>17;state<=DEEMPH;end
                    else begin tap<=tap+1'b1;state<=READ;end
                end
                DEEMPH:begin
                    // Preserve the full signed difference; separate subtraction
                    // from multiplication to close the 150MHz implementation.
                    deemph_delta<=$signed({filtered[31],filtered})-$signed({deemphasis[31],deemphasis});
                    state<=DEEMPH_MULT;
                end
                DEEMPH_MULT:begin
                    deemph_product<=deemph_delta*$signed(DEEMPH_BETA);
                    state<=UPDATE;
                end
                UPDATE:begin deemphasis<=deemphasis+(deemph_product>>>18);state<=GAIN;end
                GAIN:begin gain_product<=deemphasis*17'sd41943;state<=EMIT;end
                EMIT:begin
                    // gain=.2 for75kHz peak FM at480kHz: .2*480k/(2*75k)=.64.
                    if((gain_product>>>16)>49'sd8388607) m_axis_tdata<=32'h007fffff;
                    else if((gain_product>>>16)< -49'sd8388608) m_axis_tdata<=32'hff800000;
                    else m_axis_tdata<=gain_product>>>16;
                    m_axis_tvalid<=1;state<=IDLE;
                    if(samples_out!=32'hffffffff) samples_out<=samples_out+1'b1;
                end
                default:begin end
            endcase
        end
    end
endmodule
