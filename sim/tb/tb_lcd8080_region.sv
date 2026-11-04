`timescale 1ns/1ps
module tb_lcd8080_region;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0,opvalid=0,pixelvalid=0,pixellast=0,ready=0;
    reg [1:0] kind=0;
    reg [15:0] p0=0,p1=0,p2=0,p3=0,color=16'h07e0,pixel=0;
    wire opready,pixelready,valid,busy,done,error_sticky;
    wire [16:0] data;
    reg [16:0] expected[0:82];
    reg [31:0] random_state=32'ha903517d;
    reg stalled=0;
    reg [16:0] held;
    integer received=0,cycles=0,i,done_count=0;
    lcd8080_region dut(.sys_clk(clk),.aresetn(resetn),
        .op_kind(kind),.op_p0(p0),.op_p1(p1),.op_p2(p2),.op_p3(p3),.fill_color(color),.op_valid(opvalid),.op_ready(opready),
        .s_axis_pixel_tdata(pixel),.s_axis_pixel_tvalid(pixelvalid),.s_axis_pixel_tready(pixelready),.s_axis_pixel_tlast(pixellast),
        .m_axis_cmd_tdata(data),.m_axis_cmd_tvalid(valid),.m_axis_cmd_tready(ready),.busy(busy),.done(done),.error_sticky(error_sticky));
    task automatic operation(input [1:0] k,input [15:0] a,b,c,d);
        @(negedge clk);kind=k;p0=a;p1=b;p2=c;p3=d;opvalid=1;
        do @(posedge clk);while(!opready);@(negedge clk);opvalid=0;
    endtask
    initial begin
        $readmemh("n4_region_expected.hex",expected);
        repeat(5) @(negedge clk);resetn=1;
        operation(0,1,3,2,3);
        for(i=0;i<6;i=i+1) begin
            @(negedge clk);pixel=16'hf000+i;pixelvalid=1;pixellast=i==5;
            do @(posedge clk);while(!pixelready);@(negedge clk);pixelvalid=0;
        end
        wait(!busy);operation(1,0,7,0,3);wait(!busy);
        operation(2,160,240,80,0);wait(!busy);operation(3,399,0,0,0);wait(!busy);
        operation(0,560,561,400,400);
        for(i=0;i<2;i=i+1) begin
            @(negedge clk);pixel=i==0 ? 16'h1234 : 16'habcd;pixelvalid=1;pixellast=i==1;
            do @(posedge clk);while(!pixelready);@(negedge clk);pixelvalid=0;
        end
        wait(!busy);
        repeat(3) @(negedge clk);
        if(received!=83 || done_count!=5 || error_sticky) $fatal(1,"region count/done/error");
        operation(1,800,801,0,0);repeat(3) @(negedge clk);
        if(!error_sticky || received!=83 || busy) $fatal(1,"invalid rectangle emitted data");
        operation(2,1,2,2,0);repeat(3) @(negedge clk);
        operation(3,400,0,0,0);repeat(3) @(negedge clk);
        operation(2,65535,65535,482,0);repeat(3) @(negedge clk);
        if(received!=83 || busy) $fatal(1,"invalid scroll emitted data");
        $display("TB_RESULT: PASS LCD windows,pixels,fill,scroll,start,invalid bounds,random stalls");$finish;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        ready=random_state[2] && random_state[17];
        if(cycles>60 && cycles<100) ready=0;
    end
    always @(posedge clk) if(resetn) begin
        cycles=cycles+1;
        if(done) done_count=done_count+1;
        if(stalled && (!valid || data!==held)) $fatal(1,"region unstable");
        stalled=valid && !ready;held=data;
        if(valid && ready) begin
            if(received>=83 || data!==expected[received]) $fatal(1,"region word%0d got=%h exp=%h",received,data,expected[received]);
            received=received+1;
        end
        if(cycles>4000) $fatal(1,"region timeout");
    end
endmodule
