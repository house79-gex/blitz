/*
  BLITZ CNC — encoder inclinazione teste via RS485 Modbus RTU.

  Hardware:
    - Encoder incrementale AB NPN 360 P/R (albero 6 mm, 5-24 V)
      Verde=A, Bianco=B, Rosso=Vcc, Nero=GND
    - ESP32 + MAX485 sullo stesso bus dei moduli I/O Waveshare

  Topologie:
    - COMBINED (default): un ESP32 legge SX+DX, slave 20
        HR0 = angolo SX × 100
        HR1 = angolo DX × 100
        Coil 0 = azzera SX, Coil 1 = azzera DX
    - SPLIT: un ESP32 per testa
        #define HEAD_MODE_COMBINED 0
        SX: SLAVE_ID 20, HEAD_SIDE_DX 0
        DX: SLAVE_ID 21, HEAD_SIDE_DX 1
        HR0 = angolo × 100, Coil 0 = azzera

  NPN: A e B NON vanno a VCC. Pull-up interno ESP32 verso 3.3 V.
*/

#include "config.h"

static const int32_t COUNTS_PER_REV = (int32_t)ENCODER_PPR * (int32_t)QUADRATURE;

// Tabella quadratura x4
static const int8_t QDEC[16] = {
  0, -1, 1, 0,
  1, 0, 0, -1,
  -1, 0, 0, 1,
  0, 1, -1, 0
};

volatile int32_t g_count_sx = 0;
volatile int32_t g_count_dx = 0;
volatile uint8_t g_prev_sx = 0;
volatile uint8_t g_prev_dx = 0;

HardwareSerial Rs485(2);

static uint8_t read_ab(int pin_a, int pin_b) {
  uint8_t a = digitalRead(pin_a) ? 1 : 0;
  uint8_t b = digitalRead(pin_b) ? 1 : 0;
  return (uint8_t)((a << 1) | b);
}

void IRAM_ATTR isr_sx() {
  uint8_t now = read_ab(PIN_ENC_SX_A, PIN_ENC_SX_B);
  uint8_t idx = (uint8_t)((g_prev_sx << 2) | now);
  g_count_sx += QDEC[idx & 0x0F];
  g_prev_sx = now;
}

void IRAM_ATTR isr_dx() {
  uint8_t now = read_ab(PIN_ENC_DX_A, PIN_ENC_DX_B);
  uint8_t idx = (uint8_t)((g_prev_dx << 2) | now);
  g_count_dx += QDEC[idx & 0x0F];
  g_prev_dx = now;
}

static int16_t counts_to_cdeg(int32_t counts) {
  // gradi × 100 = counts * 36000 / COUNTS_PER_REV
  long v = (long)counts * 36000L / COUNTS_PER_REV;
  if (v > 32767) v = 32767;
  if (v < -32768) v = -32768;
  return (int16_t)v;
}

static uint16_t crc16_modbus(const uint8_t *data, size_t len) {
  uint16_t crc = 0xFFFF;
  for (size_t i = 0; i < len; i++) {
    crc ^= data[i];
    for (uint8_t b = 0; b < 8; b++) {
      if (crc & 1) crc = (crc >> 1) ^ 0xA001;
      else crc >>= 1;
    }
  }
  return crc;
}

static void rs485_begin_tx() {
  digitalWrite(PIN_RS485_DE, HIGH);
  delayMicroseconds(50);
}

static void rs485_end_tx() {
  Rs485.flush();
  delayMicroseconds(50);
  digitalWrite(PIN_RS485_DE, LOW);
}

static void send_response(const uint8_t *pdu, size_t len) {
  uint16_t crc = crc16_modbus(pdu, len);
  rs485_begin_tx();
  Rs485.write(pdu, len);
  Rs485.write((uint8_t)(crc & 0xFF));
  Rs485.write((uint8_t)(crc >> 8));
  rs485_end_tx();
}

static void handle_read_holding(uint8_t start_hi, uint8_t start_lo, uint8_t qty_hi, uint8_t qty_lo) {
  uint16_t start = (uint16_t)((start_hi << 8) | start_lo);
  uint16_t qty = (uint16_t)((qty_hi << 8) | qty_lo);
  if (qty == 0 || qty > 8) return;

  int16_t regs[8];
#if HEAD_MODE_COMBINED
  noInterrupts();
  int32_t sx = g_count_sx;
  int32_t dx = g_count_dx;
  interrupts();
  regs[0] = counts_to_cdeg(sx);
  regs[1] = counts_to_cdeg(dx);
#else
  noInterrupts();
  int32_t c = HEAD_SIDE_DX ? g_count_dx : g_count_sx;
  interrupts();
  regs[0] = counts_to_cdeg(c);
#endif

  uint8_t pdu[3 + 16];
  pdu[0] = SLAVE_ID;
  pdu[1] = 0x03;
  pdu[2] = (uint8_t)(qty * 2);
  for (uint16_t i = 0; i < qty; i++) {
    int16_t val = 0;
    uint16_t idx = (uint16_t)(start + i);
    if (idx < 8) val = regs[idx];
    pdu[3 + i * 2] = (uint8_t)((val >> 8) & 0xFF);
    pdu[4 + i * 2] = (uint8_t)(val & 0xFF);
  }
  send_response(pdu, 3 + qty * 2);
}

static void handle_write_coil(uint8_t addr_hi, uint8_t addr_lo, uint8_t val_hi, uint8_t val_lo) {
  uint16_t coil = (uint16_t)((addr_hi << 8) | addr_lo);
  bool on = (val_hi == 0xFF && val_lo == 0x00);
  if (!on) {
    // echo comunque
  } else {
#if HEAD_MODE_COMBINED
    if (coil == 0) {
      noInterrupts();
      g_count_sx = 0;
      interrupts();
    } else if (coil == 1) {
      noInterrupts();
      g_count_dx = 0;
      interrupts();
    }
#else
    if (coil == 0) {
      noInterrupts();
      if (HEAD_SIDE_DX) g_count_dx = 0;
      else g_count_sx = 0;
      interrupts();
    }
#endif
  }
  uint8_t pdu[6] = {SLAVE_ID, 0x05, addr_hi, addr_lo, val_hi, val_lo};
  send_response(pdu, 6);
}

static uint8_t rxbuf[64];
static size_t rxlen = 0;
static uint32_t last_rx_ms = 0;

static void poll_modbus() {
  while (Rs485.available()) {
    if (rxlen < sizeof(rxbuf)) {
      rxbuf[rxlen++] = (uint8_t)Rs485.read();
    } else {
      Rs485.read();
    }
    last_rx_ms = millis();
  }
  if (rxlen == 0) return;
  if (millis() - last_rx_ms < 5) return;  // fine frame RTU (~3.5 char)

  if (rxlen >= 8 && rxbuf[0] == SLAVE_ID) {
    uint16_t crc_rx = (uint16_t)(rxbuf[rxlen - 2] | (rxbuf[rxlen - 1] << 8));
    uint16_t crc_calc = crc16_modbus(rxbuf, rxlen - 2);
    if (crc_rx == crc_calc) {
      uint8_t fn = rxbuf[1];
      if (fn == 0x03 && rxlen >= 8) {
        handle_read_holding(rxbuf[2], rxbuf[3], rxbuf[4], rxbuf[5]);
      } else if (fn == 0x05 && rxlen >= 8) {
        handle_write_coil(rxbuf[2], rxbuf[3], rxbuf[4], rxbuf[5]);
      }
    }
  }
  rxlen = 0;
}

void setup() {
  pinMode(PIN_STATUS_LED, OUTPUT);
  pinMode(PIN_RS485_DE, OUTPUT);
  digitalWrite(PIN_RS485_DE, LOW);

  pinMode(PIN_ENC_SX_A, INPUT_PULLUP);
  pinMode(PIN_ENC_SX_B, INPUT_PULLUP);
  pinMode(PIN_ENC_DX_A, INPUT_PULLUP);
  pinMode(PIN_ENC_DX_B, INPUT_PULLUP);

  g_prev_sx = read_ab(PIN_ENC_SX_A, PIN_ENC_SX_B);
  g_prev_dx = read_ab(PIN_ENC_DX_A, PIN_ENC_DX_B);

#if HEAD_MODE_COMBINED
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_SX_A), isr_sx, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_SX_B), isr_sx, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_DX_A), isr_dx, CHANGE);
  attachInterrupt(digitalPinToInterrupt(PIN_ENC_DX_B), isr_dx, CHANGE);
#else
  if (HEAD_SIDE_DX) {
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_DX_A), isr_dx, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_DX_B), isr_dx, CHANGE);
  } else {
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_SX_A), isr_sx, CHANGE);
    attachInterrupt(digitalPinToInterrupt(PIN_ENC_SX_B), isr_sx, CHANGE);
  }
#endif

  Rs485.begin(MODBUS_BAUD, SERIAL_8N1, PIN_RS485_RX, PIN_RS485_TX);
}

void loop() {
  poll_modbus();
  digitalWrite(PIN_STATUS_LED, (millis() / 500) % 2);
}
