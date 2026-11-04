"""Two-rate RX-only delay-margin scan; restore the original delay register."""
import ctypes as ct
import json
import os
from pathlib import Path
os.environ['XILINX_XRT']='/usr'
from sentinel.overlay import SentinelOverlay
from sentinel.rf.ad9361 import bind_library

root=Path('/home/xilinx/sentinel')
overlay=SentinelOverlay(str(root/'overlay/live_z20_lcd/live_z20_lcd.bit'),download=False)
if not overlay.overlay.is_loaded():raise RuntimeError('Required LCD image not loaded')
lib=bind_library(str(root/'ps/libad9361_pynq/libad9361_pynq.so'))
result=dict(status='started',checks=[],rf_transmission_requested=False)
def save():
 (root/'measurements/rx_timing_margin.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
 print(result['status'],len(result['checks']),flush=True)
def check(code,label):
 if code<0:raise RuntimeError(label+': '+str(code))
def window(values,position):
 if values[position]!=0:return 0
 a=b=position
 while a>0 and values[a-1]==0:a-=1
 while b<15 and values[b+1]==0:b+=1
 return b-a+1
save()
try:
 check(lib.z20_ad9361_open(),'init')
 for rate,bw in ((30720000,24000000),(3840000,1500000)):
  check(lib.z20_configure_receive(98000000,rate,bw),'configure')
  original=lib.z20_read_register(6);check(original,'read delay')
  table=(ct.c_uint32*256)(*([0xffffffff]*256))
  check(lib.z20_scan_rx_delays(10,table),'scan')
  grid=[list(table[c*16:(c+1)*16]) for c in range(16)]
  c=original>>4;d=original&15
  restored=lib.z20_read_register(6)
  statuses=(ct.c_uint32*4)();prbs_code=lib.z20_check_rx_prbs(500,statuses)
  attenuation=[]
  for channel in (0,1):
   a=ct.c_uint32();check(lib.z20_get_tx_attenuation(channel,ct.byref(a)),'attenuation');attenuation.append(a.value)
  entry=dict(sample_rate_hz=rate,observation_ms_per_point=10,settle_ms_per_point=5,
   saved_delay_register=original,restored_delay_register=restored,
   clock_delay=c,data_delay=d,status_grid_clock_rows_data_columns=grid,
   data_axis_window_at_saved_clock=window(grid[c],d),
   clock_axis_window_at_saved_data=window([row[d] for row in grid],c),
   passing_points=sum(v==0 for v in table),prbs_after_restore_code=prbs_code,
   prbs_after_restore_status=list(statuses),tx_attenuation_mdb=attenuation)
  entry['passed']=(restored==original and grid[c][d]==0 and
   max(entry['data_axis_window_at_saved_clock'],entry['clock_axis_window_at_saved_data'])>=3 and
   prbs_code==0 and attenuation==[89750,89750])
  result['checks'].append(entry);save()
  if not entry['passed']:raise RuntimeError('RX delay-window acceptance failed')
 result['status']='passed'
except Exception as error:result.update(status='failed',error=str(error))
finally:
 lib.z20_ad9361_close();result['gpio_after_close']=overlay.registers('axi_ad9361_gpio').read(0);save()
 print(json.dumps(result),flush=True)
if result['status']!='passed':raise SystemExit(1)
