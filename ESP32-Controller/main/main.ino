#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_MCP4725.h>
#include "max6675.h"

// =============================================================================
// SERIAL COMMUNICATION PROTOCOL
// All commands are wrapped: <command>
// Response format: [OK] ... or [ERR] ...
// Status output (command <3>): CSV per line: name,gas,max_flow,setpoint,std_sp,rate
// Temperature output: T,<value>  (every 500ms)
//
// COMMANDS:
//   <0,flow_N,gas>        Set gas type for flow_N
//   <a0,gas>              Set gas type for ALL flows
//   <1,flow_N,value>      Set max flow for flow_N
//   <a1,value>            Set max flow for ALL flows
//   <2,flow_N,value>      Set setpoint for flow_N
//   <a2,value>            Set setpoint for ALL flows
//   <3>                   Print status of all flows (CSV)
//   <4,flow_N,value>      Set standard setpoint for flow_N
//   <a4,value>            Set standard setpoint for ALL flows
//   <5>                   Apply standard setpoints to all flows
//   <6>                   Set all flow setpoints to 0
//
// GASES: nitrogen, butane, air, argon
// FLOWS: flow_1, flow_2, flow_3, flow_4
// =============================================================================

// =============================================================================
// PIN ASSIGNMENTS
// I2C Bus 1 (SDA=19, SCL=20): DAC1 @ 0x60, DAC2 @ 0x61
// I2C Bus 2 (SDA=2,  SCL=4):  DAC3 @ 0x60, DAC4 @ 0x61
//
// ADC (analog flow rate read):
//   flow_1 -> GPIO 13
//   flow_2 -> GPIO 11
//   flow_3 -> GPIO  9
//   flow_4 -> GPIO  3
//
// MAX6675 thermocouple (software SPI):
//   CLK    -> GPIO 7
//   CS     -> GPIO 6
//   DO     -> GPIO 5
// =============================================================================

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
#define ADC_RESOLUTION  4095.0
#define TEMP_INTERVAL   500

TwoWire I2C_Bus1 = TwoWire(0);
TwoWire I2C_Bus2 = TwoWire(1);

Adafruit_MCP4725 dac1, dac2, dac3, dac4;
MAX6675 thermocouple(THERMO_CLK, THERMO_CS, THERMO_DO);

// --- Gas table ---
struct Gas { const char* name; float k; };

Gas gas_table[] = {
  {"nitrogen", 1.0000},
  {"butane",   0.2631},
  {"air",      1.0000},
  {"argon",    1.4573}
};
const int num_gasses = 4;

float get_K(const char* gas) {
  for (int i = 0; i < num_gasses; i++)
    if (!strcmp(gas, gas_table[i].name)) return gas_table[i].k;
  return -1.0;
}

// --- Flow table ---
struct Flow {
  const char name[8];
  char gas[16];
  int max_flow;
  const byte pin;
  double flow_rate;
  double set_point;
  double standard_set_point;
};

Flow flow_table[NUM_FLOWS] = {
  {"flow_1", "air", 10000, 13, 0, 0, 0},
  {"flow_2", "air", 10000, 11, 0, 0, 0},
  {"flow_3", "air", 10000,  9, 0, 0, 0},
  {"flow_4", "air", 10000,  3, 0, 0, 0}
};

Flow* get_flow(const char* name) {
  for (int i = 0; i < NUM_FLOWS; i++)
    if (!strcmp(flow_table[i].name, name)) return &flow_table[i];
  return nullptr;
}

// --- DAC output ---
void update_dac(const char* name, double set_point, int max_flow) {
  uint16_t val = (uint16_t)((set_point / (double)max_flow) * ADC_RESOLUTION);
  if      (!strcmp(name, "flow_1")) dac1.setVoltage(val, false);
  else if (!strcmp(name, "flow_2")) dac2.setVoltage(val, false);
  else if (!strcmp(name, "flow_3")) dac3.setVoltage(val, false);
  else if (!strcmp(name, "flow_4")) dac4.setVoltage(val, false);
}

// --- Flow read ---
double read_flow(Flow* f) {
  return analogRead(f->pin) * get_K(f->gas) * f->max_flow / ADC_RESOLUTION;
}

// --- Serial ---
static char serial_buf[64];
bool new_data = false;

void receive_serial() {
  static bool receiving = false;
  static byte idx = 0;
  char c = Serial.read();
  if (receiving) {
    if (c != '>') { serial_buf[idx++] = c; }
    else { serial_buf[idx] = '\0'; idx = 0; receiving = false; new_data = true; }
  } else if (c == '<') { receiving = true; }
}

// --- Parsed command args ---
struct ParsedCmd { char flow_name[8]; char str_arg[16]; double num_arg; };

ParsedCmd parse_args(int offset) {
  ParsedCmd p = {};
  char* flow = strtok(&serial_buf[offset], ",");
  char* arg  = strtok(NULL, ",");
  if (flow) strlcpy(p.flow_name, flow, sizeof(p.flow_name));
  if (arg)  { strlcpy(p.str_arg, arg, sizeof(p.str_arg)); p.num_arg = atof(arg); }
  return p;
}

void printFlows() {
  for (int i = 0; i < NUM_FLOWS; i++)
    Serial.printf("%s,%s,%d,%.2f,%.2f,%.2f\n",
      flow_table[i].name, flow_table[i].gas, flow_table[i].max_flow,
      flow_table[i].set_point, flow_table[i].standard_set_point, flow_table[i].flow_rate);
}

// --- Command handlers ---
void cmd_set_gas(const char* flow_name, const char* gas_name) {
  if (get_K(gas_name) == -1.0)     { Serial.println(F("[ERR] unknown gas"));   return; }
  Flow* f = get_flow(flow_name);
  if (!f)                          { Serial.println(F("[ERR] flow not found")); return; }
  strlcpy(f->gas, gas_name, sizeof(f->gas));
  Serial.printf("[OK] %s gas->%s\n", flow_name, gas_name);
}

void cmd_set_max(const char* flow_name, int max_flow) {
  if (max_flow <= 0)               { Serial.println(F("[ERR] max must be >0")); return; }
  Flow* f = get_flow(flow_name);
  if (!f)                          { Serial.println(F("[ERR] flow not found")); return; }
  f->max_flow = max_flow;
  Serial.printf("[OK] %s max->%d\n", flow_name, max_flow);
}

void cmd_set_setpoint(const char* flow_name, double sp) {
  if (sp < 0)                      { Serial.println(F("[ERR] sp must be >=0")); return; }
  Flow* f = get_flow(flow_name);
  if (!f)                          { Serial.println(F("[ERR] flow not found")); return; }
  f->set_point = sp;
  update_dac(flow_name, sp, f->max_flow);
  Serial.printf("[OK] %s sp->%.2f\n", flow_name, sp);
}

void cmd_set_standard(const char* flow_name, double sp) {
  if (sp < 0)                      { Serial.println(F("[ERR] sp must be >=0")); return; }
  Flow* f = get_flow(flow_name);
  if (!f)                          { Serial.println(F("[ERR] flow not found")); return; }
  f->standard_set_point = sp;
  Serial.printf("[OK] %s std->%.2f\n", flow_name, sp);
}

void cmd_apply_standard() {
  for (int i = 0; i < NUM_FLOWS; i++) {
    flow_table[i].set_point = flow_table[i].standard_set_point;
    update_dac(flow_table[i].name, flow_table[i].set_point, flow_table[i].max_flow);
  }
  Serial.println(F("[OK] standard setpoints applied"));
}

void cmd_all_off() {
  for (int i = 0; i < NUM_FLOWS; i++) {
    flow_table[i].set_point = 0;
    update_dac(flow_table[i].name, 0, flow_table[i].max_flow);
  }
  Serial.println(F("[OK] all flows off"));
}

// --- Apply a single-flow command to one or all flows ---
void dispatch(char cmd, bool all, ParsedCmd& p) {
  auto for_each = [&](auto fn) {
    if (all) for (int i = 0; i < NUM_FLOWS; i++) fn(flow_table[i].name);
    else     fn(p.flow_name);
  };

  switch (cmd) {
    case '0': for_each([&](const char* n){ cmd_set_gas     (n, p.str_arg);        }); break;
    case '1': for_each([&](const char* n){ cmd_set_max     (n, (int)p.num_arg);   }); break;
    case '2': for_each([&](const char* n){ cmd_set_setpoint(n, p.num_arg);        }); break;
    case '3': printFlows(); return;
    case '4': for_each([&](const char* n){ cmd_set_standard(n, p.num_arg);        }); break;
    case '5': cmd_apply_standard(); return;
    case '6': cmd_all_off();        return;
    default:  Serial.println(F("[ERR] unknown command (0-6)")); return;
  }
  printFlows();
}

// --- Setup / Loop ---
void setup() {
  Serial.begin(115200);
  delay(500); // MAX6675 stabilization

  I2C_Bus1.begin(I2C_BUS1_SDA, I2C_BUS1_SCL, I2C_FREQ);
  dac1.begin(DAC_ADDR_A, &I2C_Bus1);
  dac2.begin(DAC_ADDR_B, &I2C_Bus1);

  I2C_Bus2.begin(I2C_BUS2_SDA, I2C_BUS2_SCL, I2C_FREQ);
  dac3.begin(DAC_ADDR_A, &I2C_Bus2);
  dac4.begin(DAC_ADDR_B, &I2C_Bus2);

  dac1.setVoltage(0, false);
  dac2.setVoltage(0, false);
  dac3.setVoltage(0, false);
  dac4.setVoltage(0, false);

  while (!Serial);
  Serial.println(F("[OK] ready"));
}

unsigned long last_temp = 0;

void loop() {
  for (int i = 0; i < NUM_FLOWS; i++)
    flow_table[i].flow_rate = read_flow(&flow_table[i]);

  while (Serial.available() && !new_data) receive_serial();

  if (new_data) {
    bool all    = (serial_buf[0] == 'a');
    int  offset = all ? 1 : 0;
    char cmd    = serial_buf[offset];
    ParsedCmd p = parse_args(offset + 1);
    dispatch(cmd, all, p);
    new_data = false;
  }

  if (millis() - last_temp >= TEMP_INTERVAL) {
    Serial.printf("T,%.2f\n", thermocouple.readCelsius());
    last_temp = millis();
  }
}
