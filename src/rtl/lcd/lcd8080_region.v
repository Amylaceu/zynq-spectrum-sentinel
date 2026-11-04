module lcd8080_region #(parameter SCREEN_WIDTH=800,parameter SCREEN_HEIGHT=480)(
    input wire sys_clk,input wire aresetn,
    input wire [1:0] op_kind,input wire [15:0] op_p0,op_p1,op_p2,op_p3,
    input wire [15:0] fill_color,input wire op_valid,output wire op_ready,
    input wire [15:0] s_axis_pixel_tdata,input wire s_axis_pixel_tvalid,
    output wire s_axis_pixel_tready,input wire s_axis_pixel_tlast,
    output wire [16:0] m_axis_cmd_tdata,output wire m_axis_cmd_tvalid,input wire m_axis_cmd_tready,
    output wire busy,output reg done,output reg error_sticky
);
    localparam IDLE=0,WORDS=1,PIXELS=2;
    reg [1:0] state,kind;
    reg [15:0] p0,p1,p2,p3,color;
    reg [3:0] word_index;
    reg [18:0] pixels_left;
    reg [15:0] scroll_top,scroll_height;
    reg [16:0] command;
    wire [17:0] requested_sum={2'b0,op_p0}+{2'b0,op_p1}+{2'b0,op_p2};
    wire rectangle_ok=op_p0<=op_p1 && op_p2<=op_p3 && op_p1<SCREEN_WIDTH && op_p3<SCREEN_HEIGHT;
    wire area_ok=requested_sum==SCREEN_HEIGHT && op_p1!=0;
    wire start_ok=op_p0>=scroll_top && {1'b0,op_p0}<({1'b0,scroll_top}+{1'b0,scroll_height});
    wire [31:0] area=({16'b0,op_p1}-{16'b0,op_p0}+1)*({16'b0,op_p3}-{16'b0,op_p2}+1);
    assign op_ready=state==IDLE;assign busy=state!=IDLE;
    assign m_axis_cmd_tdata=state==WORDS ? command : {1'b1,kind==1 ? color : s_axis_pixel_tdata};
    assign m_axis_cmd_tvalid=state==WORDS || (state==PIXELS && (kind==1 || s_axis_pixel_tvalid));
    assign s_axis_pixel_tready=state==PIXELS && kind==0 && m_axis_cmd_tready;
    always @* begin
        command=0;
        if(kind<2) case(word_index)
            0:command=17'h0002a;
            1:command={1'b1,8'b0,p0[15:8]};2:command={1'b1,8'b0,p0[7:0]};
            3:command={1'b1,8'b0,p1[15:8]};4:command={1'b1,8'b0,p1[7:0]};
            5:command=17'h0002b;
            6:command={1'b1,8'b0,p2[15:8]};7:command={1'b1,8'b0,p2[7:0]};
            8:command={1'b1,8'b0,p3[15:8]};9:command={1'b1,8'b0,p3[7:0]};
            10:command=17'h0002c;
            default:command=0;
        endcase
        else if(kind==2) case(word_index)
            0:command=17'h00033;
            1:command={1'b1,8'b0,p0[15:8]};2:command={1'b1,8'b0,p0[7:0]};
            3:command={1'b1,8'b0,p1[15:8]};4:command={1'b1,8'b0,p1[7:0]};
            5:command={1'b1,8'b0,p2[15:8]};6:command={1'b1,8'b0,p2[7:0]};
            default:command=0;
        endcase
        else case(word_index)
            0:command=17'h00037;
            1:command={1'b1,8'b0,p0[15:8]};2:command={1'b1,8'b0,p0[7:0]};
            default:command=0;
        endcase
    end
    always @(posedge sys_clk) begin
        if(!aresetn) begin
            state<=IDLE;word_index<=0;done<=0;error_sticky<=0;
            scroll_top<=0;scroll_height<=SCREEN_HEIGHT;
        end else begin
            done<=0;
            if(op_valid && op_ready) begin
                if((op_kind<2 && !rectangle_ok) || (op_kind==2 && !area_ok) || (op_kind==3 && !start_ok)) begin error_sticky<=1;done<=1;end
                else begin
                    state<=WORDS;kind<=op_kind;p0<=op_p0;p1<=op_p1;p2<=op_p2;p3<=op_p3;color<=fill_color;
                    word_index<=0;pixels_left<=area[18:0];
                end
            end
            if(m_axis_cmd_tvalid && m_axis_cmd_tready) begin
                if(state==WORDS) begin
                    if(kind<2 && word_index==10) state<=PIXELS;
                    else if((kind==2 && word_index==6) || (kind==3 && word_index==2)) begin
                        state<=IDLE;done<=1;
                        if(kind==2) begin scroll_top<=p0;scroll_height<=p1;end
                    end else word_index<=word_index+1;
                end else if(state==PIXELS) begin
                    if(kind==0 && s_axis_pixel_tlast!=(pixels_left==1)) error_sticky<=1;
                    if(pixels_left==1) begin state<=IDLE;done<=1;end
                    else pixels_left<=pixels_left-1;
                end
            end
        end
    end
endmodule
