// Two banks; only complete, equal-sequence spectrum/threshold pairs are published.
module lcd_snapshot (
    input wire dsp_clk,input wire dsp_aresetn,
    input wire [15:0] s_spec_tdata,input wire [9:0] s_spec_tuser,
    input wire s_spec_tvalid,input wire s_spec_tlast,
    input wire [15:0] s_thr_tdata,input wire [9:0] s_thr_tuser,
    input wire s_thr_tvalid,input wire s_thr_tlast,
    output reg [31:0] dropped_frames,output reg [31:0] dropped_gray,output reg error_sticky,
    input wire lcd_clk,input wire lcd_aresetn,
    output wire frame_available,input wire accept_frame,
    output reg [31:0] frame_id,
    input wire [9:0] read_column,output reg [15:0] spec_data,threshold_data
);
    (* ram_style="block" *) reg [15:0] spectrum[0:2047];
    (* ram_style="block" *) reg [15:0] threshold[0:2047];
    reg [31:0] bank_id[0:1];
    reg request_toggle,ack_toggle,read_bank;
    (* ASYNC_REG="TRUE" *) reg [1:0] ack_sync,request_sync;
    reg reserved,capture_spec,spec_complete,thr_complete;
    reg [31:0] spec_sequence,thr_sequence,capture_id;
    reg [9:0] spec_index,thr_index;
    wire slot_free=!reserved && request_toggle==ack_sync[1];
    wire write_spec=s_spec_tvalid && s_spec_tuser<560 && (s_spec_tuser==0 ? slot_free : capture_spec);
    wire write_thr=s_thr_tvalid && s_thr_tuser<560 && reserved && thr_sequence==capture_id;
    assign frame_available=request_sync[1]!=ack_toggle;
    always @(posedge dsp_clk) begin
        if(write_spec) spectrum[{request_toggle,s_spec_tuser}]<=s_spec_tdata;
        if(write_thr) threshold[{request_toggle,s_thr_tuser}]<=s_thr_tdata;
        if(reserved && spec_complete && thr_complete) bank_id[request_toggle]<=capture_id;
    end
    always @(posedge lcd_clk) begin
        spec_data<=spectrum[{read_bank,read_column}];
        threshold_data<=threshold[{read_bank,read_column}];
    end
    always @(posedge dsp_clk) begin
        if(!dsp_aresetn) begin
            request_toggle<=0;ack_sync<=0;reserved<=0;capture_spec<=0;
            spec_complete<=0;thr_complete<=0;spec_sequence<=0;thr_sequence<=0;
            capture_id<=0;spec_index<=0;thr_index<=0;dropped_frames<=0;dropped_gray<=0;error_sticky<=0;
        end else begin
            ack_sync<={ack_sync[0],ack_toggle};
            if(s_spec_tvalid) begin
                if(s_spec_tuser!=spec_index || s_spec_tlast!=(spec_index==559)) error_sticky<=1;
                spec_index<=s_spec_tlast ? 0 : spec_index+1;
                if(s_spec_tuser==0) begin
                    capture_spec<=slot_free;
                    if(slot_free) begin
                        reserved<=1;capture_id<=spec_sequence;spec_complete<=0;thr_complete<=0;
                    end else begin
                        dropped_frames<=dropped_frames+1;
                        dropped_gray<=((dropped_frames+32'd1)>>1)^(dropped_frames+32'd1);
                    end
                end
                if(s_spec_tlast) begin
                    spec_sequence<=spec_sequence+1;
                    if(capture_spec) spec_complete<=1;
                    capture_spec<=0;
                end
            end
            if(s_thr_tvalid) begin
                if(s_thr_tuser!=thr_index || s_thr_tlast!=(thr_index==559)) error_sticky<=1;
                thr_index<=s_thr_tlast ? 0 : thr_index+1;
                if(s_thr_tlast) begin
                    thr_sequence<=thr_sequence+1;
                    if(reserved && thr_sequence==capture_id) thr_complete<=1;
                end
            end
            if(reserved && spec_complete && thr_complete) begin
                request_toggle<=!request_toggle;reserved<=0;spec_complete<=0;thr_complete<=0;
            end
        end
    end
    always @(posedge lcd_clk) begin
        if(!lcd_aresetn) begin request_sync<=0;ack_toggle<=0;read_bank<=0;frame_id<=0;end
        else begin
            request_sync<={request_sync[0],request_toggle};
            if(accept_frame && frame_available) begin
                read_bank<=!request_sync[1];frame_id<=bank_id[!request_sync[1]];
                ack_toggle<=request_sync[1];
            end
        end
    end
endmodule
