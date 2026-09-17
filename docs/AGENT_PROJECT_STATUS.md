# Traccia progetto BLITZ — per l’agente

File di stato per chi riprende il lavoro. Aggiornare questa pagina a ogni intervento sostanziale.

Ultimo aggiornamento: 2026-09-17  
Aggiunto `avvia_blitz.bat` per PC Windows (menu avvio / test / setup).  
PR: https://github.com/house79-gex/blitz/pull/37

## Decisione hardware corrente

| Parte | Scelta |
|--------|--------|
| Carro | Cytron MD25HV 48 V, PWM GPIO 12/13/16, PID software |
| Encoder carro | ELTRA EH63D **NPN 1000 P/R 12 V**, AL-ZARD #1 → GPIO 17/27/22 |
| Encoder teste | Incrementale **AB NPN 600 P/R 12 V**, albero 6 mm, AL-ZARD #2 → GPIO 5/6 e 19/26 |
| Opto | AL-ZARD DST-1R4P-N, **NPN** anodo comune, VCC uscita **3,3 V** |
| Cavo teste | FR2OHH2R 6×0,50 schermato, calza a PE solo in quadro |
| ESP32 / RS485 teste | Non servono (resta `interface=modbus` come alternativa) |
| Freno | Bistabile: OUT5 Mod#2 BLOCCO, OUT6 SBLOCCO (impulso). A fine posa si blocca |

NPN e PNP **non** sono indifferenti: stesso modulo AL-ZARD, cablaggio diverso. L’ELTRA è NPN; comprare le teste NPN.

## Fatto

- Cutlist integrata in Automatico (niente pagina standalone)
- Tipologie e Quote Vani in Home / `main_qt`
- Encoder teste GPIO + docs `docs/HEAD_ENCODERS.md`
- Grafica teste Semi-auto: segue l’angolo **comandato** 0–45° (misura encoder in etichetta)
- Freno: `command_lock_brake` a fine movimento (sim e real) e da Semi-auto
- Mappa coils real allineata allo schema (freno Mod#2 OUT5/OUT6)
- Driver carro: rimosso ogni riferimento e file Leadshine / vecchio driver seriale
- Pagina Tipologie: Header, stato vuoto, toast se la pagina non carica, DB in `data/typologies.db`

## Aperto / da fare sul campo

- Commissioning MD25HV + PID (taratura `pulses_per_mm`, Kp/Ki/Kd)
- Montaggio secondo AL-ZARD e due encoder 600 P/R NPN
- Verifica impulsi freno bistabile (durata 250 ms) con le EV reali
- `planner.plan_ilp` è ancora uno stub; il taglio usa `refiner.py`
- Copertura test complessiva bassa sulle pagine lunghe (Automatico/Semi)
- Arduino MT6701 in alcuni documenti storici: **non** è più il percorso angolo teste

## File chiave

- `data/hardware_config.json` — GPIO, PPR, Modbus I/O
- `qt6_app/ui_qt/machine/real_machine.py` / `simulation_machine.py`
- `qt6_app/ui_qt/widgets/heads_view.py`
- `qt6_app/ui_qt/pages/tipologie_page.py`
- `qt6_app/ui_qt/pages/semi_auto_page.py`
- `docs/HEAD_ENCODERS.md`
- `docs/blitz/recap/schema_elettrico_blitz_recap.md`

## Come lanciare

Su **Windows** (doppio click o da prompt, nella root del repo):

```
avvia_blitz.bat
avvia_blitz.bat avvia
avvia_blitz.bat test
avvia_blitz.bat setup
```

Lo script usa `.venv`, `requirements-windows.txt` e `SIMULATION=1`.

Su Linux:

```
SIMULATION=1 python3 qt6_app/main_qt.py
QT_QPA_PLATFORM=offscreen python3 -m pytest tests --ignore=tests/hardware/test_encoder_live.py --ignore=tests/hardware/test_motor_driver.py
```

Non committare `qt6_app/data/*.db` né sqlite locali.
