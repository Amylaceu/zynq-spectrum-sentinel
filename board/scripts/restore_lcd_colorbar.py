"""Reload the verified joint image to restart LCD initialization; keep RF reset."""
import fcntl
import hashlib
import json
import os
import time
from pathlib import Path

os.environ['XILINX_XRT'] = '/usr'
from pynq import PL
from sentinel.overlay import SentinelOverlay, validate_artifacts

root = Path('/home/xilinx/sentinel')
bit = validate_artifacts(root / 'overlay/bringup_z20_lcd/bringup_z20_lcd.bit')
lock = open('/run/lock/zss_ad9361.lock', 'a')
fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
result = dict(expected_image=str(bit), bit_sha256=hashlib.sha256(bit.read_bytes()).hexdigest(),
              loaded_image_before=PL.bitfile_name, timestamp_before=PL.timestamp,
              rf_transmission_requested=False, visual_confirmation='pending_user')
try:
    overlay = SentinelOverlay(str(bit), download=True)
    result['image_loaded_after'] = overlay.overlay.is_loaded()
    if not result['image_loaded_after']:
        raise RuntimeError('Required image not loaded after download')
    gpio = overlay.registers('axi_ad9361_gpio')
    gpio.write(0, 0)
    result['gpio_after_restore'] = gpio.read(0)
    if result['gpio_after_restore'] != 0:
        raise RuntimeError('RF reset readback mismatch')
    time.sleep(2)
    result['loaded_image_after'] = PL.bitfile_name
    result['status'] = 'program_loaded_visual_check_pending'
except Exception as error:
    result.update(status='failed', error=str(error))
    raise
finally:
    (root / 'measurements/lcd_restore.json').write_text(
        json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, indent=2), flush=True)
