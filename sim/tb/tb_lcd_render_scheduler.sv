`timescale 1ns/1ps
module tb_lcd_render_scheduler;
    reg clk=0;always #10 clk=~clk;
    reg resetn=0,initialized=0,enable=0,available=0;
    reg [31:0] epoch=0,ui_word=0;
    wire [31:0] applied,ui_address,frames,gray;
    wire accept,busy,opvalid,opready,opdone,pvalid,pready,plast,cmdvalid;
    wire [1:0] kind;
    wire [15:0] a,b,c,d,fill,pixel;
    wire [16:0] cmddata;
    reg cmdready=0;
    wire region_error;
    wire [9:0] read_column;
    reg [15:0] spec,thr;
    reg [15:0] spec_ref[0:559],thr_ref[0:559],trace_ref[0:89599],wf_ref[0:559],memory[0:383999];
    reg [31:0] rng=32'hbff038ad;
    integer cycles=0,accepted=0,command=0,param_index=0,parameters[0:5];
    integer x0=0,x1=0,y0=0,y1=0,write_x=0,write_y=0,remaining=0,scroll_start=0;
    integer clear_pixels=0,ui_pixels=0,spectrum_pixels=0,wf_pixels=0;
    function [15:0] palette(input integer code);
        case(code) 0:palette=0;1:palette=16'hffff;2:palette=16'hffe0;3:palette=16'h07ff;endcase
    endfunction
    lcd_render_scheduler dut(.sys_clk(clk),.aresetn(resetn),.initialized(initialized),.enable(enable),
        .frame_available(available),.accept_frame(accept),.read_column(read_column),.spec_db(spec),.threshold_db(thr),
        .ui_epoch(epoch),.ui_applied_epoch(applied),.ui_address(ui_address),.ui_word(ui_word),
        .op_kind(kind),.op_p0(a),.op_p1(b),.op_p2(c),.op_p3(d),.fill_color(fill),.op_valid(opvalid),.op_ready(opready),.op_done(opdone),
        .pixel_data(pixel),.pixel_valid(pvalid),.pixel_ready(pready),.pixel_last(plast),.frame_count(frames),.frame_gray(gray),.busy(busy));
    lcd8080_region region(.sys_clk(clk),.aresetn(resetn),.op_kind(kind),.op_p0(a),.op_p1(b),.op_p2(c),.op_p3(d),
        .fill_color(fill),.op_valid(opvalid),.op_ready(opready),.s_axis_pixel_tdata(pixel),.s_axis_pixel_tvalid(pvalid),
        .s_axis_pixel_tready(pready),.s_axis_pixel_tlast(plast),.m_axis_cmd_tdata(cmddata),.m_axis_cmd_tvalid(cmdvalid),
        .m_axis_cmd_tready(cmdready),.done(opdone),.error_sticky(region_error));
    always @(posedge clk) begin
        spec<=spec_ref[read_column];thr<=thr_ref[read_column];ui_word<=32'he4e4e4e4;
        if(resetn) begin
            cycles=cycles+1;
            if(accept) begin accepted=accepted+1;available<=0;end
            if(ui_address>25596) $fatal(1,"UI address out of range");
            if(cmdvalid && cmdready) begin
                if(!cmddata[16]) begin
                    if(remaining!=0) $fatal(1,"premature next command");
                    command=cmddata[15:0];param_index=0;
                    if(command==44) begin
                        remaining=(x1-x0+1)*(y1-y0+1);write_x=x0;write_y=y0;
                    end else if(command!=42 && command!=43 && command!=51 && command!=55) $fatal(1,"unexpected command");
                end else if(command==44) begin
                    if(remaining<=0 || write_x<0 || write_x>=800 || write_y<0 || write_y>=480) $fatal(1,"pixel outside window");
                    memory[write_y*800+write_x]=cmddata[15:0];
                    if(x0==0 && x1==799 && y0==0 && y1==479) clear_pixels=clear_pixels+1;
                    else if(x0==0 && x1==559 && y0==0 && y1==159) spectrum_pixels=spectrum_pixels+1;
                    else if(x0==0 && x1==559 && y0==y1 && y0>=160 && y0<400) wf_pixels=wf_pixels+1;
                    else ui_pixels=ui_pixels+1;
                    remaining=remaining-1;
                    if(write_x==x1) begin write_x=x0;write_y=write_y+1;end else write_x=write_x+1;
                end else begin
                    parameters[param_index]=cmddata[7:0];param_index=param_index+1;
                    if(command==42 && param_index==4) begin x0=parameters[0]*256+parameters[1];x1=parameters[2]*256+parameters[3];end
                    if(command==43 && param_index==4) begin y0=parameters[0]*256+parameters[1];y1=parameters[2]*256+parameters[3];end
                    if(command==51 && param_index==6) begin
                        if(parameters[0]*256+parameters[1]!=160 || parameters[2]*256+parameters[3]!=240 || parameters[4]*256+parameters[5]!=80) $fatal(1,"scroll area mismatch");
                    end
                    if(command==55 && param_index==2) scroll_start=parameters[0]*256+parameters[1];
                end
            end
            if(region_error) $fatal(1,"region framing/bounds error");
            if(cycles>4000000) $fatal(1,"scheduler timeout frames=%0d state=%0d",frames,dut.state);
        end
    end
    always @(negedge clk) begin
        rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};cmdready=rng[1] || rng[19];
    end
    initial begin
        $readmemh("n4_pixel_spec.hex",spec_ref);$readmemh("n4_pixel_thr.hex",thr_ref);
        $readmemh("n4_pixel_expected.hex",trace_ref);$readmemh("n4_waterfall_expected.hex",wf_ref);
        repeat(5) @(negedge clk);resetn=1;initialized=1;
        wait(!busy);@(negedge clk);epoch=1;
        wait(applied==1);@(negedge clk);enable=1;available=1;
        wait(frames==1);@(negedge clk);available=1;
        wait(frames==2);repeat(4) @(negedge clk);
        if(accepted!=2 || scroll_start!=162 || gray!==3 || clear_pixels!=384000 || ui_pixels!=102400 || spectrum_pixels!=179200 || wf_pixels!=1120)
            $fatal(1,"scheduler totals accepted%0d scroll%0d clear%0d ui%0d spectrum%0d wf%0d",accepted,scroll_start,clear_pixels,ui_pixels,spectrum_pixels,wf_pixels);
        for(integer row=0;row<160;row=row+1) for(integer col=0;col<560;col=col+1)
            if(memory[row*800+col]!==trace_ref[row*560+col]) $fatal(1,"render mismatch %0d,%0d",col,row);
        for(integer row=0;row<160;row=row+1) for(integer col=560;col<800;col=col+1)
            if(memory[row*800+col]!==palette((row*240+col-560)%4)) $fatal(1,"list UI mismatch");
        for(integer row=400;row<480;row=row+1) for(integer col=0;col<800;col=col+1)
            if(memory[row*800+col]!==palette(((row-400)*800+col)%4)) $fatal(1,"status UI mismatch");
        for(integer col=0;col<560;col=col+1) begin
            if(memory[160*800+col]!==wf_ref[col] || memory[161*800+col]!==wf_ref[col]) $fatal(1,"waterfall mismatch");
        end
        for(integer row=160;row<400;row=row+1) for(integer col=560;col<800;col=col+1)
            if(memory[row*800+col]!==0) $fatal(1,"scrolling UI area was touched");
        $display("TB_RESULT: PASS complete scheduler two frames,full clear,paired RAM latency,UI,waterfall rows,scroll and backpressure");$finish;
    end
endmodule
