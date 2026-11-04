"""Known native12-bit sequences and all-sample cyclic alignment acceptance."""
import numpy as np
def sequence(kind,n=8192):
    i=np.arange(n,dtype=np.int32)
    if kind=='ramp':
        words=np.stack((i,3*i+(i//4096)*257,5*i+317,7*i+(i//4096)*503+719),axis=1)&4095
    elif kind=='pn':
        state=0xace1;words=np.empty((n,4),dtype=np.int32)
        for row in range(n):
            for col in range(4):
                state=(state>>1)^((-(state&1))&0xb400)
                words[row,col]=state&4095
    else:raise ValueError('Unknown sequence')
    return np.where(words>=2048,words-4096,words).astype('<i2')
def compare_cyclic(reference,received):
    a=np.asarray(reference);b=np.asarray(received)
    if a.ndim!=2 or a.shape[1]!=4 or b.ndim!=2 or b.shape[1]!=4 or len(b)<len(a):
        raise ValueError('Need native four-channel cyclic data')
    candidates=np.flatnonzero(np.all(a==b[0],axis=1))
    best=None
    for offset in candidates:
        expected=a[(np.arange(len(b))+int(offset))%len(a)]
        bad=b!=expected
        record=dict(alignment_samples=int(offset),compared_words=int(b.size),
                    mismatch_words=int(bad.sum()),mismatch_by_channel=bad.sum(axis=0).astype(int).tolist(),
                    passed=bool(not bad.any()))
        if best is None or record['mismatch_words']<best['mismatch_words']:best=record
        if record['passed']:return record
    return best or dict(alignment_samples=None,compared_words=int(b.size),mismatch_words=int(b.size),passed=False)
