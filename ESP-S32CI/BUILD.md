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

## Local changes to the vendored tree
Re-apply both after any fresh clone.
- `~/esp/lvgl_micropython/lib/lv_conf.h`: `LV_FONT_MONTSERRAT_24` set to `1`
  (stock: 12/14/16 only). It's used for the large readouts on the calibration
  screen.
- `lib/micropython/ports/esp32/boards/ESP32_GENERIC/mpconfigboard.h`: append
  `#define MICROPY_PY_BLUETOOTH (0)`. It goes with `CONFIG_BT_ENABLED=n` on the
  build line below.
- `lib/micropython/ports/esp32/gccollect.c`, `gc_get_max_new_split()`: return
  at most `free - MP_IDF_HEAP_RESERVE` (24 KB), not the whole largest free IDF
  block. When LVGL needs room, the MicroPython heap grows by that amount. Stock
  firmware handed it everything, leaving ~1.6 KB for WiFi and the touch
  driver's I2C, which then aborted (`i2c_cmd_log_alloc_error`). Verified
  2026-10-03: with the GC heap exhausted, the IDF heap stays at 24.6 KB free
  and WiFi still works.

Only the app partition changes between these rebuilds (same partition table),
so flash just `micropython.bin` at `0x10000`. No `--erase-all`, so the board's
files (`wifi_secrets.py`, logs) survive:
```
esptool.py --chip esp32 -p /dev/cu.usbserial-20144212 -b 460800 write_flash \
  0x10000 ~/esp/lvgl_micropython/lib/micropython/ports/esp32/build-ESP32_GENERIC/micropython.bin
```
Compare `build/partitions.csv` with the previous build first. If it changed,
do the full erase-and-flash below and redeploy every file.

## Why Bluetooth is off (rebuilt 2026-10-01 for Milestone 2)
With Bluetooth compiled in, WiFi and the HMI didn't fit in RAM together, and
`wlan.active(True)` failed with "WiFi Out of Memory". The MicroPython heap
starts at 56 KB. When LVGL fills it, it grows by taking the **largest free IDF
heap block** (another ~56 KB), and the display driver already holds ~46 KB of
IDF heap (two 15 KB DMA frame buffers plus SPI). Turning Bluetooth off raised
the IDF heap at boot from 137 KB to 192 KB. Measured with WiFi, the push
thread, a listening socket and every screen loaded: ~41 KB of IDF heap free,
and an unchanged 112 KB MicroPython heap. Six static WiFi RX buffers instead
of ten save another ~6 KB. Phone access needs no BLE, since WiFi was chosen
because iOS Safari can't use Web Bluetooth.

**Order matters:** `net.start()` runs before `hw.init()` in `main.py`, so WiFi
and the push thread get their IDF memory before the MicroPython heap grows.

The previous image, with Bluetooth, is kept at
`~/esp/firmware_backup/lvgl_micropy_ESP32_GENERIC-4_with_bt_2026-09-28.bin`.

## Build
```
git clone --depth 1 https://github.com/lvgl-micropython/lvgl_micropython.git ~/esp/lvgl_micropython
cd ~/esp/lvgl_micropython
# (apply the lv_conf.h font change above)
python3 make.py esp32 BOARD=ESP32_GENERIC DISPLAY=st7789 INDEV=gt911 --flash-size=4 \
  CONFIG_BT_ENABLED=n CONFIG_ESP_WIFI_STATIC_RX_BUFFER_NUM=6
```
(`CONFIG_*` arguments are appended to the generated `sdkconfig.board`, the
last defaults file applied.)
- Use plain `ESP32_GENERIC`, **not** the `SPIRAM` variant that
  `display_configs/CYD-2432S032C.toml` assumes, because this board has no
  PSRAM.
- The TOML's frozen display init isn't used either. `hw.py` initializes the
  display and touch at runtime, so pin, rotation and color tweaks only need an
  `mpremote cp`, not a rebuild.

Result without Bluetooth: a 0x291000 app partition (auto-sized, essentially
full), leaving about 1.4MB of filesystem for the UI files.

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
python3 tools/esp_deploy.py              # all *.py + web_ui.html, then reset
python3 tools/esp_deploy.py net.py       # just one file
```
Disconnect VS Code's MicroPico from the port first, since it holds it. If
MicroPico connects to the ESP32 it interrupts `main.py` and the screen
freezes; that happened on 2026-10-01.

`wifi_secrets.py` (gitignored, copied from `wifi_secrets_example.py`) is
deployed with everything else once it exists locally. Without it, the HMI runs
with phone access off.
