// WQCS bench-test UART bridge.
//
// Not the Phase 3 touchscreen HMI -- just enough to drive/observe the
// Phase 2 Pico bench test (see Phase2_BenchTest_Sequence.md). Forwards
// whatever you type into the Arduino Serial Monitor out over UART1 to the
// Pico, and prints back whatever the Pico sends. Board: DIYmalls/Sunton
// ESP32-2432S032C (plain ESP32-WROOM-32, select a generic "ESP32 Dev
// Module" board profile -- not an S3 target).

#include <HardwareSerial.h>

HardwareSerial PicoLink(1);  // UART1

const int PICO_TX_PIN = 22;  // ESP32 GPIO22 -> Pico GP1 (RX)
const int PICO_RX_PIN = 35;  // ESP32 GPIO35 <- Pico GP0 (TX); input-only, fine for RX
const long BAUD = 115200;

String inputLine;
String statusLine;

void setup() {
  Serial.begin(115200);
  PicoLink.begin(BAUD, SERIAL_8N1, PICO_RX_PIN, PICO_TX_PIN);
  Serial.println("WQCS bench bridge ready. Type a command and press Enter:");
  Serial.println("  START | STOP | STERILIZE | EMPTY | RESET | ACK");
  Serial.println("  TARE:BOILER | CAL:BOILER:<grams>  (also COLLECTOR / RESERVOIR)");
}

void loop() {
  // Typed command -> Pico
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      if (inputLine.length() > 0) {
        PicoLink.print(inputLine);
        PicoLink.print('\n');
        Serial.print("-> ");
        Serial.println(inputLine);
        inputLine = "";
      }
    } else {
      inputLine += c;
    }
  }

  // Status JSON <- Pico
  while (PicoLink.available()) {
    char c = PicoLink.read();
    if (c == '\n') {
      Serial.print("<- ");
      Serial.println(statusLine);
      statusLine = "";
    } else if (c != '\r') {
      statusLine += c;
    }
  }
}
