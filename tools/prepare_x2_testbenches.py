"""Derive independent X2 ADC and full-chain benches; never edit X1 evidence."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def save(name, text):
    path = ROOT / "sim/tb" / name
    if path.exists():
        raise FileExistsError(path)
    path.write_bytes(text.encode())


def main():
    text = (ROOT / "sim/tb/tb_adc_tap.sv").read_text()
    text = text.replace("module tb_adc_tap;", "module tb_adc_tap_x2;")
    text = text.replace("adc_tap #", "adc_tap_x2 #")
    text = text.replace("wire valid,last,overflow,mismatch;", "wire valid,last,overflow,mismatch;wire [31:0] sample_drop;integer drained=0;")
    text = text.replace(".overflow_sticky(overflow)", ".sample_drop(sample_drop),.overflow_sticky(overflow)")
    text = text.replace("if(overflow || mismatch) $fatal", "if(overflow || mismatch || sample_drop!=0) $fatal")
    text = text.replace("adc_reset=1;resetn=0;repeat(20)", """ready=1;
        wait(!valid);repeat(20) @(negedge dsp_clk);
        if(sample_drop==0 || sample_drop+drained!=128) $fatal(1,"drop conservation drop%0d drained%0d",sample_drop,drained);
        $display("X2_ADC forced_input=128 sample_drop=%0d drained=%0d",sample_drop,drained);
        adc_reset=1;resetn=0;repeat(20)""")
    text = text.replace("cycles=cycles+1;", "cycles=cycles+1;\n        if(resetn && !compare && valid && ready) drained=drained+1;")
    save("tb_adc_tap_x2.sv", text)

    text = (ROOT / "sim/tb/tb_sentinel_chain_x1.sv").read_text()
    text = text.replace("module tb_sentinel_chain_x1;", "module tb_sentinel_chain_x2;")
    text = text.replace("reg resetn=0,input_valid=0,input_last=0;reg [31:0] input_data=0;", """reg resetn=0;
    reg adc_clk=0;always #8.138 adc_clk=~adc_clk;
    reg adc_reset=1,vi=0;reg [15:0] ai=0,aq=0;
    wire input_valid,input_last,input_ready;wire [31:0] input_data;
    wire [31:0] sample_drop,frames_in,frames_out,frame_drop;
    wire overflow,mismatch,queue_error;wire [12:0] fifo_level;
    adc_tap_x2 tap(.adc_clk(adc_clk),.adc_reset(adc_reset),.adc_i(ai),.adc_q(aq),
        .adc_valid_i(vi),.adc_valid_q(vi),.dsp_clk(clk),.dsp_aresetn(resetn),
        .m_axis_tdata(input_data),.m_axis_tvalid(input_valid),.m_axis_tready(input_ready),.m_axis_tlast(input_last),
        .sample_drop(sample_drop),.overflow_sticky(overflow),.mismatch_sticky(mismatch),.fifo_level(fifo_level));""")
    text = text.replace("    wire input_ready;", "")
    text = text.replace("[0:15]", "[0:63]")
    text = text.replace("spec_front dut", "spec_front_x2 dut")
    # The pre-queue logarithm is drained. Only the retained frame stream is
    # displayed, alongside thresholds generated from those very same frames.
    text = text.replace(".m_axis_db_tdata(db_data),.m_axis_db_tuser(db_pixel),.m_axis_db_tvalid(db_valid),.m_axis_db_tready(db_ready),.m_axis_db_tlast(db_last)",
                        ".m_axis_db_tdata(),.m_axis_db_tuser(),.m_axis_db_tvalid(),.m_axis_db_tready(1'b1),.m_axis_db_tlast()")
    text = text.replace("cfar_core_x1 cfar", "cfar_core_x2 cfar")
    text = text.replace(".s_axis_pwr_tready(pwr_ready),.s_axis_pwr_tlast(pwr_last),", """.s_axis_pwr_tready(pwr_ready),.s_axis_pwr_tlast(pwr_last),
        .m_axis_db_tdata(db_data),.m_axis_db_tuser(db_pixel),.m_axis_db_tvalid(db_valid),.m_axis_db_tready(db_ready),.m_axis_db_tlast(db_last),
        .frames_in(frames_in),.frames_out(frames_out),.frame_drop(frame_drop),.queue_error(queue_error),""")
    text = text.replace("force cfar.registers", "force cfar.core.registers")
    start = text.index("        for(sent=0;sent<32768;")
    end = text.index("        @(negedge lc);accept_frame=1;", start)
    text = text[:start] + """        adc_reset=0;wait(!tap.wr_busy && !tap.rd_busy);repeat(8) @(negedge adc_clk);
        // Non-backpressurable ADC: one IQ pair per two 61.44MHz clocks,
        // regardless of the downstream tready. This is 30.72MSPS, not a
        // handshake-limited stimulus claiming to be a zero-loss ADC.
        for(sent=0;sent<64*2048;sent=sent+1) begin
            @(negedge adc_clk);ai=$signed(stimulus[sent%8192][15:0]) >>> 4;
            aq=$signed(stimulus[sent%8192][31:16]) >>> 4;vi=1;
            @(negedge adc_clk);vi=0;
        end
        wait(frames_in==64 && frames_out+frame_drop==64);
        wait(cfar.core.frames==frames_out && tn==frames_out*560);repeat(30) @(negedge lc);
        if(!snapshot_ready || n!=64*2048 || sample_drop!=0 || overflow || mismatch || queue_error ||
            error_sticky || reduce_error || snapshot_error || cfar.core.detect_error) $fatal(1,"X2 chain loss/framing error n%0d sd%0d",n,sample_drop);
""" + text[end:]
    start = text.index('        $display("CHAIN_STEADY')
    end = text.index("    end\n    initial begin", start)
    text = text[:start] + """        $display("X2_CHAIN sample_rate=30720000 adc_inputs=131072 power_words=%0d sample_drop=%0d frames_in=%0d frames_out=%0d frame_drop=%0d threshold_pixels=%0d",n,sample_drop,frames_in,frames_out,frame_drop,tn);
        $display("TB_RESULT: PASS ADC async FIFO->FFT->Welch->whole-frame queue->CFAR->paired LCD,64 frames,zero lost samples,first8192 exact power words");$finish;
""" + text[end:]
    save("tb_sentinel_chain_x2.sv", text)


if __name__ == "__main__":
    main()
