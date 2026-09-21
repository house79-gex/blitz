# Traccia progetto BLITZ — per l’agente

File di stato per chi riprende il lavoro. Aggiornare questa pagina a ogni intervento sostanziale.

**Ultimo aggiornamento: 2026-09-21 (locale, PC faleg)**  
Branch: `cursor/integrate-cutlist-heads-encoders-5073`  
PR: https://github.com/house79-gex/blitz/pull/37

Sessione: Configurazione Utility unificata Modulo A/B; encoder teste solo GPIO/rotativi (no Arduino MT6701); OUT7 service inibizione motori lama senza EMG; calibrazione 2 punti carro.

## Decisione hardware corrente

| Parte | Scelta |
|--------|--------|
| Carro | Cytron MD25HV 48 V, PWM GPIO 12/13/16, PID software |
| Encoder carro | ELTRA EH63D **NPN 1000 P/R 12 V**, AL-ZARD #1 → GPIO 17/27/22 |
| Encoder teste | Incrementale **AB NPN 600 P/R 12 V**, albero 6 mm, AL-ZARD #2 → GPIO 5/6 e 19/26 |
| FC 0° teste | Induttivo **LR12-04N1** M12 NPN NO 4 mm, 10–30 V. Due pezzi (SX/DX) |
| Montaggio FC | Fisso sul telaio **di fianco al fermo 0°**, bandiera **acciaio** (la testa è alluminio). Traferro 1–2 mm. A 45° OFF, a 0° ON pieno. Può scattare prima del fermo: va bene |
| I/O FC | Mod#1 **IN4 SX / IN5 DX**, morsetti T95/T96, 24 V F1. Cavo 2 m PVC + prolunga schermata in quadro |
| Zero teste | **Homing unico**: comando 0° → attesa FC assestato (`settle_ms` 400 + encoder fermo) → zero encoder → homing carro. `auto_zero: false` in ciclo |
| Inclinazione oggi | Cilindri 2 pos 0°/45°, impulso EV Mod#1 OUT1–OUT4 (`head_tilt.mode = pneumatic_2pos`) |
| Inclinazione futuro | Attuatori lineari 48 V, **corsa 100 mm** (effettivi 85 mm, ~4 s come i pneumatici). Stub software |
| Opto | AL-ZARD DST-1R4P-N, **NPN** anodo comune, VCC uscita **3,3 V** |
| Cavo teste encoder | FR2OHH2R 6×0,50 schermato, calza a PE solo in quadro |
| ESP32 / RS485 / Arduino MT6701 | **Non usati** — angolo teste solo encoder rotativi + AL-ZARD + GPIO |
| OUT7 Modulo A | Inibizione MOTORI lama (service calibrazione, senza EMG) |
| Freno | Bistabile: OUT5 Mod#2 BLOCCO, OUT6 SBLOCCO (impulso 250 ms). Si blocca **solo** a fine posa in Automatico/Semi/Manuale; **non** a fine homing |

NPN e PNP **non** sono indifferenti. FC teste: **NO**, non NC (un filo staccato non deve sembrare “a 0°”). Non capacitivi, non microswitch sul fermo.

## Homing (un colpo)

1. Impulso EV teste a **0°** (entrambe).
2. Attesa IN4/IN5 ON e angolo fermo (`settle_ms` / `stable_deg`). Se i FC non sono montati, dopo ~1 s si prosegue comunque (`heads_required: false`).
3. `command_zero_head_encoder("both")`.
4. Homing carro (FC_MIN / index Z). **Freno sbloccato** a fine azzeramento.
5. UI Semi-auto: spin angoli a 0° a fine callback.

Non azzerare l’encoder a ogni passaggio sul FC in lavorazione.

## Fatto (software)

- Cutlist in Automatico (niente pagina standalone)
- Tipologie e Quote Vani in Home / `main_qt`
- Encoder teste GPIO, PPR 600, niente DCS810/Leadshine
- Grafica teste Semi-auto: rotazione animata (~12°/s); riquadro angolo **sempre orizzontale** in tempo reale
- Freno: `command_lock_brake` a fine **posa di ciclo**, non a fine homing
- FC teste + helper `HeadHomeLimitHelper` (assestamento, non fronte immediato)
- Homing carro+teste; `PneumaticTwoPosDrive` impulsi 0/45
- Stub `LinearActuatorTiltDrive` + `docs/HEAD_TILT_ACTUATORS.md`
- Corretti Automatico: `tan(90°)` che azzerava le quote, teste a 45° invece di quadro, inhibit lame a 0°, packing BFD e stato ARMING bloccato
- Automatico piano: dopo taglio attende lame rientrate + pausa, sblocca, riposiziona, blocca, pezzo successivo (stessa barra). Nuova barra: F9
- Semi-auto: 0°/45° immediati; spin custom + pulsante **Vai a pos.**
- Piano ottimizzazione: niente pezzi/trapezi a quota 0; ordine barre/pezzi solo misura decrescente; packing ILP/BFD priorità lunghi
- Frizione sempre ON fuori Manuale (`set_mode_context`); morse SW in Auto/Semi/speciali (blocco a posa, sblocco a fine taglio)
- Semi corto/ultra/extra: dopo conferma dialog ora parte davvero (`execute_step_1` + continuazione multi-step in `_tick`)

## Aperto / da fare sul campo

- Commissioning MD25HV + PID (`pulses_per_mm`, Kp/Ki/Kd)
- Secondo AL-ZARD + due encoder 600 P/R NPN
- Due **LR12-04N1** + bandiera acciaio sul fermo 0° (IN4/IN5)
- Verifica impulsi freno 250 ms e EV inclinazione 0°/45°
- Misurati cilindri teste: **85 mm** in **~4 s** (dolce). Attuatore 100 mm / 20 mm/s è in pari; non 200 mm
- `planner.plan_ilp` è stub; Automatico usa `refiner.pack_bars_knapsack_ilp`
- Automatico: angoli **0–45°** (90° = quadro). Sequenza taglio→posa su tutta la barra; F9 per barra successiva
- Copertura test bassa su Automatico/Semi
- Documenti storici Arduino MT6701 / ESP32 RS485: **obsoleti** — percorso ufficiale GPIO
- Utility → **Configurazione** unificata (Modulo A/B, encoder, calibrazione, service OUT7)

## File chiave

- `docs/AGENT_PROJECT_STATUS.md` — questo file
- `data/hardware_config.json` — `head_home_fc`, `head_tilt`, `head_tilt_actuators`
- `qt6_app/ui_qt/hardware/head_home_fc.py`
- `qt6_app/ui_qt/hardware/head_tilt_drive.py`
- `qt6_app/ui_qt/machine/real_machine.py` / `simulation_machine.py`
- `qt6_app/ui_qt/pages/semi_auto_page.py`
- `docs/MANUALE_CONFIGURAZIONE.md` — manuale Utility Configurazione (A/B, service OUT7)
- `docs/HEAD_ENCODERS.md`
- `docs/HEAD_TILT_ACTUATORS.md`
- `docs/blitz/recap/schema_elettrico_blitz_recap.md`
- `docs/blitz/tables/mappa_io_modbus_blitz.csv` / `tabella_morsetti_blitz.csv`

## Come lanciare

Windows (root repo):

```
avvia_blitz.bat
avvia_blitz.bat avvia
avvia_blitz.bat test
avvia_blitz.bat setup
```

`.venv` + `requirements-windows.txt` + `SIMULATION=1`. `PYTHONPATH` = repo + `qt6_app`.

Linux:

```
SIMULATION=1 python3 qt6_app/main_qt.py
QT_QPA_PLATFORM=offscreen python3 -m pytest tests --ignore=tests/hardware/test_encoder_live.py --ignore=tests/hardware/test_motor_driver.py
```

Non committare `qt6_app/data/*.db`, `.venv/`, sqlite locali.
