"""Validate artifact pairs and explicit custom-IP version/scratch contracts."""
import hashlib
from pathlib import Path

from .mmio import make_mmio


CUSTOM_MODULES = {'src_mux', 'spec_front', 'cfar_core', 'pfb_os2', 'nco_capture',
                  'disp_engine', 'hoc_moments', 'demod_audio', 'dpx_hist', 'perf_mon'}


def validate_artifacts(bit):
    bit=Path(bit)
    hwh=bit.with_suffix('.hwh')
    if not bit.is_file() or not hwh.is_file():
        raise FileNotFoundError('Matching .bit and .hwh are required')
    if abs(bit.stat().st_mtime-hwh.stat().st_mtime) >= 60:
        raise ValueError('Bit/HWH timestamps differ by at least 60 seconds')
    manifest=bit.parent/'sha256.txt'
    if manifest.exists():
        expected={}
        for line in manifest.read_text(encoding='utf-8-sig').splitlines():
            fields=line.split()
            if len(fields)==2:
                expected[fields[1].lstrip('*')]=fields[0].lower()
        for path in (bit,hwh):
            digest=hashlib.sha256(path.read_bytes()).hexdigest()
            if expected.get(path.name)!=digest:
                raise ValueError('Artifact hash mismatch or missing manifest entry: '+path.name)
    return bit.resolve()


class SentinelOverlay:
    def __init__(self, bit='/home/xilinx/sentinel/overlay/sentinel/sentinel.bit', check=True,
                 download=True, contracts=None, factory=None, mmio_factory=make_mmio):
        bit=validate_artifacts(bit)
        if factory is None:
            from pynq import Overlay
            factory=Overlay
        self.overlay=factory(str(bit), download=download)
        # HWH metadata alone does not prove that the matching PL image is
        # loaded after a reboot. Reject before any custom-register access.
        self._require_loaded()
        self.contracts={} if contracts is None else contracts
        self.mmio_factory=mmio_factory
        if check:
            self.check()

    @property
    def ip_dict(self):
        return self.overlay.ip_dict

    def registers(self,name):
        self._require_loaded()
        info=self.ip_dict[name]
        return self.mmio_factory(int(info['phys_addr']), int(info.get('addr_range',4096)))

    def _require_loaded(self):
        if not self.overlay.is_loaded():
            raise RuntimeError('Requested overlay is not loaded; explicitly load the accepted bitstream before MMIO access')

    def check(self):
        self._require_loaded()
        result={}
        for name,info in self.ip_dict.items():
            module=info.get('type','').split(':')
            module=module[2] if len(module)>2 else ''
            if module not in CUSTOM_MODULES and name not in self.contracts:
                continue
            contract=self.contracts.get(name)
            if contract is None:
                result[name]='fail:missing generated version contract'
                continue
            mmio=self.registers(name)
            value=mmio.read(0xfc)
            if value in (0,0xffffffff) or value>>16 != int(contract['version'])>>16:
                result[name]='fail:version mismatch'
                continue
            if 'scratch' in contract:
                offset=int(contract['scratch']); old=mmio.read(offset)
                try:
                    mmio.write(offset,0xa55a3cc3)
                    valid=mmio.read(offset)==0xa55a3cc3
                    mmio.write(offset,0x5aa5c33c)
                    valid &= mmio.read(offset)==0x5aa5c33c
                finally:
                    mmio.write(offset,old)
                if not valid:
                    result[name]='fail:scratch readback'
                    continue
            result[name]='ok'
        if any(v!='ok' for v in result.values()):
            raise RuntimeError('Overlay contract validation failed: '+str(result))
        return result
