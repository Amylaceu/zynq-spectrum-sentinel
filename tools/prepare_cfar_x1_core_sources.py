"""One-time, reviewed derivation of X1 interfaces from accepted v1 sources.

Refuses to overwrite X1 output. Kept to make the initial derivation auditable;
subsequent edits are made directly to the generated X1 source files.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one source anchor: ' + old[:80])
    return text.replace(old, new, 1)


def main():
    dest = ROOT / 'src/rtl/cfar_x1/cfar_x1_regs.v'
    if dest.exists():
        raise FileExistsError('Preserve existing X1 source')
    text = (ROOT / 'src/rtl/regs/cfar_ctrl_regs.v').read_text(encoding='utf-8')
    text = text.replace('// Custom synchronous memory windows; contract: src/regs/cfar_ctrl.yaml.',
                        '// X1 AXI-Lite bank: src/regs/cfar_x1.yaml. Old v1 bank remains unchanged.')
    text = text.replace('module cfar_ctrl_regs (', 'module cfar_x1_regs (')
    text = replace_once(text, 'output reg [31:0] reg_alarm_limit,reg_occ_clear_token,',
        'output reg [31:0] reg_alarm_limit,reg_occ_clear_token,reg_min_width,reg_mask_count,\n'
        '    output reg [511:0] reg_masks,')
    text = replace_once(text, 'input wire [31:0] target_count,frame_count,hit_count,alarm,occ_frames,status,',
        'input wire [31:0] target_count,frame_count,hit_count,alarm,occ_frames,status,\n'
        '    input wire [31:0] status_latch,raw_count,filtered_count,candidate_count,')
    text = replace_once(text, 'assign target_word_addr=s_axi_araddr[8:2];',
        '// The X1 target window is combinational and uses the captured address.\n'
        '    assign target_word_addr=read_address[8:2];')
    text = text.replace('reg_dc_mask<=3;reg_gap<=2;', 'reg_dc_mask<=3;reg_gap<=6;')
    text = replace_once(text, 'reg_alarm_limit<=1;reg_occ_clear_token<=0;',
        'reg_alarm_limit<=1;reg_occ_clear_token<=0;\n'
        '            reg_min_width<=2;reg_mask_count<=0;reg_masks<=0;')
    text = replace_once(text, "'h2c:reg_occ_clear_token[lane*8+:8]<=w_data[lane*8+:8];",
        "'h2c:reg_occ_clear_token[lane*8+:8]<=w_data[lane*8+:8];\n"
        "                        'h38:reg_min_width[lane*8+:8]<=w_data[lane*8+:8];\n"
        "                        'h3c:reg_mask_count[lane*8+:8]<=w_data[lane*8+:8];")
    text = replace_once(text, 'default:begin end',
        "default:if(aw_address>='h80 && aw_address<'hc0 && aw_address[1:0]==0)\n"
        "                            reg_masks[(aw_address[5:2]*32)+(lane*8)+:8]<=w_data[lane*8+:8];")
    text = replace_once(text, "else case(read_address)",
        "else if(read_address>='h80 && read_address<'hc0 && read_address[1:0]==0)\n"
        "                    s_axi_rdata<=reg_masks[read_address[5:2]*32+:32];\n"
        "                else case(read_address)")
    text = replace_once(text, "'h34:s_axi_rdata<=status;",
        "'h34:s_axi_rdata<=status;\n"
        "                    'h38:s_axi_rdata<=reg_min_width;\n"
        "                    'h3c:s_axi_rdata<=reg_mask_count;\n"
        "                    'h40:s_axi_rdata<=status_latch;\n"
        "                    'h44:s_axi_rdata<=raw_count;\n"
        "                    'h48:s_axi_rdata<=filtered_count;\n"
        "                    'h4c:s_axi_rdata<=candidate_count;")
    text = text.replace("32'h43460001", "32'h43460002")
    dest.write_bytes(text.encode('utf-8'))
    print('X1_REGS_SOURCE_PREPARED', dest.relative_to(ROOT))


if __name__ == '__main__':
    main()
