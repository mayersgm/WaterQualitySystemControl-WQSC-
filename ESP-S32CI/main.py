# WQCS bench-test console (MicroPython).
#
# Not the Phase 3 touchscreen HMI -- just a thin stdin/stdout wrapper around
# PicoLink for driving/observing the Phase 2 Pico bench test (see
# Phase2_BenchTest_Sequence.md). The Phase 3 UI will use PicoLink directly
# with touchscreen input instead of this console loop -- this file is the
# only bench-only part; pico_link.py is the reusable part.

import sys
import select
from pico_link import PicoLink

link = PicoLink()

poll = select.poll()
poll.register(sys.stdin, select.POLLIN)

print("WQCS bench console ready. Type a command and press Enter:")
print("  START | STOP | STERILIZE | EMPTY | RESET | ACK")
print("  TARE:BOILER | CAL:BOILER:<grams>  (also COLLECTOR / RESERVOIR)")
print("  GET:LIMITS | RESET_LIMITS | SET:BOILER_FULL:<g> | SET:BOILER_TOPOFF=<g>,BOILER_FULL=<g>")

input_line = ""
reported_errors = 0

while True:
    # Typed command -> Pico
    while poll.poll(0):
        ch = sys.stdin.read(1)
        if not ch:
            # stdin reporting ready but returning nothing (can happen after
            # the USB serial connection has been reconnected) -- without
            # this, the loop spins here forever and link.poll() below never
            # runs, so incoming status silently stops appearing.
            break
        if ch in ("\n", "\r"):
            if input_line:
                link.send(input_line)
                print("->", input_line)
                input_line = ""
        elif ch in ("\x08", "\x7f"):  # backspace/delete
            input_line = input_line[:-1]
        else:
            input_line += ch

    # Status <- Pico
    status = link.poll()
    if status is not None:
        print("<-", status)
    if link.last_limits is not None:
        print("<- LIMITS", link.last_limits)
        link.last_limits = None
    if link.link_errors != reported_errors:
        reported_errors = link.link_errors
        print("!! link_errors:", reported_errors, "last_bad_line:", link.last_bad_line)
