module cfar_cluster (
    input wire aclk,input wire aresetn,input wire [7:0] cfg_gap,
    input wire [11:0] alarm_limit,
    input wire [31:0] power,input wire hit,input wire [10:0] bin_index,
    input wire last,input wire valid,output wire ready,
    output wire busy, output reg irq_list_ready,
    output reg [5:0] target_count,output reg [31:0] frame_count,
    output reg [11:0] frame_hits,output reg alarm,
    output reg overflow,
    input wire [6:0] mmio_word_addr,output reg [31:0] mmio_data,
    output wire [127:0] m_axis_tdata,output wire m_axis_tvalid,
    input wire m_axis_tready,output wire m_axis_tlast
);
    (* ram_style="block" *) reg [127:0] list_ram[0:63];
    reg write_bank,published_bank;
    reg [5:0] count;
    reg dropped,active;
    reg [7:0] gap_limit,gap_count;
    reg [10:0] start_bin,stop_bin,peak_bin,gap_peak_bin;
    reg [31:0] peak,sum,gap_sum,gap_peak;
    reg [11:0] hits;
    reg [1:0] finish_state;
    reg [1:0] stream_state;
    reg [4:0] stream_index;
    reg [127:0] stream_data,mmio_record;
    reg [1:0] mmio_lane;
    reg [127:0] write_record;
    reg write_record_enable;
    reg [31:0] next_peak,next_sum;
    reg [10:0] next_peak_bin;
    wire fire=valid && ready;
    assign ready=finish_state==0 && stream_state==0;
    assign busy=finish_state!=0 || stream_state!=0;
    function [31:0] sat_add;
        input [31:0] a,b;
        reg [32:0] total;
        begin total={1'b0,a}+{1'b0,b};sat_add=total[32]?32'hffffffff:total[31:0];end
    endfunction
    function [31:0] sat_add3;
        input [31:0] a,b,c;
        reg [31:0] propagate,generate_carry;
        reg [33:0] total;
        begin
            propagate=a^b^c;generate_carry=(a&b)|(a&c)|(b&c);
            total={2'b0,propagate}+{1'b0,generate_carry,1'b0};
            sat_add3=(|total[33:32]) ? 32'hffffffff : total[31:0];
        end
    endfunction
    always @* begin
        next_peak=peak;next_peak_bin=peak_bin;
        if(gap_peak>next_peak) begin next_peak=gap_peak;next_peak_bin=gap_peak_bin;end
        if(power>next_peak) begin next_peak=power;next_peak_bin=bin_index;end
        next_sum=sat_add3(sum,gap_sum,power);
        write_record_enable=0;write_record=0;
        if(fire) begin
            if(hit && last) begin
                write_record_enable=1;
                if(active) write_record={next_sum,next_peak,16'b0,{5'b0,next_peak_bin},{5'b0,bin_index},{5'b0,start_bin}};
                else write_record={power,power,16'b0,{5'b0,bin_index},{5'b0,bin_index},{5'b0,bin_index}};
            end else if(!hit && active && (last || gap_count==gap_limit)) begin
                write_record_enable=1;
                write_record={sum,peak,16'b0,{5'b0,peak_bin},{5'b0,stop_bin},{5'b0,start_bin}};
            end
        end
    end
    always @(posedge aclk) begin
        if(write_record_enable && count<32) list_ram[{write_bank,count[4:0]}]<=write_record;
        // Two independent synchronous consumers; implementation may replicate small RAM.
        mmio_record<=list_ram[{published_bank,mmio_word_addr[6:2]}];
        mmio_lane<=mmio_word_addr[1:0];
        if(stream_state==1 || (stream_state==2 && m_axis_tready && !m_axis_tlast))
            stream_data<=list_ram[{published_bank,(stream_state==1 ? stream_index : stream_index+5'd1)}];
    end
    always @* begin
        case(mmio_lane)
            0:mmio_data=mmio_record[31:0];
            1:mmio_data={mmio_record[63:49],overflow,mmio_record[47:32]};
            2:mmio_data=mmio_record[95:64];
            3:mmio_data=mmio_record[127:96];
        endcase
    end
    assign m_axis_tdata={stream_data[127:49],overflow,stream_data[47:0]};
    assign m_axis_tvalid=stream_state==2;
    assign m_axis_tlast=stream_index==target_count-1;
    always @(posedge aclk) begin
        if(!aresetn) begin
            write_bank<=0;published_bank<=1;count<=0;dropped<=0;active<=0;
            gap_limit<=2;gap_count<=0;gap_sum<=0;gap_peak<=0;hits<=0;
            finish_state<=0;stream_state<=0;target_count<=0;frame_count<=0;
            frame_hits<=0;alarm<=0;overflow<=0;irq_list_ready<=0;stream_index<=0;
        end else begin
            irq_list_ready<=0;
            if(fire) begin
                if(bin_index==0) gap_limit<=cfg_gap;
                if(hit) hits<=hits+1;
                if(hit) begin
                    if(!active) begin
                        active<=1;start_bin<=bin_index;peak_bin<=bin_index;peak<=power;sum<=power;
                    end else begin peak<=next_peak;peak_bin<=next_peak_bin;sum<=next_sum;end
                    stop_bin<=bin_index;gap_count<=0;gap_sum<=0;gap_peak<=0;
                end else if(active) begin
                    if(last || gap_count==gap_limit) begin active<=0;gap_count<=0;gap_sum<=0;gap_peak<=0;end
                    else begin
                        gap_count<=gap_count+1;gap_sum<=sat_add(gap_sum,power);
                        if(gap_count==0 || power>gap_peak) begin gap_peak<=power;gap_peak_bin<=bin_index;end
                    end
                end
                if(write_record_enable) begin
                    if(count<32) count<=count+1;else dropped<=1;
                end
                if(last) begin finish_state<=1;active<=0;end
            end
            if(finish_state==1) begin
                target_count<=count;frame_count<=frame_count+1;frame_hits<=hits;
                alarm<=(alarm_limit!=0 && hits>=alarm_limit);overflow<=dropped;
                published_bank<=write_bank;write_bank<=!write_bank;irq_list_ready<=1;
                count<=0;hits<=0;dropped<=0;gap_sum<=0;gap_peak<=0;gap_count<=0;
                finish_state<=2;
            end else if(finish_state==2) begin
                finish_state<=0;
                if(target_count!=0) begin stream_state<=1;stream_index<=0;end
            end
            if(stream_state==1) stream_state<=2;
            else if(stream_state==2 && m_axis_tready) begin
                if(m_axis_tlast) stream_state<=0;else stream_index<=stream_index+1;
            end
        end
    end
endmodule
