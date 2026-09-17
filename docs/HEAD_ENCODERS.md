# Encoder inclinazione teste (cavo schermato + AL-ZARD + GPIO)

Sì: con il cavo schermato portato nel quadro e un secondo modulo AL-ZARD, **non servono ESP32 né RS485** per gli angoli delle teste. I segnali A/B arrivano ai GPIO del Raspberry Pi, come già avviene per l’encoder del carro.

Non collegare gli encoder **direttamente** ai GPIO: le uscite NPN sono a 12 V. Tra cavo e Pi deve restare l’optoaccoppiatore (AL-ZARD DST-1R4P-N), con VCC lato uscita a **3,3 V**.

## Perché questa topologia

| Punto | Dettaglio |
|--------|-----------|
| Cavo | FR2OHH2R 6×0,50 mm² schermato, gomma, antifiamma, 10 m |
| Isolamento | AL-ZARD 4 canali (NPN 12 V → 3,3 V) |
| Lettura | pigpio in interrupt, quadratura x4 |
| ESP32 / RS485 | Non necessari per le teste |

10 metri di 0,50 mm² su encoder incrementali sono ampiamente sufficienti: le teste ruotano piano (pochi kHz al massimo, ben sotto i 20 kHz del datasheet). Lo schermo riduce i disturbi dei VFD e del motore carro.

L’ESP32+MAX485 resta solo come alternativa (`interface: "modbus"`). Documentazione: `docs/HEAD_ENCODERS_RS485.md`.

## Due moduli AL-ZARD

Il DST-1R4P-N ha **4 canali**. L’encoder carro ELTRA usa A, B e Z (3 canali). Le teste usano SX A/B + DX A/B (4 canali). Un solo modulo non basta.

| Modulo | Segnali | GPIO Pi |
|--------|---------|---------|
| AL-ZARD #1 (già previsto) | Carro A, B, Z | 17, 27, 22 |
| AL-ZARD #2 (teste) | SX A, SX B, DX A, DX B | 5, 6, 19, 26 |

Lato uscita AL-ZARD: VCC = 3,3 V (dal Pi), GND comune col Pi. Lato ingresso: 12 V macchina, anodo comune (figura 3 NPN): **12 V su tutti i +**, fasi A/B sui **−**.

## Cavo FR2OHH2R 6×0,50

Due soluzioni valide. Meglio **un cavo per testa** (meno diafonia). Un solo 6 poli condiviso è accettabile se le due teste arrivano nello stesso quadro.

### Un cavo per testa (consigliato)

| Polo | Segnale |
|------|---------|
| 1 | A (verde) |
| 2 | B (bianco) |
| 3 | +12 V (rosso) |
| 4 | GND (nero) |
| 5 | riserva |
| 6 | riserva |
| Treccia | PE **solo in quadro** (massa da un lato) |

### Un cavo 6 poli per entrambe le teste

| Polo | Segnale |
|------|---------|
| 1 | SX A |
| 2 | SX B |
| 3 | DX A |
| 4 | DX B |
| 5 | +12 V comune (rosso SX + rosso DX) |
| 6 | GND comune (nero SX + nero DX) |
| Treccia | PE solo in quadro |

Non collegare A/B a VCC. Non portare i 12 V sui GPIO. Alimentare gli encoder da 12 V quadro, non dal 3,3 V del Pi.

## Cosa fa il software

- `head_encoders.interface` = `gpio` (default in `data/hardware_config.json`)
- `HeadAngleGpioService` decodifica A/B su GPIO 5/6 (SX) e 19/26 (DX)
- `HeadsView` in Semi-automatico ruota le teste sull’angolo **misurato** se l’encoder è online
- Pulsanti **Azzera enc.** in Semi-automatico, con la testa meccanicamente a 0°

Quadratura x4: 360 P/R → 1440 conteggi/giro → 0,25° se il rapporto meccanico è 1:1. Se il verso è invertito, `invert_sx` / `invert_dx`. Se c’è un offset meccanico, `zero_offset_*_deg`.
