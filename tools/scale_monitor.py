"""Live timestamped monitor for the Pico's status stream (USB serial).

Usage:  python3 tools/scale_monitor.py [--port /dev/cu.usbmodemXXXX]

Prints one line per Pico status (about 1/s): elapsed time, state, valve/heater
flags, and each scale's weight, change since the previous reading, and a tag
when a threshold from Pico/main.py is crossed. Read-only; sends nothing.
Only one program can hold the serial port, so close other monitors first.
"""
import argparse
import ast
import glob
import re
import sys
import time
from pathlib import Path

import serial

MAIN_PY = Path(__file__).resolve().parent.parent / "Pico" / "main.py"


def load_thresholds():
    names = ("BOILER_TOPOFF_G", "BOILER_FULL_G", "BOILER_OVERFLOW_G",
             "COLLECTOR_EMPTY_G", "COLLECTOR_FULL_G",
             "RESERVOIR_TRANSFER_LOW_G", "RESERVOIR_FULL_G")
    text = MAIN_PY.read_text()
    return {n: int(re.search(rf"^{n}\s*=\s*(\d+)", text, re.M).group(1)) for n in names}


def tags(t, boiler, collector, reservoir):
    b = "OVER" if boiler >= t["BOILER_OVERFLOW_G"] else \
        "FULL" if boiler >= t["BOILER_FULL_G"] else \
        "<TOPOFF" if boiler < t["BOILER_TOPOFF_G"] else ""
    c = "FULL" if collector >= t["COLLECTOR_FULL_G"] else \
        "EMPTY" if collector <= t["COLLECTOR_EMPTY_G"] else ""
    r = "FULL" if reservoir >= t["RESERVOIR_FULL_G"] else \
        "LOW" if reservoir < t["RESERVOIR_TRANSFER_LOW_G"] else ""
    return b, c, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None)
    args = ap.parse_args()

    port = args.port or (sorted(glob.glob("/dev/cu.usbmodem*")) or [None])[0]
    if not port:
        sys.exit("No /dev/cu.usbmodem* device found; pass --port.")

    thresholds = load_thresholds()
    print(f"port {port}   thresholds from {MAIN_PY.name}: {thresholds}")
    print(f"{'t(s)':>7} {'state':8} MRTH  {'boiler':>16}  {'collector':>16}  {'reservoir':>16}  faults")

    ser = serial.Serial(port, 115200, timeout=1)
    start = time.time()
    prev = None
    try:
        while True:
            raw = ser.readline().decode(errors="replace").strip()
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
