"""Finite tone/replay tests of an explicitly selected, accepted image."""
import argparse
import hashlib
from pathlib import Path

import numpy as np

from .monitor_x1 import checked_bundle
from .runtime_v1 import Session
from .selftest_v1 import finite_frame, bin_error
from ..artifacts import atomic_json, atomic_write
from ..v1b import V1b
from ..params import clock_hz_for_image


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bit',required=True)
    parser.add_argument('--out',required=True)
    parser.add_argument('--references',required=True,type=Path)
    parser.add_argument('--image', choices=('sentinel_v1b', 'sentinel_v2_100m'),
                        default='sentinel_v1b')
    args=parser.parse_args()
    output=Path(args.out)
    if output.exists() or output.with_suffix('.npz').exists():
        parser.error('Preserve prior self-test')
    if args.image == 'sentinel_v2_100m':
        from ..v2 import V2
        from ..v_y3 import checked_y3_bundle
        acceptance=checked_y3_bundle(args.bit, image=args.image)
        factory=V2
    else:
        acceptance=checked_bundle(args.bit)
        factory=V1b
    files=[args.references/name for name in ('in_axis32.hex','exp_power_shifted.hex')]
    inputs=np.array([int(x,16) for x in files[0].read_text().split()],dtype=np.uint32).reshape(4,2048)
    golden=np.array([int(x,16) for x in files[1].read_text().split()],dtype=np.uint32).reshape(4,2048)
    result={'status':'started','RF_TX_requested':False,'rf_initialized':False,
            'image':args.image,'dsp_clock_hz':clock_hz_for_image(args.image),
            'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
            'artifacts_sha256':acceptance['artifacts_sha256'],
            'bit_sha256':hashlib.sha256(Path(args.bit).read_bytes()).hexdigest(),'tests':[],
            'reference_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    try:
        atomic_json(output,result)
        with Session(args.bit,'test',True,hw_factory=factory) as session:
            h=session.hw
            if args.image == 'sentinel_v2_100m':
                h.audio.disable(release_pins=True)
            h.enable_processing(average_shift=0)
            h.lcd.set_bus_phase(3)
            h.lcd.enable()
            h.perf.clear()
            h.perf.arm()
            single,targets,perf=finite_frame(h,'test',rate=3840000)
            peak=int(np.argmax(single));error=bin_error(peak,1088)
            result['tests'].append({'name':'single_tone','peak_bin':peak,'expected_bin':1088,'error_bins':error})
            if error>1:
                raise AssertionError('Single-tone peak exceeds one bin')
            triple,targets,perf=finite_frame(h,'test',(-300,64,300),(4096,4096,4096),rate=3840000)
            peaks=[t.peak_bin for t in targets]
            result['tests'].append({'name':'three_tones','peaks':peaks,'target_count':len(peaks),'expected_peaks':[724,1088,1324]})
            if len(peaks)!=3 or any(min(bin_error(x,y) for x in peaks)>1 for y in (724,1088,1324)):
                raise AssertionError('Three-tone target test failed')
            actual=[]
            for index in range(4):
                power,_,perf=finite_frame(h,'replay',replay=inputs[index],rate=3840000)
                actual.append(power)
                differences=int(np.count_nonzero(power!=golden[index]))
                result['tests'].append({'name':'golden_replay','frame':index,'words':2048,'mismatches':differences})
                atomic_json(output,result)
                if differences:
                    raise AssertionError('Power replay differs from reference')
            archive=output.with_suffix('.npz')
            atomic_write(archive,lambda stream:np.savez_compressed(stream,power=np.stack(actual),golden=golden,
                input_words=inputs,single_tone_power=single,triple_tone_power=triple))
            result.update(raw_archive_sha256=hashlib.sha256(archive.read_bytes()).hexdigest(),perf=perf.__dict__)
        result['status']='passed'
    except BaseException as error:
        result.update(status='failed',error=str(error))
        raise
    finally:
        atomic_json(output,result)
        digest=hashlib.sha256(output.read_bytes()).hexdigest()
        atomic_write(output.with_name(output.name+'.sha256'),
                     lambda stream:stream.write((digest+'  '+output.name+'\n').encode('ascii')))
    print('X1_FINITE_SELFTEST_PASS',flush=True)


if __name__=='__main__':
    main()
