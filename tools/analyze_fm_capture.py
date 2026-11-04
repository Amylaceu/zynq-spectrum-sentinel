"""Verify SigMF bytes, demodulate gapped captures separately, export evidence."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
from scipy.io.wavfile import write
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'src/ps'))
from sentinel.fm_receive import demodulate_chunk

parser=argparse.ArgumentParser()
parser.add_argument('--station',type=int,default=90000000)
parser.add_argument('--attempt',type=int,default=1)
parser.add_argument('--profile',choices=('wide','voice'),default='wide')
args=parser.parse_args()
name='fm_%d_round%d'%(args.station,args.attempt)
folder=root/'data/captured/fm_diagnostic'
meta=json.loads((folder/(name+'.sigmf-meta')).read_text())
data=(folder/(name+'.sigmf-data')).read_bytes()
if hashlib.sha512(data).hexdigest()!=meta['global']['core:sha512']:raise RuntimeError('SigMF hash mismatch')
samples=np.frombuffer(data,dtype='<i2').reshape(-1,2)
iq=(samples[:,0].astype(float)+1j*samples[:,1].astype(float))/32768
records=[];audios=[];powers=[]
for item in meta['captures']:
    start=item['core:sample_start'];count=item['zss:sample_count']
    audio,result,f,p=demodulate_chunk(iq[start:start+count],meta['global']['core:sample_rate'],item['core:frequency'],args.station,profile=args.profile)
    records.append(result);audios.append(audio);powers.append(p)
audio=audios[0]
for chunk in audios[1:]:
    overlap=min(240,len(audio),len(chunk)) if args.profile=='voice' else 0
    if overlap:
        audio=np.r_[audio[:-overlap],audio[-overlap:]+chunk[:overlap],chunk[overlap:]]
    else:
        audio=np.r_[audio,chunk]
scale=max(float(np.quantile(abs(audio),.999)),1e-12)
audio=np.clip(audio/scale*.25,-.3,.3)
suffix='_voice' if args.profile=='voice' else '_demod'
wav=root/'report/results'/(name+suffix+'.wav')
write(wav,48000,np.rint(audio*32767).astype(np.int16))
result=dict(candidate_hz=args.station,source='antenna_rx1',segmented_recording=True,audio_profile=args.profile,
            playback_duration_s=len(audio)/48000,wav=wav.relative_to(root).as_posix(),
            stereo_pilot_in_all_chunks=all(r['stereo_pilot_evidence'] for r in records),chunks=records,
            station_identity_verified=False,intelligible_audio_verified=False)
(root/'board/measurements'/(name+suffix+'.json')).write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8',newline='\n')
p=np.mean(powers,axis=0);db=10*np.log10(np.maximum(p,1e-20))
fig,ax=plt.subplots(2,1,figsize=(10,6),constrained_layout=True)
ax[0].plot(np.arange(len(audio))/48000,audio);ax[0].set(xlabel='Playback time (s)',ylabel='Audio amplitude',title='%.1f MHz FM %s profile (gapped snapshots)'%(args.station/1e6,args.profile))
ax[1].plot(f/1000,db);ax[1].axvline(19,color='orange',ls='--',label='19 kHz pilot position');ax[1].set(xlim=(0,60),xlabel='Discriminator frequency (kHz)',ylabel='PSD (dB Hz²/Hz)');ax[1].legend()
for a in ax:a.grid(alpha=.25)
fig.savefig(root/'report/figures'/(name+suffix+'.png'),dpi=150)
print(json.dumps(result,indent=2))
