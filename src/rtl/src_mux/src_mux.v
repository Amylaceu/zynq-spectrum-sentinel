module src_mux (
    input wire aclk,input wire aresetn,
    input wire [31:0] s_axis_rf_tdata,input wire s_axis_rf_tvalid,output wire s_axis_rf_tready,
    input wire [31:0] s_axis_replay_tdata,input wire s_axis_replay_tvalid,output wire s_axis_replay_tready,
    input wire s_axis_replay_tlast,
    output wire [31:0] m_axis_tdata,output wire [1:0] m_axis_tuser,
    output wire m_axis_tvalid,input wire m_axis_tready,output wire m_axis_tlast,
    output reg error_sticky,
    input wire [7:0] s_axi_awaddr,input wire s_axi_awvalid,output wire s_axi_awready,
    input wire [31:0] s_axi_wdata,input wire [3:0] s_axi_wstrb,
    input wire s_axi_wvalid,output wire s_axi_wready,
    output wire s_axi_bvalid,input wire s_axi_bready,output wire [1:0] s_axi_bresp,
    input wire [7:0] s_axi_araddr,input wire s_axi_arvalid,output wire s_axi_arready,
    output wire [31:0] s_axi_rdata,output wire s_axi_rvalid,
    input wire s_axi_rready,output wire [1:0] s_axi_rresp
);
    wire [31:0] ctrl,rate_div,fcw0,fcw1,fcw2,amp0,amp1,amp2,noise_amp,seed_i,seed_q,arm_token,frame_limit;
    reg [31:0] frame_count,sample_count,input_frames,arm_seen;
    src_ctrl_regs registers(.aclk(aclk),.aresetn(aresetn),
        .s_axi_awaddr(s_axi_awaddr),.s_axi_awvalid(s_axi_awvalid),.s_axi_awready(s_axi_awready),
        .s_axi_wdata(s_axi_wdata),.s_axi_wstrb(s_axi_wstrb),.s_axi_wvalid(s_axi_wvalid),.s_axi_wready(s_axi_wready),
        .s_axi_bvalid(s_axi_bvalid),.s_axi_bready(s_axi_bready),.s_axi_bresp(s_axi_bresp),
        .s_axi_araddr(s_axi_araddr),.s_axi_arvalid(s_axi_arvalid),.s_axi_arready(s_axi_arready),
        .s_axi_rdata(s_axi_rdata),.s_axi_rvalid(s_axi_rvalid),.s_axi_rready(s_axi_rready),.s_axi_rresp(s_axi_rresp),
        .reg_ctrl(ctrl),.reg_rate_div(rate_div),.reg_fcw0(fcw0),.reg_fcw1(fcw1),.reg_fcw2(fcw2),
        .reg_amp0(amp0),.reg_amp1(amp1),.reg_amp2(amp2),.reg_noise_amp(noise_amp),
        .reg_seed_i(seed_i),.reg_seed_q(seed_q),.reg_arm_token(arm_token),.reg_frame_limit(frame_limit),
        .ro_frame_cnt(frame_count),.ro_sample_cnt(sample_count));
    reg [10:0] input_index;
    reg [1:0] frame_mode;
    reg [31:0] frame_rate,frame_fcw0,frame_fcw1,frame_fcw2;
    reg [15:0] frame_amp0,frame_amp1,frame_amp2,frame_noise_amp;
    wire [1:0] mode=input_index==0 ? ctrl[2:1] : frame_mode;
    reg [31:0] pacing_rate;
    wire [31:0] active_rate=pacing_rate;
    wire [31:0] active_fcw0=input_index==0 ? fcw0 : frame_fcw0;
    wire [31:0] active_fcw1=input_index==0 ? fcw1 : frame_fcw1;
    wire [31:0] active_fcw2=input_index==0 ? fcw2 : frame_fcw2;
    wire [15:0] active_amp0=input_index==0 ? amp0[15:0] : frame_amp0;
    wire [15:0] active_amp1=input_index==0 ? amp1[15:0] : frame_amp1;
    wire [15:0] active_amp2=input_index==0 ? amp2[15:0] : frame_amp2;
    wire [15:0] active_noise_amp=input_index==0 ? noise_amp[15:0] : frame_noise_amp;
    (* dont_touch="true" *) reg [31:0] phase0,phase1,phase2;
    reg [31:0] rng_i,rng_q,pacer;
    (* rom_style="block" *) reg signed [15:0] sine[0:1023];
    initial $readmemh("n4_sine.hex",sine);
    reg [4:0] valid_pipe;
    reg [1:0] modes[0:4];
    reg [4:0] lasts;
    reg [31:0] source_data[0:4];
    reg signed [15:0] si0,sq0,si1,sq1,si2,sq2;
    reg [15:0] a0,a1,a2,noise_a[0:2];
    reg [143:0] uniform_i,uniform_q;
    reg [13:0] partial_i[0:2],partial_q[0:2];
    reg signed [15:0] gaussian_i,gaussian_q;
    reg signed [32:0] prod_i0,prod_q0,prod_i1,prod_q1,prod_i2,prod_q2;
    reg signed [32:0] mixed_ni,mixed_nq;
    reg signed [18:0] tone_i,tone_q;
    reg signed [18:0] tone_i_delayed,tone_q_delayed;
    reg [31:0] final_data;
    wire advance=!valid_pipe[4] || m_axis_tready;
    wire rearm=arm_seen!=arm_token;
    wire limited=frame_limit!=0 && input_frames>=frame_limit;
    wire enabled=input_index!=0 || (ctrl[0] && !limited && !rearm);
    wire [32:0] pace_next={1'b0,pacer}+33'd65536;
    wire due=(mode==0 || mode==3) || pace_next>={1'b0,active_rate};
    wire config_ok=amp0<=65535 && amp1<=65535 && amp2<=65535 && noise_amp<=65535 &&
                   rate_div>=65536 && seed_i!=0 && seed_q!=0;
    wire take=advance && enabled && due && (input_index!=0 || (config_ok && pacing_rate==rate_div));
    wire source_valid=(mode==2) || ((mode==1)?s_axis_replay_tvalid:s_axis_rf_tvalid);
    wire issue=take && source_valid;
    // Unselected/disabled RF is drained, so a stopped software display cannot fill the RF FIFO.
    assign s_axis_rf_tready=(mode==0 || mode==3) && enabled ? take : 1'b1;
    assign s_axis_replay_tready=mode==1 && take;
    assign m_axis_tdata=final_data;assign m_axis_tuser=modes[4];assign m_axis_tlast=lasts[4];assign m_axis_tvalid=valid_pipe[4];
    function [175:0] draws;
        input [31:0] initial_state;
        reg [31:0] state_value;
        reg [143:0] words;
        integer u,b;
        begin
            state_value=initial_state;words=0;
            for(u=0;u<12;u=u+1) begin
                for(b=0;b<12;b=b+1) state_value=(state_value>>1)^((state_value[0])?32'h80200003:32'b0);
                words[u*12+:12]=state_value[11:0];
            end
            draws={state_value,words};
        end
    endfunction
    wire [175:0] next_rng_i=draws(rng_i),next_rng_q=draws(rng_q);
    wire [9:0] cosine_index0=phase0[31:22]+10'd256;
    wire [9:0] cosine_index1=phase1[31:22]+10'd256;
    wire [9:0] cosine_index2=phase2[31:22]+10'd256;
    function [15:0] saturate;
        input signed [34:0] value;
        begin
            if(value>32767) saturate=16'h7fff;
            else if(value< -32768) saturate=16'h8000;
            else saturate=value[15:0];
        end
    endfunction
    wire signed [34:0] noisy_i=$signed(source_data[3][15:0])+(mixed_ni>>>15);
    wire signed [34:0] noisy_q=$signed(source_data[3][31:16])+(mixed_nq>>>15);
    integer j;
    always @(posedge aclk) begin
        if(!aresetn) begin
            input_index<=0;frame_mode<=0;valid_pipe<=0;lasts<=0;phase0<=0;phase1<=0;phase2<=0;
            rng_i<=32'h12345678;rng_q<=32'h87654321;pacer<=0;arm_seen<=0;pacing_rate<=320000;
            input_frames<=0;frame_count<=0;sample_count<=0;error_sticky<=0;
        end else begin
            if(input_index==0 && !issue) pacing_rate<=rate_div;
            if(ctrl[0] && !config_ok) error_sticky<=1;
            if(rearm && input_index==0 && valid_pipe==0) begin
                rng_i<=seed_i;rng_q<=seed_q;phase0<=0;phase1<=0;phase2<=0;pacer<=0;
                arm_seen<=arm_token;input_frames<=0;frame_count<=0;sample_count<=0;error_sticky<=0;
            end
            if(m_axis_tvalid && m_axis_tready) begin
                sample_count<=sample_count+1;
                if(m_axis_tlast) frame_count<=frame_count+1;
            end
            if(advance && enabled && config_ok && (mode==1 || mode==2)) begin
                if(issue) pacer<=pace_next-active_rate;
                else if(!due) pacer<=pace_next[31:0];
            end
            if(issue) begin
                if(input_index==0) begin
                    frame_mode<=mode;frame_rate<=rate_div;frame_fcw0<=fcw0;frame_fcw1<=fcw1;frame_fcw2<=fcw2;
                    frame_amp0<=amp0[15:0];frame_amp1<=amp1[15:0];frame_amp2<=amp2[15:0];frame_noise_amp<=noise_amp[15:0];
                end
                input_index<=input_index+1'b1;
                if(input_index==2047) input_frames<=input_frames+1;
                if(mode==1 && s_axis_replay_tlast!=(input_index==2047)) error_sticky<=1;
                if(mode==2) begin phase0<=phase0+active_fcw0;phase1<=phase1+active_fcw1;phase2<=phase2+active_fcw2;end
                if(mode==3) begin rng_i<=next_rng_i[175:144];rng_q<=next_rng_q[175:144];end
            end
            if(advance) begin
                valid_pipe<={valid_pipe[3:0],issue};lasts<={lasts[3:0],input_index==2047};
                modes[0]<=mode;
                source_data[0]<=mode==1 ? s_axis_replay_tdata : s_axis_rf_tdata;
                uniform_i<=next_rng_i[143:0];uniform_q<=next_rng_q[143:0];
                si0<=sine[cosine_index0];sq0<=sine[phase0[31:22]];
                si1<=sine[cosine_index1];sq1<=sine[phase1[31:22]];
                si2<=sine[cosine_index2];sq2<=sine[phase2[31:22]];
                a0<=active_amp0;a1<=active_amp1;a2<=active_amp2;noise_a[0]<=active_noise_amp;
                for(j=1;j<5;j=j+1) begin modes[j]<=modes[j-1];source_data[j]<=source_data[j-1];end
                for(j=1;j<3;j=j+1) noise_a[j]<=noise_a[j-1];
                for(j=0;j<3;j=j+1) begin
                    partial_i[j]<={2'b0,uniform_i[j*48+:12]}+{2'b0,uniform_i[j*48+12+:12]}+{2'b0,uniform_i[j*48+24+:12]}+{2'b0,uniform_i[j*48+36+:12]};
                    partial_q[j]<={2'b0,uniform_q[j*48+:12]}+{2'b0,uniform_q[j*48+12+:12]}+{2'b0,uniform_q[j*48+24+:12]}+{2'b0,uniform_q[j*48+36+:12]};
                end
                gaussian_i<=$signed({2'b0,partial_i[0]})+$signed({2'b0,partial_i[1]})+$signed({2'b0,partial_i[2]})-16'sd24570;
                gaussian_q<=$signed({2'b0,partial_q[0]})+$signed({2'b0,partial_q[1]})+$signed({2'b0,partial_q[2]})-16'sd24570;
                prod_i0<=si0*$signed({1'b0,a0});prod_q0<=sq0*$signed({1'b0,a0});
                prod_i1<=si1*$signed({1'b0,a1});prod_q1<=sq1*$signed({1'b0,a1});
                prod_i2<=si2*$signed({1'b0,a2});prod_q2<=sq2*$signed({1'b0,a2});
                tone_i<=(prod_i0>>>15)+(prod_i1>>>15)+(prod_i2>>>15);
                tone_q<=(prod_q0>>>15)+(prod_q1>>>15)+(prod_q2>>>15);
                tone_i_delayed<=tone_i;tone_q_delayed<=tone_q;
                mixed_ni<=gaussian_i*$signed({1'b0,noise_a[2]});mixed_nq<=gaussian_q*$signed({1'b0,noise_a[2]});
                if(modes[3]==3) final_data<={saturate(noisy_q),saturate(noisy_i)};
                else if(modes[3]==2) final_data<={saturate(tone_q_delayed),saturate(tone_i_delayed)};
                else final_data<=source_data[3];
            end
        end
    end
endmodule
