# Encoder inclinazione teste — alternativa ESP32 + MAX485

Percorso **opzionale**. La soluzione di default è cavo schermato + AL-ZARD + GPIO: vedere `docs/HEAD_ENCODERS.md`.

Usare questo schema solo se gli encoder non possono arrivare nel quadro (cavi troppo corti, disturbi non gestibili, GPIO già tutti occupati).

## Un ESP32 o due

| Scelta | Quando |
|--------|--------|
| **Un ESP32, un MAX485, slave 20** | Cavi encoder abbastanza lunghi da arrivare a un unico quadro |
| **Due coppie ESP32+MAX485** (slave 20 e 21) | Teste lontane, cavi encoder corti |

In `data/hardware_config.json` impostare `"interface": "modbus"` e `head_encoders.mode` = `combined` o `split`.

## Cablaggio encoder (NPN)

Verde = A, Bianco = B, Rosso = Vcc (5–24 V), Nero = GND.

Non collegare A/B a VCC. Pull-up sul GPIO ESP32. GND comune encoder–ESP32. Vcc encoder da 12 V o 24 V macchina, non dal 3,3 V dell’ESP32.

Firmware: `firmware/esp32_head_encoder/`.
