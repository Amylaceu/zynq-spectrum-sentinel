`timescale 1ns/1ps
module tb_spec_front;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0;
    reg [31:0] input_data=0;
    reg input_valid=0,input_last=0;
    wire input_ready;
    wire [31:0] pwr_data;
    wire [10:0] pwr_bin;
    wire pwr_valid,pwr_last;
    reg pwr_ready=0,db_ready=0;
    wire [15:0] db_data,db_full;
    wire [9:0] db_pixel;
    wire db_valid,db_last,db_full_valid,error_sticky;
    wire [47:0] fft_data;
    wire fft_valid,power_valid;
    wire [31:0] power_data,frame_count;
    reg [7:0] awaddr=0;
    reg [31:0] wdata=0;
    reg awvalid=0,wvalid=0,bready=0;
    wire awready,wready,bvalid;
    wire [1:0] bresp;
    reg [31:0] stimulus[0:8191],expected_power[0:8191],expected_avg[0:8191];
    reg [23:0] expected_fft[0:16383];
    reg [15:0] expected_db[0:8191],expected_pixel[0:2239];
    integer sent,cycles=0,nfft=0,npower=0,navg=0,ndb=0,npixel=0;
    integer fft_file,power_file,avg_file,db_file,pixel_file;
    reg [31:0] random_state=32'hb13a75e9;
    reg pwr_stalled=0,db_stalled=0;
    reg [43:0] held_pwr;
    reg [26:0] held_db;
    spec_front dut(.aclk(clk),.aresetn(resetn),
        .s_axis_tdata(input_data),.s_axis_tvalid(input_valid),.s_axis_tready(input_ready),.s_axis_tlast(input_last),
        .m_axis_pwr_tdata(pwr_data),.m_axis_pwr_tuser(pwr_bin),.m_axis_pwr_tvalid(pwr_valid),.m_axis_pwr_tready(pwr_ready),.m_axis_pwr_tlast(pwr_last),
        .m_axis_db_tdata(db_data),.m_axis_db_tuser(db_pixel),.m_axis_db_tvalid(db_valid),.m_axis_db_tready(db_ready),.m_axis_db_tlast(db_last),
        .s_axi_awaddr(awaddr),.s_axi_awvalid(awvalid),.s_axi_awready(awready),
        .s_axi_wdata(wdata),.s_axi_wstrb(4'b1111),.s_axi_wvalid(wvalid),.s_axi_wready(wready),
        .s_axi_bvalid(bvalid),.s_axi_bready(bready),.s_axi_bresp(bresp),
        .s_axi_araddr(8'b0),.s_axi_arvalid(1'b0),.s_axi_rready(1'b1),
        .dbg_fft_tdata(fft_data),.dbg_fft_valid(fft_valid),.dbg_power_shifted(power_data),.dbg_power_valid(power_valid),
        .dbg_db_full(db_full),.dbg_db_valid(db_full_valid),.frame_count(frame_count),.error_sticky(error_sticky));
    task automatic write_bus(input [7:0] addr,input [31:0] value);
        @(negedge clk);awaddr=addr;wdata=value;awvalid=1;wvalid=1;
        do @(posedge clk);while(!(awready && wready));
        @(negedge clk);awvalid=0;wvalid=0;bready=1;
        do @(posedge clk);while(!bvalid);
        if(bresp!=0) $fatal(1,"AXI write failed");
        @(negedge clk);bready=0;
    endtask
    initial begin
        $readmemh("in_axis32.hex",stimulus);$readmemh("exp_fft.hex",expected_fft);
        $readmemh("exp_power_shifted.hex",expected_power);$readmemh("exp_welch.hex",expected_avg);
        $readmemh("exp_db.hex",expected_db);$readmemh("n2_display_expected.hex",expected_pixel);
        fft_file=$fopen("spec_front_fft_out.hex","w");power_file=$fopen("spec_front_power_out.hex","w");
        avg_file=$fopen("spec_front_avg_out.hex","w");db_file=$fopen("spec_front_db_out.hex","w");pixel_file=$fopen("spec_front_display_out.hex","w");
        repeat(12) @(negedge clk);resetn=1;
        write_bus(8'h04,3);write_bus(8'h08,1);write_bus(8'h00,1);
        for(sent=0;sent<8192;sent=sent+1) begin
            @(negedge clk);input_data=stimulus[sent];input_valid=1;input_last=(sent%2048)==2047;
            do @(posedge clk);while(!input_ready);
        end
        @(negedge clk);input_valid=0;
    end
    always @(negedge clk) begin
        random_state={random_state[30:0],random_state[31]^random_state[21]^random_state[1]^random_state[0]};
        pwr_ready=resetn && random_state[3:0]>2 && !(cycles>=10000 && cycles<30000);
        db_ready=resetn && random_state[7:4]>3;
    end
    always @(posedge clk) if(resetn) begin
        cycles<=cycles+1;
        if(cycles>300000) $fatal(1,"Full pipeline timeout");
        if(error_sticky) $fatal(1,"Full pipeline error flag");
        if(pwr_stalled && (!pwr_valid || {pwr_bin,pwr_last,pwr_data}!==held_pwr)) $fatal(1,"Power branch changed while stalled");
        if(db_stalled && (!db_valid || {db_pixel,db_last,db_data}!==held_db)) $fatal(1,"Display branch changed while stalled");
        pwr_stalled<=pwr_valid && !pwr_ready;held_pwr<={pwr_bin,pwr_last,pwr_data};
        db_stalled<=db_valid && !db_ready;held_db<={db_pixel,db_last,db_data};
        if(fft_valid) begin
            if(nfft>=8192 || fft_data[23:0]!==expected_fft[2*nfft] || fft_data[47:24]!==expected_fft[2*nfft+1]) $fatal(1,"Integrated FFT mismatch %0d",nfft);
            $fwrite(fft_file,"%06x\n%06x\n",fft_data[23:0],fft_data[47:24]);nfft<=nfft+1;
        end
        if(power_valid) begin
            if(npower>=8192 || power_data!==expected_power[npower]) $fatal(1,"FFTshift/power mismatch %0d got=%h expected=%h",npower,power_data,expected_power[npower]);
            $fwrite(power_file,"%08x\n",power_data);npower<=npower+1;
        end
        if(pwr_valid && pwr_ready) begin
            if(navg>=8192 || pwr_data!==expected_avg[navg] || pwr_bin!==navg%2048 || pwr_last!==((navg%2048)==2047)) $fatal(1,"Welch/output routing mismatch %0d",navg);
            $fwrite(avg_file,"%08x\n",pwr_data);navg<=navg+1;
        end
        if(db_full_valid) begin
            if(ndb>=8192 || db_full!==expected_db[ndb]) $fatal(1,"Full dB mismatch %0d",ndb);
            $fwrite(db_file,"%04x\n",db_full);ndb<=ndb+1;
        end
        if(db_valid && db_ready) begin
            if(npixel>=2240 || db_data!==expected_pixel[npixel] || db_pixel!==npixel%560 || db_last!==((npixel%560)==559)) $fatal(1,"Display reduction mismatch %0d",npixel);
            $fwrite(pixel_file,"%04x\n",db_data);npixel<=npixel+1;
        end
    end
    initial begin
        wait(nfft==8192 && npower==8192 && navg==8192 && ndb==8192 && npixel==2240);
        repeat(12) @(posedge clk);
        if(frame_count!=4) $fatal(1,"Frame count mismatch");
        $fclose(fft_file);$fclose(power_file);$fclose(avg_file);$fclose(db_file);$fclose(pixel_file);
        $display("TB_RESULT: PASS full spec_front, 4 frames, 2240 display maxima, independent sinks + long stall");$finish;
    end
endmodule
