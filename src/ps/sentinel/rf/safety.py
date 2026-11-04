"""Fail-closed attenuation/link checks; no RF transmission is enabled here."""
import math

class TxGuard:
    MODES={'air':30.,'cable':10.}
    def __init__(self,mode='air',confirm_attenuator=False):
        self.set_mode(mode,confirm_attenuator)
    def set_mode(self,mode,confirm_attenuator=False):
        if mode not in self.MODES:raise ValueError('Unknown link mode')
        if mode=='cable' and confirm_attenuator is not True:
            raise PermissionError('Cable mode requires explicit inline attenuator confirmation')
        self.mode=mode
    def check(self,db):
        if not math.isfinite(float(db)) or not self.MODES[self.mode]<=db<=89.75:
            raise PermissionError('TX attenuation outside permitted limits')
        return db
    def check_rssi(self,dbm):
        if not math.isfinite(float(dbm)) or dbm>-30:
            raise PermissionError('RSSI exceeds -30dBm or is invalid')
