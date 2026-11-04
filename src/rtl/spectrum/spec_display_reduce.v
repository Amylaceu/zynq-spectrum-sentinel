module spec_display_reduce (
    input wire aclk,input wire aresetn,input wire [15:0] frame_decim,
    input wire [15:0] s_axis_tdata,input wire s_axis_tvalid,
    output wire s_axis_tready,input wire s_axis_tlast,
    output reg [15:0] m_axis_tdata,output reg [9:0] m_axis_tuser,
    output reg m_axis_tvalid,input wire m_axis_tready,output reg m_axis_tlast,
    output reg framing_error
);
    reg [10:0] segment_end[0:559];
    integer j;
    initial for(j=0;j<560;j=j+1) segment_end[j]=((j+1)*2048)/560-1;
    reg [10:0] bin,end_bin;
    reg [9:0] pixel;
    reg signed [15:0] maximum;
    reg [15:0] skip_left,latched_decim;
    wire signed [15:0] value=s_axis_tdata;
    wire signed [15:0] candidate=value>maximum ? value : maximum;
    assign s_axis_tready=!m_axis_tvalid || m_axis_tready;
    always @(posedge aclk) begin
        if(!aresetn) begin
            bin<=0;end_bin<=2;pixel<=0;maximum<=16'sh8000;skip_left<=0;latched_decim<=1;
            m_axis_tvalid<=0;m_axis_tdata<=0;m_axis_tuser<=0;m_axis_tlast<=0;framing_error<=0;
        end else begin
            if(m_axis_tvalid && m_axis_tready) m_axis_tvalid<=0;
            if(s_axis_tvalid && s_axis_tready) begin
                if(bin==0) latched_decim<=frame_decim==0 ? 16'd1 : frame_decim;
                if(s_axis_tlast!=(bin==2047)) framing_error<=1;
                bin<=bin+1'b1;
                if(bin==end_bin) begin
                    if(skip_left==0) begin
                        m_axis_tdata<=candidate;m_axis_tuser<=pixel;
                        m_axis_tlast<=pixel==559;m_axis_tvalid<=1;
                    end
                    maximum<=16'sh8000;
                    if(pixel==559) begin
                        pixel<=0;end_bin<=2;
                        skip_left<=skip_left==0 ? latched_decim-1'b1 : skip_left-1'b1;
                    end else begin pixel<=pixel+1'b1;end_bin<=segment_end[pixel+1'b1];end
                end else maximum<=candidate;
            end
        end
    end
endmodule
