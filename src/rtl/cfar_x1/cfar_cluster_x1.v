// Standalone X1 cluster engine; not integrated into sentinel_v1.
// blocked is the frame-snapshotted explicit/DC mask union. It cuts clusters.
// Input bin_index must be 0..2047, last asserted exactly at bin2047.
module cfar_cluster_x1 (
    input wire aclk, input wire aresetn,
    input wire [7:0] cfg_gap, input wire [11:0] cfg_min_width,
    input wire [11:0] cfg_alarm_limit, input wire [1:0] frame_error,
    input wire [31:0] power, input wire hit, input wire blocked,
    input wire [10:0] bin_index, input wire last, input wire valid,
    output wire ready, output wire busy,
    output reg irq_list_ready, output reg [31:0] frame_count,
    output reg [5:0] target_count,
    output reg [11:0] frame_hits, raw_count, filtered_count, candidate_count,
    output reg [31:0] status_latch,
    output reg alarm,
    input wire [6:0] mmio_word_addr, output wire [31:0] mmio_data,
    output wire [127:0] m_axis_tdata, output wire m_axis_tvalid,
    input wire m_axis_tready, output wire m_axis_tlast
);
    localparam SCAN=0, CANDIDATE=1, SEARCH=2, SHIFT=3, PUBLISH=4, STREAM=5, CLEAR=6;
    reg [2:0] state;
    reg [127:0] work_list[0:31], published[0:31];
    reg [5:0] work_count, search_index, shift_index, insert_position;
    reg [4:0] stream_index;
    reg [7:0] gap_limit, gap_count;
    reg [11:0] min_width, alarm_limit, hits, raw, filtered, candidates;
    reg active, frame_end;
    reg [10:0] start_bin, stop_bin, peak_bin, gap_peak_bin;
    reg [31:0] peak, sum, gap_sum, gap_peak;
    reg [127:0] candidate, closing_record;
    reg close_cluster;
    reg [31:0] merged_peak, merged_sum;
    reg [10:0] merged_peak_bin;
    integer index;
    wire fire=valid && ready;
    wire effective_hit=hit && !blocked;
    assign ready=state==SCAN;
    assign busy=state!=SCAN || active;
    assign m_axis_tvalid=state==STREAM;
    assign m_axis_tdata=published[stream_index];
    assign m_axis_tlast=state==STREAM && stream_index==target_count-1;
    assign mmio_data=published[mmio_word_addr[6:2]][32*mmio_word_addr[1:0]+:32];

    function [31:0] sat_add;
        input [31:0] a,b;
        reg [32:0] value;
        begin value={1'b0,a}+{1'b0,b};sat_add=value[32]?32'hffffffff:value[31:0];end
    endfunction

    always @* begin
        merged_peak=peak;merged_peak_bin=peak_bin;
        if(gap_peak>merged_peak) begin merged_peak=gap_peak;merged_peak_bin=gap_peak_bin;end
        if(power>merged_peak) begin merged_peak=power;merged_peak_bin=bin_index;end
        merged_sum=sat_add(sat_add(sum,gap_sum),power);
        close_cluster=0;closing_record=0;
        if(fire) begin
            if(effective_hit && last) begin
                close_cluster=1;
                if(active) closing_record={merged_sum,merged_peak,16'b0,{5'b0,merged_peak_bin},{5'b0,bin_index},{5'b0,start_bin}};
                else closing_record={power,power,16'b0,{5'b0,bin_index},{5'b0,bin_index},{5'b0,bin_index}};
            end else if(!effective_hit && active && (blocked || last || gap_count==gap_limit)) begin
                close_cluster=1;
                closing_record={sum,peak,16'b0,{5'b0,peak_bin},{5'b0,stop_bin},{5'b0,start_bin}};
            end
        end
    end

    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=SCAN;work_count<=0;active<=0;frame_end<=0;
            gap_limit<=6;min_width<=2;alarm_limit<=1;gap_count<=0;gap_sum<=0;gap_peak<=0;
            start_bin<=0;stop_bin<=0;peak_bin<=0;gap_peak_bin<=0;peak<=0;sum<=0;
            hits<=0;raw<=0;filtered<=0;candidates<=0;
            target_count<=0;frame_count<=0;frame_hits<=0;raw_count<=0;filtered_count<=0;candidate_count<=0;
            status_latch<=0;alarm<=0;irq_list_ready<=0;stream_index<=0;
            candidate<=0;search_index<=0;shift_index<=0;insert_position<=0;
        end else begin
            irq_list_ready<=0;
            case(state)
                SCAN: if(fire) begin
                    if(bin_index==0) begin gap_limit<=cfg_gap;min_width<=cfg_min_width;alarm_limit<=cfg_alarm_limit;end
                    if(effective_hit) begin
                        hits<=hits+1;
                        if(!active) begin start_bin<=bin_index;peak_bin<=bin_index;peak<=power;sum<=power;end
                        else begin peak<=merged_peak;peak_bin<=merged_peak_bin;sum<=merged_sum;end
                        active<=1;stop_bin<=bin_index;gap_count<=0;gap_sum<=0;gap_peak<=0;
                    end else if(active) begin
                        if(blocked || last || gap_count==gap_limit) begin
                            active<=0;gap_count<=0;gap_sum<=0;gap_peak<=0;
                        end else begin
                            gap_count<=gap_count+1;gap_sum<=sat_add(gap_sum,power);
                            if(gap_count==0 || power>gap_peak) begin gap_peak<=power;gap_peak_bin<=bin_index;end
                        end
                    end
                    if(close_cluster) begin
                        candidate<=closing_record;raw<=raw+1;frame_end<=last;state<=CANDIDATE;active<=0;
                    end else if(last) begin frame_end<=1;state<=PUBLISH;active<=0;end
                end
                CANDIDATE: begin
                    if(({1'b0,candidate[31:16]}-{1'b0,candidate[15:0]}+17'd1)<min_width) begin
                        filtered<=filtered+1;state<=frame_end?PUBLISH:SCAN;
                    end else begin candidates<=candidates+1;search_index<=0;state<=SEARCH;end
                end
                SEARCH: begin
                    if(search_index==work_count) begin
                        if(work_count<32) begin
                            insert_position<=search_index;shift_index<=work_count;state<=SHIFT;
                        end else state<=frame_end?PUBLISH:SCAN;
                    end else if(candidate[95:64]>work_list[search_index[4:0]][95:64] ||
                        (candidate[95:64]==work_list[search_index[4:0]][95:64] && candidate[15:0]<work_list[search_index[4:0]][15:0])) begin
                        insert_position<=search_index;shift_index<=(work_count<32)?work_count:31;state<=SHIFT;
                    end else search_index<=search_index+1;
                end
                SHIFT: begin
                    if(shift_index>insert_position) begin
                        work_list[shift_index[4:0]]<=work_list[shift_index-1];shift_index<=shift_index-1;
                    end else begin
                        work_list[insert_position[4:0]]<=candidate;
                        if(work_count<32) work_count<=work_count+1;
                        state<=frame_end?PUBLISH:SCAN;
                    end
                end
                PUBLISH: begin
                    for(index=0;index<32;index=index+1) begin
                        if(index<work_count) published[index]<={work_list[index][127:64],15'b0,(candidates>32),work_list[index][47:0]};
                        else published[index]<=0;
                    end
                    target_count<=work_count;frame_count<=frame_count+1;frame_hits<=hits;
                    raw_count<=raw;filtered_count<=filtered;candidate_count<=candidates;
                    status_latch<={27'b0,(candidates>32),frame_error,2'b0};
                    alarm<=alarm_limit!=0 && hits>=alarm_limit;irq_list_ready<=1;stream_index<=0;
                    state<=(work_count!=0)?STREAM:CLEAR;
                end
                STREAM: if(m_axis_tready) begin
                    if(m_axis_tlast) state<=CLEAR;else stream_index<=stream_index+1;
                end
                CLEAR: begin
                    work_count<=0;active<=0;frame_end<=0;gap_count<=0;gap_sum<=0;gap_peak<=0;
                    hits<=0;raw<=0;filtered<=0;candidates<=0;state<=SCAN;
                end
                default:state<=CLEAR;
            endcase
        end
    end
endmodule
