"""Tests the timing evidence gate against a real routed checkpoint report."""

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import timing_triage  # noqa: E402


class TimingTriageTests(unittest.TestCase):
    def test_real_baseline_distinguishes_recovery_from_setup(self):
        report = (ROOT / "report/results/timing_v1d_baseline.rpt").read_text(
            encoding="utf-8", errors="replace"
        )
        parsed = timing_triage.parse_report(report)
        self.assertEqual(parsed["summary"]["wns_ns"], 0.092)
        self.assertEqual(parsed["summary"]["whs_ns"], 0.037)
        self.assertTrue(timing_triage.routed_timing_gate(parsed["summary"], parsed["design_state"]))
        first = parsed["critical_max_paths"][0]
        self.assertEqual(first["path_type"], "Recovery")
        self.assertEqual(first["logic_levels"], 1)
        self.assertGreater(first["route_fraction"], 0.85)
        self.assertTrue(any(path.get("logic_levels") == 10 and
                            path.get("path_type") == "Setup"
                            for path in parsed["critical_max_paths"]))

    def test_negative_slack_and_unrouted_reports_are_rejected(self):
        summary = {"wns_ns": -0.1, "whs_ns": 0.04,
                   "setup_failing_endpoints": 1, "hold_failing_endpoints": 0}
        self.assertFalse(timing_triage.routed_timing_gate(summary, "Routed"))
        with self.assertRaises(ValueError):
            timing_triage.routed_timing_gate(summary, "Synthesized")


if __name__ == "__main__":
    unittest.main()
