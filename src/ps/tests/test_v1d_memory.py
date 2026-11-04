"""BRAM validation must work with PYNQ2.7's missing ip_dict entries."""
import hashlib
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from sentinel.v1d import checked_memory_windows


def bundle(tmp_path, windows=None):
    windows = windows if windows is not None else [
        ('axi_lcd_ui', 0x42100000, 131072), ('axi_power_capture', 0x42010000, 8192)]
    bit = tmp_path/'sentinel_v1d.bit'
    bit.write_bytes(b'test fixture, not programmable')
    hwh = bit.with_suffix('.hwh')
    hwh.write_text('<ROOT>'+''.join(
        '<MEMRANGE INSTANCE="%s" MEMTYPE="MEMORY" BASEVALUE="%s" HIGHVALUE="%s"/>'
        % (name, hex(base), hex(base+size-1)) for name, base, size in windows)+'</ROOT>')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    acceptance = tmp_path/'acceptance.json'
    acceptance.write_text(json.dumps(dict(status='PASS', image='sentinel_v1d',
                                         artifacts_sha256={p.name: sha(p) for p in (bit, hwh)})))
    (tmp_path/'acceptance.json.sha256').write_text(sha(acceptance)+'  acceptance.json\n')
    return bit


def test_memory_ranges_without_pynq_or_hardware(tmp_path):
    checked_memory_windows(bundle(tmp_path))


@pytest.mark.parametrize('windows', [[], [('axi_lcd_ui', 0x42100000, 65536)],
    [('axi_lcd_ui', 0x42100000, 131072), ('axi_power_capture', 0x42010004, 8192)]])
def test_missing_or_misaddressed_bram_rejected(tmp_path, windows):
    with pytest.raises(RuntimeError, match='memory window'):
        checked_memory_windows(bundle(tmp_path, windows))


def test_modified_hwh_cannot_supply_fake_map(tmp_path):
    bit = bundle(tmp_path)
    bit.with_suffix('.hwh').write_text('<ROOT/>')
    with pytest.raises(ValueError, match='artifact mismatch'):
        checked_memory_windows(bit)
