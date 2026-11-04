"""Collect X5 local verification evidence without building or changing inputs."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCES = [
    "src/rtl/pfb/pfb_os2.v", "src/rtl/pfb/x5_pfb_coeff.hex",
    "src/rtl/nco_capture/nco_capture.v", "src/rtl/nco_capture/x5_nco_sine.hex",
    "src/rtl/nco_capture/x5_channel_capture.v",
    "sim/golden/nco_capture_fixed.py", "sim/tb/tb_x5_pfb.sv",
    "sim/tb/tb_x5_nco_capture.sv", "tools/x5_create_fft.tcl",
    "tools/x5_vectors.py", "tools/x5_run_sim.ps1", "tools/x5_synth.tcl",
    "tools/x5_freeze_evidence.py", "docs/x5_pl_interface.md",
]
FROZEN_RTL = {
    "src/rtl/pfb/pfb_os2.v": "7eb2955a9bd9d6d3e3fc70a556888ec816253394f4e2ae9573eb2091d425575c",
    "src/rtl/nco_capture/nco_capture.v": "b816645ba84d95261700007f5975b84e66c73ac4bfdc5266a4a6f42b432a8dbe",
    "src/rtl/nco_capture/x5_channel_capture.v": "76ced9ed55b5831362f0ef6141ea8d1fb5f4949f891d32b5c30ca0882e560412",
}
FFT_XCI = "build/work/x5_fft/x5_fft.srcs/sources_1/ip/pfb_fft16/pfb_fft16.xci"


def file_record(relative):
    path = ROOT / relative
    if not path.is_file():
        return {"path": relative, "exists": False}
    data = path.read_bytes()
    return {"path": relative, "exists": True, "bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def passed_log(relative, marker):
    record = file_record(relative)
    record["required_marker"] = marker
    text = (ROOT / relative).read_text(errors="replace") if record["exists"] else ""
    record["status"] = "PASS" if marker in text else "NOT_CONFIRMED"
    return record


def main():
    sources = [file_record(path) for path in SOURCES]
    hashes = {entry["path"]: entry.get("sha256") for entry in sources}
    unchanged = all(hashes[path] == expected for path, expected in FROZEN_RTL.items())
    nco = passed_log("logs/X5_nco_round3.log", "TB_RESULT: PASS X5 NCO 4513 exact words")
    pfb = passed_log("logs/X5_pfb_round3.log", "TB_RESULT: PASS X5 PFB+NCO exact")
    suite = passed_log("logs/X5_sim_round3.stdout.log", "X5_SIM_ROUND_3_PASS")
    ooc = passed_log("logs/X5_synth_round3.stdout.log", "X5_STANDALONE_150MHZ_PASS")
    evidence = {
        "schema": "x5-core-verification-v1", "round": 3,
        "collected_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if unchanged and all(item["status"] == "PASS"
                   for item in (nco, pfb, suite, ooc)) else "NOT_CONFIRMED",
        "rtl_matches_preverification_freeze": unchanged,
        "expected_rtl_sha256": FROZEN_RTL, "sources": sources,
        "shared_fft_read_only_snapshot": file_record(FFT_XCI),
        "simulation": {"nco": nco, "pfb_chain": pfb, "suite": suite,
            "expected_counts": {"nco_words": 4513, "pfb_baseline_inputs": 32769,
                "pfb_baseline_frames": 4097, "pfb_baseline_iq_words": 65552,
                "scap_words": 4104, "reset_burst_pfb_iq_words": 2048},
            "reference": "pfb_os2_fixed using AMD bit-accurate C model; nco_capture_fixed"},
        "ooc": {"run": ooc, "clock_mhz": 150,
            "wns_ns": 0.296, "whs_ns": 0.032, "wpws_ns": 2.203,
            "resources": {"lut": 2024, "ff": 2971, "ramb36": 8, "ramb18": 2, "dsp": 12},
            "reports": [file_record("build/reports/x5_core/round3/" + name)
                        for name in ("routed_timing.rpt", "routed_utilization.rpt", "routed_drc.rpt")]},
        "limits": ["Standalone OOC only; 1 ns IO delays and 0.10 ns clock uncertainty; integrated BD timing not established",
            "OOC clock HD.CLK_SRC unset; integrated clock skew requires full-system timing closure",
            "PFB history maps to LUTRAM despite ram_style attribute",
            "3.84 MSPS input / 480 kSPS selected channel baseline only; DEC=1",
            "4096-entry DDS phase table truncates phase to upper 12 bits",
            "Upstream drop-counter changes invalidate capture; bin sequence cannot detect lost ADC input",
            "No board or RF validation performed"],
    }
    destination = ROOT / "logs/X5_verification_final.json"
    destination.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    sha_lines = [f"{entry['sha256']}  {entry['path']}" for entry in sources if entry["exists"]]
    sha_lines.append(f"{evidence['shared_fft_read_only_snapshot']['sha256']}  {FFT_XCI}")
    (ROOT / "logs/X5_sources_final.sha256").write_text("\n".join(sha_lines) + "\n", encoding="ascii")
    print(f"X5_EVIDENCE: {evidence['status']}; RTL frozen={unchanged}; {destination}")
    if not unchanged:
        raise SystemExit("RTL differs from preverification freeze")


if __name__ == "__main__":
    main()
