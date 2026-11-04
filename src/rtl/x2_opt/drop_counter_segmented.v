// Isolated timing candidate; NOT connected to a deployed ADC tap.
// Same-cycle saturating event count and registered Gray encoding. Registered
// prefix carries split the increment into BYTE_WIDTH-bit chains; they describe
// the CURRENT count, so even consecutive events have no extra count latency.
module drop_counter_segmented #(
    parameter WIDTH=32,
    parameter BYTE_WIDTH=8
) (
    input wire clk, input wire reset, input wire event_valid,
    output reg [WIDTH-1:0] binary_count,
    output reg [WIDTH-1:0] gray_count
);
    localparam SEGMENTS=WIDTH/BYTE_WIDTH;
    reg [SEGMENTS:1] prefix_full;
    wire [WIDTH-1:0] next_count;
    wire increment=event_valid && !prefix_full[SEGMENTS];
    genvar segment;
    generate for(segment=0;segment<SEGMENTS;segment=segment+1) begin: slice
        if(segment==0) begin
            assign next_count[segment*BYTE_WIDTH+:BYTE_WIDTH]=
                binary_count[segment*BYTE_WIDTH+:BYTE_WIDTH]+increment;
        end else begin
            assign next_count[segment*BYTE_WIDTH+:BYTE_WIDTH]=
                binary_count[segment*BYTE_WIDTH+:BYTE_WIDTH]+(increment && prefix_full[segment]);
        end
        always @(posedge clk) begin
            if(reset) prefix_full[segment+1]<=0;
            else prefix_full[segment+1]<=(&next_count[(segment+1)*BYTE_WIDTH-1:0]);
        end
    end endgenerate
    always @(posedge clk) begin
        if(reset) begin binary_count<=0;gray_count<=0;end
        else begin binary_count<=next_count;gray_count<=(next_count>>1)^next_count;end
    end
    // Supported widths are positive multiples of BYTE_WIDTH (at least two
    // segments). Reset must be asserted before the first event, as in adc_tap.
endmodule
