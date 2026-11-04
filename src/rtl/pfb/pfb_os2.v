// M=16, D=8, 8 taps/phase. See docs/x5_pl_interface.md.
// Two real multipliers; independent synchronous history write/read ports.
module pfb_os2 #(
    parameter COEFF_FILE="x5_pfb_coeff.hex"
) (
    input wire aclk, input wire aresetn,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire [31:0] m_axis_tdata, output wire [3:0] m_axis_tuser,
    output wire m_axis_tvalid, input wire m_axis_tready,
    output wire m_axis_tlast, output reg error_sticky
);
    localparam IDLE=0, RUN=1, FLUSH=2, SEND=3;
    reg [1:0] state;
    (* ram_style="block" *) reg [31:0] history[0:255];
    (* rom_style="distributed" *) reg signed [17:0] coeff[0:127];
    initial $readmemh(COEFF_FILE,coeff);
    reg [7:0] wr_ptr,endpoint;
    reg [6:0] history_valid,frame_history;
    reg [2:0] input_mod;
    reg rotation,frame_rotation;
    reg [6:0] issue_index;
    wire [3:0] phase_index=(frame_rotation ? 4'd8 : 4'd0)-issue_index[6:3];
    wire [6:0] offset={issue_index[2:0],phase_index};
    wire [7:0] rd_addr=endpoint-{1'b0,offset};
    reg [31:0] rd_sample;
    reg signed [17:0] rd_coeff;
    reg rd_valid,prod_valid;
    reg rd_zero;
    reg [6:0] rd_index,prod_index;
    reg signed [33:0] prod_i,prod_q;
    reg signed [39:0] acc_i,acc_q;
    wire signed [39:0] sum_i=(prod_index[2:0]==0 ? 40'sd0 : acc_i)+{{6{prod_i[33]}},prod_i};
    wire signed [39:0] sum_q=(prod_index[2:0]==0 ? 40'sd0 : acc_q)+{{6{prod_q[33]}},prod_q};
    reg [47:0] fft_frame[0:15];
    reg [3:0] send_index;
    reg configured;
    wire cfg_ready,fft_ready;
    wire [47:0] fft_data;
    wire fft_valid,fft_last,overflow,unexpected,missing;
    reg [3:0] out_bin;
    // While a frame is computing, at most seven younger samples enter history.
    // This prevents ring overwrite even during arbitrarily long FFT stalls.
    assign s_axis_tready=aresetn && (input_mod!=0 || state==IDLE);
    function [15:0] restore;
        input signed [23:0] value;
        reg signed [23:0] shifted;
        begin
            shifted=value >>> 4;
            if(shifted>24'sd32767) restore=16'h7fff;
            else if(shifted< -24'sd32768) restore=16'h8000;
            else restore=shifted[15:0];
        end
    endfunction
    assign m_axis_tdata={restore($signed(fft_data[47:24])),restore($signed(fft_data[23:0]))};
    assign m_axis_tuser=out_bin;
    assign m_axis_tvalid=fft_valid;
    assign m_axis_tlast=fft_last;
    pfb_fft16 fft (
        .aclk(aclk),.aresetn(aresetn),
        .s_axis_config_tdata(8'h15),.s_axis_config_tvalid(!configured && aresetn),.s_axis_config_tready(cfg_ready),
        .s_axis_data_tdata(fft_frame[send_index]),.s_axis_data_tvalid(state==SEND && configured),
        .s_axis_data_tready(fft_ready),.s_axis_data_tlast(send_index==15),
        .m_axis_data_tdata(fft_data),.m_axis_data_tvalid(fft_valid),.m_axis_data_tready(m_axis_tready),
        .m_axis_data_tlast(fft_last),
        .m_axis_status_tready(1'b1),
        .event_fft_overflow(overflow),.event_tlast_unexpected(unexpected),.event_tlast_missing(missing)
    );
    // Standard simple-dual-port BRAM template. In particular, the read register
    // has no reset/hold mux; pipeline validity and rd_zero handle unused reads.
    always @(posedge aclk) begin
        if(aresetn && s_axis_tvalid && s_axis_tready) history[wr_ptr]<=s_axis_tdata;
        rd_sample<=history[rd_addr];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=IDLE;wr_ptr<=0;endpoint<=0;history_valid<=0;frame_history<=0;
            input_mod<=0;rotation<=0;frame_rotation<=0;issue_index<=0;
            rd_valid<=0;prod_valid<=0;rd_index<=0;prod_index<=0;
            acc_i<=0;acc_q<=0;send_index<=0;configured<=0;out_bin<=0;error_sticky<=0;
        end else begin
            if(!configured && cfg_ready) configured<=1;
            if(overflow || unexpected || missing) error_sticky<=1;
            if(fft_valid && m_axis_tready) begin
                if(fft_last!=(out_bin==15)) error_sticky<=1;
                out_bin<=out_bin+1'b1;
            end
            if(s_axis_tvalid && s_axis_tready) begin
                wr_ptr<=wr_ptr+1'b1;input_mod<=input_mod+1'b1;
                if(history_valid!=127) history_valid<=history_valid+1'b1;
                if(input_mod==0) begin
                    endpoint<=wr_ptr;frame_history<=history_valid;
                    frame_rotation<=rotation;rotation<=!rotation;
                    issue_index<=0;state<=RUN;
                end
            end
            rd_valid<=state==RUN;
            if(state==RUN) begin
                rd_coeff<=offset<=frame_history ? coeff[offset] : 18'sd0;
                rd_zero<=offset>frame_history;
                rd_index<=issue_index;
                if(issue_index==127) state<=FLUSH;
                else issue_index<=issue_index+1'b1;
            end
            prod_valid<=rd_valid;
            if(rd_valid) begin
                // Explicit mask also prevents uninitialized BRAM simulation
                // values propagating through a multiply-by-zero at startup.
                prod_i<=rd_zero ? 34'sd0 : $signed(rd_sample[15:0])*rd_coeff;
                prod_q<=rd_zero ? 34'sd0 : $signed(rd_sample[31:16])*rd_coeff;
                prod_index<=rd_index;
            end
            if(prod_valid) begin
                acc_i<=sum_i;acc_q<=sum_q;
                if(prod_index[2:0]==7) begin
                    // Arithmetic >>9, exact signed24 bits under this prototype.
                    fft_frame[prod_index[6:3]]<={sum_q[32:9],sum_i[32:9]};
                    if(prod_index==127) begin state<=SEND;send_index<=0;end
                end
            end
            if(state==SEND && configured && fft_ready) begin
                if(send_index==15) state<=IDLE;
                else send_index<=send_index+1'b1;
            end
        end
    end
endmodule
