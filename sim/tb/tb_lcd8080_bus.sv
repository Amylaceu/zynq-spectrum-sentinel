`timescale 1ns/1ps
module tb_lcd8080_bus;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0,valid=0;
    reg [7:0] phase=2;
    reg [16:0] data=0;
    wire ready,initialized,cs,rs,wr,rd,rst;
    wire [15:0] pins;
    reg [16:0] expected[0:71];
    integer expected_phases[0:71];
    integer count=0,cycles=0,fall_cycle=0,i;
    reg previous_wr=1;
    reg [16:0] low_data;
    lcd8080_bus #(.RESET_CYCLES(3),.STARTUP_CYCLES(5),.DELAY_SHIFT(20)) dut (
        .sys_clk(clk),.aresetn(resetn),.bus_phase_cycles(phase),
        .s_axis_tdata(data),.s_axis_tvalid(valid),.s_axis_tready(ready),.initialized(initialized),
        .lcd_data(pins),.lcd_cs_n(cs),.lcd_rs(rs),.lcd_wr_n(wr),.lcd_rd_n(rd),.lcd_reset_n(rst));
    task automatic send(input [16:0] word_value);
        @(negedge clk);data=word_value;valid=1;
        do @(posedge clk);while(!ready);@(negedge clk);valid=0;
    endtask
    initial begin
        $readmemh("n4_lcd_init_bus.hex",expected,0,67);
        for(i=0;i<68;i=i+1) expected_phases[i]=2;
        expected[68]=17'h0002a;expected_phases[68]=2;
        expected[69]=17'h1f81f;expected_phases[69]=4;
        expected[70]=17'h107e0;expected_phases[70]=1;
        expected[71]=17'h10000;expected_phases[71]=1;
        repeat(4) @(negedge clk);resetn=1;
        wait(initialized);if(count!=68) $fatal(1,"initialization word count%0d",count);
        fork
            send(expected[68]);
            begin wait(!wr);@(negedge clk);phase=4;end
        join
        wait(ready);send(expected[69]);wait(ready);
        @(negedge clk);phase=1;send(expected[70]);wait(ready);
        @(negedge clk);phase=0;send(expected[71]);wait(ready);
        if(count!=72) $fatal(1,"stream word count");
        repeat(5) @(negedge clk);
        if(!wr || !rd || cs || !rst) $fatal(1,"idle pins");
        $display("TB_RESULT: PASS LCD init68 writes,16-bit command/data,phases2/4/1,mid-word change,zero clamp");$finish;
    end
    always @(posedge clk) begin
        cycles=cycles+1;
        if(resetn) begin
            if(previous_wr && !wr) begin
                fall_cycle=cycles;low_data={rs,pins};
                if(!rst || !rd || cs) $fatal(1,"LCD pins during write");
            end
            if(!wr && {rs,pins}!==low_data) $fatal(1,"LCD data changed during low pulse");
            if(!previous_wr && wr) begin
                if(count>=72 || {rs,pins}!==expected[count]) $fatal(1,"LCD word%0d got=%h exp=%h",count,{rs,pins},expected[count]);
                if(cycles-fall_cycle!=expected_phases[count]) $fatal(1,"LCD pulse width%0d got%0d exp%0d",count,cycles-fall_cycle,expected_phases[count]);
                count=count+1;
            end
        end
        previous_wr=wr;
        if(cycles>5000) $fatal(1,"LCD timeout count%0d",count);
    end
endmodule
