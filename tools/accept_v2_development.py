"""Package the reviewed r2 checkpoint for nonnegative-slack development.

No hardware access. This preserves Z10/T5 failures and requires subsequent
digital, RX-interface, display and human audio regression on the new image.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

from accept_sentinel_v1 import timing_summary, utilization
from accept_sentinel_v1b import bus_skew_summary
from accept_sentinel_y3 import hwh_contract, check_audio_io
from x2_transport import sha, verified, write_evidence

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT/'build/reports/sentinel_v2_100m'


def bit_payload(data):
    """Parse .bit fields rather than ignoring arbitrary differing bytes."""
    size = struct.unpack_from('>H', data)[0]
    position = 2 + size
    if data[position:position+3] != b'\x00\x01a':
        raise ValueError('Unrecognized .bit header')
    position += 2
    metadata = {}
    for field in b'abcd':
        if data[position] != field:
            raise ValueError('Invalid .bit field order')
        size = struct.unpack_from('>H', data, position+1)[0]
        metadata[chr(field)] = data[position+3:position+3+size].decode('ascii')
        position += 3+size
    if data[position:position+1] != b'e':
        raise ValueError('Missing .bit payload')
    size = struct.unpack_from('>I', data, position+1)[0]
    payload = data[position+5:]
    if len(payload) != size or b'\xaa\x99\x55\x66' not in payload:
        raise ValueError('Invalid configuration data')
    return metadata, payload


def edge_bounds(text):
    """Include actual launch clock insertion in each reported pin arrival."""
    result = []
    for block in text.split('Slack:')[1:]:
        kind = re.search(r'Path Type:\s+(Max|Min) at (\w+) Process Corner', block)
        data = re.search(r'Data Path Delay:\s+([0-9.]+)ns', block)
        launch = re.search(r'^\s+SLICE_\S+\s+FDRE\s+r\s+.*serializer/.*?/C\s*$',
                           block, re.M)
        if not kind or not data or not launch:
            raise ValueError('Incomplete physical edge report')
        before = block[:launch.start()]
        arrivals = re.findall(
            r'net \(fo=\d+, routed\)\s+[-0-9.]+\s+([-0-9.]+)\s+.*serializer/audio_mclk',
            before)
        if not arrivals:
            raise ValueError('Missing launch clock insertion')
        insertion = float(arrivals[-1])
        delay = float(data[1])
        result.append(dict(kind=kind[1], corner=kind[2],
                           launch_clock_ns=insertion, c_to_pad_ns=delay,
                           pin_arrival_ns=round(insertion+delay, 3)))
    if not any(x['kind'] == 'Max' for x in result) or not any(x['kind'] == 'Min' for x in result):
        raise ValueError('Both physical min and max are required')
    return dict(early_ns=min(x['pin_arrival_ns'] for x in result),
                late_ns=max(x['pin_arrival_ns'] for x in result), paths=result)


def main():
    bundle = ROOT/'board/overlay/sentinel_v2_100m'
    if bundle.exists():
        raise FileExistsError('Preserve existing development bundle')
    repair = REPORTS/'audio_route_repair_r2'
    export = REPORTS/'development_export_r2'
    manifest_path = REPORTS/'inputs_Y3_v2_audio_route_repair_r2.json'
    frozen = verified(manifest_path)
    for name, digest in frozen['build_input_sha256'].items():
        if sha(ROOT/name) != digest:
            raise ValueError('Build input changed: '+name)
    timing = timing_summary((export/'timing.rpt').read_text())
    if timing != timing_summary((repair/'timing.rpt').read_text()):
        raise ValueError('Export does not match repaired timing')
    skew = bus_skew_summary((repair/'bus_skew.rpt').read_text())
    resources = utilization((repair/'utilization.rpt').read_text())
    io_rows = check_audio_io((repair/'io.rpt').read_text())
    if io_rows != check_audio_io((REPORTS/'audit_development_r2/io.rpt').read_text()):
        raise ValueError('Pin/voltage map changed during repair')
    drc = (repair/'drc.rpt').read_text()
    if re.search(r'\|\s*(?:Error|Critical Warning)\s*\|', drc):
        raise ValueError('Unreviewed DRC error')
    if re.search(r'nets with routing errors\.+\s*:\s*0\s*:',
                 (repair/'route_status.rpt').read_text()) is None:
        raise ValueError('Unrouted/failed net')
    provenance = (export/'checkpoint_provenance.txt').read_text()
    if 'blackbox_count 0' not in provenance or 'unsafe_fifo_reset_d_count 0' not in provenance:
        raise ValueError('Checkpoint structural provenance failed')
    edges = {name: edge_bounds((export/(name+'_physical.rpt')).read_text())
             for name in ('bclk', 'lrc', 'dacdat')}
    bclk, lrc, data = (edges[k] for k in ('bclk', 'lrc', 'dacdat'))
    pcb_skew = 2.0
    lrck_delta = max(lrc['late_ns']-bclk['early_ns'],
                     bclk['late_ns']-lrc['early_ns']) + pcb_skew
    half_period = 325.523/2
    # Common same-edge source jitter cancels for LRCK/BCLK. For data across
    # half a BCLK period, reserve twice the largest reported uncertainty.
    uncertainties = [float(x) for name in edges for x in re.findall(
        r'Clock Uncertainty:\s+([0-9.]+)ns', (export/(name+'_physical.rpt')).read_text())]
    jitter_budget = 2*max(uncertainties)
    setup = half_period+bclk['early_ns']-data['late_ns']-pcb_skew-jitter_budget
    hold = half_period+data['early_ns']-bclk['late_ns']-pcb_skew-jitter_budget
    if lrck_delta > 10 or min(setup, hold) < 10:
        raise ValueError('ES8388 edge budget failed')
    physical = dict(status='PASS_DEVELOPMENT_EDGE_REVIEW', edges=edges,
        lrck_max_abs_delta_ns=round(lrck_delta, 3), lrck_limit_ns=10,
        data_setup_lower_bound_ns=round(setup, 3), data_hold_lower_bound_ns=round(hold, 3),
        data_setup_hold_required_ns=10, pcb_differential_budget_ns=pcb_skew,
        half_cycle_uncertainty_budget_ns=jitter_budget,
        limitations=['PCB differential <=2ns is a development assumption, not a scope measurement',
                    'No full PVT board signoff; RX PN/delay scan required before live reception',
                    'Disposable false-path report views were not saved to deployed checkpoint'])
    with zipfile.ZipFile(export/'sentinel_v2_100m.xsa') as archive:
        bit = archive.read('sentinel_v2_100m.bit')
        hwh = archive.read('system.hwh')
    local_meta, local_payload = bit_payload((export/'sentinel_v2_100m.bit').read_bytes())
    xsa_meta, xsa_payload = bit_payload(bit)
    if (local_payload != xsa_payload or
            any(local_meta[k] != xsa_meta[k] for k in ('a', 'b', 'c'))):
        raise ValueError('XSA bit configuration differs from repaired export')
    # Use XSA's own bit and HWH verbatim; timestamp-only re-emission is recorded.
    bundle.mkdir()
    (bundle/'sentinel_v2_100m.bit').write_bytes(bit)
    (bundle/'sentinel_v2_100m.hwh').write_bytes(hwh)
    (bundle/'sentinel_v2_100m.xsa').write_bytes((export/'sentinel_v2_100m.xsa').read_bytes())
    addresses = hwh_contract(bundle/'sentinel_v2_100m.hwh', dsp_mhz=100)
    artifacts = {p.name: sha(p) for p in bundle.iterdir()}
    inputs = dict(frozen['build_input_sha256'])
    evidence_paths = [manifest_path, REPORTS/'inputs_T5_v2_impl_only_r1.json',
        repair/'repaired.dcp', ROOT/'build/scripts/repair_v2_audio_routes_r2.tcl',
        ROOT/'build/scripts/export_v2_repaired_r2.tcl',
        ROOT/'build/scripts/inspect_v2_audio_early_r2.tcl', Path(__file__),
        ROOT/'docs/v2_development_review.md']
    inputs.update({p.relative_to(ROOT).as_posix(): sha(p) for p in evidence_paths})
    report_paths = list(repair.glob('*.rpt')) + list(export.glob('*.rpt'))
    report_hashes = {p.relative_to(ROOT).as_posix(): sha(p) for p in report_paths}
    review = dict(status='PASS_DEVELOPMENT_REVIEW', image='sentinel_v2_100m',
        recorded_utc=datetime.now(timezone.utc).isoformat(),
        checks={k: True for k in ('basic_timing', 'cdc', 'external_io',
                                 'pins_and_voltages', 'build_inputs', 'route_and_drc')},
        scope='Development review only, with documented CDC/board-interface restrictions; no board acceptance',
        artifacts_sha256=artifacts, audio_edge_review=physical,
        cdc_review='docs/v2_development_review.md; warnings retained, static configuration and one session only',
        cdc_critical_counts={'CDC-1': 110, 'CDC-10': 4, 'CDC-13': 26},
        xsa_bit_metadata=xsa_meta, exported_bit_metadata=local_meta,
        configuration_payload_sha256=hashlib.sha256(xsa_payload).hexdigest(),
        xsa_bit_payload_matches_export=True, bit_and_hwh_extracted_verbatim_from_xsa=True,
        evidence_sha256=report_hashes, required_runtime_gates=['digital_selftest',
            '3.84MSPS_RX_PN_delay_window', 'receive_display', 'human_visual', 'human_speaker'])
    write_evidence(bundle/'development_review.json', review)
    acceptance = dict(status='PASS', image='sentinel_v2_100m',
        scope='PC development implementation only, not Z10 +1ns or board acceptance',
        deployment_policy='development_nonnegative_v1',
        development_review_sha256=sha(bundle/'development_review.json'),
        final_timing=timing, resources=resources, bus_skew=skew, addresses=addresses,
        artifacts_sha256=artifacts, build_input_sha256=inputs,
        report_sha256=report_hashes, historical_Z10_T5_status='FAIL_PRESERVED')
    write_evidence(bundle/'acceptance.json', acceptance)
    (bundle/'sha256.txt').write_text(''.join(d+'  '+n+'\n' for n,d in sorted(artifacts.items())), encoding='ascii')
    import sys
    sys.path.insert(0, str(ROOT/'src/ps'))
    from sentinel.v_y3 import checked_y3_bundle
    checked_y3_bundle(bundle/'sentinel_v2_100m.bit', image='sentinel_v2_100m')
    print(json.dumps(dict(status=review['status'], timing=timing, audio=physical,
                         artifact_sha256=artifacts), indent=2))


if __name__ == '__main__':
    main()
