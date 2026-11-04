`timescale 1ns/1ps
module tb_src_mux;
    reg clk=0;
    `ifdef DSP_100MHZ
    always #5 clk=~clk;
    `else
    always #3.333 clk=~clk;
    `endif
    reg resetn=0,rf_valid=0,replay_valid=0,replay_last=0,ready=0;
    reg [31:0] rf_data=0,replay_data=0;
    wire rf_ready,replay_ready;
    wire [31:0] data;
    wire [1:0] mode;
    wire valid,last,error_sticky;
    reg [7:0] awaddr=0,araddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0,arvalid=0,rready=0;
    wire awready,wready,bvalid,arready,rvalid;
    wire [31:0] rdata;
    wire [1:0] bresp,rresp;
    reg [31:0] inputs[0:16383],expected[0:16383],config_words[0:87];
    reg [31:0] random_state=32'h8431e05f;
    reg stalled=0;
    reg [34:0] held;
    integer current_case=0,received=0,case_received=0,sent=0,cycles=0,j,file_out;
    reg [31:0] value;
    src_mux dut(.aclk(clk),.aresetn(resetn),
        .s_axis_rf_tdata(rf_data),.s_axis_rf_tvalid(rf_valid),.s_axis_rf_tready(rf_ready),
        .s_axis_replay_tdata(replay_data),.s_axis_replay_tvalid(replay_valid),.s_axis_replay_tready(replay_ready),.s_axis_replay_tlast(replay_last),
        .m_axis_tdata(data),.m_axis_tuser(mode),.m_axis_tvalid(valid),.m_axis_tready(ready),.m_axis_tlast(last),.error_sticky(error_sticky),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'b1111),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
        .s_axi_araddr(araddr),.s_axi_arvalid(arvalid),.s_axi_arready(arready),
        .s_axi_rdata(rdata),.s_axi_rvalid(rvalid),.s_axi_rready(rready),.s_axi_rresp(rresp));
    task automatic wr(input [7:0] addr,input [31:0] word_value);
        @(negedge clk);awaddr=addr;wdata=word_value;awvalid=1;wvalid=1;
        do @(posedge clk);while(!(awready&&wready));@(negedge clk);awvalid=0;wvalid=0;bready=1;
        do @(posedge clk);while(!bvalid);@(negedge clk);bready=0;
    endtask
    task automatic rd(input [7:0] addr,output [31:0] word_value);
        @(negedge clk);araddr=addr;arvalid=1;do @(posedge clk);while(!arready);
        @(negedge clk);arvalid=0;rready=1;do @(posedge clk);while(!rvalid);
        word_value=rdata;@(negedge clk);rready=0;
    endtask
    initial begin
        $readmemh("n4_src_input.hex",inputs);$readmemh("n4_src_expected.hex",expected);$readmemh("n4_src_config.hex",config_words);
        file_out=$fopen("n4_src_out.hex","w");
        repeat(12) @(negedge clk);resetn=1;
        rd('hfc,value);if(value!==32'h53520001) $fatal(1,"source version");
        for(current_case=0;current_case<8;current_case=current_case+1) begin
            case_received=0;
            wr(0,0);
            for(j=1;j<11;j=j+1) wr(j*4,config_words[current_case*11+j]);
            wr('h30,1);wr('h2c,current_case+1);repeat(5) @(negedge clk);
            wr(0,config_words[current_case*11]);
            if(config_words[current_case*11][2:1]!=2) begin
                for(sent=0;sent<2048;sent=sent+1) begin
                    @(negedge clk);
                    rf_data=inputs[current_case*2048+sent];replay_data=rf_data;
                    if(config_words[current_case*11][2:1]==1) begin
                        replay_valid=1;replay_last=sent==2047;
                        do @(posedge clk);while(!replay_ready);
                    end else begin
                        rf_valid=1;do @(posedge clk);while(!rf_ready);
                    end
                    @(negedge clk);rf_valid=0;replay_valid=0;
                end
            end
            wait(case_received==2048);repeat(10) @(negedge clk);
            if(valid || error_sticky) $fatal(1,"source limit or error");
            rd('h34,value);if(value!==1) $fatal(1,"source frame counter");
            rd('h38,value);if(value!==2048) $fatal(1,"source sample counter");
            $display("SOURCE_CASE_PASS %0d",current_case);
        end
        $fclose(file_out);$display("TB_RESULT: PASS four source modes,three DDS tones,noise,saturation,rearm,backpressure");$finish;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        ready=random_state[0] || random_state[16];
        if(cycles>500 && cycles<600) ready=0;
    end
    always @(posedge clk) if(resetn) begin
        cycles=cycles+1;
        if(stalled && (!valid || {last,mode,data}!==held)) $fatal(1,"source payload changed");
        stalled=valid && !ready;held={last,mode,data};
        if(valid && ready) begin
            if(data!==expected[received] || mode!==config_words[current_case*11][2:1] || last!==(case_received==2047))
                $fatal(1,"source case%0d idx%0d got=%h expected=%h mode=%h",current_case,case_received,data,expected[received],mode);
            $fdisplay(file_out,"%08x",data);received=received+1;case_received=case_received+1;
        end
        `ifdef DSP_100MHZ
        if(cycles>900000) $fatal(1,"source timeout case%0d sent%0d recv%0d",current_case,sent,received);
        `else
        if(cycles>400000) $fatal(1,"source timeout case%0d sent%0d recv%0d",current_case,sent,received);
        `endif
    end
endmodule
