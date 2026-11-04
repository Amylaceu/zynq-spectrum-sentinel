// Buffered SCAP packetizer and 32-bit phase-accumulator DDS, DEC=1 only.
// IQ convention, rounding, control handshake: docs/x5_pl_interface.md.
module nco_capture #(
    parameter SINE_FILE="x5_nco_sine.hex"
) (
    input wire aclk,input wire aresetn,
    input wire arm_toggle,input wire clear_errors,
    input wire [3:0] cfg_ch_sel,input wire [31:0] cfg_fcw,
    input wire [3:0] cfg_dec,input wire [12:0] cfg_len,
    input wire [31:0] cfg_src,input wire [63:0] timestamp,
    output wire busy,output reg done_toggle,
    output reg [3:0] error_sticky,output reg [12:0] captured_count,
    input wire [31:0] s_axis_tdata,input wire [3:0] s_axis_tuser,
    input wire s_axis_tvalid,output wire s_axis_tready,input wire s_axis_tlast,
    output wire [31:0] m_axis_tdata,output wire [3:0] m_axis_tkeep,
    output wire m_axis_tvalid,input wire m_axis_tready,output wire m_axis_tlast
);
    localparam IDLE=0,ACQUIRE=1,FLUSH=2,HEADER=3,LOAD=4,DATA=5;
    reg [2:0] state;
    reg arm_seen,request_level;
    reg [3:0] channel;
    reg [31:0] fcw,src,phase;
    reg [12:0] length,received;
    reg [63:0] first_timestamp;
    reg checking;
    reg [3:0] expected_bin;
    wire selected=state==ACQUIRE && s_axis_tvalid && s_axis_tuser==channel;
    wire framing_fault=state==ACQUIRE && s_axis_tvalid &&
        (checking || selected) &&
        ((checking && s_axis_tuser!=expected_bin) || s_axis_tlast!=(s_axis_tuser==15));
    (* rom_style="block" *) reg signed [17:0] sine[0:4095];
    initial $readmemh(SINE_FILE,sine);
    wire [11:0] phase_index=phase[31:20];
    wire [11:0] cos_index=phase_index+12'd1024;
    reg signed [17:0] sin_value,cos_value;
    reg signed [15:0] sample_i,sample_q;
    reg signed [33:0] ic,qs,qc,is;
    reg signed [34:0] mixed_i,mixed_q;
    reg [2:0] valid_pipe;
    (* ram_style="block" *) reg [31:0] samples[0:4095];
    reg [2:0] header_index;
    reg [11:0] read_index;
    reg [31:0] read_data,header_data;
    assign s_axis_tready=aresetn;
    assign busy=state!=IDLE;
    assign m_axis_tvalid=aresetn && (state==HEADER || state==DATA);
    assign m_axis_tdata=state==HEADER ? header_data : read_data;
    assign m_axis_tkeep=4'hf;
    assign m_axis_tlast=state==DATA && {1'b0,read_index}==length-1'b1;
    function [15:0] quantize;
        input signed [34:0] value;
        reg signed [34:0] shifted;
        begin
            shifted=value >>> 16;
            if(shifted>35'sd32767) quantize=16'h7fff;
            else if(shifted< -35'sd32768) quantize=16'h8000;
            else quantize=shifted[15:0];
        end
    endfunction
    always @* begin
        case(header_index)
            0:header_data=32'h53434150;
            1:header_data=first_timestamp[31:0];
            2:header_data=first_timestamp[63:32];
            3:header_data={28'b0,channel};
            4:header_data=fcw;
            5:header_data=32'd1;
            6:header_data={19'b0,length};
            default:header_data=src;
        endcase
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=IDLE;arm_seen<=0;request_level<=0;done_toggle<=0;
            error_sticky<=0;captured_count<=0;received<=0;valid_pipe<=0;
            channel<=0;fcw<=0;src<=0;length<=0;phase<=0;checking<=0;
            expected_bin<=0;first_timestamp<=0;header_index<=0;read_index<=0;
        end else begin
            if(clear_errors) error_sticky<=0;
            valid_pipe<={valid_pipe[1:0],selected};
            if(selected) begin
                // Two synchronous reads infer a dual-port sine ROM.
                sin_value<=sine[phase_index];cos_value<=sine[cos_index];
                sample_i<=$signed(s_axis_tdata[15:0]);sample_q<=$signed(s_axis_tdata[31:16]);
                phase<=phase+fcw;
                if(received==0) first_timestamp<=timestamp;
                received<=received+1'b1;
                if(received==length-1'b1) state<=FLUSH;
            end
            if(state==ACQUIRE && s_axis_tvalid && (checking || selected)) begin
                checking<=1;expected_bin<=s_axis_tuser+1'b1;
            end
            if(valid_pipe[0]) begin
                ic<=sample_i*cos_value;qs<=sample_q*sin_value;
                qc<=sample_q*cos_value;is<=sample_i*sin_value;
            end
            if(valid_pipe[1]) begin
                mixed_i<={ic[33],ic}+{qs[33],qs};
                mixed_q<={qc[33],qc}-{is[33],is};
            end
            if(valid_pipe[2] && (state==ACQUIRE || state==FLUSH)) begin
                samples[captured_count[11:0]]<={quantize(mixed_q),quantize(mixed_i)};
                captured_count<=captured_count+1'b1;
                if(captured_count==length-1'b1) begin state<=HEADER;header_index<=0;end
            end
            if(state==HEADER && m_axis_tready) begin
                if(header_index==7) begin state<=LOAD;read_index<=0;end
                else header_index<=header_index+1'b1;
            end
            if(state==LOAD) begin read_data<=samples[read_index];state<=DATA;end
            if(state==DATA && m_axis_tready) begin
                if(m_axis_tlast) begin state<=IDLE;done_toggle<=request_level;end
                else begin read_index<=read_index+1'b1;state<=LOAD;end
            end
            if(arm_toggle!=arm_seen) begin
                arm_seen<=arm_toggle;
                if(state!=IDLE) error_sticky[1]<=1;
                else if(cfg_dec!=1 || cfg_len==0 || cfg_len>4096) error_sticky[0]<=1;
                else begin
                    channel<=cfg_ch_sel;fcw<=cfg_fcw;src<=cfg_src;length<=cfg_len;
                    request_level<=arm_toggle;state<=ACQUIRE;checking<=0;
                    phase<=0;received<=0;captured_count<=0;valid_pipe<=0;
                end
            end
            if(framing_fault) begin
                error_sticky[2]<=1;state<=IDLE;valid_pipe<=0;checking<=0;
            end
        end
    end
endmodule
