"""Export fixed-point stage vectors, including decreasing uint32 averages and endpoints."""
import json
import sys
from pathlib import Path
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from sim.golden.spectrum import window_coefs, welch_update, to_db_q88


def main():
    out = ROOT/'data/reference/spectrum'
    rng = np.random.default_rng(20261102)
    iq = np.load(out/'in_iq.npy').reshape(-1, 2)
    window_input = np.tile(iq, (2, 1)).astype(np.int64)
    window_input[-8:] = [[-32768,-32768],[32767,32767],[0,0],[1,-1]]*2
    selections = (0,1,2,0,1,2,0,1)
    window_output = np.empty_like(window_input)
    for frame, sel in enumerate(selections):
        sl = slice(frame*2048,(frame+1)*2048)
        window_output[sl] = (window_input[sl]*window_coefs(('bh4','hann','rect')[sel])[:,None]) >> 17
    pack = lambda x: (x[:,0]&65535) | ((x[:,1]&65535)<<16)
    fft = np.load(out/'exp_fft.npy').reshape(-1,2).astype(np.int64) >> 8
    native = np.vstack((fft, rng.integers(-32768,32768,(8192,2),dtype=np.int64)))
    native[-4:] = [[-32768,-32768],[32767,32767],[0,0],[1,-1]]
    power = native[:,0]**2 + native[:,1]**2
    pw = np.vstack((np.load(out/'exp_power_shifted.npy'),
                    np.full((1,2048),0xffffffff,dtype=np.uint32),
                    np.zeros((1,2048),dtype=np.uint32),
                    rng.integers(0,2**32,(2,2048),dtype=np.uint32)))
    avg=[]; state=np.zeros(2048,dtype=np.uint32)
    shifts=(3,3,3,3,0,31,3,3)
    for frame, shift in zip(pw,shifts):
        state=welch_update(state,frame,shift); avg.append(state)
    db_input=rng.integers(0,2**32,16384,dtype=np.uint32)
    db_input[:8192]=np.load(out/'exp_welch.npy').reshape(-1)
    edge=[0,1,0xffffffff]+[2**n+d for n in range(1,32) for d in (-1,0,1)]
    db_input[8192:8192+len(edge)] = edge
    inputs=np.concatenate((pack(window_input),pack(native),pw.reshape(-1),db_input))
    expected=np.concatenate((pack(window_output),power,np.array(avg).reshape(-1),
                              to_db_q88(db_input).astype(np.uint16)))
    for name, values in (('n2_stages_in',inputs),('n2_stages_expected',expected)):
        (out/(name+'.hex')).write_bytes(''.join('%08x\n' % (int(x)&0xffffffff) for x in values).encode())
    (out/'n2_stages_contract.json').write_bytes((json.dumps(dict(words_per_stage=16384,
        stages=['window','power','welch','db'],window_selections=selections,avg_shifts=shifts,
        seed=20261102),indent=2)+'\n').encode())
    full_db=np.load(out/'exp_db.npy').reshape(4,2048)
    pixels=np.array([[frame[j*2048//560:(j+1)*2048//560].max() for j in range(560)] for frame in full_db])
    (out/'n2_display_expected.hex').write_bytes(''.join('%04x\n' % (int(x)&65535) for x in pixels.flat).encode())
    print('N2_STAGE_VECTORS_PASS',len(inputs))


if __name__=='__main__':main()
