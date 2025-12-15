# Retrofit Troncatrice CNC BLITZ — Riepilogo completo schema elettrico, logiche, cablaggio e tabelle (Rev. aggiornato)

Dimensionamento pannello: 600 mm (L) x 850 mm (H)
Layout 3 zone: Zona 1 = Alimentazione + portafusibili; Zona 2 = Logica (RPi + I/O Waveshare); Zona 3 = Driver + Morsettiere
Canalette 40x40: laterali SX/DX e orizzontali per ogni zona. Guide DIN allineate con le canalette.

1) Ruoli di controllo e sicurezza
- Catena di sicurezza (fungo + logiche cablate macchina): totalmente hardware, indipendente dal software.
- Taglio (discesa/rientro lama): gestito 100% dalla pulsantiera mobile; il software non comanda il taglio.
- Inibizione lama: il software può interrompere in serie la bobina EV lama SX/DX (contatto NC) in modalità dedicate (es. “ultra corta”).
- Inclinazione teste, freno carro, frizione: pilotabili via software per setup/posizionamento.
- Morse (apri/chiudi): gestibili via software in specifiche modalità operative (fuori ciclo o speciali) con inibizione hardware selettiva per lato (es. in “ultra corta” apri DX, inibisci apertura SX).

2) Architettura elettrica

2.1 Alimentazioni e protezioni (portafusibili DIN)
- 230VAC → Sezionatore/MT → Alimentatori DC:
  - 48V: Mean Well TDR-960-48 → Driver Leadshine DCS810
  - 24V: Mean Well SDR-240-24 → Rami con portafusibili DIN:
    - F1: 24V I/O (moduli Waveshare, sensori 24V)
    - F2: 24V Elettrovalvole Testa SX (inclinazioni, morsa SX)
    - F3: 24V Elettrovalvole Testa DX (inclinazioni, morsa DX)
    - F4: 24V Frizione + Freno
  - 12V: Mean Well SDR-120-12 → Ausiliari
  - 5V: Mean Well MDR-10-5 → Arduino MT6701, futuri 5V
- Raspberry Pi 5: alimentatore originale USB‑C su presa 230V interna quadro.
- Fusibili: dimensionare su assorbimenti reali (bobine EV ~0.2–0.5 A); tipicamente 1–2 A per rami EV/I/O; margine 25–50%. Preferire portafusibili con indicatore di guasto.

2.2 Comunicazioni
- RPi 5 + Waveshare USB 4-CH:
  - RS232 → DCS810 (comandi posizione/parametri).
  - RS485 (Modbus RTU) → Modulo I/O #1 (ID 1) → Modulo I/O #2 (ID 2) → Arduino SX (ID 10) → Arduino DX (ID 11); ultimo nodo con terminazione 120 Ω.
- Cavi RS485: twistati, schermati; calza a PE lato quadro.

2.3 Motion e attuatori
- Leadshine DCS810 (48V) + Motore DC PENTA 48V; encoder ELTRA su driver per chiusura anello.
- Frizione 24V: ON = trazione attiva; OFF = carro libero (movimento manuale). Comandata via relè Modbus.
- Freno 24V: bistabile doppia bobina (blocco/sblocco) → 2 uscite relè.
- Inclinazioni teste: doppia bobina (0°/45°) → 2 uscite relè per testa.
- Morse SX/DX: doppia bobina (chiudi/apri), con gestione software in modalità speciali e inibizione hardware per lato.

2.4 Sensori e ingressi
- FC_MIN (induttivo NPN NO) → IN digitale (homing/min).
- FC_MAX (microswitch NA) → IN digitale (max).
- Conteggio pezzi SX/DX (microswitch NC) → IN digitali (conteggio su fronte di apertura con debounce software).
- Stato emergenza (contatto ausiliario NO consigliato) → IN digitale (solo supervisione).
- Angolo teste: MT6701 → Arduino Nano (SPI) → RS485 (MAX485) → Modbus registri.

3) Logiche operative

- Emergenza: se attiva, software in stato sicuro; disabilita comandi non critici; nessun intervento sul ciclo di taglio.
- Homing asse: verso MIN (~0.5 m/min), trigger FC_MIN → inversione lenta (~0.1 m/min), posizionamento a 0 con offset (~30 mm).
- Taglio standard: 100% pulsantiera; il software non interviene.
- Inibizione lama: contatto NC in serie alla bobina EV — quando attivo, la lama non scende anche a pulsante premuto.
- Inclinazione teste: comandi 0°/45° via relè (impulsi), solo fuori dal ciclo e con consensi.
- Freno carro: blocco/sblocco via relè (impulsi), con interlock EMERG/consensi.
- Frizione: ON/OFF con consensi (non disinserire con asse in moto).
- Morse — gestione software in modalità speciali + inibizione hardware per lato:
  - Esempio modalità “ultra corta”:
    - Morsa DX: consentita apertura (software attiva bobina APRI DX).
    - Morsa SX: inibita hardware l’apertura (contatto NC in serie sul ramo APRI SX), quindi non si apre anche se arriva comando (pulsantiera o software).
  - In modalità normale: nessuna inibizione; le morse restano sotto autorità pulsantiera (ciclo). Il software può comandarle solo se la modalità consente (setup/speciale) e non è in corso un taglio.

Interlock software raccomandati:
- Disabilitare comandi morse/inclinazioni/freno/frizione quando EMERG attiva o taglio in corso.
- Consentire comandi software solo in modalità autorizzate (setup/speciali).

4) Mappatura I/O (moduli Waveshare)

Modulo I/O + Relè #1 (ID 1) — Inclinazioni / Lame / Sicurezze
- IN:
  - IN1: FC_MIN (NPN NO)
  - IN2: FC_MAX (Microswitch NA)
  - IN3: Stato EMERG (NO → 1=OK, 0=EMERG)
  - IN4–IN8: riserva
- OUT (relè):
  - OUT1: Testa SX 45° (bobina A)
  - OUT2: Testa SX 0°  (bobina B)
  - OUT3: Testa DX 45° (bobina A)
  - OUT4: Testa DX 0°  (bobina B)
  - OUT5: INIBIZIONE LAMA SX (contatto NC in serie alla bobina EV)
  - OUT6: INIBIZIONE LAMA DX (contatto NC in serie alla bobina EV)
  - OUT7–OUT8: riserva

Modulo I/O + Relè #2 (ID 2) — Morse / Frizione / Freno / Conteggi
- IN:
  - IN1: Conteggio pezzi SX (Microswitch NC)
  - IN2: Conteggio pezzi DX (Microswitch NC)
  - IN3–IN8: riserva
- OUT (relè):
  - OUT1: Morsa SX CHIUDI (bobina A)
  - OUT2: Morsa SX APRI   (bobina B) — linea con INIBIZIONE HW (contatto NC in serie) attivabile da software
  - OUT3: Morsa DX CHIUDI (bobina A)
  - OUT4: Morsa DX APRI   (bobina B) — linea normalmente non inibita in “ultra corta”
  - OUT5: Freno BLOCCO    (bobina A)
  - OUT6: Freno SBLOCCO   (bobina B)
  - OUT7: Frizione ON/OFF (24V)
  - OUT8: riserva

Implementazione pratica inibizione HW morse:
- Ogni ramo “APRI” (DX/SX) ha un contatto relè NC in serie, alimentato dal 24V del ramo EV corrispondente (F2/F3).
- In “ultra corta”: apri DX normalmente; mantieni aperto (logica attiva) il contatto NC sul ramo APRI SX → morsa SX non si apre.

5) Linee e cablaggi principali
- 230VAC: ingresso → sezionatore/MT → alimentatori DC + presa 230V RPi PSU.
- 48V DC: TDR-960 → DCS810 (cavi corti, separati).
- 24V DC:
  - SDR-240 → Portafusibili (F1..F4) → rami:
    - F1 → Moduli I/O/sensori
    - F2 → EV SX (inclinazioni + morsa SX)
    - F3 → EV DX (inclinazioni + morsa DX)
    - F4 → Frizione/Freno
  - 0V comune su barra (punto stella).
- 12V DC: SDR-120 → morsettiera AUX.
- 5V DC: MDR-10 → Arduino/ESP32; RPi su PSU originale.
- RS232: RPi ↔ DCS810 (cavo schermato).
- RS485: RPi → Mod#1 → Mod#2 → Arduino SX → Arduino DX; terminazione 120 Ω ultimo nodo.
- Encoder motore ELTRA: su DCS810 (schermato; calza a PE lato driver).
- Inibizione lama: contatto NC in serie al positivo bobina EV (SX e DX).
- Inibizione morse per lato: contatto NC in serie al positivo del ramo “APRI” (SX o DX) secondo modalità.

EMC:
- Separare 230VAC/potenze da segnali/RS485; diodi flyback su bobine; schermi a PE lato quadro.

6) Tabella morsetti (riassunto)
Vedi file CSV ../tables/tabella_morsetti_blitz.csv nel repository (mapping completo).

---

## Schema di principio — Inibizione APRI morsa per lato

In modalità operative speciali (es. "ultra corta"), può essere necessario inibire l'apertura di una morsa mentre si consente l'altra. L'inibizione è realizzata via hardware (contatto NC in serie) per garantire sicurezza indipendente dal software.

```
  +24V (F2/F3)
      │
      ├──[Relè inibizione]──NC────[Bobina APRI morsa SX/DX]───GND
      │           (ID 2)
      │
    (Normale: NC chiuso → morsa può aprire)
    (Inibito: NC aperto  → morsa NON può aprire)
```

Esempio modalità "ultra corta":
- Morsa DX: consentita apertura (NC chiuso, relè disattivato)
- Morsa SX: inibita apertura (NC aperto, relè attivato) → la bobina APRI SX non può essere alimentata

Comando software:
- Software attiva/disattiva il relè di inibizione secondo la modalità operativa
- Anche con comando APRI attivo (da pulsantiera o software), la morsa inibita non si apre
- Garantisce protezione hardware su cicli con pezzo "ultra corto" bloccato su un solo lato

---

## Encoder ELTRA — caratteristiche e cablaggio
- Tipologia: Incrementale (serie tipiche E6/E8)
- Alimentazione: 5V DC (±5%)
- Uscite: Canali A, B (quadratura); Indice Z opzionale
- Segnali: TTL single-ended oppure Line Driver (differenziale). Preferibile Line Driver su tratte >1–2 m
- Risoluzione: da 500 a 1024 PPR (impostare secondo cinematica e requisiti del driver)
- Cablaggio su DCS810:
  - 5V → pin alimentazione encoder
  - GND → ritorno encoder
  - EA (A), EB (B), EZ (Z) → ingressi encoder del driver
  - Schermo/calza → PE lato driver (un solo lato)
- Raccomandazioni EMC: cavo schermato, coppie twistate per A/B; separare da linee 48V e bobine EV

---

## Mappa indirizzi Modbus dettagliata

### Moduli I/O Waveshare (Modbus RTU, ID 1 e ID 2)

**Ingressi digitali (DI)** e **Coils (Uscite relè)**:

**Modulo #1 (ID 1) — Inclinazioni / Lame / Sicurezze**
- DI (Discrete Input):
  - Indirizzo 0: IN1 (FC_MIN)
  - Indirizzo 1: IN2 (FC_MAX)
  - Indirizzo 2: IN3 (EMERG Stato)
  - Indirizzi 3–7: IN4–IN8 (riserva)
- Coils (Uscite relè):
  - Indirizzo 0: OUT1 (Testa SX 45°)
  - Indirizzo 1: OUT2 (Testa SX 0°)
  - Indirizzo 2: OUT3 (Testa DX 45°)
  - Indirizzo 3: OUT4 (Testa DX 0°)
  - Indirizzo 4: OUT5 (INIBIZIONE LAMA SX)
  - Indirizzo 5: OUT6 (INIBIZIONE LAMA DX)
  - Indirizzi 6–7: OUT7–OUT8 (riserva)

**Modulo #2 (ID 2) — Morse / Frizione / Freno / Conteggi**
- DI (Discrete Input):
  - Indirizzo 0: IN1 (Conteggio pezzi SX)
  - Indirizzo 1: IN2 (Conteggio pezzi DX)
  - Indirizzi 2–7: IN3–IN8 (riserva)
- Coils (Uscite relè):
  - Indirizzo 0: OUT1 (Morsa SX CHIUDI)
  - Indirizzo 1: OUT2 (Morsa SX APRI)
  - Indirizzo 2: OUT3 (Morsa DX CHIUDI)
  - Indirizzo 3: OUT4 (Morsa DX APRI)
  - Indirizzo 4: OUT5 (Freno BLOCCO)
  - Indirizzo 5: OUT6 (Freno SBLOCCO)
  - Indirizzo 6: OUT7 (Frizione ON/OFF)
  - Indirizzo 7: OUT8 (riserva)

### Arduino Nano + MT6701 (Modbus RTU, ID 10 e ID 11)

**Holding Registers (HR)** — Angolo encoder magnetico:

**Arduino SX (ID 10)**
- HR 0: Angolo_raw (0–16383, 14 bit da MT6701)
- HR 1: Angolo_deg (0–359, gradi interi)
- HR 2: Status (bit flag: 0=OK, 1=errore SPI, 2=timeout)

**Arduino DX (ID 11)**
- HR 0: Angolo_raw (0–16383, 14 bit da MT6701)
- HR 1: Angolo_deg (0–359, gradi interi)
- HR 2: Status (bit flag: 0=OK, 1=errore SPI, 2=timeout)

**Lettura da RPi**:
- Funzione 0x01 (Read Coils): leggere stato uscite
- Funzione 0x02 (Read Discrete Inputs): leggere ingressi digitali
- Funzione 0x03 (Read Holding Registers): leggere angolo Arduino MT6701
- Funzione 0x05 (Write Single Coil): attivare/disattivare relè singoli
- Timeout: 500 ms; retry: 2 volte

---

## Elenco cavi consigliati

Dimensionamento e schermatura per ridurre EMI e garantire affidabilità:

| Applicazione | Sezione | Schermatura | Colori / Note |
|---|---|---|---|
| **230VAC** | 1.5–2.5 mm² | NO | Nero (L), Blu (N), Giallo/Verde (PE). Separare da segnali. |
| **48V DC Driver** | 1.5 mm² | NO | Rosso (+48V), Nero (0V). Tratte corte (<1 m), coppie twistate. |
| **24V EV/I/O** | 0.5–1 mm² | NO | Rosso (+24V), Blu (0V). Rami F1–F4 su portafusibili DIN. |
| **24V Sensori (NPN/PNP)** | 0.25–0.5 mm² | SÌ (se >2 m) | Marrone (+24V), Blu (0V), Nero (OUT). Calza a PE quadro. |
| **RS485 Modbus** | 0.25–0.5 mm² | SÌ | Twistato (A, B), schermo. Calza a PE lato quadro (un solo lato). Terminazione 120Ω ultimo nodo. |
| **RS232 Driver DCS810** | N/A | SÌ | Cavo schermato 3 fili (TXD, RXD, GND). Lunghezza <5 m. |
| **Encoder ELTRA** | 0.15–0.25 mm² | SÌ | 5V (Rosso), GND (Nero), A/B/Z (coppie twistate). Calza a PE lato driver. |
| **PE (Terra protezione)** | 1.5–2.5 mm² | NO | Giallo/Verde. Barra PE quadro; un punto stella. |

**Note EMC**:
- Separare 230VAC e 48V da segnali/RS485 in canalette distinte (40x40 laterali vs centrali).
- Diodi flyback su bobine EV/frizione/freno (se non integrati nei moduli Waveshare).
- Schermi/calze a PE lato quadro (un solo lato) — evitare loop di massa.
- Cavi di potenza corti e paralleli (andata/ritorno vicini per ridurre loop).
- RS485: terminazione 120Ω solo ultimo nodo; no stub lunghi.

---

## Morsetti Driver Leadshine DCS810 — piedinatura
- Alimentazione: +VDC (+48V), GND (0V)
- Motore: M+ (U+), M− (U−)
- Encoder: 5V, GND, EA (A), EB (B), EZ (Z)
- I/O: ENA+/ENA− (enable), ALM+/ALM− (allarme)
- RS232: TXD/RXD/GND (comunicazione con RPi/Waveshare)

---

## Allegati
- ../layouts/layout_quadro_blitz_rev5.svg: posizioni guide DIN, canalette 40x40 e linee schematiche.
- ../tables/tabella_morsetti_blitz.csv: mappatura morsetti.
- ../tables/mappa_io_modbus_blitz.csv: mappatura I/O Modbus.
- ../tables/morsetti_driver_dcs810.csv: morsetti driver DCS810.
- ../scripts/make_excel_from_csv.py: script per generare Excel con tre fogli (Morsetti, I/O Modbus, Lista componenti).
- ../scripts/make_pdfs.py: script per generare PDF con tabelle multipage (morsetti, Modbus, driver, lista componenti).
- ../scripts/requirements-mapping.txt: dipendenze per Excel/PDF.
