import bluetooth
import utime
from micropython import const

_IRQ_CENTRAL_CONNECT    = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_IRQ_GATTS_WRITE        = const(3)

_FLAG_WRITE_NO_RESP = const(0x0004)
_FLAG_WRITE        = const(0x0008)
_FLAG_NOTIFY       = const(0x0010)

# Nordic UART Service (NUS)
_NUS_UUID  = bluetooth.UUID("6E400001-B5A3-F393-E0A9-E50E24DCCA9E")
_NUS_RX    = (bluetooth.UUID("6E400002-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_WRITE | _FLAG_WRITE_NO_RESP)
_NUS_TX    = (bluetooth.UUID("6E400003-B5A3-F393-E0A9-E50E24DCCA9E"), _FLAG_NOTIFY)
_NUS_SERVICE = (_NUS_UUID, (_NUS_TX, _NUS_RX))

ADV_TYPE_FLAGS        = const(0x01)
ADV_TYPE_NAME         = const(0x09)
ADV_TYPE_UUID128_COMP = const(0x07)


def _adv_payload(name: str) -> bytes:
    payload = bytearray()

    # Flags: LE General Discoverable, BR/EDR not supported
    payload += bytes([2, ADV_TYPE_FLAGS, 0x06])

    # Complete local name
    enc = name.encode()
    payload += bytes([len(enc) + 1, ADV_TYPE_NAME]) + enc

    return bytes(payload)


class BLEUart:
    def __init__(self, name="PicoScale"):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        self._ble.irq(self._irq)

        ((self._tx_handle, self._rx_handle),) = self._ble.gatts_register_services((_NUS_SERVICE,))

        self._connected = False
        self._conn_handle = None
        self._rx_callback = None

        self._payload = _adv_payload(name)
        self._advertise()
        print(f"BLE advertising as '{name}'")

    def _irq(self, event, data):
        if event == _IRQ_CENTRAL_CONNECT:
            self._conn_handle, _, _ = data
            self._connected = True
            print("BLE connected")

        elif event == _IRQ_CENTRAL_DISCONNECT:
            self._conn_handle = None
            self._connected = False
            print("BLE disconnected — re-advertising")
            self._advertise()

        elif event == _IRQ_GATTS_WRITE:
            _, value_handle = data
            if value_handle == self._rx_handle and self._rx_callback:
                raw = self._ble.gatts_read(self._rx_handle)
                self._rx_callback(raw.decode().strip())

    def _advertise(self):
        self._ble.gap_advertise(100_000, adv_data=self._payload)

    def on_rx(self, callback):
        """Register a callback(msg: str) for incoming commands."""
        self._rx_callback = callback

    def send(self, text: str):
        """Send text, chunked to 20-byte BLE MTU limit."""
        if not self._connected:
            return
        data = text.encode()
        for offset in range(0, len(data), 20):
            try:
                self._ble.gatts_notify(self._conn_handle, self._tx_handle, data[offset:offset + 20])
                utime.sleep_ms(30)   # give central time to process each chunk
            except OSError:
                break

    @property
    def connected(self) -> bool:
        return self._connected
