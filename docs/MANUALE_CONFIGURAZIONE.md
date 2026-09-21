# Manuale — Utility → Configurazione (Modulo A / Modulo B)

Guida operativa per parametrizzare hardware e sensori della troncatrice BLITZ senza passare da file JSON a mano.

## Dove si trova

Nel menu **Utility** la voce **Configurazione** apre un’unica scheda organizzata per categorie:

| Scheda | Contenuto |
|--------|-----------|
| **0. Bus** | Porta RS485, baud, indirizzi Modulo A (ID 1) e Modulo B (ID 2) |
| **1. Encoder** | Carro ELTRA (AL-ZARD #1) e teste (encoder rotativi + AL-ZARD #2 → GPIO) |
| **2. Sensori / FC** | Homing FC_MIN, FC_MAX, zero teste 0°, micro taglio/conteggio |
| **3. Waveshare A/B** | Mappa canale→segnale (8+8 ingressi) e documentazione uscite |
| **4. Calibrazione** | Due punti carro + modalità servizio misura lama↔lama |
| **5. Monitor** | Stato live (se collegato) |
| **6. Documentazione** | Link a schemi e questo manuale |

**Nomenclatura:** Modulo **A** = Waveshare ID 1 (inclinazioni, FC, inibizioni lame/motori). Modulo **B** = Waveshare ID 2 (morse, freno, frizione, conteggi).

---

## Sblocco modifica Waveshare

La mappa canali in **3. Waveshare A/B** è in **sola lettura** di default, per evitare spostamenti accidentali.

1. Premi **ABILITA MODIFICA** (diventa **BLOCCA MODIFICA** quando sbloccato).
2. Assegna i segnali logici ai canali IN1–IN8 di A e B.
3. Per i micro NC (conteggio) deseleziona **active high**.
4. **Salva** in fondo alla pagina Configurazione.
5. Premi di nuovo il pulsante per **bloccare**.

I tooltip sui controlli spiegano il significato di ogni parametro.

---

## Encoder inclinazione teste (rotativi)

Percorso ufficiale (unico configurabile):

```text
Encoder rotativo AB NPN 12 V → cavo schermato → AL-ZARD #2 → GPIO Pi
  SX: GPIO 5 / 6
  DX: GPIO 19 / 26
```

- **Non** si usa più Arduino Nano + encoder magnetici MT6701.
- **Non** si configura interfaccia Modbus/ESP32 per l’angolo teste.
- PPR tipico 600, quadratura ×4.
- Zero meccanico: FC induttivi su Modulo A IN4 (SX) e IN5 (DX); azzeramento in **homing** a testa ferma.

Dettaglio cablaggio: `docs/HEAD_ENCODERS.md`.

---

## Calibrazione lineare carro (due punti)

1. Homing completo (FC_MIN + zero teste).
2. In **4. Calibrazione**: vai a quota **vicino** (~400 mm), cattura encoder, misura con metro/laser, inserisci mm reali.
3. Ripeti sul punto **lontano** (~3600 mm).
4. **Calcola correzione** → fattore = Δmisura / Δencoder; ppm effettivo = ppm_nom / fattore.
5. **Applica e salva**.

Su guide tonde la scala può scostarsi sulla lunga distanza: i due punti correggono la deriva.

---

## Modalità servizio — misura lama↔lama (senza emergenza)

Il selettore a chiave sulla pulsantiera mette l’**emergenza** e blocca anche il carro: non serve per parametrizzare.

In Configurazione → Calibrazione:

1. **INIBISCI MOTORI LAMA (service ON)** — attiva **OUT7 Modulo A**: interrompe le bobine dei teleruttori motori lama. I motori non possono partire; **carro e teste restano movimentabili**.
2. **Prepara uscita lame per misura** — rilascia l’inibizione EV lama (OUT5/OUT6). In campo: discesa pneumatica dalla **pulsantiera** (motori già spenti).
3. Misura con laser la distanza lama↔lama / parametri.
4. **Esci da service** — ripristina uscite.

Cablaggio quadro: OUT7 deve pilotare un relè in serie alle bobine dei teleruttori motori lama (non sulla catena EMG).

---

## Micro taglio / conteggio

I micro SX/DX (default Modulo B IN1/IN2, NC) contano i pezzi **e** segnalano rientro / fine ciclo (`cut_cycle.blade_pulse_source = piece_count`).

L’uscita lama resta abilitata solo con lama ON (interlock elettrico in quadro).

---

## File e documentazione correlata

| File | Ruolo |
|------|--------|
| `data/hardware_config.json` | Persistenza parametri |
| `docs/WIRING_SENSORS_RPI.md` | Cablaggio sensori / GPIO |
| `docs/HEAD_ENCODERS.md` | Encoder teste |
| `docs/CALIBRATION_CARRIAGE.md` | Dettaglio calibrazione carro |
| `docs/blitz/tables/mappa_io_modbus_blitz.csv` | Mappa I/O Modbus |
| `docs/blitz/recap/schema_elettrico_blitz_recap.md` | Schema elettrico riepilogo |

Dopo ogni salvataggio in Utility, riavviare l’applicazione se il motion stack o gli encoder GPIO non rileggono a caldo tutti i parametri.
