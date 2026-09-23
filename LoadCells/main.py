import utime
from scale import Scale
from ble_uart import BLEUart

STREAM_INTERVAL_MS = 1000    # send reading every 1 second

# Pin assignments per Phase0_Design.md
SCALES = {
    "BOILER":    {"dout": 2, "sck": 3, "capacity_g": 3785},   # 1 gal
    "COLLECTOR": {"dout": 4, "sck": 5, "capacity_g": 7570},   # 2 gal
    "RESERVOIR": {"dout": 6, "sck": 7, "capacity_g": 34065},  # 9 gal
}


def pct(grams: float, capacity_g: float) -> float:
    return max(0.0, min(100.0, grams / capacity_g * 100))


def main():
    scales = {
        name: Scale(name.lower(), cfg["dout"], cfg["sck"])
        for name, cfg in SCALES.items()
    }
    ble = BLEUart(name="WQCS-Scales")

    streaming = True
    last_send = utime.ticks_ms()

    def on_command(cmd: str):
        nonlocal streaming
        cmd = cmd.upper()
        parts = cmd.split(":")
        verb = parts[0]

        if verb == "TARE" and len(parts) == 2 and parts[1] in scales:
            name = parts[1]
            ble.send(f"Taring {name}...\n")
            scales[name].tare()
            ble.send(f"{name} tare complete.\n")

        elif verb == "CAL" and len(parts) == 3 and parts[1] in scales:
            name = parts[1]
            try:
                grams = float(parts[2])
                ble.send(f"Calibrating {name} with {grams}g...\n")
                scales[name].calibrate(grams)
                ble.send(f"{name} cal done. upg={scales[name].units_per_gram:.4f}\n")
            except (ValueError, RuntimeError) as e:
                ble.send(f"ERR:{e}\n")

        elif verb == "READ" and len(parts) == 2 and parts[1] in scales:
            _send_reading(parts[1], scales[parts[1]], ble)

        elif cmd == "READ:ALL":
            for name in scales:
                _send_reading(name, scales[name], ble)

        elif cmd == "STREAM":
            streaming = not streaming
            ble.send(f"Streaming {'ON' if streaming else 'OFF'}\n")

        elif cmd == "STATUS":
            for name, s in scales.items():
                cal = "YES" if s.is_calibrated() else "NO"
                ble.send(f"{name}: cal={cal} capacity={SCALES[name]['capacity_g']}g\n")

        else:
            ble.send("Commands: TARE:<NAME> | CAL:<NAME>:<grams> | READ:<NAME> | READ:ALL | STREAM | STATUS\n")
            ble.send(f"Names: {', '.join(scales)}\n")

    ble.on_rx(on_command)

    uncalibrated = [name for name, s in scales.items() if not s.is_calibrated()]
    if uncalibrated:
        print(f"WARNING: Not calibrated: {uncalibrated}. Connect via BLE, TARE:<NAME> then CAL:<NAME>:<grams>.")

    while True:
        now = utime.ticks_ms()
        if streaming and ble.connected and utime.ticks_diff(now, last_send) >= STREAM_INTERVAL_MS:
            for name in scales:
                _send_reading(name, scales[name], ble)
            last_send = now
        utime.sleep_ms(50)


def _send_reading(name: str, scale: Scale, ble: BLEUart):
    try:
        g = scale.read_grams()
        p = pct(g, SCALES[name]["capacity_g"])
        msg = f"{name}: {g:.1f}g  {p:.1f}%\n"
        ble.send(msg)
        print(msg, end="")
    except Exception as e:
        ble.send(f"{name} read error: {e}\n")


main()
