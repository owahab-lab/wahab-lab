#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MCP4725.h>

TwoWire I2C_Bus1 = TwoWire(0);
TwoWire I2C_Bus2 = TwoWire(1);

Adafruit_MCP4725 dac1, dac2, dac3, dac4;

void set_dac(int index, float voltage) {
  uint16_t val = (uint16_t)constrain((voltage / 5.0f) * 4095, 0, 4095);
  switch (index) {
    case 1: dac1.setVoltage(val, false); break;
    case 2: dac2.setVoltage(val, false); break;
    case 3: dac3.setVoltage(val, false); break;
    case 4: dac4.setVoltage(val, false); break;
  }
}

void set_all(float voltage) {
  for (int i = 1; i <= 4; i++) set_dac(i, voltage);
}

static char received_chars[64];
bool new_data = false;

void receive_serial() {
  static bool receiving = false;
  static byte char_index = 0;
  char c = Serial.read();
  if (receiving) {
    if (c != '>') { received_chars[char_index++] = c; }
    else { received_chars[char_index] = '\0'; char_index = 0; receiving = false; new_data = true; }
  } else if (c == '<') { receiving = true; }
}

void print_status() {
  Serial.println(F("\n┌───────┬───────────┐"));
  Serial.println(F("│  DAC  │  voltage  │"));
  Serial.println(F("├───────┼───────────┤"));
  Adafruit_MCP4725* dacs[4] = { &dac1, &dac2, &dac3, &dac4 };
  for (int i = 0; i < 4; i++) {
    // MCP4725 doesn't have a readback — track setpoints locally
  }
}

float setpoints[4] = {0, 0, 0, 0};

void print_status_tracked() {
  Serial.println(F("\n┌───────┬───────────┐"));
  Serial.println(F("│  DAC  │  voltage  │"));
  Serial.println(F("├───────┼───────────┤"));
  for (int i = 0; i < 4; i++)
    Serial.printf("│  dac%d │   %5.3f V │\n", i + 1, setpoints[i]);
  Serial.println(F("└───────┴───────────┘"));
}

void set_dac_tracked(int index, float voltage) {
  voltage = constrain(voltage, 0.0f, 5.0f);
  setpoints[index - 1] = voltage;
  set_dac(index, voltage);
}

void set_all_tracked(float voltage) {
  for (int i = 1; i <= 4; i++) set_dac_tracked(i, voltage);
}

void setup() {
  Serial.begin(115200);
  while (!Serial);

  I2C_Bus1.begin(19, 20, 100000);
  I2C_Bus2.begin(2, 4, 100000);

  Serial.println(F("Scanning Bus 1..."));
  for (byte addr = 1; addr < 127; addr++) {
    I2C_Bus1.beginTransmission(addr);
    if (I2C_Bus1.endTransmission() == 0)
      Serial.printf("  found: 0x%02X\n", addr);
  }

  Serial.println(F("Scanning Bus 2..."));
  for (byte addr = 1; addr < 127; addr++) {
    I2C_Bus2.beginTransmission(addr);
    if (I2C_Bus2.endTransmission() == 0)
      Serial.printf("  found: 0x%02X\n", addr);
  }

  Serial.println(F("Done."));
}

void loop() {
  while (Serial.available() && !new_data) receive_serial();

  if (new_data) {
    if (received_chars[0] == 's') {
      print_status_tracked();

    } else {
      char* target  = strtok(received_chars, ",");
      char* volt_str = strtok(NULL, ",");

      if (!target || !volt_str) {
        Serial.println(F("Error: bad format. Use <all,V> or <1-4,V>"));
      } else {
        float v = atof(volt_str);
        if (v < 0 || v > 5) {
          Serial.println(F("Error: voltage must be 0.0 – 5.0"));
        } else if (!strcmp(target, "all")) {
          set_all_tracked(v);
          Serial.printf("[OK] all DACs -> %.3fV\n", v);
          print_status_tracked();
        } else {
          int idx = atoi(target);
          if (idx < 1 || idx > 4) {
            Serial.println(F("Error: DAC index must be 1–4"));
          } else {
            set_dac_tracked(idx, v);
            Serial.printf("[OK] dac%d -> %.3fV\n", idx, v);
            print_status_tracked();
          }
        }
      }
    }
    new_data = false;
  }
}