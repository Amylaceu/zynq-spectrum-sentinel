"""Second candidate: register configuration validity with AXI write quiet gate."""
from pathlib import Path
from prepare_x2_maskpipe import replace
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=ROOT/'src/rtl/x2_opt/cfar_core_cfgpipe_x2.v'
    tb=ROOT/'sim/tb/tb_cfar_cfgpipe_x2.sv'
    wrapper=ROOT/'sim/tb/cfar_cfgpipe_regwrap.v'
    if any(p.exists() for p in (out,tb,wrapper)):raise FileExistsError('Preserve prior candidate')
    text=(ROOT/'src/rtl/x2_opt/cfar_core_maskpipe_x2.v').read_text()
    text=replace(text,'module cfar_core_maskpipe_x2 (','module cfar_core_cfgpipe_x2 (')
    text=replace(text,'wire valid_config=n_shift<=6', 'wire valid_config_raw=n_shift<=6')
    anchor='    wire enable=ctrl[0]'
    inserted='''    // AXI accepts AW/W independently. A quiet gate blocks new frames
    // while either write half is outstanding, a response is pending, or the
    // registered validity result may still describe the previous configuration.
    // Existing frames retain their snapshotted parameters and keep draining.
    reg valid_config;
    reg [1:0] config_quiet;
    wire config_write_busy=s_axi_awvalid || s_axi_wvalid ||
        !s_axi_awready || !s_axi_wready || s_axi_bvalid;
    always @(posedge aclk) begin
        if(!aresetn) begin valid_config<=0;config_quiet<=0;end
        else begin
            valid_config<=valid_config_raw;
            if(config_write_busy) config_quiet<=0;
            else config_quiet<={config_quiet[0],1'b1};
        end
    end
    wire enable=(&config_quiet) && !config_write_busy && ctrl[0]'''
    text=replace(text,anchor,inserted)
    out.write_bytes(text.encode())
    bench=(ROOT/'sim/tb/tb_cfar_maskpipe_x2.sv').read_text().replace('tb_cfar_maskpipe_x2','tb_cfar_cfgpipe_x2').replace('cfar_core_maskpipe_x2','cfar_core_cfgpipe_x2').replace('x2_maskpipe_','x2_cfgpipe_')
    # Existing split AW/W writes and mid-frame config changes exercise the gate.
    tb.write_bytes(bench.encode())
    template=(ROOT/'sim/tb/cfar_maskpipe_regwrap.v').read_text()
    wrapper.write_bytes(template.replace('cfar_maskpipe_regwrap','cfar_cfgpipe_regwrap').replace('cfar_core_maskpipe_x2','cfar_core_cfgpipe_x2').encode())
    print('X2_CFGPIPE_PREPARED')

if __name__=='__main__':main()
