# Template for wifi_secrets.py -- copy it, fill it in, deploy it to the ESP32:
#   cp ESP-S32CI/wifi_secrets_example.py ESP-S32CI/wifi_secrets.py
#   python3 tools/esp_deploy.py wifi_secrets.py
# wifi_secrets.py is gitignored: never commit real values. Without it on the
# board, the HMI runs exactly as before with phone access off.

WIFI_SSID = "your-network"
WIFI_PASSWORD = "your-password"   # 2.4 GHz network: the ESP32 has no 5 GHz radio

# Required for every phone command (START/STOP/STERILIZE/EMPTY/RESET/ACK).
# 5 wrong tries lock commands out for a minute.
CMD_PIN = "0000"

# Push alerts via ntfy (free; install the ntfy app on the iPhone and subscribe
# to this topic). Anyone who knows the topic can read the alerts, so use a long
# random name, e.g.  python3 -c "import secrets; print('wqcs-' + secrets.token_hex(8))"
# Set NTFY_TOPIC = None to turn push alerts off.
NTFY_TOPIC = "wqcs-change-me"
NTFY_SERVER = "ntfy.sh"
