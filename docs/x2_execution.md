# X2 execution and handoff

Run from the Git repository root, using PowerShell 7 and its `.venv`. Do not
copy these commands into the old planning directory. Read `AGENTS.md`,
`runbook/90_plan.md`, and `docs/antenna_sd_guide.md` first.

## Current checkpoint

- X0 DONE; X1 FAIL remains recorded. The user authorized proceeding to X2.
- X2 configuration A is confirmed: current 20–512 MHz antenna on RX1A,
  TX1A empty, J22 SSD1963 and J7/J8=2.5V unchanged. RX only.
- 30.72 MSPS/64-frame chain simulation passed: 131072 input samples,
  SAMPLE_DROP=0, FRAME_DROP=4, first 8192 powers bit exact. Queue decimation
  is distinct from sample loss and must always be reported.
- Implementation attempt 1 failed routed setup timing (WNS -0.331 ns,
  TNS -68.884 ns; WHS +0.032 ns). Its 282-file archive and verified manifest
  are recorded in `docs/x2_implementation_r1_failure.json`. It was not loaded.
- Attempt 2 reuses completed synthesis and unchanged HDL/clocks, changing only
  the implementation strategy to `Performance_ExtraTimingOpt`. Its 188 frozen
  inputs are in `docs/x2_v1c_prebuild_r2.json`. It completed with routed setup
  -0.709 ns and hold -0.058 ns; the runner rejected it before collection,
  deployment or board loading. Its 267-file archive is recorded in
  `docs/x2_implementation_r2_failure.json`. No build is running now.
- Python regression: 235 passed (`logs/X2_python_tests_fast_r2.log`), including
  separate screening/qualification gates, corrupt-measurement rejection and
  ownership checks on RSSI shutdown. Software freeze is
  `docs/x2_software_predeployment_r2.json` (24 files; board Python 3.8 syntax).
- No X2 bitstream has been loaded; no X2 bandwidth or visual result is accepted.
- X2 is FAIL/deferred at the user's request to prioritize functions. No third
  implementation attempt is authorized by this execution decision. Continue
  with the accepted 3.84 MSPS baseline; retain X1 FAIL and X2 FAIL in X3 tables.

## Build gates

Inspect progress without restarting the active build:

```powershell
Get-Content logs/X2_v1c_implementation_r2_exit.txt
Get-Content logs/X2_v1c_implementation_r2.log -Tail 30
.venv/Scripts/python.exe tools/freeze_x2_build.py --attempt 2 --verify
Get-Content logs/X2_final_audit_r2_exit.txt -ErrorAction SilentlyContinue
```

`tools/retry_x2_implementation.ps1` would collect and audit after successful
implementation. Attempt 2 instead exited 1 at its routed timing gate; no final
audit or X2 deployment was performed. Do not rerun it or overwrite its records.

Require hashed `board/overlay/sentinel_v1c/acceptance.json` with status PASS.
This checks the routed design, not a pre-route report: setup/hold/pulse,
unconstrained endpoints, CDC counter endpoints, bus skew, resources and HWH.
If it fails, archive all failed inputs/reports before a new attempt, max 3.
Never load an unaudited implementation.

The user's current priority is functional progress. Finish attempt 2 already
running; if it fails timing, archive it with
`tools/archive_x2_failed_build.py --attempt 2`, defer further wideband timing
optimization, and continue X3 using the previously accepted 3.84 MSPS image.
Do not launch implementation attempt 3 automatically. Record X2 as FAIL/deferred
and all unmeasured wideband rates as NOT_TESTED, rather than claiming milestone
A's original bandwidth target passed. Request X3 configuration A confirmation
before its RF operations. This decision supersedes the generic retry allowance
above; no failing implementation is loaded for a demonstration.

## Board gates (future resumption only; currently blocked by timing)

The following are sequential. Use `--sudo-stdin` only with a private credential
source; it reads one line and never writes it to evidence. Otherwise a
noninteractive sudo configuration is required. Do not include a password in
scripts, command arguments, logs or handoff documents. Existing limited N4
administration is not a bypass for X2.

```powershell
# Software attempt 2 is already frozen; do not overwrite its evidence.
.venv/Scripts/python.exe tools/deploy_x2.py --attempt 2
.venv/Scripts/python.exe tools/run_x2_board.py --mode build-library --attempt 1 --deployment-attempt 2 --confirm-configuration-a
.venv/Scripts/python.exe tools/run_x2_board.py --mode selftest --attempt 1 --deployment-attempt 2 --confirm-configuration-a
.venv/Scripts/python.exe tools/accept_x2_selftest.py --measurement board/measurements/x2_selftest_r1.json
```

Deployment only creates independent X2 files. It validates accepted shared
sources and imports with the board's Python 3.8. The separate RF library is
`libad9361_x2.so`; the original library must retain its SHA256. Its default
Make target and the explicit build command both select the X2 library.
Digital self-test holds RF in reset and checks two tone cases plus four exact
2048-word replay frames. The host independently verifies the retrieved NPZ.

For each rate below, run the monitor in a hidden background process, with
stdout/stderr in unique `logs/X2_*.log` files. Do not launch the next rate until
the previous command exits successfully and independent acceptance passes:

```powershell
.venv/Scripts/python.exe tools/run_x2_board.py --mode monitor --rate 7680000 --attempt 1 --deployment-attempt 2 --confirm-configuration-a --screening
.venv/Scripts/python.exe tools/analyze_x2.py --measurement board/measurements/x2_screen_7680000_r1.json --screening
# Then repeat the same pair with 15360000, 24576000, 30720000, in that order.
```

At the user's request to shorten testing, first screen each rate for 60 seconds
in ascending order. Each independent screen acceptance is `PASS_SCREENING`,
qualification `SCREENING_ONLY`. After all four pass, qualify 30.72 MSPS for
600 seconds (or the highest passing lower rate if a higher rate fails):

```powershell
.venv/Scripts/python.exe tools/run_x2_board.py --mode monitor --rate 30720000 --attempt 1 --deployment-attempt 2 --confirm-configuration-a --fast-path
.venv/Scripts/python.exe tools/analyze_x2.py --measurement board/measurements/x2_monitor_30720000_r1.json
```

This takes 14 minutes of acquisition, plus initialization, deployment and
self-test. A fast-path 600-second run requires independently accepted screens
at that rate and every lower rate from the same deployment. Screening does not
satisfy the original four-times-600-second plan: report lower rates as screened
only, and the selected rate as sustained-qualified only after it passes.
The original four-times-600-second path remains available by omitting both
`--screening` and `--fast-path`, then analyzing each monitor without `--screening`.

Each monitor reinitializes the audited overlay. Its
configured RF bandwidth is 6/12/20/25 MHz respectively. Keep the board powered
and all connections unchanged throughout. The wrapper verifies file hashes,
boot continuity, source-off and GPIO=0 before and after each finite job.

Acceptance requires absolute SAMPLE_DROP=0 (including the initial snapshot),
no reset/saturation/framing errors, final IN=OUT+DROP, 600 seconds for sustained
qualification (60 seconds for screening, at least 45 telemetry samples), measured
input throughput within 1%, median display fps>=15 and 30–85°C. Record
FRAME_DROP and its fraction without treating it as a failure by itself.
The final error flags are checked again after draining the processing chain.
An RSSI abort keeps ownership until the source is stopped, then closes RF.

Retry attempts use unique names, max 3. Dependency selection accepts successful
hashed attempts only from the same deployment, with separate host acceptance
for self-test and earlier rates. A newer unaccepted run does not hide an older
accepted run. A compiled library left by failed postflight can be recovered only
when its previous receipt, deployment and both library hashes match. Never
overwrite an old result, raw NPZ or log.

## Human and final gates

At the highest accepted rate, request a J22 visual inspection and wait for the
user: FRAME increases, spectrum/waterfall update, frequency scale covers the
full 88–108 MHz FM band, no obvious flashing or corruption. Digital span Fs
does not establish analog filter flatness or full-span detection accuracy.

Write the measured rate table with each run's duration and qualification scope,
frame-drop fraction, resource/timing results and
limitations to `docs/x2_acceptance_summary.md` and hashed JSON. Update
`runbook/STATUS.md`; mark DONE only after all required gates, then commit
`[X2] ...`. If the 30.72 MSPS target fails, retain the highest measured zero-loss
rate as the explicitly permitted fallback; do not label it 30.72 MSPS.
Before X3 RF operations, request its stage-specific configuration A confirmation.

Before any power-off, execute `sudo sync && sudo shutdown -h now`, wait for
halt, then ask the user to disconnect power. Never unplug/reset during a test.
