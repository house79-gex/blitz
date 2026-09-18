#pragma once

// Configurazione firmware encoder inclinazione teste BLITZ
// Un ESP32 può leggere UNA o ENTRAMBE le teste.

// 1 = un ESP32 per entrambe le teste (slave 20, HR0=SX HR1=DX)
// 0 = un ESP32 per testa (impostare HEAD_SIDE e SLAVE_ID)
#ifndef HEAD_MODE_COMBINED
#define HEAD_MODE_COMBINED 1
#endif

// Usato solo se HEAD_MODE_COMBINED == 0: 0 = SX, 1 = DX
#ifndef HEAD_SIDE_DX
#define HEAD_SIDE_DX 0
#endif

#ifndef SLAVE_ID
#define SLAVE_ID 20
#endif

#ifndef MODBUS_BAUD
#define MODBUS_BAUD 115200
#endif

// Encoder incrementale 360 P/R, quadratura x4 → 1440 conteggi/giro
#ifndef ENCODER_PPR
#define ENCODER_PPR 360
#endif

#ifndef QUADRATURE
#define QUADRATURE 4
#endif

// GPIO encoder (NPN open collector → INPUT_PULLUP, NON collegare A/B a VCC)
#define PIN_ENC_SX_A 16
#define PIN_ENC_SX_B 17
#define PIN_ENC_DX_A 18
#define PIN_ENC_DX_B 19

// MAX485: RO→RX, DI→TX, DE e RE uniti
#define PIN_RS485_RX 26
#define PIN_RS485_TX 27
#define PIN_RS485_DE 25

#define PIN_STATUS_LED 2
