`timescale 1ns/1ps
module tb_lcd_snapshot;
    reg dsp_clk=0;always #3.333 dsp_clk=~dsp_clk;
    reg lcd_clk=0;always #10 lcd_clk=~lcd_clk;
    reg resetn=0;
    reg [15:0] spec=0,thr=0;
    reg [9:0] spec_col=0,thr_col=0,read_col=0;
    reg spec_valid=0,thr_valid=0,spec_last=0,thr_last=0,accept=0;
    wire available,error_sticky;
    wire [31:0] id,dropped;
    wire [15:0] spec_out,thr_out;
    integer i,received=0,last_id=-1,producer_done=0;
    lcd_snapshot dut(.dsp_clk(dsp_clk),.dsp_aresetn(resetn),
        .s_spec_tdata(spec),.s_spec_tuser(spec_col),.s_spec_tvalid(spec_valid),.s_spec_tlast(spec_last),
        .s_thr_tdata(thr),.s_thr_tuser(thr_col),.s_thr_tvalid(thr_valid),.s_thr_tlast(thr_last),
        .dropped_frames(dropped),.error_sticky(error_sticky),.lcd_clk(lcd_clk),.lcd_aresetn(resetn),
        .frame_available(available),.accept_frame(accept),.frame_id(id),.read_column(read_col),.spec_data(spec_out),.threshold_data(thr_out));
    task automatic send_spectrum(input integer frame);
        integer col;
        for(col=0;col<560;col=col+1) begin
            @(negedge dsp_clk);spec_valid=1;spec_col=col;spec=frame*1000+col;spec_last=col==559;
            @(negedge dsp_clk);spec_valid=0;
        end
    endtask
    task automatic send_threshold(input integer frame);
        integer col;
        for(col=0;col<560;col=col+1) begin
            @(negedge dsp_clk);thr_valid=1;thr_col=col;thr=20000+frame*1000+col;thr_last=col==559;
            @(negedge dsp_clk);thr_valid=0;
        end
    endtask
    initial begin
        repeat(12) @(negedge lcd_clk);resetn=1;
        for(i=0;i<12;i=i+1) begin
            fork
                send_spectrum(i);
                begin repeat(200) @(negedge dsp_clk);send_threshold(i);end
            join
            repeat(10) @(negedge dsp_clk);
        end
        producer_done=1;
    end
    initial begin
        wait(resetn);
        forever begin
            wait(available || producer_done);
            if(!available && producer_done) begin
                if(received<2 || dropped==0 || error_sticky) $fatal(1,"snapshot acceptance counts");
                $display("TB_RESULT: PASS snapshot paired frames=%0d dropped=%0d,async bank ownership",received,dropped);$finish;
            end
            @(negedge lcd_clk);accept=1;@(negedge lcd_clk);accept=0;
            if((last_id>=0 && id<=last_id) || id>=12) $fatal(1,"snapshot sequence id=%0d previous=%0d",id,last_id);
            last_id=id;
            for(integer col=0;col<560;col=col+1) begin
                @(negedge lcd_clk);read_col=col;@(posedge lcd_clk);#1;
                if(spec_out!==id*1000+col || thr_out!==20000+id*1000+col) $fatal(1,"mixed snapshot id=%0d col=%0d data=%h/%h",id,col,spec_out,thr_out);
                repeat(2) @(negedge lcd_clk);
            end
            // Keep reading the active bank while producer submits many newer frames.
            repeat(3000) begin
                @(negedge lcd_clk);read_col=17;@(posedge lcd_clk);#1;
                if(spec_out!==id*1000+17 || thr_out!==20000+id*1000+17) $fatal(1,"active bank overwritten");
            end
            received=received+1;
        end
    end
    initial begin #2000000;$fatal(1,"snapshot timeout");end
endmodule
