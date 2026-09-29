"""Append timestamped serial output from a board to a log file.

Usage: python3 tools/serial_log.py <port> <logfile> [minutes]
Opens the port with DTR/RTS held low (may still reset an ESP32 once on macOS).
"""
import sys
import time

import serial

port, path = sys.argv[1], sys.argv[2]
minutes = float(sys.argv[3]) if len(sys.argv) > 3 else 30

s = serial.Serial()
s.port, s.baudrate, s.timeout = port, 115200, 0.5
s.dtr = s.rts = False
s.open()
end = time.time() + minutes * 60
with open(path, "a") as f:
    f.write("\n=== logger start %s ===\n" % time.strftime("%Y-%m-%d %H:%M:%S"))
    pending = ""
    while time.time() < end:
        chunk = s.read(4096)
        if not chunk:
            continue
        pending += chunk.decode(errors="replace")
        *lines, pending = pending.split("\n")
        for line in lines:
            f.write(time.strftime("%H:%M:%S ") + line.rstrip("\r") + "\n")
        f.flush()
s.close()
