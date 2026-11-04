"""PRBS sticky-error diagnostic at both rates used by antenna captures."""
import ctypes as ct
import json
import os
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
from sentinel.overlay import SentinelOverlay
from sentinel.rf.ad9361 import bind_library

root=Path('/home/xilinx/sentinel')
overlay=SentinelOverlay(str(root/'overlay/bringup_z20_lcd/bringup_z20_lcd.bit'),download=False)
if not overlay.overlay.is_loaded():raise RuntimeError('Required image is not loaded')
lib=bind_library(str(root/'ps/libad9361_pynq/libad9361_pynq.so'))
result={'status':'started','checks':[],'rf_transmission_requested':False}
def save():
    (root/'measurements/rx_prbs_rates.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
def check(code,what):
    if code<0:raise RuntimeError(what+': '+str(code))
save()
try:
    check(lib.z20_ad9361_open(),'init')
    for rate,bw in ((30720000,24000000),(3840000,1500000)):
        check(lib.z20_configure_receive(96050000,rate,bw),'configure')
        actual=ct.c_uint32();check(lib.z20_get_sample_rate(ct.byref(actual)),'rate')
        statuses=(ct.c_uint32*4)()
        code=lib.z20_check_rx_prbs(500,statuses)
        adc=overlay.registers('axi_ad9361')
        result['checks'].append(dict(requested_rate_hz=rate,actual_rate_hz=actual.value,
            duration_ms=500,channel_sticky_status=[hex(v) for v in statuses],return_code=code,
            adc_clock_frequency_register=adc.read(0x54),adc_clock_ratio_register=adc.read(0x58),adc_status=adc.read(0x5c)))
        save();check(code,'RX PRBS')
        if not result['checks'][-1]['adc_status']&1 or not result['checks'][-1]['adc_clock_frequency_register']:
            raise RuntimeError('ADC interface activity/status check failed')
    result['status']='passed'
except Exception as error:
    result.update(status='failed',error=str(error))
finally:
    lib.z20_ad9361_close()
    result['gpio_after_close']=overlay.registers('axi_ad9361_gpio').read(0)
    save();print(json.dumps(result,indent=2),flush=True)
if result['status']!='passed':raise SystemExit(1)
