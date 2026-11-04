module axis_broadcast2 #(parameter WIDTH=93) (
    input wire aclk,input wire aresetn,
    input wire [WIDTH-1:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
    output wire [WIDTH-1:0] m0_axis_tdata,output wire m0_axis_tvalid,input wire m0_axis_tready,
    output wire [WIDTH-1:0] m1_axis_tdata,output wire m1_axis_tvalid,input wire m1_axis_tready
);
    reg [WIDTH-1:0] payload;
    reg [1:0] pending;
    assign s_axis_tready=(!pending[0] || m0_axis_tready) && (!pending[1] || m1_axis_tready);
    assign m0_axis_tdata=payload;assign m1_axis_tdata=payload;
    assign m0_axis_tvalid=pending[0];assign m1_axis_tvalid=pending[1];
    always @(posedge aclk) begin
        if(!aresetn) begin payload<=0;pending<=0;end
        else if(s_axis_tready) begin
            if(s_axis_tvalid) begin payload<=s_axis_tdata;pending<=3;end
            else pending<=0;
        end else begin
            if(m0_axis_tready) pending[0]<=0;
            if(m1_axis_tready) pending[1]<=0;
        end
    end
endmodule
