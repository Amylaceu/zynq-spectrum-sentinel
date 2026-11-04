"""Generate isolated X1 constants; never modify v1 constants or RTL."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def contract_values(source):
    contract = yaml.load(source.read_text(encoding='utf-8'), Loader=yaml.BaseLoader)
    values = {'BASE': int(contract['base'], 0)}
    occupied = set()
    for record in contract['regs'] + contract['windows']:
        name = record['name']
        offset = int(record['off'], 0)
        size = int(record.get('bytes', '4'))
        if name in values or offset % 4 or size <= 0 or size % 4:
            raise ValueError('Invalid or duplicate X1 register/window')
        addresses = set(range(offset, offset + size, 4))
        if occupied & addresses or offset + size > (1 << int(contract['address_width'])):
            raise ValueError('Overlapping or out-of-range X1 register/window')
        occupied.update(addresses)
        values[name] = offset
        if 'bytes' in record:
            values[name + '_BYTES'] = size
        if name == 'VERSION':
            values['VERSION_VALUE'] = int(record['reset'], 0)
    return values


def main():
    values = contract_values(ROOT / 'src/regs/cfar_x1.yaml')
    header = 'Generated from src/regs/cfar_x1.yaml; X1 hardware is not yet deployed.'
    outputs = {
        ROOT / 'src/ps/sentinel/drivers/regs/cfar_x1.py':
            '"""' + header + '"""\n' + ''.join('%s = 0x%x\n' % item for item in values.items()),
        ROOT / 'src/ps/include/cfar_x1.h':
            '// ' + header + '\n#pragma once\n' + ''.join(
                '#define CFAR_X1_%s 0x%08xu\n' % item for item in values.items()),
        ROOT / 'sim/tb/cfar_x1_defs.vh':
            '// ' + header + '\n' + ''.join(
                "localparam CFAR_X1_%s = 32'h%08x;\n" % item for item in values.items()),
    }
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode('utf-8'))
    print('CFAR_X1_CONSTANTS_GENERATED', len(values))


if __name__ == '__main__':
    main()
