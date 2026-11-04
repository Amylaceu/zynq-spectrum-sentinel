"""Wrap both CFAR cores with identical registers for isolated timing study."""
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]

def main():
    source=(ROOT/'src/rtl/cfar_x1/cfar_core_x1.v').read_text()
    header=source[source.index('(')+1:source.index(');')]
    declarations=[]
    for part in header.split(','):
        tokens=part.split()
        if len(tokens) not in (3,4) or tokens[0] not in ('input','output') or tokens[1]!='wire':
            raise ValueError('Unexpected port declaration: '+part)
        declarations.append((tokens[0],tokens[2] if len(tokens)==4 else '',tokens[-1]))
    for core,name in [('cfar_core_x1','cfar_reference_regwrap'),
                      ('cfar_core_maskpipe_x2','cfar_maskpipe_regwrap')]:
        dest=ROOT/'sim/tb'/(name+'.v')
        if dest.exists():raise FileExistsError(dest)
        lines=['// Identical registered boundary; CPU/FPGA deployment unchanged.',
               'module '+name+' (']
        lines.append(',\n'.join('    '+direction+' wire '+(width or '')+' '+port
                               for direction,width,port in declarations))
        lines.append(');')
        connects=[]
        for direction,width,port in declarations:
            width=width or ''
            if port=='aclk': connects.append('.aclk(aclk)');continue
            lines.append('    reg '+width+' q_'+port+';')
            if direction=='input':
                lines.append('    always @(posedge aclk) q_'+port+' <= '+port+';')
                connects.append('.'+port+'(q_'+port+')')
            else:
                lines.append('    wire '+width+' d_'+port+';')
                lines.append('    always @(posedge aclk) q_'+port+' <= d_'+port+';')
                lines.append('    assign '+port+' = q_'+port+';')
                connects.append('.'+port+'(d_'+port+')')
        lines.extend(['    '+core+' core('+','.join(connects)+');','endmodule'])
        dest.write_bytes(('\n'.join(lines)+'\n').encode())
    print('REGISTERED_TIMING_WRAPPERS_READY')

if __name__=='__main__':main()
