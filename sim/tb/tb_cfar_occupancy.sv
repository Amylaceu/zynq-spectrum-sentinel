`timescale 1ns/1ps
module tb_cfar_occupancy;
    reg clk=0;always #3.333 clk=~clk;
    reg resetn=0,clear_request=0,valid=0,hit=0,last=0;
    reg [10:0] bin_index=7,mmio_index=7;
    wire [15:0] mmio_data;
    wire clearing;
    wire [31:0] frames;
    cfar_occupancy dut(.aclk(clk),.aresetn(resetn),.clear_request(clear_request),
        .bin_index(bin_index),.hit(hit),.valid(valid),.last(last),
        .mmio_index(mmio_index),.mmio_data(mmio_data),.clearing(clearing),.frame_count(frames));
    task automatic sample(input bit value);
        @(negedge clk);valid=1;hit=value;last=1;
        @(negedge clk);valid=0;last=0;
        repeat(3) @(negedge clk);
    endtask
    initial begin
        repeat(10) @(negedge clk);resetn=1;wait(!clearing);
        @(negedge clk);
        // Preload near the saturation boundary; avoids65534 identical frames.
        dut.counts[7]=16'hfffe;
        dut.counts_mmio[7]=16'hfffe;
        sample(1);if(mmio_data!==16'hffff) $fatal(1,"increment to max");
        sample(1);if(mmio_data!==16'hffff) $fatal(1,"must saturate, never wrap");
        sample(0);if(mmio_data!==16'hffff || frames!==3) $fatal(1,"non-hit/frame counter");
        @(negedge clk);clear_request=1;@(negedge clk);clear_request=0;
        wait(!clearing);repeat(3) @(negedge clk);
        if(mmio_data!==0 || frames!==0) $fatal(1,"clear all state");
        $display("TB_RESULT: PASS occupancy saturation and clear");$finish;
    end
    initial begin repeat(6000) @(posedge clk);$fatal(1,"occupancy timeout");end
endmodule
