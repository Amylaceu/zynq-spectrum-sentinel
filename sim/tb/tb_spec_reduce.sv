`timescale 1ns/1ps
module tb_spec_reduce;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [15:0] input_data=0;
    reg input_valid=0,input_last=0,out_ready=0;
    wire input_ready,out_valid,out_last,error;
    wire [15:0] out_data;
    wire [9:0] out_pixel;
    reg signed [15:0] samples[0:8191],expected[0:1119];
    integer frame,j,k,position,sent,received=0;
    reg signed [15:0] maximum;
    reg [31:0] random_state=32'hbf193857;
    spec_display_reduce dut(.aclk(clk),.aresetn(resetn),.frame_decim(16'd2),
        .s_axis_tdata(input_data),.s_axis_tvalid(input_valid),.s_axis_tready(input_ready),.s_axis_tlast(input_last),
        .m_axis_tdata(out_data),.m_axis_tuser(out_pixel),.m_axis_tvalid(out_valid),.m_axis_tready(out_ready),.m_axis_tlast(out_last),.framing_error(error));
    initial begin
        for(frame=0;frame<4;frame=frame+1) begin
            for(j=0;j<2048;j=j+1) samples[frame*2048+j]=((j*103+frame*7919)%65536)-32768;
            samples[frame*2048]=16'sh8000;samples[frame*2048+2047]=16'sh7fff;
        end
        position=0;
        for(frame=0;frame<4;frame=frame+2) begin
            for(j=0;j<560;j=j+1) begin
                maximum=16'sh8000;
                for(k=j*2048/560;k<(j+1)*2048/560;k=k+1)
                    if(samples[frame*2048+k]>maximum) maximum=samples[frame*2048+k];
                expected[position]=maximum;position=position+1;
            end
        end
        repeat(12) @(negedge clk);resetn=1;
        for(sent=0;sent<8192;sent=sent+1) begin
            @(negedge clk);input_data=samples[sent];input_valid=1;input_last=(sent%2048)==2047;
            do @(posedge clk);while(!input_ready);
        end
        @(negedge clk);input_valid=0;
        repeat(20) @(posedge clk);
        if(received!=1120 || error) $fatal(1,"Frame decimation count/error mismatch");
        $display("TB_RESULT: PASS signed 560-bin maxima + 2-frame decimation under stalls");$finish;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        out_ready=resetn && random_state[3:0]>3;
    end
    always @(posedge clk) if(resetn && out_valid && out_ready) begin
        if(received>=1120 || out_data!==expected[received] || out_pixel!==received%560 || out_last!==((received%560)==559))
            $fatal(1,"Display max/decimation mismatch %0d",received);
        received<=received+1;
    end
    initial begin repeat(30000) @(posedge clk);$fatal(1,"Reducer timeout");end
endmodule
