# Encoder inclinazione teste (ESP32 + MAX485)

Sì: due encoder rotativi incrementali sulle teste, letti da ESP32 e instradati sul bus RS485 Modbus esistente, sono la soluzione corretta. Non servono GPIO extra sul Raspberry: lo stesso cavo A/B dei moduli I/O porta anche gli angoli.

## Perché RS485 e non GPIO sul Pi

L’encoder è NPN 5–24 V, fino a 20 kHz. Sul Pi i GPIO 3,3 V sono già usati dal carro (MD25HV + ELTRA). Un ESP32 vicino alla testa fa quadratura in interrupt, isola galvanicamente via MAX485 e pubblica l’angolo come holding register.

## Un ESP32 o due

| Scelta | Quando |
|--------|--------|
| **Un ESP32, un MAX485, slave 20** (consigliato) | Cavi encoder abbastanza lunghi da arrivare a un unico quadro; un solo nodo sul bus |
| **Due coppie ESP32+MAX485** (slave 20 e 21) | Teste lontane, cavi encoder corti, meno rumore |

Il software accetta entrambe: `head_encoders.mode` = `combined` o `split` in `data/hardware_config.json`.

## Cablaggio encoder (NPN)

Verde = A, Bianco = B, Rosso = Vcc (5–24 V), Nero = GND.

Non collegare A/B a VCC. Pull-up sul GPIO ESP32. GND comune encoder–ESP32. Vcc encoder da 12 V o 24 V macchina, non dal 3,3 V dell’ESP32.

## Cosa fa il software

- `HeadAngleEncoderService` legge HR0/HR1 a ogni `tick` di `RealMachine`
- `HeadsView` in Semi-automatico ruota le teste sull’angolo **misurato** se l’encoder è online, altrimenti sul comando
- Pulsanti **Azzera enc.** in Semi-automatico (testa meccanicamente a 0°)

Firmware: `firmware/esp32_head_encoder/`.
