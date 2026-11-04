// Reference copied from the X2 ADC tap count expression, no deployed changes.
module drop_counter_reference (
    input wire clk,reset,event_valid,
    output reg [31:0] binary_count,gray_count
);
    wire [31:0] next_count=event_valid && binary_count!=32'hffffffff ? binary_count+1'b1 : binary_count;
    always @(posedge clk) begin
        if(reset) begin binary_count<=0;gray_count<=0;end
        else begin binary_count<=next_count;gray_count<=(next_count>>1)^next_count;end
    end
endmodule
