"""One-time derivation of integrated X1 regression from the preserved N3 TB."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def rep(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected one testbench anchor: '+old[:70])
    return text.replace(old, new, 1)


def main():
    path = ROOT/'sim/tb/tb_cfar_core_x1.sv'
    if path.exists():
        raise FileExistsError('Preserve existing X1 TB')
    t = (ROOT/'sim/tb/tb_cfar_core.sv').read_text(encoding='utf-8')
    t = t.replace('tb_cfar_core;', 'tb_cfar_core_x1;').replace('CASES=13', 'CASES=18')
    t = t.replace('cfar_core dut(', 'cfar_core_x1 dut(').replace("32'h43460001", "32'h43460002")
    t = t.replace('config_words[0:CASES*6-1]', 'config_words[0:CASES*24-1],stats[0:CASES*7-1]')
    t = t.replace('integer fthr,fhit,fdb,focc,ftarget;', 'integer fthr,fhit,fdb,focc,ftarget,fstats;\n    reg checking=1;')
    t = t.replace('reg [75:0] held_hit;', 'reg [83:0] held_hit;')
    t = t.replace('{hit_last,hit_bin,threshold,power}', '{hit_last,hit_bin,hit_data,threshold,power}')
    t = t.replace('"cfar_', '"x1_core_')
    t = rep(t, '$readmemh("config.hex",config_words);', '$readmemh("stats.hex",stats);$readmemh("config.hex",config_words);')
    t = rep(t, 'repeat(12) @(negedge clk);resetn=1;',
        'fstats=$fopen("x1_core_stats_out.hex","w");\n        repeat(12) @(negedge clk);resetn=1;')
    t = rep(t, '        wait(!dut.occ_clearing);\n        for(current_case=', '''        // Mask-window WSTRB, read-only snapshot and invalid configuration guards.
        wr('h80,32'hdeadbeef);wr('h80,32'h11223344,4'b0101);rd('h80,temp);
        if(temp!==32'hde22be44) $fatal(1,"mask WSTRB");
        wr('h40,32'hffffffff);rd('h40,temp);if(temp!==0) $fatal(1,"RO snapshot");
        wait(!dut.occ_clearing);
        wr('h3c,17);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"invalid mask count accepted");
        wr(0,0);wr('h3c,1);wr('h80,32'h00030004);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"reversed mask accepted");
        wr(0,0);wr('h80,32'h08000000);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"out of range mask accepted");
        wr(0,0);wr('h3c,0);wr('h38,2049);wr(0,1);repeat(5) @(negedge clk);
        rd('h34,temp);if(!temp[3] || input_ready) $fatal(1,"invalid width accepted");
        wr(0,0);wr('h38,2);
        for(current_case=''')
    t = rep(t, 'for(r=1;r<6;r=r+1) wr(r*4,config_words[current_case*6+r]);\n            wr(0,config_words[current_case*6]);',
        '''for(r=1;r<6;r=r+1) wr(r*4,config_words[current_case*24+r]);
            wr('h38,config_words[current_case*24+6]);wr('h3c,config_words[current_case*24+7]);
            for(r=0;r<16;r=r+1) wr('h80+r*4,config_words[current_case*24+8+r]);
            wr(0,config_words[current_case*24]);''')
    t = rep(t, 'if(random_state[3:2]==0) begin @(negedge clk);input_valid=0;end',
        '''if(send_index==20) begin
                    @(negedge clk);input_valid=0;
                    // Current frame must retain the original mask/DC/gap/width.
                    wr('h14,0);wr('h38,2048);wr('h80,32'h07ff0000);wr('h3c,1);wr('h10,255);
                end
                if(random_state[3:2]==0) begin @(negedge clk);input_valid=0;end''')
    t = rep(t, "rd('h34,temp);if(temp[3:0]!==0) $fatal(1,\"STATUS %h\",temp);", '''wait(!dut.cluster_busy);
            rd('h34,temp);if(temp[3:0]!==0) $fatal(1,"STATUS %h",temp);
            rd('h18,temp);$fdisplay(fstats,"%08x",temp);
            rd('h44,temp);if(temp!==stats[current_case*7+1]) $fatal(1,"RAW_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h48,temp);if(temp!==stats[current_case*7+2]) $fatal(1,"FILTERED_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h4c,temp);if(temp!==stats[current_case*7+3]) $fatal(1,"CANDIDATE_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h20,temp);if(temp!==stats[current_case*7+4]) $fatal(1,"HIT_COUNT");$fdisplay(fstats,"%08x",temp);
            rd('h40,temp);if(temp!==stats[current_case*7+5]) $fatal(1,"STATUS_LATCH");$fdisplay(fstats,"%08x",temp);
            rd('h28,temp);if(temp!==stats[current_case*7+6]) $fatal(1,"ALARM");$fdisplay(fstats,"%08x",temp);''')
    t = t.replace('$display("CFAR_CASE_PASS ', '$display("X1_CORE_CASE_PASS ')
    t = rep(t, 'if(irq) nirq=nirq+1;', '''if(irq) begin
            nirq=nirq+1;
            if(checking && (dut.frames!==current_case+1 || dut.targets!==stats[current_case*7] ||
                dut.raw_count!==stats[current_case*7+1] || dut.filtered_count!==stats[current_case*7+2] ||
                dut.candidate_count!==stats[current_case*7+3] || dut.hits!==stats[current_case*7+4] ||
                dut.status_latch!==stats[current_case*7+5] || dut.alarm!==stats[current_case*7+6]))
                $fatal(1,"non-atomic frame publication");
        end''')
    t = t.replace('if(hit_valid && hit_ready) begin', 'if(checking && hit_valid && hit_ready) begin')
    t = t.replace('if(thr_valid && thr_ready) begin', 'if(checking && thr_valid && thr_ready) begin')
    t = t.replace('if(tgt_valid && tgt_ready) begin', 'if(checking && tgt_valid && tgt_ready) begin')
    t = rep(t, '$fclose(fthr);$fclose(fhit);$fclose(fdb);$fclose(focc);$fclose(ftarget);',
        '''$fclose(fthr);$fclose(fhit);$fclose(fdb);$fclose(focc);$fclose(ftarget);$fclose(fstats);
        // Framing errors are visible both live and in the published frame.
        checking=0;wr('h3c,0);wr('h38,2);wr('h10,255);wr('hc,1974);wr(0,1);
        for(send_index=0;send_index<2048;send_index=send_index+1) begin
            @(negedge clk);input_data=0;input_valid=1;input_last=(send_index==100 || send_index==2047);
            do @(posedge clk);while(!input_ready);
        end
        @(negedge clk);input_valid=0;wait(nirq==CASES+1);wait(!dut.cluster_busy);
        wr(0,0);rd('h40,temp);if(!temp[2]) $fatal(1,"framing error not latched");
        rd('h34,temp);if(!temp[2]) $fatal(1,"framing error not live");
        @(negedge clk);resetn=0;repeat(5) @(negedge clk);resetn=1;
        rd('h1c,temp);if(temp!==0) $fatal(1,"reset sequence");
        rd('h40,temp);if(temp!==0) $fatal(1,"reset snapshot");''')
    t = t.replace('TB_RESULT: PASS CFAR 13 cases, modes/wrap/stalls/lists/occupancy/AXI',
        'TB_RESULT: PASS X1_CORE 18 cases, modes/masks/frame_config/atomic_stats/AXI/occupancy/framing')
    path.write_bytes(t.encode('utf-8'))
    print('X1_CORE_TB_PREPARED')


if __name__ == '__main__':
    main()
