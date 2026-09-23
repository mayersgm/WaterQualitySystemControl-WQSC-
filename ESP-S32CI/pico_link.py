import json
from machine import UART

# A real status line is ~300-400 bytes. If the buffer grows far past that
# without ever finding a newline, the link is receiving noise (e.g. a
# missing common ground, or nothing connected) rather than real JSON --
# drop it instead of accumulating without bound and crashing with a
# MemoryError.
MAX_BUF_LEN = 4096


class PicoLink:
    """UART link to the Pico controller (GPIO22 TX / GPIO35 RX by default,
    see Phase0_Design.md). Owns sending commands and parsing the JSON status
    stream. Shared by bench-test tooling and the Phase 3 touchscreen HMI --
    the eventual UI loop calls poll()/send() directly rather than this being
    rewritten per use case."""

    def __init__(self, uart_id=1, tx=22, rx=35, baudrate=9600):
        # Explicit rxbuf: a ~300-400 byte status line arriving faster than
        # the console loop drains it can overflow the ESP32 UART driver's
        # default receive buffer (commonly 256 bytes), silently dropping
        # bytes mid-message -- every line then fails to parse as JSON with
        # no obvious symptom other than status never appearing.
        self.uart = UART(uart_id, baudrate=baudrate, tx=tx, rx=rx, rxbuf=1024)
        self._buf = b""
        self.last_status = {}
        self.link_errors = 0  # count of overflow/decode failures, for diagnostics
        self.last_bad_line = None  # most recent line that failed to parse

    def send(self, command):
        self.uart.write(command.strip() + "\n")

    def poll(self):
        """Call frequently (each UI frame / loop pass). Returns the newest
        parsed status dict received since the last call, or None if nothing
        new arrived. Malformed lines are skipped."""
        if not self.uart.any():
            return None
        self._buf += self.uart.read()
        if len(self._buf) > MAX_BUF_LEN:
            self.link_errors += 1
            self._buf = b""
            return None
        newest = None
        while b"\n" in self._buf:
            line, self._buf = self._buf.split(b"\n", 1)
            try:
                newest = json.loads(line.decode().strip())
            except ValueError:
                self.link_errors += 1
                self.last_bad_line = line
                continue
        if newest is not None:
            self.last_status = newest
        return newest
