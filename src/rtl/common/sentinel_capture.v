module sentinel_capture (
    input wire dsp_clk,input wire dsp_aresetn,
    input wire cpu_clk,input wire cpu_aresetn,
    input wire arm_toggle,
    input wire [31:0] power_data,input wire [10:0] power_bin,
    input wire power_valid,input wire power_ready,input wire power_last,
    output wire [31:0] mem_addr,output wire [31:0] mem_data,output wire [3:0] mem_we,
    output wire mem_en,output wire mem_reset,
    output wire done_toggle,output wire error_sticky
);
    (* ASYNC_REG="TRUE" *) reg [1:0] arm_sync;
    reg arm_seen,pending,active,done_dsp,error_dsp;
    reg [10:0] expected_bin;
    (* ASYNC_REG="TRUE" *) reg [1:0] done_sync,error_sync;
    wire accepted=power_valid && power_ready;
    wire writing=accepted && (active || (pending && power_bin==0));
    assign mem_addr={19'b0,power_bin,2'b0};assign mem_data=power_data;
    assign mem_en=writing;assign mem_we=writing?4'hf:4'h0;assign mem_reset=!dsp_aresetn;
    assign done_toggle=done_sync[1];assign error_sticky=error_sync[1];
    always @(posedge dsp_clk) begin
        if(!dsp_aresetn) begin arm_sync<=0;arm_seen<=0;pending<=0;active<=0;done_dsp<=0;error_dsp<=0;expected_bin<=0;end
        else begin
            arm_sync<={arm_sync[0],arm_toggle};
            if(arm_sync[1]!=arm_seen) begin
                arm_seen<=arm_sync[1];
                if(pending || active) error_dsp<=1;
                else pending<=1;
            end
            if(writing) begin
                if((active && power_bin!=expected_bin) || power_last!=(power_bin==2047)) error_dsp<=1;
                pending<=0;active<=!power_last;expected_bin<=power_bin+1'b1;
                if(power_last) done_dsp<=arm_seen;
            end
        end
    end
    always @(posedge cpu_clk) begin
        if(!cpu_aresetn) begin done_sync<=0;error_sync<=0;end
        else begin done_sync<={done_sync[0],done_dsp};error_sync<={error_sync[0],error_dsp};end
    end
endmodule
