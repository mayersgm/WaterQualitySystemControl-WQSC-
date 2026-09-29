# ESP32 HMI firmware build (lvgl_micropython)

The touchscreen HMI runs on a custom MicroPython firmware with LVGL compiled
in. The firmware is built **outside this repo** (it pulls in several GB of
submodules and toolchains). Only the UI `.py` files in this folder are tracked.

## Board
DIYmalls/Sunton **ESP32-2432S032C**: ESP32-D0WD-V3, **no PSRAM**, 4MB flash
(confirmed with `esptool.py chip_id` / `flash_id`). It has an ST7789 320x240
display on SPI and a GT911 capacitive touch controller on I2C. Pins are in
`hw.py`.

## Versions (first build, 2026-09-28)
| Component | Version / commit |
|---|---|
| lvgl_micropython | `d2d2646` |
| MicroPython | 1.27.0 (`78ff170`) |
| LVGL | 9.4.0 (`c016f72`) |
| ESP-IDF | 5.5.1 (`fcae3288`), installed by `make.py` into `~/.espressif` |

## Host prerequisites (macOS, Apple Silicon)
- Xcode with its license accepted: `sudo xcodebuild -license accept`
- `cmake` and `ninja`. Homebrew isn't installed on this Mac, so they came from
  PyPI: `python3 -m pip install cmake ninja`

## Local change to the vendored config
`~/esp/lvgl_micropython/lib/lv_conf.h`: `LV_FONT_MONTSERRAT_24` set to `1`
(stock: 12/14/16 only). It's used for the large readouts on the calibration
screen. Re-apply this after any fresh clone.

## Build
```
git clone --depth 1 https://github.com/lvgl-micropython/lvgl_micropython.git ~/esp/lvgl_micropython
cd ~/esp/lvgl_micropython
# (apply the lv_conf.h font change above)
python3 make.py esp32 BOARD=ESP32_GENERIC DISPLAY=st7789 INDEV=gt911 --flash-size=4
```
- Use plain `ESP32_GENERIC`, **not** the `SPIRAM` variant that
  `display_configs/CYD-2432S032C.toml` assumes, because this board has no
  PSRAM.
- The TOML's frozen display init isn't used either. `hw.py` initializes the
  display and touch at runtime, so pin, rotation and color tweaks only need an
  `mpremote cp`, not a rebuild.

Result: the app partition is auto-sized to 0x2c5000, so it's essentially
full. That leaves about 1.2MB of filesystem for the UI files. WiFi and
`network` are already included, so Milestone 2 needs no rebuild.

## Flash
This erases the whole ESP32, including any `.py` files, so redeploy the UI
afterwards:
```
esptool.py --chip esp32 -p /dev/cu.usbserial-20144212 -b 460800 \
  --before default_reset --after hard_reset write_flash --flash_mode dio \
  --flash_size 4MB --flash_freq 40m --erase-all \
  0x0 ~/esp/lvgl_micropython/build/lvgl_micropy_ESP32_GENERIC-4.bin
```

## Known quirks
- **Never soft-reset (Ctrl-D) and then re-init the display.** The SPI bus
  driver keeps a C pointer to its Python object across a soft reset, so the
  next `machine.SPI.Bus()` dereferences freed memory and panics
  (`InstrFetchProhibited` in `machine_hw_spi_bus_make_new`). Always hard-reset
  (`mpremote ... reset`) before running `hwtest` or `main`. `main.py`
  hard-resets itself after an unhandled error for the same reason.
- **Touch panel is mounted 180° from the display's native orientation.**
  `hw.py` passes `startup_rotation=_180` to the GT911 driver and creates it
  *before* rotating the display. Verify with `import hwtest;
  hwtest.touch_map()`; each logged `lvgl` point should land within about
  10 px of its target.
- **Display:** colors are correct with `BYTE_ORDER_BGR`, and rotation `_90`
  gives landscape. Both were verified with `hwtest.run()`.

## Deploy the UI
```
mpremote connect /dev/cu.usbserial-20144212 cp ESP-S32CI/*.py :
mpremote connect /dev/cu.usbserial-20144212 reset
```
Disconnect VS Code's MicroPico from the port first, since it holds it.
