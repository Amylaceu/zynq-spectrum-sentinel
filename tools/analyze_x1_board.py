"""Compare X1 periodic coherent snapshots with archived N4 records."""
import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import statistics
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def detection(row, lo_hz, rate_hz, frequency=95800000, tolerance=25000):
    return any(abs(lo_hz+(target['peak_bin']-1024)*rate_hz/2048-frequency)<=tolerance
               for target in row['targets'])


def advancing(values, name, wrapped=False):
    """A repeated/stale snapshot must not pass a live receiver acceptance."""
    for previous, current in zip(values, values[1:]):
        delta = (current-previous)&0xffffffff if wrapped else current-previous
        if not 0 < delta < (0x80000000 if wrapped else float('inf')):
            raise ValueError('Non-advancing '+name)


def summarize(data, expected_lo):
    samples = data['samples']
    if (data['status']!='completed' or data['stopped_by_signal'] or data['RF_TX_requested']
            or abs(data['actual_lo_hz']-expected_lo)>5 or data['actual_rate_hz']!=3840000
            or data['rf_bandwidth_hz']!=1500000 or data['bus_phase']!=3
            or not 120<=data['elapsed_total_s']<125 or len(samples)<100):
        raise ValueError('Incomplete or incompatible RF comparison run')
    valid = [s for s in samples if s.get('snapshot_available')]
    missing = len(samples)-len(valid)
    if data['telemetry_attempts']!=len(samples) or data['snapshot_misses']!=missing:
        raise ValueError('Missing telemetry not fully accounted for')
    if any(not isinstance(s[key], (int, float)) or not math.isfinite(s[key])
           for s in samples for key in ('elapsed_s','display_fps','temperature_c','rx_rssi_dbm')):
        raise ValueError('Non-finite telemetry')
    advancing([s['elapsed_s'] for s in samples], 'telemetry time')
    advancing([s['input_samples'] for s in samples], 'input_samples')
    for key in ('display_frames','fft_frames'):
        advancing([s[key] for s in samples], key, wrapped=True)
    advancing([s['cfar_sequence'] for s in valid], 'CFAR sequence', wrapped=True)
    if any(s['overflow'] or s['tx_atten_mdb']!=[89750,89750] or s['rx_rssi_dbm']>-30
           or not 30<=s['temperature_c']<=85 for s in samples):
        raise ValueError('Unsafe RF/temperature or input FIFO overflow')
    for s in valid:
        candidates = s['candidate_count']
        if (s['status_latch']&0x0c or s['list_overflow'] != bool(s['status_latch']&0x10)
                or s['list_overflow']!=(candidates>32) or len(s['targets'])!=min(candidates,32)
                or s['raw_count']-s['filtered_count']!=candidates):
            raise ValueError('Inconsistent same-frame telemetry')
    alarms = sum(s['list_overflow'] for s in valid)
    hits = sum(detection(s,data['actual_lo_hz'],data['actual_rate_hz']) for s in valid)
    return {'telemetry_records':len(samples),'coherent_snapshots':len(valid),'snapshot_misses':missing,
            'capacity_alarm_records':alarms,
            'capacity_alarm_rate_valid':alarms/len(valid) if valid else None,
            'capacity_alarm_rate_upper_bound_all_attempts':(alarms+missing)/len(samples),
            'station_detected_records':hits,'station_detection_rate_all_attempts':hits/len(samples),
            'target_count_median':statistics.median(len(s['targets']) for s in valid) if valid else None,
            'display_fps_median':statistics.median(s['display_fps'] for s in samples),
            'temperature_range_c':[min(s['temperature_c'] for s in samples),max(s['temperature_c'] for s in samples)],
            'sample_overflow_records':0,'configuration':data['configuration']}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capacity',type=Path,required=True)
    p.add_argument('--station',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args = p.parse_args()
    if args.out.exists() or Path(str(args.out)+'.sha256').exists():
        p.error('Preserve previous measurements')
    paths = {'capacity':args.capacity,'station':args.station}
    data = {k:json.loads(v.read_text(encoding='utf-8-sig')) for k,v in paths.items()}
    for path in paths.values():
        if sha(path)!=Path(str(path)+'.sha256').read_text().split()[0]:
            raise ValueError('Measurement hash mismatch')
    if data['capacity']['configuration']!=data['station']['configuration']:
        raise ValueError('Use the same CFAR/averaging configuration for both comparison windows')
    results = {k:summarize(data[k],lo) for k,lo in [('capacity',98000000),('station',96400000)]}
    summary_path = ROOT/'board/measurements/n4_acceptance_summary.json'
    archived = json.loads(summary_path.read_text(encoding='utf-8-sig'))
    baseline = {}
    for item in archived['rf_runs']:
        path = ROOT/item['measurement']
        if sha(path)!=item['measurement_sha256']:
            raise ValueError('N4 baseline changed')
        run = json.loads(path.read_text(encoding='utf-8-sig'))
        rows = run['samples']
        baseline[str(run['requested_lo_hz'])] = {
            'path':item['measurement'],'sha256':sha(path),'records':len(rows),
            'capacity_alarm_rate':sum(s['list_overflow'] for s in rows)/len(rows),
            'station_detection_rate':sum(detection(s,run['actual_lo_hz'],run['actual_rate_hz']) for s in rows)/len(rows),
            'status_snapshot_caveat':'v1 live status and target list may come from different frames'}
    metric_pass = results['capacity']['capacity_alarm_rate_upper_bound_all_attempts']<.05 and results['station']['station_detection_rate_all_attempts']>=.8
    result = {'status':'PASS_METRICS' if metric_pass else 'FAIL_METRICS',
              'recorded_at_pc':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
              'scope':'Periodic RF metrics only; hardware audit, human visual acceptance and step commit are separate',
              'x1':results,'n4':baseline,
              'denominator':'Scheduled telemetry snapshots; missing snapshots counted conservatively, never silently discarded',
              'evidence':{k:{'path':v.as_posix(),'sha256':sha(v)} for k,v in paths.items()}}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,indent=2)+chr(10),encoding='utf-8')
    Path(str(args.out)+'.sha256').write_text(sha(args.out)+'  '+args.out.name+chr(10),encoding='ascii')
    print(json.dumps(result,indent=2))
    return 0 if metric_pass else 1


if __name__=='__main__':
    raise SystemExit(main())
