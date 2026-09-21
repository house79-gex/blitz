# Cablaggio sensori, encoder e integrazione Raspberry Pi 5

Guida operativa per collegare encoder, sensori di prossimità e ingressi digitali all’impianto BLITZ.  
Configurazione software: **Utility → Encoder & Ingressi** (file `data/hardware_config.json`).

## Architettura a colpo d’occhio

```
                    ┌─────────────────────────────┐
  48V ──────────────┤  Cytron MD25HV              │── Motore carro
                    └──────────▲──────────────────┘
                               │ PWM/DIR/EN
                               │ GPIO 12 / 13 / 16
                    ┌──────────┴──────────────────┐
                    │     Raspberry Pi 5           │
                    │  pigpiod + BLITZ Qt6         │
                    └──┬───────────────┬──────────┘
           GPIO 3,3 V  │               │ USB RS485
     ┌─────────────────┼───────┐       │
     │                 │       │       ▼
 AL-ZARD #1        AL-ZARD #2   │  Waveshare I/O #1 + #2
 carro A/B/Z       teste A/B    │  (Modbus RTU ID 1/2)
     ▲                 ▲        │       ▲
  ELTRA 12V      Encoder 12V    │   Sensori 24 V (F1)
  NPN            teste NPN      │   induttivi / micro
```

**Regola d’oro:** mai 12 V o 24 V sui GPIO del Pi. Encoder NPN → optoisolamento AL-ZARD → 3,3 V. Sensori campo → moduli Waveshare (24 V).

## Raspberry Pi — pin usati

| Funzione | GPIO BCM | Note |
|----------|----------|------|
| MD25HV PWM | 12 | 20 kHz |
| MD25HV DIR | 13 | |
| MD25HV EN | 16 | |
| Encoder carro A | 17 | via AL-ZARD #1 |
| Encoder carro B | 27 | via AL-ZARD #1 |
| Encoder carro Z | 22 | via AL-ZARD #1 |
| Encoder testa SX A | 5 | via AL-ZARD #2 |
| Encoder testa SX B | 6 | via AL-ZARD #2 |
| Encoder testa DX A | 19 | via AL-ZARD #2 |
| Encoder testa DX B | 26 | via AL-ZARD #2 |

Avvio demone: `sudo pigpiod`. Alimentazione Pi: PSU ufficiale USB‑C su presa 230 V interna quadro.

## Encoder carro (ELTRA EH63D)

1. Alimentare l’encoder a **12 V** quadro (non dal 3,3 V Pi).
2. A/B/Z (NPN) → ingressi AL-ZARD #1 (anodo comune: **12 V su tutti i +**, fasi sui **−**).
3. Uscite AL-ZARD (VCC = 3,3 V dal Pi, GND comune) → GPIO 17 / 27 / 22.
4. Schermo cavo → PE **solo in quadro**.

Parametri in Utility: PPR, quadratura, Ø puleggia, impulsi/mm.

## Encoder inclinazione teste

Vedi anche `docs/HEAD_ENCODERS.md`.

1. Un cavo schermato per testa (consigliato) FR2OHH2R 6×0,50.
2. 12 V encoder → AL-ZARD #2 (4 canali: SX A/B, DX A/B).
3. Uscite 3,3 V → GPIO 5/6 e 19/26.
4. Zero meccanico: induttivi 0° (sotto), non azzerare al primo contatto FC.

## Sensori di prossimità (induttivi)

Ci sono **più** induttivi, non solo i FC 0° teste:

| Sensore | Dove | Segnale | Default Waveshare |
|---------|------|---------|-------------------|
| FC_MIN | Homing carro | `fc_min` | Modulo #1 IN1 |
| FC testa SX 0° | Blocco meccanico SX | `head_sx_zero` | Modulo #1 IN4 |
| FC testa DX 0° | Blocco meccanico DX | `head_dx_zero` | Modulo #1 IN5 |

| Voce | Specifica |
|------|-----------|
| Tipo | Induttivo M12 NPN NO 24 V (es. LR12-04N1, sn 4 mm) |
| Posizione teste | Fisso sul telaio, di fianco al fermo 0° |
| Target | Bandiera acciaio 2–3 mm sulla testa |
| Gap | 1–2 mm a testa seduta sul blocco |
| Alimentazione | +24 V ramo F1, 0 V comune |

In Utility: categoria **2. Sensori / FC** (sottocategorie Homing / Limite max / Zero teste) e assegnazione canali in **3. Waveshare I/O** (tutti gli 8+8 canali, comprese le riserve).


## Ingressi ciclo (modulo I/O #2)

| IN | Segnale logico (default) | Uso |
|----|--------------------------|-----|
| IN1 | piece_count_sx | Micro NC conteggio SX |
| IN2 | piece_count_dx | Micro NC conteggio DX |
| IN3 | blade_pulse | Impulso fine taglio / pedale |
| IN4 | start_pressed | START / conferma sequenza |
| IN5 | dx_blade_out | Uscita lama DX |

La mappa è modificabile in **Utility → Encoder & Ingressi → Ingressi digitali**.  
In Automatico/Semi il software legge `blade_pulse` e `start_pressed` tramite `get_input()` (modalità reale).

## Checklist montaggio

1. [ ] `pigpiod` attivo  
2. [ ] AL-ZARD #1 e #2 con VCC uscita a 3,3 V  
3. [ ] Nessun 12/24 V sui GPIO  
4. [ ] Schermi encoder a PE quadro (un solo lato)  
5. [ ] Induttivi 0° allineati (ON a testa seduta, OFF a 45°)  
6. [ ] RS485 terminato 120 Ω sull’ultimo nodo  
7. [ ] Utility → Monitor live: verificare ON/OFF muovendo i sensori  
8. [ ] Salvata `hardware_config.json` e riavvio app dopo cambio GPIO  

## Documenti correlati

- Schema elettrico: `docs/blitz/recap/schema_elettrico_blitz_recap.md`
- SVG cablaggio: `docs/blitz/layouts/wiring_sensors_rpi.svg`
- Mappa Modbus CSV: `docs/blitz/tables/mappa_io_modbus_blitz.csv`
- Encoder teste: `docs/HEAD_ENCODERS.md`
- Hardware stack: `qt6_app/ui_qt/hardware/README.md`
