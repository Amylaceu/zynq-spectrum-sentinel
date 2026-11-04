// Audio-clock-domain serializer. Supply a verified 256*Fs MCLK (nominal12.288MHz).
// 32-bit I2S slots, 24-bit signed mono duplicated to both channels. The receiver
// sees one dummy bit after each LRCK transition before the MSB, not left-justified.
// Feed via an asynchronous AXIS FIFO; never wire unsynchronized PS-domain signals.
module i2s_tx_y3 (
    input wire mclk,
    input wire aresetn,
    input wire enable,
    input wire [31:0] s_axis_tdata,
    input wire s_axis_tvalid,
    output wire s_axis_tready,
    output wire bclk,
    output reg lrck,
    output reg dacdat,
    output reg [31:0] frames,
    output reg [31:0] underflows
);
    reg [7:0] phase;
    reg [23:0] sample;
    wire [5:0] slot=phase[7:2];
    assign bclk=phase[1];
    assign s_axis_tready=aresetn && enable && phase==0;
    always @(posedge mclk) begin
        if(!aresetn) begin
            phase<=0;sample<=0;lrck<=0;dacdat<=0;frames<=0;underflows<=0;
        end else begin
            phase<=phase+1'b1;
            if(phase==0) begin
                sample<=enable && s_axis_tvalid ? s_axis_tdata[23:0] : 24'b0;
                if(enable) begin
                    if(frames!=32'hffffffff) frames<=frames+1'b1;
                    if(!s_axis_tvalid && underflows!=32'hffffffff) underflows<=underflows+1'b1;
                end
            end
            if(phase[1:0]==3) begin
                lrck<=slot[5];
                if(!enable) dacdat<=0;
                else if(slot>=1 && slot<=24) dacdat<=sample[24-slot];
                else if(slot>=33 && slot<=56) dacdat<=sample[56-slot];
                else dacdat<=0;
            end
        end
    end
endmodule
