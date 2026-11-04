`timescale 1ns/1ps
module tb_sentinel_observers;
    reg dc=0,cc=0,lc=0;always #3.333 dc=~dc;always #5 cc=~cc;always #10 lc=~lc;
    reg rn=0,arm=0,pv=0,pr=0,pl=0,ci=0,li=0;
    reg [31:0] pd=0;reg [10:0] bin=0;
    wire [31:0] ma,md;wire [3:0] we;wire en,mrst,done,err,dsp_error;wire [1:0] interrupts;
    reg [31:0] memory[0:2047];integer writes=0,cirq=0,lirq=0,i;
    sentinel_capture cap(.dsp_clk(dc),.dsp_aresetn(rn),.cpu_clk(cc),.cpu_aresetn(rn),.arm_toggle(arm),
        .power_data(pd),.power_bin(bin),.power_valid(pv),.power_ready(pr),.power_last(pl),
        .mem_addr(ma),.mem_data(md),.mem_we(we),.mem_en(en),.mem_reset(mrst),.done_toggle(done),.error_sticky(err));
    sentinel_events events(.dsp_clk(dc),.dsp_aresetn(rn),.cfar_irq(ci),.lcd_clk(lc),.lcd_aresetn(rn),.lcd_irq(li),
        .cpu_clk(cc),.cpu_aresetn(rn),.src_error(1'b0),.spec_error(1'b0),.adc_error(1'b0),.dsp_error(dsp_error),.interrupts(interrupts));
    always @(posedge dc) if(en && !mrst) begin
        if(we!==4'hf || ma[1:0]!==0 || ma>8191) $fatal(1,"native RAM write");
        memory[ma[12:2]]<=md;writes=writes+1;
    end
    always @(posedge cc) if(rn) begin if(interrupts[0]) cirq=cirq+1;if(interrupts[1]) lirq=lirq+1;end
    task automatic word(input integer b,input integer frame);
        @(negedge dc);bin=b;pd=32'h12340000+frame*4096+b;pv=1;pr=0;pl=b==2047;
        repeat(b%3) @(negedge dc);pr=1;
        @(negedge dc);pv=0;pr=0;
    endtask
    initial begin
        repeat(12) @(negedge cc);rn=1;
        @(negedge cc);arm=1;repeat(8) @(negedge dc);
        // Arming in the middle of a stream must wait for bin zero.
        for(i=2000;i<2048;i=i+1) word(i,0);
        if(writes!=0) $fatal(1,"partial frame captured");
        for(i=0;i<2048;i=i+1) word(i,1);
        repeat(8) @(negedge cc);
        if(!done || err || writes!=2048) $fatal(1,"first snapshot");
        for(i=0;i<2048;i=i+1) if(memory[i]!==32'h12341000+i) $fatal(1,"frame value");
        for(i=0;i<2048;i=i+1) word(i,2);
        if(writes!=2048) $fatal(1,"unarmed overwrite");
        @(negedge cc);arm=0;repeat(8) @(negedge dc);
        for(i=0;i<2048;i=i+1) word(i,3);
        repeat(8) @(negedge cc);
        if(done || err || writes!=4096) $fatal(1,"second toggle");
        for(i=0;i<2048;i=i+1) if(memory[i]!==32'h12343000+i) $fatal(1,"second frame");
        for(i=0;i<10;i=i+1) begin
            @(negedge dc);ci=1;@(negedge dc);ci=0;
            @(negedge lc);li=1;@(negedge lc);li=0;
            repeat(10) @(negedge cc);
        end
        repeat(12) @(negedge cc);
        if(cirq!=10 || lirq!=10 || dsp_error) $fatal(1,"interrupt CDC loss %d %d",cirq,lirq);
        $display("TB_RESULT: PASS two 2048-word coherent snapshots, no unarmed overwrite, stalled bus and 20 asynchronous interrupts");$finish;
    end
    initial begin #1000000;$fatal(1,"timeout");end
endmodule
