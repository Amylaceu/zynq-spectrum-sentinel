"""Indexed PCM WAV writer with explicit network gaps and immutable sidecars.

Prepared for the PS-parallel stream. This class does not enable PC listening
or certify ADC continuity. A FIFO overflow must stop the producer.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import wave


def sha(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576),b''):
            value.update(block)
    return value.hexdigest()


class PCMRecording:
    rate=48000

    def __init__(self,path,max_seconds=300):
        self.path=Path(path)
        if self.path.suffix.lower()!='.wav' or type(max_seconds) is not int or not 1<=max_seconds<=3600:
            raise ValueError('Require WAV path and bounded recording duration')
        if any(p.exists() for p in (self.path,Path(str(self.path)+'.json'),Path(str(self.path)+'.sha256'),
                                   Path(str(self.path)+'.json.sha256'))):
            raise FileExistsError('Preserve existing recording and evidence')
        self.limit=max_seconds*self.rate
        self.stream=self.path.open('xb')
        self.wav=wave.open(self.stream,'wb')
        self.wav.setparams((1,2,self.rate,0,'NONE','not compressed'))
        self.next_index=None
        self.samples=self.received_samples=0
        self.gaps=[]
        self.closed=False
        self.error=None
        self.created_utc=datetime.now(timezone.utc).isoformat()

    def append(self,header,payload):
        if self.closed:
            raise ValueError('Recording already closed')
        try:
            self._append(header,payload)
        except BaseException as error:
            self.error=repr(error)
            self.close()
            raise

    def _append(self,h,payload):
        if (h.get('source')!='ps_parallel_demod' or h.get('synthetic') or
            h.get('sample_rate_hz')!=self.rate or h.get('channels')!=1 or h.get('format')!='s16le'):
            raise ValueError('Require explicitly sourced mono48k real PS PCM')
        index=h.get('first_sample_index')
        count=h.get('samples')
        if type(index) is not int or index<0 or type(count) is not int or count<=0 or len(payload)!=count*2:
            raise ValueError('PCM index/length mismatch')
        if h.get('fifo_overflow'):
            raise ValueError('ADC overflow: missing sample count unknown; stop recording')
        gap=0 if self.next_index is None else index-self.next_index
        if gap<0 or gap>10*self.rate:
            raise ValueError('Overlapping PCM or unbounded discontinuity')
        if self.samples+gap+count>self.limit:
            raise ValueError('Recording duration limit reached')
        if gap:
            self.wav.writeframesraw(bytes(gap*2))
            self.gaps.append(dict(first_sample_index=self.next_index,samples=gap,
                                  reason='Missing PCM delivery; inserted silence'))
        self.wav.writeframesraw(payload)
        self.samples+=gap+count
        self.received_samples+=count
        self.next_index=index+count

    def close(self):
        if self.closed:
            return
        self.closed=True
        try:
            self.wav.close()
        finally:
            self.stream.close()
        digest=sha(self.path)
        Path(str(self.path)+'.sha256').write_text(digest+'  '+self.path.name+'\n',encoding='ascii')
        value=dict(schema='ps_parallel_wav/1',status='INCOMPLETE' if self.error else 'SAVED',
            source='ps_parallel_demod',sample_rate_hz=self.rate,channels=1,format='s16le',
            created_host_utc=self.created_utc,received_samples=self.received_samples,
            wav_samples=self.samples,gaps=self.gaps,error=self.error,wav_sha256=digest,
            adc_exact_lost_samples=None,adc_continuity_certified=False,
            scope='Independent PS FM demodulation; not the PL speaker playback PCM')
        sidecar=Path(str(self.path)+'.json')
        with sidecar.open('x',encoding='utf-8') as stream:
            json.dump(value,stream,indent=2,allow_nan=False)
            stream.write('\n')
        Path(str(sidecar)+'.sha256').write_text(sha(sidecar)+'  '+sidecar.name+'\n',encoding='ascii')
