#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MCP4725.h>
#include "MAX6675.h"

/* =============================================================================
  SERIAL COMMUNICATION PROTOCOL  (115200 baud)

  COMMANDS  (host -> ESP32, wrapped in angle brackets):

    setpoint -> set the flow meters to a specific thing
    max      -> change the max of a flow meter
    gas      -> change the gas that a specific flowmeter is using
    standard -> create a 'saved' set point you can go back to
    apply    -> apply the saved setpoint to all flow meters
    off      -> turn off all flow meters
    temp     -> recieve the current temperature
    ?        -> ping / connection test

    <setpoint,N,value>    Set flow N (1–4) setpoint
    <setpoint,all,value>  Set all flows to same setpoint
    <max,N,value>         Set flow N max range
    <max,all,value>       Set all flows max range
    <gas,N,name>          Set gas type for flow N
    <gas,all,name>        Set gas type for all flows
    <standard,N,value>    Save standard setpoint for flow N
    <standard,all,value>  Save standard setpoint for all flows
    <apply>               Apply all saved standard setpoints
    <off>                 Zero all flow setpoints
    <flowrate,N>          Request flow N rate
    <flowrate,all>        Request all flow rates
    <temp>                Request thermocouple temperature
    <?>                   Ping — test communication

  RESPONSES  (ESP32 -> host, wrapped in angle brackets):
    Set/apply/off:  <ok>  or  <err:reason>
    <flowrate,N>:   <value>              e.g. <142.30>
    <flowrate,all>: <v1,v2,v3,v4>       e.g. <142.30,85.10,0.00,300.00>
    <temp>:         <value>              e.g. <24.50>
    <?>:            <ok>

  GASES: nitrogen, butane, air, argon
   ========================================================================== */

   /* =============================================================================
     PIN ASSIGNMENTS
     I2C Bus 1 (SDA=19, SCL=20): DAC1 @ 0x60, DAC2 @ 0x61
     I2C Bus 2 (SDA=2,  SCL=4):  DAC3 @ 0x60, DAC4 @ 0x61

     ADC (analog flow rate read):
       flow 1 -> GPIO 13
       flow 2 -> GPIO 11
       flow 3 -> GPIO  9
       flow 4 -> GPIO  3

     MAX6675 thermocouple (software SPI):
       CLK -> GPIO 7 | CS -> GPIO 6 | DO -> GPIO 5
      ========================================================================== */

      // --- I2C ---
#define I2C_BUS1_SDA  19
#define I2C_BUS1_SCL  20
#define I2C_BUS2_SDA  2
#define I2C_BUS2_SCL  4
#define I2C_FREQ      100000
#define DAC_ADDR_A    0x60
#define DAC_ADDR_B    0x61

// --- MAX6675 ---
#define THERMO_CLK  7
#define THERMO_CS   6
#define THERMO_DO   5

// --- Misc ---
#define NUM_FLOWS       4
#define ADC_RESOLUTION  4095.0f

// ─── Hardware objects ────────────────────────────────────────────────────────

TwoWire I2C_Bus1 = TwoWire(0);
TwoWire I2C_Bus2 = TwoWire(1);

Adafruit_MCP4725 dac[NUM_FLOWS];   // dac[0]–dac[3]
MAX6675 thermocouple(THERMO_CLK, THERMO_CS, THERMO_DO);

// ─── Gas table ───────────────────────────────────────────────────────────────

struct Gas { const char* name; float k; };
static const Gas GAS_TABLE[] = {
  {"nitrogen", 1.0000f},
  {"butane",   0.2631f},
  {"air",      1.0000f},
  {"argon",    1.4573f}
};
static const int NUM_GASES = sizeof(GAS_TABLE) / sizeof(GAS_TABLE[0]);

float get_K(const char* gas) {
  for (int i = 0; i < NUM_GASES; i++)
    if (!strcmp(gas, GAS_TABLE[i].name)) return GAS_TABLE[i].k;
  return -1.0f;
}

// ─── Flow table ──────────────────────────────────────────────────────────────

struct Flow {
  char    gas[16];
  int     max_flow;
  uint8_t pin;
  float   set_point;
  float   standard_set_point;
};

static Flow flows[NUM_FLOWS] = {
  {"air", 10000, 13, 0, 0},
  {"air", 10000, 11, 0, 0},
  {"air", 10000,  9, 0, 0},
  {"air", 10000,  3, 0, 0}
};

// ─── DAC / ADC helpers ───────────────────────────────────────────────────────

void dac_write(int idx, float setpoint, int max_flow) {
  uint16_t val = (uint16_t)((setpoint / (float)max_flow) * ADC_RESOLUTION);
  dac[idx].setVoltage(val, false);
}

float read_flow(int idx) {
  float k = get_K(flows[idx].gas);
  if (k < 0) k = 1.0f;
  return analogRead(flows[idx].pin) * k * flows[idx].max_flow / ADC_RESOLUTION;
}

// ─── Serial receive ──────────────────────────────────────────────────────────

static char  serial_buf[64];
static bool  new_data = false;

void receive_serial() {
  static bool receiving = false;
  static byte idx = 0;
  char c = Serial.read();
  if (receiving) {
    if (c == '>') { serial_buf[idx] = '\0'; idx = 0; receiving = false; new_data = true; }
    else if (idx < (int)sizeof(serial_buf) - 1) serial_buf[idx++] = c;
  }
  else if (c == '<') {
    receiving = true;
    idx = 0;
  }
}

// ─── Command helpers ─────────────────────────────────────────────────────────

// Returns 0-based index (0–3) for a valid single flow, -1 for "all", -2 for error.
int parse_flow_target(const char* tok) {
  if (!tok) return -2;
  if (!strcmp(tok, "all")) return -1;
  int n = atoi(tok);
  if (n < 1 || n > NUM_FLOWS) return -2;
  return n - 1;
}

// ─── Command handlers ────────────────────────────────────────────────────────

void cmd_setpoint(int idx, float val) {
  if (val < 0) { Serial.print("<err:sp<0>");         return; }
  if (val > flows[idx].max_flow) { Serial.print("<err:sp_exceeds_max>"); return; }
  flows[idx].set_point = val;
  dac_write(idx, val, flows[idx].max_flow);
}

void cmd_max(int idx, int val) {
  if (val <= 0) { Serial.print("<err:max<=0>"); return; }
  flows[idx].max_flow = val;
  dac_write(idx, flows[idx].set_point, val);
}

void cmd_gas(int idx, const char* name) {
  if (get_K(name) < 0) { Serial.print("<err:unknown_gas>"); return; }
  strlcpy(flows[idx].gas, name, sizeof(flows[idx].gas));
}

void cmd_standard(int idx, float val) {
  if (val < 0) { Serial.print("<err:sp<0>"); return; }
  flows[idx].standard_set_point = val;
}

void cmd_apply() {
  for (int i = 0; i < NUM_FLOWS; i++) {
    flows[i].set_point = flows[i].standard_set_point;
    dac_write(i, flows[i].set_point, flows[i].max_flow);
  }
  Serial.print("<ok>");
}

void cmd_off() {
  for (int i = 0; i < NUM_FLOWS; i++) {
    flows[i].set_point = 0;
    dac_write(i, 0, flows[i].max_flow);
  }
  Serial.print("<ok>");
}

void cmd_flowrate(int idx) {
  if (idx == -1) {
    Serial.print('<');
    for (int i = 0; i < NUM_FLOWS; i++) {
      if (i) Serial.print(',');
      Serial.printf("%.2f", read_flow(i));
    }
    Serial.print('>');
  }
  else {
    Serial.printf("<%.2f>", read_flow(idx));
  }
}

void cmd_temp() {
  Serial.printf("<%.2f>", thermocouple.getCelsius());
}

// ─── Dispatch ────────────────────────────────────────────────────────────────

void process_command() {
  char* cmd = strtok(serial_buf, ",");
  char* arg1 = strtok(NULL, ",");
  char* arg2 = strtok(NULL, ",");

  if (!cmd) { Serial.print("<err:empty>"); return; }

  // ── ping ──────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "?")) { Serial.print("<ok>"); return; }

  // ── setpoint ──────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "setpoint")) {
    int idx = parse_flow_target(arg1);
    if (idx == -2 || !arg2) { Serial.print("<err:bad_args>"); return; }
    float val = atof(arg2);
    if (idx == -1) { for (int i = 0; i < NUM_FLOWS; i++) cmd_setpoint(i, val); }
    else           cmd_setpoint(idx, val);
    Serial.print("<ok>");
    return;
  }

  // ── max ───────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "max")) {
    int idx = parse_flow_target(arg1);
    if (idx == -2 || !arg2) { Serial.print("<err:bad_args>"); return; }
    int val = atoi(arg2);
    if (idx == -1) { for (int i = 0; i < NUM_FLOWS; i++) cmd_max(i, val); }
    else           cmd_max(idx, val);
    Serial.print("<ok>");
    return;
  }

  // ── gas ───────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "gas")) {
    int idx = parse_flow_target(arg1);
    if (idx == -2 || !arg2) { Serial.print("<err:bad_args>"); return; }
    if (idx == -1) { for (int i = 0; i < NUM_FLOWS; i++) cmd_gas(i, arg2); }
    else           cmd_gas(idx, arg2);
    Serial.print("<ok>");
    return;
  }

  // ── standard ──────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "standard")) {
    int idx = parse_flow_target(arg1);
    if (idx == -2 || !arg2) { Serial.print("<err:bad_args>"); return; }
    float val = atof(arg2);
    if (idx == -1) { for (int i = 0; i < NUM_FLOWS; i++) cmd_standard(i, val); }
    else           cmd_standard(idx, val);
    Serial.print("<ok>");
    return;
  }

  // ── apply ─────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "apply")) { cmd_apply(); return; }

  // ── off ───────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "off")) { cmd_off(); return; }

  // ── flowrate ──────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "flowrate")) {
    int idx = parse_flow_target(arg1);
    if (idx == -2) { Serial.print("<err:bad_args>"); return; }
    cmd_flowrate(idx);
    return;
  }

  // ── temp ──────────────────────────────────────────────────────────────────
  if (!strcmp(cmd, "temp")) { cmd_temp(); return; }

  Serial.print("<err:unknown_command>");
}

// ─── Setup / Loop ────────────────────────────────────────────────────────────

void setup() {
  Serial.begin(115200);
  delay(500); // MAX6675 stabilization

  I2C_Bus1.begin(I2C_BUS1_SDA, I2C_BUS1_SCL, I2C_FREQ);
  dac[0].begin(DAC_ADDR_A, &I2C_Bus1);
  dac[1].begin(DAC_ADDR_B, &I2C_Bus1);

  I2C_Bus2.begin(I2C_BUS2_SDA, I2C_BUS2_SCL, I2C_FREQ);
  dac[2].begin(DAC_ADDR_A, &I2C_Bus2);
  dac[3].begin(DAC_ADDR_B, &I2C_Bus2);

  for (int i = 0; i < NUM_FLOWS; i++) {
    pinMode(flows[i].pin, INPUT);
    dac[i].setVoltage(0, false);
  }
}

void loop() {
  while (Serial.available() && !new_data) receive_serial();

  if (new_data) {
    process_command();
    new_data = false;
  }
}
