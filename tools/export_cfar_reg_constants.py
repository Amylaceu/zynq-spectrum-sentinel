"""Export the custom memory-window register contract to C/Python constants."""
from pathlib import Path
import yaml

root = Path(__file__).resolve().parents[1]
contract = yaml.load((root/'src/regs/cfar_ctrl.yaml').read_text(), Loader=yaml.BaseLoader)
values = {'BASE': int(contract['base'], 0)}
for record in contract['regs'] + contract['windows']:
    values[record['name']] = int(record['off'], 0)
    if 'bytes' in record: values[record['name']+'_BYTES'] = int(record['bytes'])
py = root/'src/ps/sentinel/drivers/regs/cfar_ctrl.py'
py.write_bytes(('"""Generated from src/regs/cfar_ctrl.yaml; synchronous memory windows."""\n'+
                ''.join(f'{key} = 0x{value:x}\n' for key,value in values.items())).encode())
(root/'src/ps/include/cfar_ctrl.h').write_bytes(('#pragma once\n'+''.join(
    f'#define CFAR_CTRL_{key} 0x{value:08x}u\n' for key,value in values.items())).encode())
print('CFAR_CONSTANTS_PASS',len(values))
