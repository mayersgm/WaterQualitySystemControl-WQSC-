"""Host-side tests for ESP-S32CI/net.py (phone API) and notify.py (push
alerts), with fake network + time. Run:  python3 -m unittest discover tests"""
import json
import os
import sys
import types
import unittest

# appended, not inserted: the Pico tests import Pico/main.py, and ESP-S32CI
# has a main.py too
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "ESP-S32CI"))


class FakeWLAN:
    def __init__(self, _iface):
        pass

    def active(self, on=None):
        return True

    def connect(self, ssid, pw):
        pass

    def disconnect(self):
        pass

    def isconnected(self):
        return False

    def status(self, key=None):
        return -55


sys.modules.setdefault("network", types.SimpleNamespace(
    WLAN=FakeWLAN, STA_IF=0, hostname=lambda name: None))
import net  # noqa: E402
import notify  # noqa: E402


class FakeTime:
    now = 0

    @classmethod
    def ticks_ms(cls):
        return cls.now

    @staticmethod
    def ticks_add(a, b):
        return a + b

    @staticmethod
    def ticks_diff(a, b):
        return a - b


net.time = notify.time = FakeTime


class FakeLink:
    def __init__(self):
        self.last_status = {"state": "STOPPED", "cmd": "STOP"}
        self.link_errors = 0


class FakeApp:
    def __init__(self):
        self.link = FakeLink()
        self.limits = {"boiler_full": 600}
        self.last_rx = 0
        self.link_ok = True
        self.sent = []
        self.acked = 0

    def send(self, cmd):
        self.sent.append(cmd)

    def ack(self):
        self.acked += 1


CFG = types.SimpleNamespace(WIFI_SSID="x", WIFI_PASSWORD="y", CMD_PIN="2468", NTFY_TOPIC=None)


class RequestParsingTest(unittest.TestCase):
    def test_incomplete_headers_wait(self):
        self.assertIsNone(net.parse_request(b"GET /status HTTP/1.1\r\nHost: a\r\n"))

    def test_get_strips_query(self):
        self.assertEqual(net.parse_request(b"GET /status?t=1 HTTP/1.1\r\nHost: a\r\n\r\n"),
                         ("GET", "/status", b""))

    def test_post_waits_for_whole_body(self):
        head = b"POST /cmd HTTP/1.1\r\nContent-Length: 10\r\n\r\n"
        self.assertIsNone(net.parse_request(head + b"12345"))
        self.assertEqual(net.parse_request(head + b"1234567890"), ("POST", "/cmd", b"1234567890"))

    def test_malformed_request_line(self):
        with self.assertRaises(ValueError):
            net.parse_request(b"garbage\r\n\r\n")

    def test_response_head(self):
        head = net.response_head(403, "application/json", 12).decode()
        self.assertTrue(head.startswith("HTTP/1.0 403 Forbidden\r\n"))
        self.assertIn("Content-Length: 12\r\n", head)
        self.assertTrue(head.endswith("\r\n\r\n"))


class RemoteTest(unittest.TestCase):
    def setUp(self):
        FakeTime.now = 1000
        self.app = FakeApp()
        self.r = net.Remote(self.app, CFG)

    def cmd(self, cmd, pin="2468"):
        code, _, body = self.r.handle("POST", "/cmd", json.dumps({"cmd": cmd, "pin": pin}).encode(),
                                      FakeTime.now)
        return code, json.loads(body)

    def test_page_and_status(self):
        self.assertEqual(self.r.handle("GET", "/", b"", 0)[2], net.PAGE)
        code, ctype, body = self.r.handle("GET", "/status", b"", 1500)
        snap = json.loads(body)
        self.assertEqual((code, ctype), (200, "application/json"))
        self.assertEqual(snap["status"]["state"], "STOPPED")
        self.assertEqual(snap["limits"], {"boiler_full": 600})
        self.assertEqual(snap["age_ms"], 1500)
        self.assertTrue(snap["link"])

    def test_unknown_path_and_wrong_method(self):
        self.assertEqual(self.r.handle("GET", "/secret", b"", 0)[0], 404)
        self.assertEqual(self.r.handle("GET", "/cmd", b"", 0)[0], 405)

    def test_allowed_command_relayed(self):
        self.assertEqual(self.cmd("start")[0], 200)
        self.assertEqual(self.app.sent, ["START"])

    def test_ack_goes_through_app_ack(self):
        # app.ack() also silences the touchscreen alarm
        self.assertEqual(self.cmd("ACK")[0], 200)
        self.assertEqual((self.app.acked, self.app.sent), (1, []))

    def test_wrong_pin_rejected(self):
        self.assertEqual(self.cmd("START", pin="0000")[0], 403)
        self.assertEqual(self.app.sent, [])

    def test_calibration_and_limits_not_allowed_remotely(self):
        for c in ("TARE:BOILER", "CAL:BOILER:1000", "SET:BOILER_FULL:9000", "RESET_LIMITS"):
            self.assertEqual(self.cmd(c)[0], 400, c)
        self.assertEqual(self.app.sent, [])

    def test_malformed_body(self):
        self.assertEqual(self.r.handle("POST", "/cmd", b"not json", 0)[0], 400)
        self.assertEqual(self.r.handle("POST", "/cmd", b'{"cmd":"START"}', 0)[0], 400)

    def test_no_link_refuses(self):
        self.app.link_ok = False
        self.assertEqual(self.cmd("STOP")[0], 503)
        self.assertEqual(self.app.sent, [])

    def test_test_push_needs_pin_and_stays_local(self):
        self.r.pusher = notify.NtfyPusher("ntfy.sh", "t")
        self.assertEqual(self.cmd("TEST_PUSH", pin="0000")[0], 403)
        self.app.link_ok = False                     # works even with the Pico down
        self.assertEqual(self.cmd("TEST_PUSH")[0], 200)
        self.assertEqual([a[0] for a in self.r.pusher.queue], ["WQCS test alert"])
        self.assertEqual((self.app.sent, self.app.acked), ([], 0))

    def test_test_push_without_topic(self):
        self.assertEqual(self.cmd("TEST_PUSH")[0], 400)

    def test_status_reports_uptime_and_push_counters(self):
        self.r.pusher = notify.NtfyPusher("ntfy.sh", "t")
        snap = json.loads(self.r.handle("GET", "/status", b"", 7200500)[2])
        self.assertEqual(snap["uptime_s"], 7200)
        self.assertEqual(snap["push"], {"sent": 0, "failed": 0, "queued": 0})

    def test_lockout_after_repeated_wrong_pins(self):
        for _ in range(net.BAD_PIN_LIMIT):
            self.assertEqual(self.cmd("START", pin="1111")[0], 403)
        # even the right PIN is refused during the lockout
        self.assertEqual(self.cmd("START")[0], 429)
        FakeTime.now += net.BAD_PIN_LOCKOUT_MS + 1
        self.assertEqual(self.cmd("START")[0], 200)
        self.assertEqual(self.app.sent, ["START"])

    def test_good_pin_resets_bad_count(self):
        for _ in range(net.BAD_PIN_LIMIT - 1):
            self.cmd("START", pin="1111")
        self.cmd("STOP")
        self.assertEqual(self.cmd("START", pin="1111")[0], 403)   # not locked out


def st(state="RUN", faults=(), tds2=False, transfer=0, tds2_ppm=0):
    return {"state": state, "fault": {k: True for k in faults},
            "alert": {"tds2": tds2}, "tds2_ppm": tds2_ppm, "valves": {"transfer": transfer}}


class AlertEdgesTest(unittest.TestCase):
    def setUp(self):
        FakeTime.now = 0
        self.e = notify.AlertEdges()

    def feed(self, status, link=True, dt=1000):
        FakeTime.now += dt
        return self.e.update(status, link, FakeTime.now)

    def titles(self, alerts):
        return [a[0] for a in alerts]

    def test_new_fault_alerts_once(self):
        out = self.feed(st("FAULT", ["overflow"]))
        self.assertEqual(self.titles(out), ["WQCS FAULT: Boiler overflow"])
        self.assertEqual(out[0][2], notify.URGENT)
        self.assertEqual(self.feed(st("FAULT", ["overflow"])), [])

    def test_ack_and_relatch_within_cooldown_is_quiet(self):
        self.feed(st("FAULT", ["overflow"]))
        self.feed(st("RUN"))
        self.assertEqual(self.feed(st("FAULT", ["overflow"])), [])
        FakeTime.now += notify.COOLDOWN_MS
        self.feed(st("RUN"))
        self.assertEqual(len(self.feed(st("FAULT", ["overflow"]))), 1)

    def test_second_fault_alerts_separately(self):
        self.feed(st("FAULT", ["overflow"]))
        out = self.feed(st("FAULT", ["overflow", "transfer_leak"]))
        self.assertEqual(self.titles(out), ["WQCS FAULT: Transfer leak"])

    def test_tds2_rising_edge(self):
        self.assertEqual(self.feed(st()), [])
        out = self.feed(st(tds2=True, tds2_ppm=63))
        self.assertIn("63 ppm", out[0][1])
        self.assertEqual(self.feed(st(tds2=True)), [])

    def test_standby_transferring_never_alerts(self):
        for _ in range(10):
            self.assertEqual(self.feed(st("STANDBY", transfer=1)), [])

    def test_standby_no_room_alerts_after_confirm(self):
        outs = [self.feed(st("STANDBY", transfer=0)) for _ in range(notify.STANDBY_CONFIRM)]
        self.assertEqual([len(o) for o in outs], [0] * (notify.STANDBY_CONFIRM - 1) + [1])
        self.assertEqual(self.feed(st("STANDBY", transfer=0)), [])

    def test_brief_standby_before_transfer_opens_is_quiet(self):
        self.feed(st("STANDBY", transfer=0))
        self.assertEqual(self.feed(st("STANDBY", transfer=1)), [])
        self.assertEqual(self.feed(st("STANDBY", transfer=0)), [])

    def test_link_loss_and_restore(self):
        self.assertEqual(self.feed(None, link=False), [])     # booting: never had a link
        self.feed(st())
        out = self.feed(None, link=False)
        self.assertEqual(self.titles(out), ["WQCS: no link to Pico"])
        self.assertEqual(self.feed(None, link=False), [])
        self.assertEqual(self.titles(self.feed(st())), ["WQCS link restored"])


class NtfyRequestTest(unittest.TestCase):
    def test_request_format(self):
        p = notify.NtfyPusher("ntfy.sh", "wqcs-abc")
        req = p.request("WQCS FAULT: Boiler overflow", "Check it.", 5, "rotating_light")
        head, body = req.split(b"\r\n\r\n")
        self.assertTrue(head.startswith(b"POST /wqcs-abc HTTP/1.0\r\nHost: ntfy.sh\r\n"))
        self.assertIn(b"Priority: 5", head)
        self.assertIn(b"Content-Length: 9", head)
        self.assertEqual(body, b"Check it.")

    def test_queue_drops_oldest(self):
        p = notify.NtfyPusher("ntfy.sh", "t")
        for i in range(notify.QUEUE_MAX + 2):
            p.push("t%d" % i, "m")
        self.assertEqual(len(p.queue), notify.QUEUE_MAX)
        self.assertEqual(p.queue[0][0], "t2")


if __name__ == "__main__":
    unittest.main()


class FakeSock:
    """Non-blocking socket double: connect 'in progress', then writable,
    then a canned reply. script = list of replies per attempt (None = refuse)."""
    instances = []

    def __init__(self, reply):
        self.reply, self.sent, self.closed = reply, b"", False
        FakeSock.instances.append(self)

    def setblocking(self, flag):
        pass

    def connect(self, addr):
        if self.reply is None:
            raise OSError(113)            # EHOSTUNREACH
        raise OSError(119)                # EINPROGRESS, like MicroPython

    def send(self, data):
        self.sent += bytes(data)
        return len(data)

    def recv(self, n):
        r, self.reply = self.reply[:n], self.reply[n:]
        return r

    def close(self):
        self.closed = True


class FakeSelect:
    POLLIN, POLLOUT, POLLERR, POLLHUP = 1, 4, 8, 16

    class _Poll:
        def register(self, sock, ev):
            self.ev = ev

        def poll(self, timeout):
            return [(None, self.ev)]

    poll = _Poll


class PusherTest(unittest.TestCase):
    def setUp(self):
        FakeTime.now = 0
        FakeSock.instances = []
        self.replies = []
        self.lookups = 0
        test = self

        def getaddrinfo(host, port):
            test.lookups += 1
            if test.dns_fails:
                raise OSError(-2)
            return [(0, 0, 0, "", ("1.2.3.4", port))]

        self.dns_fails = False
        notify.socket = types.SimpleNamespace(
            socket=lambda: FakeSock(self.replies.pop(0)), getaddrinfo=getaddrinfo)
        notify.select = FakeSelect
        self.p = notify.NtfyPusher("ntfy.sh", "t")

    def run_for(self, ms, step=20):
        for _ in range(ms // step):
            FakeTime.now += step
            self.p.poll(FakeTime.now)

    def test_send_success(self):
        self.replies = [b"HTTP/1.1 200 OK\r\n\r\n{}"]
        self.p.push("hello", "body")
        self.run_for(200)
        self.assertEqual((self.p.sent, self.p.failed, self.p.queue), (1, 0, []))
        self.assertTrue(FakeSock.instances[0].sent.startswith(b"POST /t HTTP/1.0"))
        self.assertTrue(FakeSock.instances[0].closed)

    def test_retries_then_drops(self):
        self.replies = [None, b"HTTP/1.1 500 Oops\r\n\r\n", None]
        self.p.push("hello", "body")
        self.run_for(notify.RETRY_WAIT_MS * 3, step=100)
        self.assertEqual((self.p.sent, self.p.failed, self.p.queue), (0, 1, []))
        self.assertEqual(len(FakeSock.instances), notify.RETRIES)

    def test_failure_then_success_on_retry(self):
        self.replies = [None, b"HTTP/1.1 200 OK\r\n\r\n"]
        self.p.push("hello", "body")
        self.run_for(notify.RETRY_WAIT_MS * 2, step=100)
        self.assertEqual((self.p.sent, self.p.failed), (1, 0))

    def test_dns_failure_is_rate_limited(self):
        self.dns_fails = True
        self.p.push("hello", "body")
        self.run_for(60000, step=100)
        self.assertEqual(self.lookups, 1)          # not retried every pass
        self.dns_fails = False
        self.replies = [b"HTTP/1.1 200 OK\r\n\r\n"]
        FakeTime.now += notify.DNS_RETRY_MS
        self.run_for(200)
        self.assertEqual((self.lookups, self.p.sent), (2, 1))
