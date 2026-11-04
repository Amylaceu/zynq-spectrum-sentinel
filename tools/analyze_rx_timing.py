"""Validate and plot finite RX PRBS delay scans, without BER claims."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap

root=Path(__file__).resolve().parents[1]
data=json.loads((root/'board/measurements/rx_timing_margin.json').read_text())
assert data['status']=='passed' and data['gpio_after_close']==0
fig,axes=plt.subplots(1,2,figsize=(10,4),constrained_layout=True)
for ax,entry in zip(axes,data['checks']):
    grid=np.asarray(entry['status_grid_clock_rows_data_columns'])
    assert grid.shape==(16,16) and np.all(grid!=0xffffffff)
    assert entry['saved_delay_register']==entry['restored_delay_register']
    assert entry['prbs_after_restore_code']==0 and entry['prbs_after_restore_status']==[0]*4
    assert entry['tx_attenuation_mdb']==[89750,89750]
    assert entry['passed'] and entry['data_axis_window_at_saved_clock']>=3
    ax.imshow(grid==0,origin='lower',interpolation='nearest',cmap=ListedColormap(['#263545','#39bd83']),vmin=0,vmax=1)
    ax.scatter(entry['data_delay'],entry['clock_delay'],marker='x',color='white',s=90,label='restored setting')
    ax.set(xticks=range(0,16,3),yticks=range(0,16,3),xlabel='RX data delay code',ylabel='RX clock delay code',
           title='%.2f MSPS; data window %d codes'%(entry['sample_rate_hz']/1e6,entry['data_axis_window_at_saved_clock']))
    ax.legend(loc='upper left',fontsize=8)
fig.suptitle('Finite RX PN9 scan: green = pass, dark = error; 10 ms per point')
fig.savefig(root/'report/figures/rx_timing_margin.png',dpi=150)
print('RX_TIMING_MARGIN_ACCEPTANCE_PASS')
