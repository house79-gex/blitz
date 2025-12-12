# Retrofit Troncatrice CNC BLITZ — Riepilogo completo schema elettrico, logiche, cablaggio e tabella morsetti (Rev. aggiornato)

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
Vedi file CSV tabella_morsetti_blitz.csv nel repository (mapping completo).

---

## Allegati
- layout_quadro_blitz_rev5.svg: posizioni guide DIN, canalette 40x40 e linee schematiche.
- tabella_morsetti_blitz.csv: mappatura morsetti.
- mappa_io_modbus_blitz.csv: mappatura I/O Modbus.
- scripts/make_excel_from_csv.py: script per generare Excel con due fogli.
