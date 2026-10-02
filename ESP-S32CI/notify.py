"""Push alerts to the phone while away from home (ntfy.sh, or a self-hosted
ntfy server).

AlertEdges turns the Pico status stream into one-off alerts (pure logic, host
tested). NtfyPusher sends them with a non-blocking socket polled from the main
loop, like the web server.

No thread: MicroPython runs scheduled callbacks -- including LVGL's render,
which task_handler schedules from a hardware timer -- in whichever thread is
running. A sender thread's small stack then overflowed during a render and
corrupted the IDF heap (panic in tlsf_walk_pool, 2026-10-01). Only the DNS
lookup blocks; it runs once per WiFi connection and after failures, rate
limited.

Plain HTTP: the ESP32 has too little RAM for TLS next to LVGL. The topic name
is the only secret, so pick a long random one (see wifi_secrets_example.py).
"""
import select
import socket
import time

COOLDOWN_MS = 10 * 60 * 1000   # same alert at most once per 10 min (ACK + re-latch)
STANDBY_CONFIRM = 3            # status lines (~3 s) before "no room" counts
QUEUE_MAX = 8
RETRIES = 3
RETRY_WAIT_MS = 10000
SEND_TIMEOUT_MS = 10000        # connect + send + reply, per attempt
DNS_RETRY_MS = 10 * 60 * 1000  # a failed lookup can block for seconds: don't repeat it often

FAULT_NAMES = {"tds1": "TDS-1 distillate", "overflow": "Boiler overflow",
               "refill_timeout": "Refill timeout", "valve_stuck": "Refill valve stuck",
               "collector_overflow": "Collector overflow",
               "reservoir_overflow": "Reservoir overflow", "transfer_leak": "Transfer leak",
               "controller": "Pico control loop failed", "sensor": "Sensor read failing"}

# ntfy priorities: 5 = urgent (breaks through Focus on iOS), 3 = default
URGENT, HIGH, DEFAULT, LOW = 5, 4, 3, 2


class AlertEdges:
    """Feed every main-loop pass; returns [(title, message, priority, tags)]
    for conditions that just started. status is None on passes with no new
    status line."""

    def __init__(self):
        self._faults = set()
        self._tds2 = False
        self._no_room_count = 0
        self._no_room = False
        self._link = None          # unknown until the first status arrives
        self._last_sent = {}

    def _fire(self, out, key, now, title, msg, prio, tags):
        last = self._last_sent.get(key)
        if last is not None and time.ticks_diff(now, last) < COOLDOWN_MS:
            return
        self._last_sent[key] = now
        out.append((title, msg, prio, tags))

    def update(self, status, link_ok, now):
        out = []
        if self._link is not None and link_ok != self._link:
            if link_ok:
                self._fire(out, "link_up", now, "WQCS link restored",
                           "The touchscreen is receiving Pico status again.", LOW, "white_check_mark")
            else:
                self._fire(out, "link_down", now, "WQCS: no link to Pico",
                           "The touchscreen stopped receiving status from the Pico "
                           "(Pico off, crashed, or UART wiring).", HIGH, "warning")
        if link_ok or self._link is not None:
            self._link = link_ok
        if status is None:
            return out

        faults = set(k for k, on in status.get("fault", {}).items() if on)
        for k in faults - self._faults:
            self._fire(out, "fault:" + k, now, "WQCS FAULT: " + FAULT_NAMES.get(k, k),
                       "Distillation halted. Check the system, then ACK.", URGENT, "rotating_light")
        self._faults = faults

        tds2 = bool(status.get("alert", {}).get("tds2"))
        if tds2 and not self._tds2:
            self._fire(out, "tds2", now, "WQCS: outlet TDS high",
                       "TDS-2 reads %s ppm at the outlet." % status.get("tds2_ppm", "?"),
                       HIGH, "droplet")
        self._tds2 = tds2

        # STANDBY with the transfer closed = collector full and the reservoir
        # can't take it: the only state that needs someone to draw water.
        # Confirmed over a few lines so the moment between "collector reached
        # FULL" and "transfer valve opened" doesn't alert.
        waiting = (status.get("state") == "STANDBY"
                   and not status.get("valves", {}).get("transfer"))
        self._no_room_count = self._no_room_count + 1 if waiting else 0
        no_room = self._no_room_count >= STANDBY_CONFIRM
        if no_room and not self._no_room:
            self._fire(out, "no_room", now, "WQCS: reservoir full",
                       "Distilling paused (STANDBY): the collector is full and the "
                       "reservoir has no room. Draw some water.", DEFAULT, "pause_button")
        self._no_room = no_room
        return out


class NtfyPusher:
    """Queue alerts from the main loop; poll() sends them without blocking
    (except a rare DNS lookup, see the module docstring)."""

    def __init__(self, server, topic, port=80):
        self.server, self.topic, self.port = server, topic, port
        self.queue = []
        self.sent = self.failed = 0
        self._addr = None
        self._dns_failed = None
        self._sock = None
        self._out = None
        self._reply = b""
        self._deadline = 0
        self._attempt = 0
        self._wait_until = None

    def push(self, title, message, priority=DEFAULT, tags=""):
        if len(self.queue) >= QUEUE_MAX:
            self.queue.pop(0)          # drop the oldest; the newest matter most
        self.queue.append((title, message, priority, tags))

    def request(self, title, message, priority, tags):
        body = message.encode()
        head = ("POST /%s HTTP/1.0\r\nHost: %s\r\nTitle: %s\r\nPriority: %d\r\n"
                "Tags: %s\r\nContent-Length: %d\r\nConnection: close\r\n\r\n"
                % (self.topic, self.server, title, priority, tags, len(body)))
        return head.encode() + body

    def resolve(self, now):
        """Blocking DNS lookup, rate limited. Call when WiFi has just connected
        (the lookup is cheapest to absorb then) or before a send."""
        if self._addr is not None:
            return True
        if self._dns_failed is not None and time.ticks_diff(now, self._dns_failed) < DNS_RETRY_MS:
            return False
        try:
            self._addr = socket.getaddrinfo(self.server, self.port)[0][-1]
            self._dns_failed = None
            print("ntfy:", self.server, "resolved")
            return True
        except OSError as e:
            self._dns_failed = now
            print("ntfy: DNS lookup failed", e)
            return False

    def poll(self, now):
        """Advance the current send by one non-blocking step."""
        if self._sock is None:
            if not self.queue:
                return
            if self._wait_until is not None and time.ticks_diff(self._wait_until, now) > 0:
                return
            if not self.resolve(now):
                return
            self._start(now)
            return
        try:
            if time.ticks_diff(now, self._deadline) > 0:
                raise OSError("timeout")
            if self._out:
                if not self._ready(select.POLLOUT):
                    return             # still connecting
                n = self._sock.send(self._out)
                self._out = self._out[n:]
                return
            if not self._ready(select.POLLIN):
                return
            data = self._sock.recv(64)
            if data and len(self._reply) < 64:
                self._reply += data
                if b"\r\n" not in self._reply:
                    return
            if b" 200 " not in self._reply:
                raise OSError("ntfy replied %r" % self._reply[:32])
            self._finish(True, now)
        except OSError as e:
            print("ntfy send failed (%d/%d): %r" % (self._attempt, RETRIES, e))
            self._addr = None if self._attempt >= 2 else self._addr  # server IP may have changed
            self._finish(False, now)

    def _ready(self, event):
        p = select.poll()
        p.register(self._sock, event)
        ev = p.poll(0)
        if ev and ev[0][1] & (select.POLLERR | select.POLLHUP) and not ev[0][1] & select.POLLIN:
            raise OSError("connection failed")
        return bool(ev)

    def _start(self, now):
        self._attempt += 1
        self._reply = b""
        self._deadline = time.ticks_add(now, SEND_TIMEOUT_MS)
        self._out = memoryview(self.request(*self.queue[0]))
        s = socket.socket()
        s.setblocking(False)
        self._sock = s
        try:
            s.connect(self._addr)
        except OSError as e:
            if not (e.args and e.args[0] in (115, 119)):   # EINPROGRESS
                print("ntfy connect failed:", e)
                self._finish(False, now)

    def _finish(self, ok, now):
        if self._sock is not None:
            try:
                self._sock.close()
            except OSError:
                pass
        self._sock = self._out = None
        if ok:
            self.sent += 1
        elif self._attempt < RETRIES:
            self._wait_until = time.ticks_add(now, RETRY_WAIT_MS)
            return
        else:
            self.failed += 1
        if self.queue:
            self.queue.pop(0)
        self._attempt = 0
        self._wait_until = None
