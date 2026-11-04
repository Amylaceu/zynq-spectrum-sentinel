# sentinel_v1 computer implementation acceptance

Final timing: {'WNS_ns': 0.086, 'TNS_ns': 0.0, 'setup_failing_endpoints': 0, 'WHS_ns': 0.046, 'THS_ns': 0.0, 'hold_failing_endpoints': 0, 'WPWS_ns': 0.264, 'pulse_failing_endpoints': 0}

Resources: {'Slice LUTs': 26625.0, 'Slice Registers': 35103.0, 'Block RAM Tile': 49.0, 'DSPs': 64.0}

The implementation acceptance.json above remains the original computer-only evidence. Subsequent board acceptance is recorded separately below; its original scope and hashes are unchanged.

## N4 board acceptance (2026-11-02)

Finite selftest: single-tone error0bin, three targets, 8192 replay power words exact. LCD phases25/12/8/6/4/3/2 all passed user visual checks; phase3 selected with one-step margin above minimum tested2. Complete RX display median49.453/49.418fps in two120s runs at3.84MSPS; all211 telemetry records have sample-FIFO overflow=false. Target-list capacity warnings42/105 and43/106 are retained and are separate from the sample FIFO. Final RF GPIO output0 and no active monitor/bench;58 PS tests passed.

See docs/n4_acceptance_summary.md and board/measurements/n4_acceptance_summary.json for measured limits, per-file SHA256 and evidence. This does not establish30.72MSPS continuous capture, full FM occupied bandwidth, all-temperature CDC/IO safety or one-hour stability. N4 marked DONE within the documented scope; N5/M-A not complete. Paused at user request; no Git commit/push.
