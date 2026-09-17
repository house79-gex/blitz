# Encoder inclinazione teste — ESP32 + MAX485

Percorso **opzionale**. Di default le teste si leggono con cavo schermato + AL-ZARD + GPIO (`docs/HEAD_ENCODERS.md`).

Questo firmware serve solo se `head_encoders.interface` è `modbus`.

## Encoder

Incrementale AB NPN, 360 P/R (x4 = 1440 conteggi/giro → 0,25° se 1:1).

| Filo | Segnale |
|------|---------|
| Verde | Fase A |
| Bianco | Fase B |
| Rosso | Vcc 5–24 V |
| Nero | GND |

**NPN open collector:** A e B non vanno collegati a VCC, altrimenti si brucia l’uscita. Pull-up sul GPIO ESP32 (3,3 V). GND encoder comune con ESP32.

Albero 6 mm + giunto verso l’asse di inclinazione della testa. Se il rapporto non è 1:1, tarare `zero_offset` / invert in `data/hardware_config.json`.

## Topologia consigliata

Un ESP32 e un MAX485 per **entrambe** le teste (meno nodi sul bus):

```
Encoder SX A/B ──► ESP32 GPIO 16/17
Encoder DX A/B ──► ESP32 GPIO 18/19
ESP32 UART2 ──► MAX485 ──► A/B RS485 (stesso bus I/O Waveshare)
Slave Modbus 20
```

Due ESP32 (uno per testa) se i cavi encoder sono corti e le teste lontane:

- SX: `HEAD_MODE_COMBINED 0`, `SLAVE_ID 20`, `HEAD_SIDE_DX 0`
- DX: `HEAD_MODE_COMBINED 0`, `SLAVE_ID 21`, `HEAD_SIDE_DX 1`
- In `hardware_config.json` impostare `"mode": "split"`

Terminazione 120 Ω sull’ultimo nodo del bus.

## Mappa Modbus (combined, slave 20)

| Registro / coil | Significato |
|-----------------|-------------|
| HR0 | Angolo SX × 100 (int16, es. 4500 = 45,00°) |
| HR1 | Angolo DX × 100 |
| Coil 0 | Azzera conteggio SX (testa a 0° meccanico) |
| Coil 1 | Azzera conteggio DX |

Baud 115200 8N1, come il resto del bus.

## Flash

Arduino IDE: scheda ESP32 Dev Module, sketch `esp32_head_encoder.ino`.

Azzerare da Semi-automatico con i pulsanti **Azzera enc.** a testa meccanicamente a 0°.
