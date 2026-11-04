# N1 recovery checkpoint — 2026-11-02

User goal: execute N1 internal digital loopback under the N0–N9 plan, retaining TX ports empty and J7/J8=2.5V. User reseated SD and changed USB port, then returned the card and powered Z20.

Evidence: all five boot files match the original ATK image. JTAG initially showed BootROM SD error 0x200A; later U-Boot/Linux and SSH recovered. The proposed RAM recovery stopped at its guard before loading anything. No SD image rewrite or Flash programming occurred.

Agent corrections: the first run lacked a loaded-overlay prerequisite; adding a Python lock initially conflicted with the C driver's existing flock, causing second-run init=-11. Corrected lock handoff. The third board result reports zero errors for both ramp and PN, but raw files were empty following a user-confirmed reset/power cycle. PC verification failed rather than accepting a JSON-only result. Three attempts used; no extra run and no N2 work.

Prepared correction: atomic synchronized result and capture writes, unique per-attempt names and archive hashes. 34 PC tests passed. N1 full acceptance remains FAIL pending user decision on additional verification. This checkpoint does not mark M-A complete, nor replace the eventual milestone collaboration report.


## Authorized completion

User reply: “允许补做一轮，我会保持上电不复位”. The agent restricted the exception to round4, added an explicit CLI flag and recorded authorization in the result. Board atomic-write smoke check passed before RF operation. Round4 then passed ramp and PN:131072words each, four channels all zero mismatch; ID0x0A; ten TX readback pairs89750mdB; GPIO0 at close, no buffer quarantine. Full NPZ files and hashes were retrieved and independently verified on PC with no input/reference substitution or discarded samples. Same boot ID before/after confirms no restart in this verification interval. Figure and JSON evidence generated,34 PC tests passed, N1/G2 marked DONE. Historical failures and the incomplete round3 archive are retained. No fifth test or RF air transmission occurred. M-A remains incomplete; proceed to N2.
