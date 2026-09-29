"""Board bring-up for the ESP32-2432S032C (ST7789 SPI display + GT911 I2C touch)
on lvgl_micropython firmware. The only module that knows this board's wiring.

Pin values match lvgl_micropython's display_configs/CYD-2432S032C.toml and
rzeldent/platformio-espressif32-sunton esp32-2432S032C.json. GPIO22/35 (Pico
UART, see pico_link.py) are not used by anything here.
"""
import lvgl as lv
import machine
import lcd_bus
import i2c
import st7789
import gt911
import task_handler

WIDTH = 320   # landscape, after rotation
HEIGHT = 240

# Runtime-tunable in case colors/touch come out wrong on first boot.
ROTATION = lv.DISPLAY_ROTATION._90
# The GT911 is mounted 180 deg from the panel's native orientation (measured
# 2026-09-28 with hwtest.touch_map(): every touch landed diagonally opposite).
TOUCH_ROTATION = lv.DISPLAY_ROTATION._180
COLOR_BYTE_ORDER = st7789.BYTE_ORDER_BGR
BACKLIGHT_PCT = 100

_display = None
_indev = None


def init():
    """Bring up display + touch + LVGL task handler. Returns (display, indev)."""
    global _display, _indev
    if _display is not None:
        return _display, _indev

    spi_bus = machine.SPI.Bus(host=1, mosi=13, miso=12, sck=14)
    display_bus = lcd_bus.SPIBus(spi_bus=spi_bus, freq=24000000, dc=2, cs=15)

    _display = st7789.ST7789(
        data_bus=display_bus,
        display_width=240,   # panel-native portrait; rotated below
        display_height=320,
        backlight_pin=27,
        backlight_on_state=st7789.STATE_PWM,
        color_space=lv.COLOR_FORMAT.RGB565,
        color_byte_order=COLOR_BYTE_ORDER,
        rgb565_byte_swap=True,
    )
    _display.set_power(True)
    _display.init()

    i2c_bus = i2c.I2C.Bus(host=0, scl=32, sda=33, freq=400000)
    touch_dev = i2c.I2C.Device(bus=i2c_bus, dev_id=gt911.I2C_ADDR, reg_bits=gt911.BITS)
    # Must be created BEFORE the display is rotated: the driver captures the
    # display size once at creation and flips raw points against it, so it
    # needs the panel's native 240x320. LVGL then applies ROTATION itself.
    # INT=21 / RST=25 give the GT911 a clean hardware reset at boot.
    _indev = gt911.GT911(touch_dev, reset_pin=25, interrupt_pin=21,
                         startup_rotation=TOUCH_ROTATION)

    _display.set_rotation(ROTATION)
    _display.set_backlight(BACKLIGHT_PCT)

    # Runs lv.task_handler() from a hardware timer every ~33 ms, so the main
    # loop only has to poll the Pico link and update widgets.
    task_handler.TaskHandler()
    return _display, _indev
