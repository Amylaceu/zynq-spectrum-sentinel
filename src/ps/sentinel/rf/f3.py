"""Explicit fixed-frequency OTA control; import has no hardware side effects.

The separate C library enforces the same 40dB floor and 3dB maximum step.
Heartbeat is renewed only after RSSI/readback progress, never by a blind thread.
"""
import atexit
import ctypes as ct
import math

from .ad9361 import AD9361, bind_library, U64

LO_HZ = 2450000000
RATE_HZ = 3840000
MIN_ATTEN_DB = 40.0
MAX_ATTEN_DB = 89.75


def attenuation_steps(floor=40.0):
    if not math.isfinite(floor) or not 40 <= floor <= 89:
        raise ValueError('F3 attenuation floor must be 40..89dB')
    if round(floor*1000) % 250:
        raise ValueError('Attenuation requires quarter-dB steps')
    values = [89.0]
    while values[-1] > floor:
        values.append(max(float(floor), values[-1]-3.0))
    return values


class F3Radio(AD9361):
    def __init__(self, path=None, backend=None):
        lib = backend if backend is not None else bind_library(path)
        if backend is None:
            signatures = {'z20_f3_prepare': [ct.c_uint64], 'z20_f3_start': [],
                          'z20_f3_stop': [], 'z20_f3_heartbeat': [],
                          'z20_f3_watchdog_status': [], 'z20_f3_set_gain': [ct.c_int32],
                          'z20_f3_get_tx_lo': [U64]}
            for name, params in signatures.items():
                fn = getattr(lib, name)
                fn.argtypes, fn.restype = params, ct.c_int
        super().__init__(backend=lib)
        self.running = False

    def open(self, lo=LO_HZ, gain=30):
        if lo != LO_HZ or type(gain) is not int or not 0 <= gain <= 60:
            raise ValueError('F3 requires 2.45GHz, RX gain 0..60dB')
        if self._opened:
            raise RuntimeError('Already open')
        self._check(self.lib.z20_ad9361_open(), 'F3 init')
        self._opened = True
        atexit.register(self.close)
        try:
            self._check(self.lib.z20_f3_prepare(lo), 'F3 prepare')
            self._check(self.lib.z20_f3_set_gain(gain), 'F3 gain')
            if self.tx_atten != (MAX_ATTEN_DB, MAX_ATTEN_DB) or self.rate != RATE_HZ:
                raise RuntimeError('Prepared RF readback mismatch')
        except BaseException:
            self.close()
            raise
        return self

    def start(self):
        if not self._opened or self.running:
            raise RuntimeError('Not prepared or already running')
        if self.tx_atten != (MAX_ATTEN_DB, MAX_ATTEN_DB):
            raise RuntimeError('Start requires maximum attenuation')
        self._check(self.lib.z20_f3_start(), 'F3 start')
        self.running = True
        return self.health()

    def health(self):
        if not self.running:
            raise RuntimeError('F3 is not running')
        self._check(self.lib.z20_f3_watchdog_status(), 'F3 watchdog')
        rssi = self.rssi(0)
        self.guard.check_rssi(rssi)
        a, b = self.tx_atten
        if not 40 <= a <= MAX_ATTEN_DB or b != MAX_ATTEN_DB:
            raise RuntimeError('F3 attenuation readback invalid')
        self._check(self.lib.z20_f3_heartbeat(), 'F3 heartbeat')
        return dict(rssi_dbm=rssi, tx_atten_db=a, tx2_atten_db=b)

    def set_attenuation(self, db):
        if type(db) not in (int, float) or not math.isfinite(db) or not 40 <= db <= MAX_ATTEN_DB:
            raise ValueError('F3 attenuation outside 40..89.75dB')
        if round(db*1000) % 250:
            raise ValueError('Quarter-dB steps required')
        before = self.health()
        change = before['tx_atten_db']-db
        if change > 3 or before['rssi_dbm']+max(change, 0) > -35:
            raise RuntimeError('F3 step or predicted RSSI limit')
        self._check(self.lib.z20_set_tx_attenuation(round(db*1000)), 'F3 attenuation')
        after = self.health()
        if after['tx_atten_db'] != db:
            raise RuntimeError('F3 attenuation differs')
        return after

    def mute(self):
        if self._opened:
            self._check(self.lib.z20_set_tx_attenuation(89750), 'F3 mute')
            if self.tx_atten != (MAX_ATTEN_DB, MAX_ATTEN_DB):
                raise RuntimeError('F3 mute readback differs')

    def stop(self):
        if self._opened:
            self._check(self.lib.z20_f3_stop(), 'F3 stop')
        self.running = False

    def close(self):
        if self._opened:
            try:
                self.lib.z20_ad9361_close()
            finally:
                self.running = False
                self._opened = False
                atexit.unregister(self.close)
