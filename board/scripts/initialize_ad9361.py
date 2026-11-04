"""Receive-only no-OS initialization acceptance; always restore hardware reset."""
import ctypes as ct
import hashlib
import json
import os
from pathlib import Path

os.environ['XILINX_XRT'] = '/usr'
from sentinel.overlay import SentinelOverlay
from sentinel.rf.ad9361 import bind_library

root = Path('/home/xilinx/sentinel')
bit = root/'overlay/bringup_z20_lcd/bringup_z20_lcd.bit'
overlay = SentinelOverlay(str(bit), download=False)
if not overlay.overlay.is_loaded():
    raise RuntimeError('Bring-up overlay is not loaded; refusing MMIO initialization')
identity = json.loads((root/'measurements/ad9361_product_id_bringup_z20_lcd.json').read_text())
if (not identity['valid'] or not identity['stable'] or
        identity['bit_sha256'] != hashlib.sha256(bit.read_bytes()).hexdigest()):
    raise RuntimeError('Stable product-ID acceptance for this image is required first')

lib = bind_library(str(root/'ps/libad9361_pynq/libad9361_pynq.so'))

result = dict(status='started', tx_enabled=False, bit_sha256=identity['bit_sha256'])
output = root/'measurements/ad9361_initialization.json'
def save():
    output.write_text(json.dumps(result, indent=2), encoding='utf-8')
def check(code, operation):
    if code < 0:
        raise RuntimeError(operation + ' failed: ' + str(code))
save()
try:
    check(lib.z20_ad9361_open(), 'no-OS initialization')
    product = lib.z20_read_register(0x037)
    check(product, 'product ID')
    rate, mode = ct.c_uint32(), ct.c_uint32()
    check(lib.z20_get_sample_rate(ct.byref(rate)), 'sample rate')
    check(lib.z20_get_ensm_mode(ct.byref(mode)), 'ENSM mode')
    attenuation = []
    for ch in (0, 1):
        value = ct.c_uint32()
        check(lib.z20_get_tx_attenuation(ch, ct.byref(value)), 'TX attenuation')
        attenuation.append(value.value)
    result.update(product_id=hex(product), sample_rate_hz=rate.value,
                  ensm_mode=mode.value, tx_attenuation_mdb=attenuation)
    if (product & 0xf8) != 8 or rate.value != 30720000 or mode.value != 2 or attenuation != [89750, 89750]:
        raise RuntimeError('Initialization readback acceptance failed')
    result['status'] = 'passed'
except Exception as error:
    result.update(status='failed', error=str(error))
    raise
finally:
    lib.z20_ad9361_close()
    result['gpio_after_close'] = overlay.registers('axi_ad9361_gpio').read(0)
    result['rf_held_in_reset_after_test'] = result['gpio_after_close'] == 0
    if not result['rf_held_in_reset_after_test']:
        result.update(status='failed', error='RF reset readback after close failed')
    save()
    print(json.dumps(result, indent=2), flush=True)
    if not result['rf_held_in_reset_after_test']:
        raise RuntimeError(result['error'])
