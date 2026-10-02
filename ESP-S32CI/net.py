"""Milestone 2: iPhone monitor + control over home WiFi.

A small HTTP server polled from the HMI main loop (App.step), so networking
never blocks rendering or the Pico link: every socket is non-blocking, and
each poll() does a bounded amount of work.

  GET  /        the mobile page (web_ui.html, streamed from flash)
  GET  /status  {"link", "age_ms", "status", "limits", "errors", "rssi"}
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
from notify import AlertEdges, NtfyPusher

ALLOWED = ("START", "STOP", "STERILIZE", "EMPTY", "RESET", "ACK")
PAGE = "web_ui.html"
HOSTNAME = "wqcs"                 # http://wqcs.local/ via the built-in mDNS responder

RECONNECT_MS = 30000              # retry joining WiFi this often while disconnected
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
    """Joins the home network and keeps retrying; never blocks after start."""

    def __init__(self, ssid, password):
        self.ssid, self.password = ssid, password
        try:
            network.hostname(HOSTNAME)
        except Exception:  # older firmware: name falls back to the default
            pass
        self.wlan = network.WLAN(network.STA_IF)
        self.wlan.active(True)
        self.ip = None
        self._last_try = None
        self._connect()

    def _connect(self):
        self._last_try = time.ticks_ms()
        try:
            self.wlan.disconnect()
        except OSError:
            pass
        try:
            self.wlan.connect(self.ssid, self.password)
        except OSError as e:
            print("wifi connect error", e)

    def poll(self):
        """Returns True while connected. Logs the IP once per connection."""
        if self.wlan.isconnected():
            if self.ip is None:
                self.ip = self.wlan.ifconfig()[0]
                print("wifi connected: http://%s/  (http://%s.local/)" % (self.ip, HOSTNAME))
            return True
        if self.ip is not None:
            print("wifi lost")
            self.ip = None
        if time.ticks_diff(time.ticks_ms(), self._last_try) > RECONNECT_MS:
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
                "rssi": self.wifi.rssi() if self.wifi else None}

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
        return "net: idf free/largest %s wifi %s rssi %s conns %d push sent/failed/queued %s" % (
            idf, self.wifi.ip, self.wifi.rssi(), len(self.conns),
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
