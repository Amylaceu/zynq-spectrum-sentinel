`timescale 1ns/1ps
module tb_x2_drop_counter;
    reg clk=0;always #2 clk=~clk;
    reg reset=1,event_valid=0;
    reg [31:0] expected=0,previous_gray=0,rng=32'h7a31d951;
    reg [15:0] expected16=0;
    wire [31:0] binary_count,gray_count;
    wire [15:0] binary16,gray16;
    integer cycles=0,i;
    drop_counter_segmented dut(.*);
    drop_counter_segmented #(.WIDTH(16)) short_counter(.clk(clk),.reset(reset),.event_valid(event_valid),
        .binary_count(binary16),.gray_count(gray16));
    always @(posedge clk) begin
        cycles=cycles+1;
        if(reset) begin expected=0;expected16=0;end
        else begin
            if(event_valid && expected!=32'hffffffff) expected=expected+1;
            if(event_valid && expected16!=16'hffff) expected16=expected16+1;
        end
        #1;
        if(binary_count!==expected || gray_count!==((expected>>1)^expected)) $fatal(1,"32-bit count/Gray mismatch");
        if(binary16!==expected16 || gray16!==((expected16>>1)^expected16)) $fatal(1,"16-bit count/Gray mismatch");
        if(!reset && $countones(gray_count^previous_gray)>1) $fatal(1,"non-Gray transition");
        previous_gray=gray_count;
    end
    // Inject a consistent reachable state to cover all 32-bit carry boundaries
    // and saturation without simulating four billion clocks.
    task automatic seed_count(input [31:0] seed);
        @(negedge clk);event_valid=0;expected=seed;dut.binary_count=seed;
        dut.gray_count=(seed>>1)^seed;previous_gray=dut.gray_count;
        dut.prefix_full={(&seed),(&seed[23:0]),(&seed[15:0]),(&seed[7:0])};
    endtask
    initial begin
        repeat(4) @(negedge clk);reset=0;event_valid=1;
        repeat(66000) @(negedge clk);
        if(binary16!=16'hffff) $fatal(1,"16-bit saturation not reached");
        for(i=0;i<30000;i=i+1) begin
            rng={rng[30:0],rng[31]^rng[21]^rng[1]^rng[0]};event_valid=rng[0];
            @(negedge clk);
        end
        seed_count(32'h0000fff0);event_valid=1;repeat(40) @(negedge clk);
        seed_count(32'h00fffff0);event_valid=1;repeat(40) @(negedge clk);
        seed_count(32'h7ffffff0);event_valid=1;repeat(40) @(negedge clk);
        seed_count(32'hfffffff0);event_valid=1;repeat(100) @(negedge clk);
        if(binary_count!=32'hffffffff) $fatal(1,"32-bit saturation not reached");
        reset=1;repeat(5) @(negedge clk);reset=0;event_valid=0;repeat(5) @(negedge clk);
        $display("TB_RESULT: PASS X2 segmented counter %0d cycles, carry boundaries, stalls, saturation, reset, one-bit Gray",cycles);
        $finish;
    end
endmodule
