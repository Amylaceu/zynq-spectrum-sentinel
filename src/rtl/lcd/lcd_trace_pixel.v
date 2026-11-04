module lcd_trace_pixel (
    input wire [9:0] x,input wire [7:0] y,
    input wire [15:0] spec_db,previous_spec_db,threshold_db,
    output reg [15:0] spectrum_pixel,output reg [15:0] waterfall_pixel
);
    function [7:0] ordinate;
        input [15:0] raw;
        reg signed [16:0] delta;
        reg [15:0] magnitude;
        begin
            delta=17'sd23119-$signed(raw);magnitude=delta[15:0];
            if(raw==16'h8000 || delta>=25600) ordinate=159;
            else if(delta<=0) ordinate=0;
            else ordinate=magnitude/16'd160;
        end
    endfunction
    wire [7:0] current_y=ordinate(spec_db);
    wire [7:0] previous_y=ordinate(previous_spec_db);
    wire [7:0] threshold_y=ordinate(threshold_db);
    wire [7:0] trace_low=current_y<previous_y ? current_y : previous_y;
    wire [7:0] trace_high=current_y>previous_y ? current_y : previous_y;
    reg signed [16:0] delta;
    reg [15:0] magnitude;
    reg [7:0] level;
    reg [7:0] intensity;
    always @* begin
        spectrum_pixel=((y%32)==0 || (x%80)==0) ? 16'h18c3 : 16'h0000;
        if(y>=trace_low && y<=trace_high) spectrum_pixel=16'h07e0;
        if(y==threshold_y && x[2:0]<4) spectrum_pixel=16'hf800;
        delta=17'sd23119-$signed(spec_db);magnitude=delta[15:0];
        if(spec_db==16'h8000 || delta>=25600) level=0;
        else if(delta<=0) level=255;
        else level=8'd255-magnitude/16'd100;
        intensity=level[7:0];
        case(intensity[7:6])
            0:waterfall_pixel={5'b0,6'b0,intensity[5:1]};
            1:waterfall_pixel={5'b0,intensity[5:0],5'd31};
            2:waterfall_pixel={intensity[5:1],6'd63,(5'd31-intensity[5:1])};
            3:waterfall_pixel={5'd31,(6'd63-intensity[5:0]),5'b0};
        endcase
    end
endmodule
