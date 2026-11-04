"""Export hardware window and logarithm ROMs from the existing numeric contract."""
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.spectrum import window_coefs, DB_MANTISSA_LUT_Q16


def main():
    out = ROOT/'data/reference/spectrum'
    files = {}
    for name in ('bh4', 'hann', 'rect'):
        words = window_coefs(name)
        path = out/('spec_window_'+name+'.hex')
        path.write_bytes(''.join('%05x\n' % (int(x) & 0x3ffff) for x in words).encode('ascii'))
        coe = path.with_suffix('.coe')
        coe.write_bytes(('memory_initialization_radix=10;\nmemory_initialization_vector=\n'+
                         ',\n'.join(str(int(x)) for x in words)+';\n').encode('ascii'))
        for file in (path, coe):
            files[file.name] = hashlib.sha256(file.read_bytes()).hexdigest()
    path = out/'spec_log_mantissa.hex'
    path.write_bytes(''.join('%08x\n' % int(x) for x in DB_MANTISSA_LUT_Q16).encode('ascii'))
    files[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out/'n2_rom_manifest.json').write_bytes((json.dumps(files, indent=2)+'\n').encode())
    print('N2_ROM_EXPORT_PASS', len(files))


if __name__ == '__main__':
    main()
