"""Bounded live tile decoder. Progress is provisional until final SHA verification."""
import base64
import json
import math
from pathlib import Path
import numpy as np

class LivePanorama:
    def __init__(self):
        self.group = None
        self.total = None
        self.tiles = []

    def apply(self, packet):
        if (packet.get('type') != 'pano_tile' or packet.get('schema') != 1
                or packet.get('group') not in ('A', 'D') or packet.get('provisional') is not True
                or type(packet.get('index')) is not int or packet['index'] != len(self.tiles)
                or type(packet.get('total')) is not int or not 1 <= packet['total'] <= 300
                or packet['index'] >= packet['total']
                or packet.get('sample_rate_hz') != 30720000 or packet.get('nfft') != 4096):
            raise ValueError('Invalid or out-of-order live panorama tile')
        group, total, lo = packet['group'], packet['total'], packet.get('lo_hz')
        low, high = (70000000, 512000000) if group == 'A' else (512000000, 2700000000)
        if (not isinstance(lo, (float, int)) or isinstance(lo, bool) or not math.isfinite(lo)
                or not low <= lo <= high or (self.group and (group != self.group or total != self.total))):
            raise ValueError('Live tile group or LO changed unexpectedly')
        encoded = packet.get('psd_f32_base64')
        if not isinstance(encoded, str) or len(encoded) != 21848:
            raise ValueError('Unexpected live PSD length')
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) != 4096*4:
            raise ValueError('Unexpected live PSD byte count')
        power = np.frombuffer(raw, dtype='<f4').copy()
        if not np.all(np.isfinite(power)) or np.any(power < 0):
            raise ValueError('Invalid live PSD power')
        self.group, self.total = group, total
        f = np.fft.fftshift(np.fft.fftfreq(4096, 1/30720000))
        # Each tile is separately masked. NaN gaps are never filled for display.
        valid = (np.abs(f) >= 150000) & (np.abs(f) <= 10000000-7500)
        absolute = f+lo
        valid &= (absolute >= low) & (absolute <= high)
        self.tiles.append((absolute[valid], 10*np.log10(np.maximum(power[valid], 1e-20))))
        x = np.concatenate([np.r_[tile[0]/1e6, np.nan] for tile in self.tiles])
        y = np.concatenate([np.r_[tile[1], np.nan] for tile in self.tiles])
        return x, y

class ProgressTail:
    """Read only complete bounded JSON lines, tolerating a writer mid-line."""
    def __init__(self, path):
        self.path = Path(path)
        self.offset = 0

    def poll(self):
        if not self.path.exists():
            return []
        packets = []
        with self.path.open('rb') as stream:
            stream.seek(self.offset)
            for _ in range(16):
                line = stream.readline(65537)
                if not line:
                    break
                if len(line) > 65536:
                    raise ValueError('Progress line exceeds size limit')
                if not line.endswith(b'\n'):
                    break
                packets.append(json.loads(line))
                self.offset = stream.tell()
        return packets
