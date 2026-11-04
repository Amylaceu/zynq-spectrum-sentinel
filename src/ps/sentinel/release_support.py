"""Portable F1 configuration, integrity and receive-quality evidence (no I/O on import)."""
import ctypes
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import time
import uuid

import numpy as np

from .artifacts import atomic_json, atomic_write
from .audio_y3 import CodecOutputs
from .capture_x5 import select_channel
from .fm_quality import stereo_quality

IMAGE = 'sentinel_v2_100m'
LIB_SHA = 'b329018314e6ecc9c0b11440b0d5449d9670fda7b5d37deabdc55c4731616e83'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_result(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_json(path, value)
    atomic_write(Path(str(path)+'.sha256'), lambda f: f.write(
        (sha(path)+'  '+path.name+'\n').encode('ascii')))


def load_config(path):
    # JSON is a YAML subset, deliberately readable without extra board dependencies.
    config = json.loads(Path(path).read_text(encoding='utf-8'))
    fixed = dict(schema=1, image=IMAGE, dsp_clock_hz=100000000, sample_rate_hz=3840000,
                 rf_bandwidth_hz=1500000, bus_phase=2, max_volume_db=-6,
                 pilot_min_db=20, tx_attenuation_db=89.75, autostart=False)
    for key, value in fixed.items():
        if key not in config or type(config[key]) is not type(value) or config[key] != value:
            raise ValueError('Frozen F1 configuration differs: '+key)
    CodecOutputs.volume_code(config['volume_db'])
    # Optional extension keeps older installed configurations readable.
    CodecOutputs.speaker_volume_code(config.get('speaker_volume_db', config['volume_db']))
    if config.get('speaker_max_volume_db', 0) != 0:
        raise ValueError('Speaker gain ceiling must remain 0 dB')
    if not isinstance(config['stations'], list) or not config['stations']:
        raise ValueError('Confirmed stereo station list required')
    for station in config['stations']:
        frequency, lo = station['frequency_hz'], station['lo_hz']
        if (type(frequency) is not int or type(lo) is not int
                or not 87500000 <= frequency <= 108000000 or not 70000000 <= lo <= 512000000
                or station.get('confirmed_stereo') is not True):
            raise ValueError('Invalid confirmed stereo station')
        select_channel(frequency-lo)
    if not any(s['frequency_hz'] == config['station_hz'] and s['lo_hz'] == config['lo_hz']
               for s in config['stations']):
        raise ValueError('Default station/LO must match the confirmed list')
    seconds = config['run_seconds']
    if type(seconds) not in (int, float) or not math.isfinite(seconds) or not 1 <= seconds <= 300:
        raise ValueError('F1 runtime must be 1..300 seconds')
    return config


def verify_release(root, require_library=True):
    root = Path(root).resolve()
    manifest = root/'manifest.json'
    if sha(manifest) != Path(str(manifest)+'.sha256').read_text().split()[0]:
        raise ValueError('Release manifest digest mismatch')
    data = json.loads(manifest.read_text())
    for name, expected in data['files'].items():
        path = PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or '\\' in name or ':' in name:
            raise ValueError('Unsafe release path')
        actual = root.joinpath(*path.parts).resolve()
        if root not in actual.parents or sha(actual) != expected:
            raise ValueError('Release file digest mismatch: '+name)
    if require_library and sha(root/'ps/libad9361_pynq/libad9361_pynq.so') != LIB_SHA:
        raise ValueError('RF library differs from accepted board library')
    return data


class NoiseRecorder:
    """Store bounded-rate raw IQ plus measured gain/RSSI; never claim mono FM is noise."""
    def __init__(self, directory, clock=time.monotonic, interval_s=10):
        self.directory = Path(directory)
        self.clock, self.interval = clock, interval_s
        self.last = None

    def observe(self, capture, quality, radio, station_hz, lo_hz):
        if quality['pilot_prominence_db'] >= 20:
            return None
        now = self.clock()
        if self.last is not None and now-self.last < self.interval:
            return None
        self.directory.mkdir(parents=True, exist_ok=True)
        stem = 'noise_'+uuid.uuid4().hex
        iq_path = self.directory/(stem+'.npz')
        gain = ctypes.c_int32()
        radio._check(radio.lib.z20_get_rx_gain(0, ctypes.byref(gain)), 'RX1 gain')
        iq = np.asarray(capture['iq'])
        if iq.ndim != 1 or len(iq) < 4096 or not np.all(np.isfinite(iq)):
            raise ValueError('Invalid noise-event IQ')
        atomic_write(iq_path, lambda f: np.savez_compressed(
            f, iq=iq, fs_hz=480000, timestamp_cycles=capture['timestamp_cycles']))
        atomic_write(Path(str(iq_path)+'.sha256'), lambda f: f.write(
            (sha(iq_path)+'  '+iq_path.name+'\n').encode('ascii')))
        event = dict(status='RF_NOISY', quality=quality, rx_gain_db=gain.value,
                     rssi_dbm=radio.rssi(0), station_hz=station_hz, lo_hz=lo_hz,
                     tx_attenuation_db=list(radio.tx_atten), iq_file=iq_path.name,
                     iq_sha256=sha(iq_path), sample_rate_hz=480000,
                     scope='Known stereo station pilot warning; not physical interference diagnosis')
        write_result(self.directory/(stem+'.json'), event)
        self.last = now
        return event


def startup_quality(hw, radio, station_hz, lo_hz, directory):
    """Called only after source start, with receiver ownership already acquired."""
    radio.check_rssi()
    capture = hw.channel_capture.acquire(select_channel(station_hz-lo_hz), source=0)
    radio.check_rssi()
    quality = stereo_quality(capture['iq'])
    event = NoiseRecorder(directory).observe(capture, quality, radio, station_hz, lo_hz)
    pilot_pass = quality['pilot_prominence_db'] >= 20
    return dict(quality=quality, noise_event=event, pilot_pass=pilot_pass,
                quality_pass=pilot_pass and bool(quality['good']))


def select_demo_station(hw, radio, config, directory):
    """Rank confirmed in-window stations by measured channel IQ power.

    This is not a broadband station search or an AMC-derived station identity.
    All candidates share the same LO/gain settings. Never play an untrusted
    candidate just because its measured power is high.
    """
    candidates = []
    for station in config['stations']:
        if station['lo_hz'] != config['lo_hz']:
            continue
        measurements = [startup_quality(hw, radio, station['frequency_hz'],
                        config['lo_hz'], directory) for _ in range(3)]
        candidates.append(dict(station=station, measurements=measurements,
            trusted=all(m['quality_pass'] for m in measurements),
            median_iq_power=float(np.median([
                m['quality']['iq_rms']**2 for m in measurements]))))
    eligible = [c for c in candidates if c['trusted']]
    winner = max(eligible, key=lambda c: c['median_iq_power']) if eligible else None
    return dict(candidates=candidates, selected=winner['station'] if winner else None,
        scope='Confirmed stereo candidates at the configured LO; relative IQ power, not calibrated RF power',
        skipped_other_lo=sum(s['lo_hz'] != config['lo_hz'] for s in config['stations']))
