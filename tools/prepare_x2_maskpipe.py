"""Derive an isolated registered-mask CFAR from the accepted X1 source."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Expected unique source anchor: '+old)
    return text.replace(old,new,1)

def main():
    dest=ROOT/'src/rtl/x2_opt/cfar_core_maskpipe_x2.v'
    tb=ROOT/'sim/tb/tb_cfar_maskpipe_x2.sv'
    if dest.exists() or tb.exists():raise FileExistsError('Preserve prior generated candidate')
    text=(ROOT/'src/rtl/cfar_x1/cfar_core_x1.v').read_text()
    text=replace(text,'module cfar_core_x1 (','module cfar_core_maskpipe_x2 (')
    text=replace(text,'wire accept=detected_valid && detected_ready;',
        'reg mask_valid; reg [93:0] mask_data;\n'
        '    wire mask_ready=broadcast_ready && cluster_ready;\n'
        '    wire accept=mask_valid && mask_ready;')
    text=replace(text,'clear_token!=clear_seen && detect_idle && !cluster_busy;',
                      'clear_token!=clear_seen && detect_idle && !cluster_busy && !mask_valid;')
    text=replace(text,'!occ_clearing && !clear_request && !cluster_busy;',
                      '!occ_clearing && !clear_request && !cluster_busy && !mask_valid;')
    text=replace(text,'!detect_idle || cluster_busy};','!detect_idle || cluster_busy || mask_valid};')
    text=replace(text,'assign filtered={detected[92:1],detected[0] && !blocked};',
        '''// Register masked hit AND blocked sideband together. One-cycle latency;
    // the complete payload holds under downstream stalls. Never mask twice.
    assign filtered=mask_data[92:0];
    always @(posedge aclk) begin
        if(!aresetn) begin mask_valid<=0;mask_data<=0;end
        else if(detected_ready) begin
            mask_valid<=detected_valid;
            if(detected_valid) mask_data<={blocked,detected[92:1],detected[0] && !blocked};
        end
    end''')
    text=replace(text,'assign detected_ready=broadcast_ready && cluster_ready;',
                      'assign detected_ready=!mask_valid || mask_ready;')
    text=replace(text,'.s_axis_tvalid(detected_valid && cluster_ready)',
                      '.s_axis_tvalid(mask_valid && cluster_ready)')
    text=replace(text,'.hit(filtered[0]),.blocked(blocked)',
                      '.hit(filtered[0]),.blocked(mask_data[93])')
    text='// EXPERIMENTAL: not packaged/deployed. Register the real mask-to-cluster critical path.\n'+text
    dest.write_bytes(text.encode('utf-8'))
    bench=(ROOT/'sim/tb/tb_cfar_guard8.sv').read_text()
    bench=replace(bench,'module tb_cfar_guard8;','module tb_cfar_maskpipe_x2;')
    bench=replace(bench,'cfar_core_x1 dut(','cfar_core_maskpipe_x2 dut(')
    bench=bench.replace('x1_guard8_','x2_maskpipe_')
    tb.write_bytes(bench.encode('utf-8'))
    print('X2_MASKPIPE_CANDIDATE_PREPARED')

if __name__=='__main__':main()
