"""Deploy HMI files to the ESP32 while the touchscreen app is running.

Usage:  python3 tools/esp_deploy.py [files...]     (default: all ESP-S32CI/*.py)
        python3 tools/esp_deploy.py --no-reset main.py

The running HMI can't be interrupted reliably from mpremote (Ctrl-C often lands
inside LVGL's timer callback instead of the main loop), so this hard-resets the
board, interrupts main.py while it is still importing, copies the files, then
hard-resets again so the new code starts. Always hard resets -- a soft reset
followed by display init panics this firmware (see ESP-S32CI/BUILD.md).
"""
import argparse
import glob
import os
import subprocess
import sys
import time

import serial

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "..", "ESP-S32CI")


def mpremote(port, *args, timeout=30):
    r = subprocess.run(["mpremote", "connect", port, *args],
                       capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError("mpremote %s failed: %s" % (" ".join(args), r.stderr.strip()[-300:]))
    return r.stdout


def interrupt_at_boot(port, seconds=4.0):
    mpremote(port, "reset")
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 0.05
    s.dtr = s.rts = False
    s.open()
    end = time.time() + seconds
    out = b""
    while time.time() < end:
        s.write(b"\x03")
        time.sleep(0.05)
        out += s.read(4096)
    s.write(b"\r\n")
    time.sleep(0.3)
    out += s.read(4096)
    s.close()
    if b">>>" not in out:
        raise RuntimeError("could not get a REPL prompt after reset")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="*")
    ap.add_argument("--port", default=(sorted(glob.glob("/dev/cu.usbserial-*")) or [None])[0])
    ap.add_argument("--no-reset", action="store_true", help="leave the board at the REPL")
    args = ap.parse_args()
    if not args.port:
        sys.exit("No /dev/cu.usbserial-* device found; pass --port.")

    # Bare names always mean ESP-S32CI/<name>: the repo root has a legacy
    # main.py that must never be copied to the ESP32.
    files = args.files or sorted(glob.glob(os.path.join(SRC, "*.py")))
    files = [os.path.join(SRC, f) if os.sep not in f else f for f in files]
    for f in files:
        if not os.path.abspath(f).startswith(os.path.abspath(SRC) + os.sep):
            sys.exit("refusing to deploy %s: not in ESP-S32CI/" % f)
        if not os.path.exists(f):
            sys.exit("no such file: %s" % f)

    interrupt_at_boot(args.port)
    for f in files:
        mpremote(args.port, "cp", f, ":" + os.path.basename(f))
        print("copied", os.path.basename(f))
    if not args.no_reset:
        mpremote(args.port, "reset")
        print("reset -- HMI restarting")


if __name__ == "__main__":
    main()
