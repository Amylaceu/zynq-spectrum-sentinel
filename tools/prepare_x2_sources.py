"""Create the independent X2 source overlay once; preserve frozen v1/v1b files."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def save(relative, text):
    path = ROOT / relative
    if path.exists():
        raise FileExistsError(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))


def main():
    text = (ROOT / "src/rtl/spectrum/spec_front.v").read_text()
    text = text.replace("module spec_front (", "module spec_front_x2 (")
    text = text.replace("spec_welch welch", "spec_welch_x2 welch")
    text = text.replace("axis_fork2 #", "axis_broadcast2 #")
    save("src/rtl/x2/spec_front_x2.v", text)

    text = (ROOT / "src/rtl/adc_tap/adc_tap.v").read_text()
    text = text.replace("module adc_tap #", "module adc_tap_x2 #")
    text = text.replace("output wire overflow_sticky,", "output wire [31:0] sample_drop,\n    output wire overflow_sticky,")
    text = text.replace("reg overflow_adc,mismatch_adc;", """reg overflow_adc,mismatch_adc;
    reg [31:0] drop_binary,drop_gray;
    (* ASYNC_REG="TRUE" *) reg [31:0] drop_sync0,drop_sync1;
    wire lost=input_valid && (full || wr_busy);
    wire [31:0] drop_next=lost && drop_binary!=32'hffffffff ? drop_binary+1'b1 : drop_binary;
    function [31:0] from_gray(input [31:0] gray);
        integer k;
        begin from_gray[31]=gray[31];
            for(k=30;k>=0;k=k-1) from_gray[k]=from_gray[k+1]^gray[k];
        end
    endfunction
    assign sample_drop=from_gray(drop_sync1);
    // Registered Gray crosses the domains; only a single bit changes per ADC
    // clock. Counters exclude reset, include valid samples during reset-busy,
    // and saturate. Rate changes require a fresh baseline after settling.
    always @(posedge adc_clk) begin
        if(fifo_reset) begin drop_binary<=0;drop_gray<=0;end
        else begin drop_binary<=drop_next;drop_gray<=(drop_next>>1)^drop_next;end
    end
    always @(posedge dsp_clk) begin
        if(!dsp_aresetn) begin drop_sync0<=0;drop_sync1<=0;end
        else begin drop_sync0<=drop_gray;drop_sync1<=drop_sync0;end
    end""")
    text = text.replace("if(input_valid && full && !wr_busy)", "if(lost)")
    save("src/rtl/x2/adc_tap_x2.v", text)

    text = (ROOT / "src/rtl/cfar_x1/cfar_core_x1.v").read_text()
    header = text[text.index("module cfar_core_x1 ("):text.index(");")]
    header = header.replace("module cfar_core_x1", "module cfar_core_x2")
    header += """,
    output wire [15:0] m_axis_db_tdata,output wire [9:0] m_axis_db_tuser,
    output wire m_axis_db_tvalid,input wire m_axis_db_tready,output wire m_axis_db_tlast,
    output wire [31:0] frames_in,output wire [31:0] frames_out,output wire [31:0] frame_drop,
    output wire queue_error
);\n"""
    names = re.findall(r"(?:input|output) wire (?:\[[^\]]+\] )?(\w+)", header.split(",\n    output wire [15:0] m_axis_db")[0])
    substitutions = {"s_axis_pwr_tdata": "detect_payload[31:0]", "s_axis_pwr_tlast": "detect_payload[32]",
                     "s_axis_pwr_tvalid": "detect_valid", "s_axis_pwr_tready": "detect_ready"}
    body = """    wire [31:0] queued;wire qvalid,qready,qlast,queue_framing,display_error;
    wire [32:0] detect_payload,display_payload;
    wire detect_valid,detect_ready,display_valid,display_ready;
    wire [15:0] db;wire db_valid,db_ready,db_last;
    assign queue_error=queue_framing || display_error;
    frame_queue_x2 queue(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(s_axis_pwr_tdata),.s_axis_tvalid(s_axis_pwr_tvalid),.s_axis_tready(s_axis_pwr_tready),.s_axis_tlast(s_axis_pwr_tlast),
        .m_axis_tdata(queued),.m_axis_tvalid(qvalid),.m_axis_tready(qready),.m_axis_tlast(qlast),
        .frames_in(frames_in),.frames_out(frames_out),.frame_drop(frame_drop),.framing_error(queue_framing));
    // Both detector and displayed spectrum see exactly the same retained frames.
    axis_broadcast2 #(.WIDTH(33)) paired(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata({qlast,queued}),.s_axis_tvalid(qvalid),.s_axis_tready(qready),
        .m0_axis_tdata(detect_payload),.m0_axis_tvalid(detect_valid),.m0_axis_tready(detect_ready),
        .m1_axis_tdata(display_payload),.m1_axis_tvalid(display_valid),.m1_axis_tready(display_ready));
    spec_db logarithm(.aclk(aclk),.aresetn(aresetn),
        .s_axis_tdata(display_payload[31:0]),.s_axis_tvalid(display_valid),.s_axis_tready(display_ready),.s_axis_tlast(display_payload[32]),
        .m_axis_tdata(db),.m_axis_tvalid(db_valid),.m_axis_tready(db_ready),.m_axis_tlast(db_last));
    spec_display_reduce reduction(.aclk(aclk),.aresetn(aresetn),.frame_decim(16'd1),
        .s_axis_tdata(db),.s_axis_tvalid(db_valid),.s_axis_tready(db_ready),.s_axis_tlast(db_last),
        .m_axis_tdata(m_axis_db_tdata),.m_axis_tuser(m_axis_db_tuser),.m_axis_tvalid(m_axis_db_tvalid),
        .m_axis_tready(m_axis_db_tready),.m_axis_tlast(m_axis_db_tlast),.framing_error(display_error));
    cfar_core_x1 core(\n"""
    body += ",\n".join("        .%s(%s)" % (name, substitutions.get(name, name)) for name in names)
    body += ");\nendmodule\n"
    save("src/rtl/x2/cfar_core_x2.v", header + body)


if __name__ == "__main__":
    main()
