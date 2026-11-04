// X5: 2x64KiB UI banks; rotate right-side writes to cancel SSD1963 full-width scroll.
module lcd_render_scheduler_x5 (
    input wire sys_clk,input wire aresetn,input wire initialized,input wire enable,
    input wire frame_available,output wire accept_frame,
    output wire [9:0] read_column,input wire [15:0] spec_db,threshold_db,
    input wire [31:0] ui_epoch,output reg [31:0] ui_applied_epoch,
    output wire [31:0] ui_address,input wire [31:0] ui_word,
    output reg [1:0] op_kind,output reg [15:0] op_p0,op_p1,op_p2,op_p3,
    output wire [15:0] fill_color,output reg op_valid,input wire op_ready,input wire op_done,
    output wire [15:0] pixel_data,output wire pixel_valid,input wire pixel_ready,output wire pixel_last,
    output reg [31:0] frame_count,output reg [31:0] frame_gray,output wire busy
);
    localparam BOOT=0,CLEAR_REQ=1,CLEAR_WAIT=2,AREA_REQ=3,AREA_WAIT=4,IDLE=5,
        SPEC_REQ=6,SPEC_PREF=7,SPEC_PIX=8,SPEC_WAIT=9,
        WF_REQ=10,WF_PREF=11,WF_PIX=12,WF_WAIT=13,SCROLL_REQ=14,SCROLL_WAIT=15,
        UI_REQ=16,UI_PREF=17,UI_PIX=18,UI_WAIT=19;
    reg [4:0] state;
    reg [9:0] x;
    reg [7:0] y,waterfall_head;
    reg [1:0] prefetch;
    reg [15:0] previous_spec;
    reg [15:0] cached_spec,cached_threshold,trace_buffer,waterfall_buffer;
    reg [17:0] ui_index;
    reg [17:0] ui_end;
    reg [2:0] ui_segment;
    reg ui_full_update,ui_has_page,frame_pending;
    reg [31:0] ui_job_epoch;
    wire [15:0] trace_pixel,waterfall_pixel;
    wire [7:0] next_head=waterfall_head==239 ? 0 : waterfall_head+8'd1;
    wire [1:0] ui_code=(ui_word>>{ui_index[3:0],1'b0});
    wire [15:0] ui_color=(ui_code==0) ? 16'h0000 : ((ui_code==1)?16'hffff:((ui_code==2)?16'hffe0:16'h07ff));
    lcd_trace_pixel renderer(.x(x),.y(y),.spec_db(cached_spec),
        .previous_spec_db(x==0 ? cached_spec : previous_spec),.threshold_db(cached_threshold),
        .spectrum_pixel(trace_pixel),.waterfall_pixel(waterfall_pixel));
    assign accept_frame=state==IDLE && enable && ui_epoch==ui_applied_epoch && frame_available;
    assign read_column=x;
    assign ui_address={15'b0,ui_job_epoch[0],ui_index[17:4],2'b0};
    assign pixel_data=(state==UI_PIX) ? ui_color : ((state==WF_PIX)?waterfall_buffer:trace_buffer);
    assign pixel_valid=state==SPEC_PIX || state==WF_PIX || state==UI_PIX;
    assign pixel_last=(state==SPEC_PIX && x==559 && y==159) || (state==WF_PIX && x==559) ||
                      (state==UI_PIX && ui_index==ui_end);
    assign fill_color=0;assign busy=state!=IDLE;
    always @* begin
        op_valid=0;op_kind=0;op_p0=0;op_p1=0;op_p2=0;op_p3=0;
        case(state)
            CLEAR_REQ:begin op_valid=1;op_kind=1;op_p1=799;op_p3=479;end
            AREA_REQ:begin op_valid=1;op_kind=2;op_p0=160;op_p1=240;op_p2=80;end
            SPEC_REQ:begin op_valid=1;op_p1=559;op_p3=159;end
            WF_REQ:begin op_valid=1;op_p1=559;op_p2=160+waterfall_head;op_p3=160+waterfall_head;end
            SCROLL_REQ:begin op_valid=1;op_kind=3;op_p0=160+next_head;end
            UI_REQ:begin
                op_valid=1;
                case(ui_segment)
                    0:begin op_p0=560;op_p1=799;op_p3=159;end
                    1:begin op_p1=799;op_p2=400;op_p3=479;end
                    2:begin op_p0=560;op_p1=799;op_p2=160+waterfall_head;op_p3=399;end
                    3:begin op_p0=560;op_p1=799;op_p2=160;op_p3=159+waterfall_head;end
                    default:begin end
                endcase
            end
        endcase
    end
    always @(posedge sys_clk) begin
        if(!aresetn) begin
            state<=BOOT;x<=0;y<=0;prefetch<=0;waterfall_head<=0;previous_spec<=16'h8000;
            ui_index<=0;ui_end<=0;ui_segment<=0;ui_full_update<=0;ui_has_page<=0;frame_pending<=0;ui_job_epoch<=0;ui_applied_epoch<=0;frame_count<=0;frame_gray<=0;
            cached_spec<=16'h8000;cached_threshold<=16'h8000;trace_buffer<=0;waterfall_buffer<=0;
        end else begin
            if((state==SPEC_PREF || state==WF_PREF) && prefetch==2) begin cached_spec<=spec_db;cached_threshold<=threshold_db;end
            if((state==SPEC_PREF || state==WF_PREF) && prefetch==1) begin trace_buffer<=trace_pixel;waterfall_buffer<=waterfall_pixel;end
            case(state)
                BOOT:if(initialized) state<=CLEAR_REQ;
                CLEAR_REQ:if(op_ready) state<=CLEAR_WAIT;
                CLEAR_WAIT:if(op_done) state<=AREA_REQ;
                AREA_REQ:if(op_ready) state<=AREA_WAIT;
                AREA_WAIT:if(op_done) state<=IDLE;
                IDLE:begin
                    if(ui_epoch!=ui_applied_epoch) begin
                        ui_job_epoch<=ui_epoch;ui_full_update<=1;ui_segment<=0;ui_index<=0;ui_end<=38399;state<=UI_REQ;
                    end else if(enable && frame_available) begin x<=0;y<=0;state<=SPEC_REQ;end
                end
                SPEC_REQ:if(op_ready) begin state<=SPEC_PREF;prefetch<=3;end
                SPEC_PREF:if(prefetch==0) state<=SPEC_PIX;else prefetch<=prefetch-1;
                SPEC_PIX:if(pixel_ready) begin
                    previous_spec<=cached_spec;
                    if(x==559 && y==159) state<=SPEC_WAIT;
                    else begin
                        if(x==559) begin x<=0;y<=y+1;end else x<=x+1;
                        prefetch<=3;state<=SPEC_PREF;
                    end
                end
                SPEC_WAIT:if(op_done) begin x<=0;state<=WF_REQ;end
                WF_REQ:if(op_ready) begin state<=WF_PREF;prefetch<=3;end
                WF_PREF:if(prefetch==0) state<=WF_PIX;else prefetch<=prefetch-1;
                WF_PIX:if(pixel_ready) begin
                    if(x==559) state<=WF_WAIT;
                    else begin x<=x+1;prefetch<=3;state<=WF_PREF;end
                end
                WF_WAIT:if(op_done) state<=SCROLL_REQ;
                SCROLL_REQ:if(op_ready) state<=SCROLL_WAIT;
                SCROLL_WAIT:if(op_done) begin
                    waterfall_head<=next_head;
                    if(ui_has_page) begin
                        frame_pending<=1;ui_full_update<=0;ui_segment<=2;
                        ui_index<=38400;ui_end<=95999-next_head*240;state<=UI_REQ;
                    end else begin
                        frame_count<=frame_count+1;
                        frame_gray<=((frame_count+32'd1)>>1)^(frame_count+32'd1);state<=IDLE;
                    end
                end
                UI_REQ:if(op_ready) begin state<=UI_PREF;prefetch<=1;end
                UI_PREF:if(prefetch==0) state<=UI_PIX;else prefetch<=prefetch-1;
                UI_PIX:if(pixel_ready) begin
                    if(pixel_last) state<=UI_WAIT;
                    else begin ui_index<=ui_index+1;prefetch<=1;state<=UI_PREF;end
                end
                UI_WAIT:if(op_done) begin
                    case(ui_segment)
                        0:begin ui_segment<=1;ui_index<=96000;ui_end<=159999;state<=UI_REQ;end
                        1:begin
                            ui_segment<=2;ui_index<=38400;ui_end<=95999-waterfall_head*240;state<=UI_REQ;
                        end
                        2:begin
                            if(waterfall_head!=0) begin
                                ui_segment<=3;ui_index<=ui_end+1;ui_end<=95999;state<=UI_REQ;
                            end else begin
                                if(ui_full_update) begin ui_applied_epoch<=ui_job_epoch;ui_has_page<=1;end
                                if(frame_pending) begin
                                    frame_count<=frame_count+1;frame_gray<=((frame_count+32'd1)>>1)^(frame_count+32'd1);
                                    frame_pending<=0;
                                end
                                state<=IDLE;
                            end
                        end
                        3:begin
                            if(ui_full_update) begin ui_applied_epoch<=ui_job_epoch;ui_has_page<=1;end
                            if(frame_pending) begin
                                frame_count<=frame_count+1;frame_gray<=((frame_count+32'd1)>>1)^(frame_count+32'd1);
                                frame_pending<=0;
                            end
                            state<=IDLE;
                        end
                        default:state<=IDLE;
                    endcase
                end
            endcase
        end
    end
endmodule
