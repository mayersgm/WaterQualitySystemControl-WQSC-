"""Live timestamped monitor for the Pico's status stream (USB serial).

Usage:  python3 tools/scale_monitor.py [--port /dev/cu.usbmodemXXXX]

Prints one line per Pico status (about 1/s): elapsed time, state, valve/heater
flags, and each scale's weight, change since the previous reading, and a tag
when a water-level limit is crossed. Read-only; sends nothing.

Limits start as the defaults in Pico/main.py, then follow the live values
whenever the Pico prints a limits line (at boot if limits.json exists, and on
every GET:LIMITS / SET / RESET_LIMITS sent via the ESP32).
Only one program can hold the serial port, so close other monitors first.
"""
import argparse
import ast
import glob
import sys
import time
from pathlib import Path

import serial

MAIN_PY = Path(__file__).resolve().parent.parent / "Pico" / "main.py"


def load_defaults():
    """DEFAULT_LIMITS dict + BOILER_OVERFLOW_G, read from main.py's source."""
    found = {}
    for node in ast.parse(MAIN_PY.read_text()).body:
        if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name in ("DEFAULT_LIMITS", "BOILER_OVERFLOW_G"):
                found[name] = ast.literal_eval(node.value)
    limits = dict(found["DEFAULT_LIMITS"])
    limits["boiler_overflow"] = found["BOILER_OVERFLOW_G"]
    return limits


def parse_limits_line(raw):
    """Live limits from a Pico console line, or None."""
    try:
        if raw.startswith("Limits loaded:"):
            return ast.literal_eval(raw.split(":", 1)[1].strip())
        if raw.startswith("{'limits'") or raw.startswith('{"limits"'):
            return ast.literal_eval(raw)["limits"]
        if "'limits':" in raw:
            return ast.literal_eval(raw)["limits"]
    except (ValueError, SyntaxError, KeyError):
        pass
    return None


def tags(t, boiler, collector, reservoir):
    b = "OVER" if boiler >= t["boiler_overflow"] else \
        "FULL" if boiler >= t["boiler_full"] else \
        "<TOPOFF" if boiler < t["boiler_topoff"] else ""
    c = "FULL" if collector >= t["collector_full"] else \
        "EMPTY" if collector <= t["collector_empty"] else ""
    r = "FULL" if reservoir >= t["reservoir_full"] else \
        "LOW" if reservoir < t["reservoir_low"] else ""
    return b, c, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    args = ap.parse_args()

    port = args.port or (sorted(glob.glob("/dev/cu.usbmodem*")) or [None])[0]
    if not port:
        sys.exit("No /dev/cu.usbmodem* device found; pass --port.")

    thresholds = load_defaults()
    header = f"{'t(s)':>7} {'state':8} MRTH  {'boiler':>16}  {'collector':>16}  {'reservoir':>16}  faults"
    print(f"port {port}")
    print(f"limits (defaults from {MAIN_PY.name}; live values replace these when the Pico reports them):")
    print(f"  {thresholds}")
    print(header)

    ser = serial.Serial(port, 115200, timeout=1)
    start = time.time()
    prev = None
    try:
        while True:
            raw = ser.readline().decode(errors="replace").strip()
            live = parse_limits_line(raw)
            if live is not None:
                thresholds.update(live)
                print(f"{time.time() - start:7.1f} LIMITS   {live}", flush=True)
                continue
            if not raw.startswith("{"):
                continue
            try:
                d = ast.literal_eval(raw)
                w = (d["boiler_g"], d["collector_g"], d["reservoir_g"])
            except (ValueError, SyntaxError, KeyError):
                continue

            deltas = [0.0] * 3 if prev is None else [a - b for a, b in zip(w, prev)]
            prev = w
            tg = tags(thresholds, *w)
            cells = [f"{g:7.1f}g {dl:+6.1f} {tag:<7}"[:16 + 9] for g, dl, tag in zip(w, deltas, tg)]
            v = d["valves"]
            flags = f"{v['main']}{v['refill']}{v['transfer']}{d['heater']}"
            faults = ",".join(k for k, x in d["fault"].items() if x) or "-"
            print(f"{time.time() - start:7.1f} {d['state']:8} {flags}  " + "  ".join(cells) + f"  {faults}",
                  flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        ser.close()


if __name__ == "__main__":
    main()
