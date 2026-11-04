module sentinel_events (
    input wire dsp_clk,input wire dsp_aresetn,input wire cfar_irq,
    input wire lcd_clk,input wire lcd_aresetn,input wire lcd_irq,
    input wire cpu_clk,input wire cpu_aresetn,
    input wire src_error,input wire spec_error,input wire adc_error,
    output wire dsp_error,output wire [1:0] interrupts,output wire interrupt_any
);
    reg cfar_toggle,lcd_toggle;
    (* ASYNC_REG="TRUE" *) reg [1:0] cfar_sync,lcd_sync;
    reg cfar_previous,lcd_previous;
    assign interrupt_any=|interrupts;
    assign dsp_error=src_error || spec_error || adc_error;
    assign interrupts={lcd_sync[1]^lcd_previous,cfar_sync[1]^cfar_previous};
    always @(posedge dsp_clk) begin
        if(!dsp_aresetn) cfar_toggle<=0;else if(cfar_irq) cfar_toggle<=!cfar_toggle;
    end
    always @(posedge lcd_clk) begin
        if(!lcd_aresetn) lcd_toggle<=0;else if(lcd_irq) lcd_toggle<=!lcd_toggle;
    end
    always @(posedge cpu_clk) begin
        if(!cpu_aresetn) begin cfar_sync<=0;lcd_sync<=0;cfar_previous<=0;lcd_previous<=0;end
        else begin
            cfar_sync<={cfar_sync[0],cfar_toggle};lcd_sync<={lcd_sync[0],lcd_toggle};
            cfar_previous<=cfar_sync[1];lcd_previous<=lcd_sync[1];
        end
    end
endmodule
