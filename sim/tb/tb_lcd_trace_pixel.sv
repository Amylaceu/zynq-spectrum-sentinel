`timescale 1ns/1ps
module tb_lcd_trace_pixel;
    reg [9:0] x=0;
    reg [7:0] y=0;
    reg [15:0] spec=0,prev=0,thr=0;
    wire [15:0] pixel,wf;
    reg [15:0] spec_mem[0:559],thr_mem[0:559],expected[0:89599],expected_wf[0:559];
    integer row,col,checked=0;
    lcd_trace_pixel dut(.x(x),.y(y),.spec_db(spec),.previous_spec_db(prev),.threshold_db(thr),.spectrum_pixel(pixel),.waterfall_pixel(wf));
    initial begin
        $readmemh("n4_pixel_spec.hex",spec_mem);$readmemh("n4_pixel_thr.hex",thr_mem);
        $readmemh("n4_pixel_expected.hex",expected);$readmemh("n4_waterfall_expected.hex",expected_wf);
        for(row=0;row<160;row=row+1) for(col=0;col<560;col=col+1) begin
            x=col;y=row;spec=spec_mem[col];prev=spec_mem[col==0?0:col-1];thr=thr_mem[col];#1;
            if(pixel!==expected[row*560+col] || wf!==expected_wf[col]) $fatal(1,"pixel mismatch at %0d,%0d got=%h/%h expected=%h/%h",col,row,pixel,wf,expected[row*560+col],expected_wf[col]);
            checked=checked+1;
        end
        $display("TB_RESULT: PASS spectrum89600 pixels and560 waterfall colors,DBFS/sentinel/clipping");$finish;
    end
endmodule
