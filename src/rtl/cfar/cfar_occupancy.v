module cfar_occupancy (
    input wire aclk,input wire aresetn,input wire clear_request,
    input wire [10:0] bin_index,input wire hit,input wire valid,input wire last,
    input wire [10:0] mmio_index,output reg [15:0] mmio_data,
    output reg clearing,output reg [31:0] frame_count
);
    (* ram_style="block" *) reg [15:0] counts[0:2047];
    (* ram_style="block" *) reg [15:0] counts_mmio[0:2047];
    reg [10:0] clear_index,pending_index;
    reg [15:0] old_count;
    reg pending,increment;
    wire write_enable=clearing || (pending && increment);
    wire [10:0] write_address=clearing ? clear_index : pending_index;
    wire [15:0] write_data=clearing ? 16'b0 : ((&old_count)?old_count:old_count+16'd1);
    always @(posedge aclk) begin
        if(write_enable) begin
            counts[write_address]<=write_data;
            counts_mmio[write_address]<=write_data;
        end
        if(valid) old_count<=counts[bin_index];
        mmio_data<=counts_mmio[mmio_index];
    end
    always @(posedge aclk) begin
        if(!aresetn) begin clearing<=1;clear_index<=0;pending<=0;increment<=0;frame_count<=0;end
        else begin
            pending<=valid;pending_index<=bin_index;increment<=hit;
            if(valid && last) frame_count<=frame_count+1;
            if(clear_request) begin clearing<=1;clear_index<=0;frame_count<=0;pending<=0;end
            else if(clearing) begin
                if(clear_index==2047) clearing<=0;else clear_index<=clear_index+1;
            end
        end
    end
endmodule
