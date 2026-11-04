module lcd8080_bus #(
    parameter RESET_CYCLES=1000000,parameter STARTUP_CYCLES=5000000,
    parameter DELAY_SHIFT=0
)(
    input wire sys_clk,input wire aresetn,input wire [7:0] bus_phase_cycles,
    input wire [16:0] s_axis_tdata,input wire s_axis_tvalid,output wire s_axis_tready,
    output reg initialized,
    output reg [15:0] lcd_data,output wire lcd_cs_n,output reg lcd_rs,
    output reg lcd_wr_n,output wire lcd_rd_n,output reg lcd_reset_n
);
    `include "lcd_init_rom.vh"
    localparam RESET=0,STARTUP=1,SELECT=2,SETUP=3,LOW=4,HIGH=5,COMPLETE=6,DELAY=7;
    reg [2:0] state;
    reg [31:0] wait_count;
    reg [7:0] init_index,phase_count,word_phase;
    wire [31:0] instruction=lcd_init_rom(init_index);
    wire [7:0] requested_phase=bus_phase_cycles==0 ? 8'd1 : bus_phase_cycles;
    assign lcd_cs_n=0;assign lcd_rd_n=1;
    assign s_axis_tready=initialized && state==SELECT;
    always @(posedge sys_clk) begin
        if(!aresetn) begin
            state<=RESET;wait_count<=0;init_index<=0;phase_count<=0;word_phase<=25;
            lcd_reset_n<=0;lcd_wr_n<=1;lcd_rs<=0;lcd_data<=0;initialized<=0;
        end else case(state)
            RESET: if(wait_count==RESET_CYCLES-1) begin wait_count<=0;lcd_reset_n<=1;state<=STARTUP;end
                else wait_count<=wait_count+1;
            STARTUP: if(wait_count==STARTUP_CYCLES-1) begin wait_count<=0;state<=SELECT;end
                else wait_count<=wait_count+1;
            SELECT: begin
                if(!initialized) begin
                    if(instruction[31:30]==2) begin wait_count<=instruction[29:0]>>DELAY_SHIFT;state<=DELAY;end
                    else begin
                        lcd_data<=instruction[15:0];lcd_rs<=instruction[30];
                        word_phase<=requested_phase;phase_count<=0;state<=SETUP;
                    end
                end else if(s_axis_tvalid) begin
                    lcd_data<=s_axis_tdata[15:0];lcd_rs<=s_axis_tdata[16];
                    word_phase<=requested_phase;phase_count<=0;state<=SETUP;
                end
            end
            SETUP: if(phase_count==word_phase-1) begin phase_count<=0;lcd_wr_n<=0;state<=LOW;end
                else phase_count<=phase_count+1;
            LOW: if(phase_count==word_phase-1) begin phase_count<=0;lcd_wr_n<=1;state<=HIGH;end
                else phase_count<=phase_count+1;
            HIGH: if(phase_count==word_phase-1) begin phase_count<=0;state<=COMPLETE;end
                else phase_count<=phase_count+1;
            COMPLETE: begin
                if(!initialized) begin
                    if(init_index==71) initialized<=1;
                    else init_index<=init_index+1;
                end
                state<=SELECT;
            end
            DELAY: if(wait_count==0) begin init_index<=init_index+1;state<=SELECT;end
                else wait_count<=wait_count-1;
        endcase
    end
endmodule
