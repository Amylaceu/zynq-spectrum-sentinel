#!/usr/bin/env python3
"""Summarize a Vivado timing report without modifying a running build.

This is a timing-only gate. It does not replace CDC, DRC, pin, or board audits.
All paths passed on the command line are resolved relative to the repository.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NUM = r"[-+]?\d+(?:\.\d+)?"
SLACK = re.compile(r"Slack \((MET|VIOLATED)\)\s*:\s*(" + NUM + r")ns")
SUMMARY_ROW = re.compile(r"^\s*" + NUM + r"\s+" + NUM + r"\s+")


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path.resolve() if path.is_absolute() else (ROOT / path).resolve()


def relative_name(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def parse_report(text: str) -> dict:
    if "| Design Timing Summary" not in text or "| Clock Summary" not in text:
        raise ValueError("Missing Vivado Design Timing Summary or Clock Summary")
    summary_text = text.split("| Design Timing Summary", 1)[1].split("| Clock Summary", 1)[0]
    row = next((line for line in summary_text.splitlines() if SUMMARY_ROW.match(line)), None)
    if row is None:
        raise ValueError("Missing numeric WNS/WHS row")
    values = re.findall(NUM, row)
    if len(values) < 12:
        raise ValueError("Incomplete timing summary row")
    summary = {
        "wns_ns": float(values[0]),
        "tns_ns": float(values[1]),
        "setup_failing_endpoints": int(values[2]),
        "whs_ns": float(values[4]),
        "ths_ns": float(values[5]),
        "hold_failing_endpoints": int(values[6]),
        "wpws_ns": float(values[8]),
    }
    state_match = re.search(r"^\| Design State\s*:\s*(.*?)\s*$", text, re.M)
    state = state_match.group(1) if state_match else None

    section = None
    clock_from = None
    clock_to = None
    current = None
    paths = []

    def finish() -> None:
        nonlocal current
        if current and current.get("source") and current.get("destination"):
            paths.append(current)
        current = None

    for line in text.splitlines():
        if "Max Delay Paths" in line:
            finish()
            section = "max"
        elif "Min Delay Paths" in line:
            finish()
            section = "min"
        from_match = re.match(r"^From Clock:\s*(\S+)", line)
        to_match = re.match(r"^\s+To Clock:\s*(\S+)", line)
        if from_match:
            finish()
            clock_from = from_match.group(1)
        if to_match:
            clock_to = to_match.group(1)
        slack_match = SLACK.search(line)
        if slack_match:
            finish()
            current = {
                "section": section,
                "from_clock": clock_from,
                "to_clock": clock_to,
                "status": slack_match.group(1),
                "slack_ns": float(slack_match.group(2)),
            }
        if current is None:
            continue
        for key, label in (("source", "Source"), ("destination", "Destination"),
                           ("path_group", "Path Group")):
            match = re.match(r"^\s*" + label + r":\s*(\S+)", line)
            if match:
                current[key] = match.group(1)
        kind = re.match(r"^\s*Path Type:\s*(\w+)", line)
        if kind:
            current["path_type"] = kind.group(1)
        delay = re.match(
            r"^\s*Data Path Delay:\s*(" + NUM + r")ns\s+\(logic\s+(" + NUM +
            r")ns.*?route\s+(" + NUM + r")ns",
            line,
        )
        if delay:
            current["data_delay_ns"] = float(delay.group(1))
            current["logic_delay_ns"] = float(delay.group(2))
            current["route_delay_ns"] = float(delay.group(3))
            if current["data_delay_ns"]:
                current["route_fraction"] = round(
                    current["route_delay_ns"] / current["data_delay_ns"], 4
                )
        levels = re.match(r"^\s*Logic Levels:\s*(\d+)", line)
        if levels:
            current["logic_levels"] = int(levels.group(1))
    finish()
    max_paths = sorted(
        (path for path in paths if path["section"] == "max"),
        key=lambda path: path["slack_ns"],
    )
    return {"design_state": state, "summary": summary, "critical_max_paths": max_paths[:12]}


def routed_timing_gate(summary: dict, design_state: str | None) -> bool:
    if design_state is None or "route" not in design_state.lower():
        raise ValueError("Route-stage gate requires a routed/post-route report")
    return (
        summary["wns_ns"] >= 0 and summary["whs_ns"] >= 0 and
        summary["setup_failing_endpoints"] == 0 and
        summary["hold_failing_endpoints"] == 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", help="Vivado report_timing_summary .rpt")
    parser.add_argument("--stage", choices=("synth", "placed", "route"), required=True)
    parser.add_argument("--output", required=True, help="New JSON output; refuses overwrite")
    args = parser.parse_args()
    report = resolve_repo_path(args.report)
    output = resolve_repo_path(args.output)
    if output.exists() or Path(str(output) + ".sha256").exists():
        parser.error("Output already exists; preserve prior measurements")
    raw = report.read_bytes()
    parsed = parse_report(raw.decode("utf-8", errors="replace"))
    s = parsed["summary"]
    try:
        timing_gate = routed_timing_gate(s, parsed["design_state"]) if args.stage == "route" else None
    except ValueError as exc:
        parser.error(str(exc))
    result = {
        "schema": "timing-triage-v1",
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "stage": args.stage,
        "report": relative_name(report),
        "report_sha256": hashlib.sha256(raw).hexdigest(),
        "timing_gate_pass": timing_gate,
        "scope": "Timing only; CDC, DRC, pins and hardware require separate audits",
        **parsed,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    output.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    Path(str(output) + ".sha256").write_text(
        f"{digest}  {output.name}\n", encoding="ascii"
    )
    print(json.dumps({"stage": args.stage, "timing_gate_pass": timing_gate,
                      "wns_ns": s["wns_ns"], "whs_ns": s["whs_ns"],
                      "critical_max_paths": len(parsed["critical_max_paths"]),
                      "output": relative_name(output)}))
    return 2 if timing_gate is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
