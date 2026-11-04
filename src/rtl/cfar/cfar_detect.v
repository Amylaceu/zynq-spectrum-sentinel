module cfar_detect (
    input wire aclk, input wire aresetn, input wire enable,
    input wire [1:0] cfg_mode, input wire [2:0] cfg_nshift,
    input wire [4:0] cfg_guard, input wire [15:0] cfg_alpha,
    input wire [7:0] cfg_dc_mask,
    input wire [31:0] s_axis_tdata, input wire s_axis_tvalid,
    output wire s_axis_tready, input wire s_axis_tlast,
    output wire [92:0] m_axis_tdata, output wire m_axis_tvalid,
    input wire m_axis_tready, output reg error_sticky, output wire idle
);
    localparam CAPTURE=0,INIT_ADDR=1,INIT_ACC=2,ISSUE=3,DRAIN=4;
    reg [2:0] state;
    reg [10:0] capture_index,issue_index;
    reg [6:0] init_index,nref;
    reg [1:0] mode;
    reg [2:0] nshift;
    reg [4:0] guard_bins;
    reg [15:0] alpha;
    reg [7:0] dc_mask;
    reg [39:0] left_sum,right_sum;
    (* ram_style="block" *) reg [31:0] ram_cut[0:2047];
    (* ram_style="block" *) reg [31:0] ram_ln[0:2047];
    (* ram_style="block" *) reg [31:0] ram_lr[0:2047];
    (* ram_style="block" *) reg [31:0] ram_rn[0:2047];
    (* ram_style="block" *) reg [31:0] ram_rr[0:2047];
    reg [31:0] read_cut,read_ln,read_lr,read_rn,read_rr;
    reg rd_valid;
    reg [10:0] rd_index;
    reg [7:0] valid_pipe;
    reg [10:0] index_pipe[0:7];
    reg [31:0] cut_pipe[0:7];
    reg [31:0] noise;
    (* use_dsp="yes" *) reg [31:0] product_low;
    (* use_dsp="no" *) reg [23:0] product_high_lo,product_high_hi;
    reg [31:0] product_high,product_low_delayed;
    reg [47:0] product;
    reg [31:0] threshold_pipe[4:7];
    reg hit_pipe[5:7];
    reg [4:0] exponent;
    reg [7:0] mantissa;
    reg zero_power;
    (* rom_style="distributed" *) reg [31:0] log_rom[0:255];
    initial $readmemh("spec_log_mantissa.hex",log_rom);
    reg [31:0] log_sum;
    reg log_zero;
    reg [15:0] db_value;
    reg [31:0] normalized,shifted;
    reg [4:0] exp_next;
    wire advance=!valid_pipe[7] || m_axis_tready;
    wire capture=s_axis_tvalid && s_axis_tready;
    wire [10:0] addr_cut=issue_index;
    wire [10:0] addr_ln=(state==INIT_ADDR) ? (11'd0-guard_bins-init_index) : (issue_index-guard_bins);
    wire [10:0] addr_lr=issue_index-guard_bins-nref;
    wire [10:0] addr_rn=(state==INIT_ADDR) ? (guard_bins+init_index) : (issue_index+guard_bins+nref+11'd1);
    wire [10:0] addr_rr=issue_index+guard_bins+11'd1;
    wire read_enable=advance && (state==INIT_ADDR || state==ISSUE);
    wire [40:0] combined={1'b0,left_sum}+{1'b0,right_sum};
    wire [39:0] selected=(mode==1) ? ((left_sum>right_sum)?left_sum:right_sum) : ((left_sum<right_sum)?left_sum:right_sum);
    wire [31:0] threshold_next=(|product[47:40]) ? 32'hffffffff : product[39:8];
    wire masked=(dc_mask!=8'hff) && (index_pipe[4]>=11'd1024-{3'b0,dc_mask}) &&
                 (index_pipe[4]<=11'd1024+{3'b0,dc_mask});
    wire [31:0] rounded_log=log_sum+32'd128;
    assign s_axis_tready=(state==CAPTURE) && (capture_index!=0 || (enable && cfg_mode<3 && cfg_nshift<=6));
    assign idle=state==CAPTURE && capture_index==0;
    assign m_axis_tvalid=valid_pipe[7];
    assign m_axis_tdata={index_pipe[7]==2047,index_pipe[7],db_value,threshold_pipe[7],cut_pipe[7],hit_pipe[7]};
    integer j;
    always @* begin
        normalized=threshold_pipe[4];exp_next=0;
        if(normalized>=65536) begin normalized=normalized>>16;exp_next=16;end
        if(normalized>=256) begin normalized=normalized>>8;exp_next=exp_next+8;end
        if(normalized>=16) begin normalized=normalized>>4;exp_next=exp_next+4;end
        if(normalized>=4) begin normalized=normalized>>2;exp_next=exp_next+2;end
        if(normalized>=2) exp_next=exp_next+1;
        if(exp_next>=8) shifted=threshold_pipe[4]>>(exp_next-8);
        else shifted=threshold_pipe[4]<<(8-exp_next);
    end
    // No RAM reset: read valid/ownership controls every observation.
    always @(posedge aclk) begin
        if(capture) begin
            ram_cut[capture_index]<=s_axis_tdata;ram_ln[capture_index]<=s_axis_tdata;
            ram_lr[capture_index]<=s_axis_tdata;ram_rn[capture_index]<=s_axis_tdata;
            ram_rr[capture_index]<=s_axis_tdata;
        end
        if(read_enable) begin
            read_cut<=ram_cut[addr_cut];read_ln<=ram_ln[addr_ln];read_lr<=ram_lr[addr_lr];
            read_rn<=ram_rn[addr_rn];read_rr<=ram_rr[addr_rr];
        end
    end
    always @(posedge aclk) begin
        if(!aresetn) begin
            state<=CAPTURE;capture_index<=0;issue_index<=0;init_index<=1;
            rd_valid<=0;valid_pipe<=0;error_sticky<=0;left_sum<=0;right_sum<=0;
            nref<=16;mode<=0;nshift<=4;guard_bins<=2;alpha<=1974;dc_mask<=3;
        end else begin
            if(enable && (cfg_mode==3 || cfg_nshift>6)) error_sticky<=1;
            if(capture) begin
                if(s_axis_tlast!=(capture_index==2047)) error_sticky<=1;
                if(capture_index==0) begin
                    mode<=cfg_mode;nshift<=cfg_nshift;nref<=7'd1<<cfg_nshift;
                    guard_bins<=cfg_guard;alpha<=cfg_alpha;dc_mask<=cfg_dc_mask;
                end
                if(capture_index==2047) begin
                    capture_index<=0;state<=INIT_ADDR;init_index<=1;left_sum<=0;right_sum<=0;
                end else capture_index<=capture_index+1;
            end
            if(advance) begin
                rd_valid<=state==ISSUE;
                if(state==ISSUE) begin
                    rd_index<=issue_index;
                    if(issue_index==2047) state<=DRAIN;
                    else issue_index<=issue_index+1;
                end
                if(state==INIT_ADDR) state<=INIT_ACC;
                if(state==INIT_ACC) begin
                    left_sum<=left_sum+read_ln;right_sum<=right_sum+read_rn;
                    if(init_index==nref) begin issue_index<=0;state<=ISSUE;end
                    else begin init_index<=init_index+1;state<=INIT_ADDR;end
                end
                valid_pipe<={valid_pipe[6:0],rd_valid};
                if(rd_valid) begin
                    noise<=(mode==0) ? (combined>>(nshift+1)) : (selected>>nshift);
                    cut_pipe[0]<=read_cut;index_pipe[0]<=rd_index;
                    left_sum<=left_sum+read_ln-read_lr;
                    right_sum<=right_sum+read_rn-read_rr;
                end
                for(j=1;j<8;j=j+1) begin cut_pipe[j]<=cut_pipe[j-1];index_pipe[j]<=index_pipe[j-1];end
                product_low<=noise[15:0]*alpha;
                product_high_lo<=noise[23:16]*alpha;product_high_hi<=noise[31:24]*alpha;
                product_high<={product_high_hi,8'b0}+product_high_lo;product_low_delayed<=product_low;
                product<={product_high,16'b0}+{16'b0,product_low_delayed};
                threshold_pipe[4]<=threshold_next;
                for(j=5;j<8;j=j+1) threshold_pipe[j]<=threshold_pipe[j-1];
                hit_pipe[5]<=(cut_pipe[4]>threshold_pipe[4]) && !masked;
                hit_pipe[6]<=hit_pipe[5];hit_pipe[7]<=hit_pipe[6];
                exponent<=exp_next;mantissa<=shifted[7:0];zero_power<=threshold_pipe[4]==0;
                log_sum<=exponent*32'd197283+log_rom[mantissa];log_zero<=zero_power;
                db_value<=log_zero ? 16'h8000 : rounded_log[23:8];
                if(valid_pipe[7] && index_pipe[7]==2047) state<=CAPTURE;
            end
        end
    end
endmodule
