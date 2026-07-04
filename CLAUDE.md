# WQCS — Water Quality Control System

## What this is
A two-controller water distillation control system:
- **PyPortal** (`code.py`, CircuitPython) — touchscreen HMI / I2C controller. Sends command bytes, displays status. No control logic of its own.
- **Raspberry Pi Pico** (`main.py`, MicroPython) — I2C responder, runs the actual state machine (boiler heater, refill/drain valves, reservoir level, TDS/temp sensors). Uses a hand-rolled register-level I2C responder driver (`I2C_Responder.py`) since stock MicroPython lacked native I2C slave support.

Full system breakdown (device roles, control flow, known bugs) is in [System_Analysis.md](System_Analysis.md) — read that first for any work on the existing firmware.

## Current status (as of 2026-07-03)
- Project was moved here from `~/Library/Mobile Documents/com~apple~CloudDocs/Python/PYPico_WLCS/Pico/WQCS` (an iCloud-synced folder — treat that as the old/legacy location, this folder is now the working copy).
- Git repo initialized here, linked to GitHub: `mayersgm/WaterQualitySystemControl-WQSC-`, branch `main`, initial commit pushed.
- Push access is via a dedicated SSH key/host alias (`github-mayersgm` in `~/.ssh/config`, key `~/.ssh/id_ed25519_mayersgm`) — separate from the user's other GitHub identity (`github-lohae` alias). Don't touch the `github-lohae` config when working here.

## Next planned step
Enter plan mode to design a **hardware upgrade** for this system (replacing/augmenting current sensors: boiler limit switches, heater relay, reservoir float sensors, and re-enabling/redesigning cooling fan control — see "Notable Existing Issues" in `System_Analysis.md` for pain points to address, e.g. unrecoverable error-latch states, fragile level-constant encoding).
