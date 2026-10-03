"""Milestone 2: iPhone monitor + control over home WiFi.

A small HTTP server polled from the HMI main loop (App.step), so networking
never blocks rendering or the Pico link: every socket is non-blocking, and
each poll() does a bounded amount of work.

  GET  /        the mobile page (web_ui.html, streamed from flash)
  GET  /status  {"link", "age_ms", "status", "limits", "errors", "rssi", ...}
  GET  /log     wifi.log: WiFi connects, drops and recovery steps
  POST /cmd     {"cmd": "START", "pin": "1234"} -> relayed to the Pico

Remote commands are allow-listed (no TARE/CAL/SET from the phone) and need the
PIN from wifi_secrets.py. The ESP32 stays a relay: every interlock lives on
the Pico, so a phone command can't bypass a fault.

Push alerts while away from home go through notify.py (ntfy).
"""
import json
import os
import socket
import time
import network
from notify import AlertEdges, NtfyPusher, DEFAULT

ALLOWED = ("START", "STOP", "STERILIZE", "EMPTY", "RESET", "ACK")
PAGE = "web_ui.html"
HOSTNAME = "wqcs"                 # http://wqcs.local/ via the built-in mDNS responder

RECONNECT_MS = 30000              # retry joining WiFi this often while disconnected
REINIT_MS = 2 * 60 * 1000         # then restart the WiFi driver once
RESET_MS = 10 * 60 * 1000         # then restart the ESP32 (only if WiFi was up this boot)
WIFI_LOG = "wifi.log"
LOG_MAX = 4096
MAX_CONNS = 3
CONN_TIMEOUT_MS = 5000
MAX_REQUEST = 2048                # Safari's headers are ~600 bytes; anything bigger is junk
CHUNK = 1024
BAD_PIN_LIMIT = 5                 # wrong PINs before a lockout
BAD_PIN_LOCKOUT_MS = 60000

_REASONS = {200: "OK", 400: "Bad Request", 403: "Forbidden", 404: "Not Found",
            405: "Method Not Allowed", 413: "Payload Too Large", 429: "Too Many Requests",
            503: "Service Unavailable"}


def _would_block(e):
    return e.args and e.args[0] in (11, 115, 119)   # EAGAIN, EINPROGRESS, EALREADY


class WiFi:
    """Joins the home network and keeps it joined; never blocks after start.

    Recovery escalates while the link is down (2026-10-03: after an overnight
    router restart the HMI stayed off WiFi with plain connect() retries):
      every RECONNECT_MS  connect() again
      after REINIT_MS     restart the WiFi driver (active False/True)
      after RESET_MS      restart the ESP32 -- only if WiFi had been up this
                          boot, so a router that's off for hours can't cause
                          a reboot loop (the Pico is unaffected either way)
    Every step goes to wifi.log (kept under LOG_MAX bytes) for diagnosis.
    """

    def __init__(self, ssid, password, log_path=WIFI_LOG):
        self.ssid, self.password = ssid, password
        self.log_path = log_path
        try:
            network.hostname(HOSTNAME)
        except Exception:  # older firmware: name falls back to the default
            pass
        self.wlan = network.WLAN(network.STA_IF)
        self.ip = None
        self.was_up = False          # connected at least once since boot
        self.down_since = time.ticks_ms()
        self._reinit_done = False
        self.drops = 0
        self.log("boot")
        self._activate()
        self._connect()

    def log(self, event):
        line = "%d %s status=%s\n" % (time.ticks_ms() // 1000, event, self._status())
        print("wifi:", line.strip())
        try:
            try:
                if os.stat(self.log_path)[6] > LOG_MAX:
                    try:
                        os.remove(self.log_path + ".1")   # rename won't overwrite on every FS
                    except OSError:
                        pass
                    os.rename(self.log_path, self.log_path + ".1")   # keep one old file
            except OSError:
                pass
            with open(self.log_path, "a") as f:
                f.write(line)
        except OSError:
            pass

    def _status(self):
        try:
            return self.wlan.status()
        except Exception:
            return None

    def _activate(self):
        self.wlan.active(True)
        try:
            # Power saving made the HMI unreachable after idling: the radio
            # naps between beacons and new connections time out until
            # traffic wakes it (seen 2026-10-02). It's on mains power.
            self.wlan.config(pm=self.wlan.PM_NONE)
        except (AttributeError, ValueError, OSError) as e:
            print("wifi: can't disable power saving", e)

    def _connect(self):
        self._last_try = time.ticks_ms()
        try:
            self.wlan.disconnect()
        except OSError:
            pass
        try:
            self.wlan.connect(self.ssid, self.password)
        except OSError as e:
            self.log("connect error %r" % (e,))

    def _connected(self):
        # associated AND holding an address (an expired lease can leave 0.0.0.0)
        if not self.wlan.isconnected():
            return False
        ip = self.wlan.ifconfig()[0]
        return ip not in ("0.0.0.0", "")

    def poll(self):
        """Returns True while connected."""
        now = time.ticks_ms()
        if self._connected():
            if self.ip is None:
                self.ip = self.wlan.ifconfig()[0]
                self.was_up = True
                self._reinit_done = False
                self.log("connected ip=%s rssi=%s down_s=%d" % (
                    self.ip, self.rssi(), time.ticks_diff(now, self.down_since) // 1000))
            return True
        if self.ip is not None:
            self.ip = None
            self.drops += 1
            self.down_since = now
            self.log("lost")
        down = time.ticks_diff(now, self.down_since)
        if self.was_up and down > RESET_MS:
            self.log("down %d s: restarting the ESP32" % (down // 1000))
            import machine
            machine.reset()
        if not self._reinit_done and down > REINIT_MS:
            self._reinit_done = True
            self.log("down %d s: restarting the WiFi driver" % (down // 1000))
            try:
                self.wlan.active(False)
            except OSError:
                pass
            self._activate()
            self._connect()
        elif time.ticks_diff(now, self._last_try) > RECONNECT_MS:
            self._connect()
        return False

    def rssi(self):
        try:
            return self.wlan.status("rssi")
        except Exception:
            return None


class _Conn:
    def __init__(self, sock, now):
        self.sock = sock
        self.started = now
        self.buf = b""
        self.out = None        # memoryview of bytes still to send
        self.file = None       # page being streamed after the headers

    def close(self):
        for f in (self.file, self.sock):
            if f is not None:
                try:
                    f.close()
                except OSError:
                    pass


def parse_request(buf):
    """(method, path, body) once buf holds a full request, else None.
    Raises ValueError on a malformed one."""
    end = buf.find(b"\r\n\r\n")
    if end < 0:
        return None
    lines = buf[:end].decode().split("\r\n")
    parts = lines[0].split(" ")
    if len(parts) < 2:
        raise ValueError("bad request line")
    length = 0
    for line in lines[1:]:
        k, _, v = line.partition(":")
        if k.strip().lower() == "content-length":
            length = int(v.strip())
    body = buf[end + 4:]
    if len(body) < length:
        return None
    return parts[0], parts[1].split("?")[0], body[:length]


def response_head(code, ctype, length):
    return ("HTTP/1.0 %d %s\r\nContent-Type: %s\r\nContent-Length: %d\r\n"
            "Cache-Control: no-store\r\nConnection: close\r\n\r\n"
            % (code, _REASONS.get(code, ""), ctype, length)).encode()


class Remote:
    """The phone-facing API. handle() is pure request -> response logic (host
    tested); poll() does the WiFi, sockets and push alerts."""

    def __init__(self, app, cfg):
        self.app = app
        self.pin = str(cfg.CMD_PIN)
        self.wifi = WiFi(cfg.WIFI_SSID, cfg.WIFI_PASSWORD)
        topic = getattr(cfg, "NTFY_TOPIC", None)
        self.pusher = None
        if topic:
            self.pusher = NtfyPusher(getattr(cfg, "NTFY_SERVER", "ntfy.sh"), topic)
        self.edges = AlertEdges()
        self.listener = None
        self.conns = []
        self._bad_pins = 0
        self._locked_until = None

    # -- request handling --
    def handle(self, method, path, body, now):
        """Returns (code, content_type, bytes) or (200, content_type, PAGE)
        for the page, which poll() streams from flash."""
        if path in ("/", "/index.html"):
            if method != "GET":
                return self._json(405, {"err": "GET only"})
            return 200, "text/html; charset=utf-8", PAGE
        if path == "/status":
            return self._json(200, self.snapshot(now))
        if path == "/log":                # WiFi history (no secrets in it)
            text = b""
            for name in (self.wifi.log_path + ".1", self.wifi.log_path):
                try:
                    with open(name, "rb") as f:
                        text += f.read()
                except OSError:
                    pass
            return 200, "text/plain", text or b"(empty)\n"
        if path == "/cmd":
            if method != "POST":
                return self._json(405, {"err": "POST only"})
            return self._command(body, now)
        return self._json(404, {"err": "not found"})

    def snapshot(self, now):
        app = self.app
        age = None if app.last_rx is None else time.ticks_diff(now, app.last_rx)
        return {"link": app.link_ok, "age_ms": age, "status": app.link.last_status,
                "limits": app.limits, "errors": app.link.link_errors,
                "rssi": self.wifi.rssi() if self.wifi else None,
                "uptime_s": now // 1000,
                "wifi_drops": self.wifi.drops,
                "push": None if self.pusher is None else {
                    "sent": self.pusher.sent, "failed": self.pusher.failed,
                    "queued": len(self.pusher.queue)}}

    def _command(self, body, now):
        if self._locked_until is not None:
            if time.ticks_diff(self._locked_until, now) > 0:
                return self._json(429, {"err": "too many wrong PINs; wait a minute"})
            self._locked_until, self._bad_pins = None, 0
        try:
            req = json.loads(body)
            cmd, pin = str(req["cmd"]).strip().upper(), str(req["pin"])
        except (ValueError, KeyError, TypeError):
            return self._json(400, {"err": "expected {cmd, pin}"})
        if pin != self.pin:
            self._bad_pins += 1
            if self._bad_pins >= BAD_PIN_LIMIT:
                self._locked_until = time.ticks_add(now, BAD_PIN_LOCKOUT_MS)
            return self._json(403, {"err": "wrong PIN"})
        self._bad_pins = 0
        if cmd == "TEST_PUSH":            # handled here; never relayed to the Pico
            if self.pusher is None:
                return self._json(400, {"err": "push alerts are off (no NTFY_TOPIC)"})
            self.pusher.push("WQCS test alert", "Push alerts are working.", DEFAULT, "bell")
            return self._json(200, {"ok": True, "cmd": cmd})
        if cmd not in ALLOWED:
            return self._json(400, {"err": "command not allowed remotely"})
        if not self.app.link_ok:
            return self._json(503, {"err": "no link to the Pico"})
        print("phone ->", cmd)
        if cmd == "ACK":
            self.app.ack()          # also silences the touchscreen's alarm
        else:
            self.app.send(cmd)
        return self._json(200, {"ok": True, "cmd": cmd})

    @staticmethod
    def _json(code, obj):
        return code, "application/json", json.dumps(obj).encode()

    def diag(self):
        """One line for the periodic heap log: IDF heap (WiFi, sockets and the
        push thread live there), WiFi, open connections, push counters."""
        try:
            import esp32
            h = esp32.idf_heap_info(esp32.HEAP_DATA)
            idf = "%d/%d" % (sum(x[1] for x in h), max(x[2] for x in h))
        except Exception:
            idf = "?"
        p = self.pusher
        return "net: idf free/largest %s wifi %s rssi %s drops %d conns %d push sent/failed/queued %s" % (
            idf, self.wifi.ip, self.wifi.rssi(), self.wifi.drops, len(self.conns),
            "%d/%d/%d" % (p.sent, p.failed, len(p.queue)) if p else "off")

    # -- main-loop hook --
    def poll(self, status, link_ok):
        now = time.ticks_ms()
        if self.pusher is not None:
            for alert in self.edges.update(status, link_ok, now):
                print("push:", alert[0])
                self.pusher.push(*alert)
        was_up = self.wifi.ip is not None
        if not self.wifi.poll():
            return
        if not was_up and self.listener is not None:
            # a restarted WiFi driver invalidates sockets; start clean
            for c in self.conns:
                c.close()
            self.conns = []
            try:
                self.listener.close()
            except OSError:
                pass
            self.listener = None
        if self.pusher is not None:
            if not was_up:
                self.pusher.resolve(now)   # the one blocking step, done at connect time
            self.pusher.poll(now)
        if self.listener is None:
            self._listen()
        self._accept(now)
        for c in self.conns[:]:
            self._service(c, now)

    def _listen(self):
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 80))
        s.listen(2)
        s.setblocking(False)
        self.listener = s

    def _accept(self, now):
        while len(self.conns) < MAX_CONNS:
            try:
                sock, _ = self.listener.accept()
            except OSError as e:
                if not _would_block(e):
                    print("accept error", e)
                return
            sock.setblocking(False)
            self.conns.append(_Conn(sock, now))

    def _drop(self, c):
        c.close()
        self.conns.remove(c)

    def _service(self, c, now):
        if time.ticks_diff(now, c.started) > CONN_TIMEOUT_MS:
            self._drop(c)
            return
        try:
            if c.out is None:
                self._read(c, now)
            if c.out is not None:
                self._write(c)
        except OSError as e:
            if not _would_block(e):
                self._drop(c)

    def _read(self, c, now):
        data = c.sock.recv(CHUNK)
        if not data:
            self._drop(c)
            return
        c.buf += data
        try:
            req = parse_request(c.buf)
        except ValueError:
            code, ctype, body = self._json(400, {"err": "bad request"})
        else:
            if req is None:
                if len(c.buf) <= MAX_REQUEST:
                    return          # wait for the rest
                code, ctype, body = self._json(413, {"err": "request too large"})
            else:
                code, ctype, body = self.handle(req[0], req[1], req[2], now)
        c.buf = b""
        if isinstance(body, str):   # a file to stream
            c.file = open(PAGE, "rb")
            c.out = memoryview(response_head(code, ctype, os.stat(PAGE)[6]))
        else:
            c.out = memoryview(response_head(code, ctype, len(body)) + body)

    def _write(self, c):
        if not c.out and c.file is not None:
            chunk = c.file.read(CHUNK)
            c.out = memoryview(chunk) if chunk else None
        if not c.out:
            self._drop(c)
            return
        sent = c.sock.send(c.out)
        c.out = c.out[sent:]
        if not c.out and c.file is None:
            self._drop(c)


def start(app):
    """Remote, or None when wifi_secrets.py hasn't been deployed. Call before
    hw.init(): WiFi and the push thread need IDF heap, and once LVGL fills the
    MicroPython heap, the heap grows by taking the largest free IDF block."""
    try:
        import wifi_secrets as cfg
    except ImportError:
        print("no wifi_secrets.py: phone access disabled (see wifi_secrets_example.py)")
        return None
    return Remote(app, cfg)
