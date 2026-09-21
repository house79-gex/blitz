# Calibrazione carro e ciclo taglio (micro)

## 1) Zero su FC_MIN (induttivo)

Parametri in **Utility → Encoder & Ingressi → 2.1 Homing carro**:

| Parametro | Ruolo |
|-----------|--------|
| approach_speed | Velocità verso il FC |
| creep_speed | Velocità lenta dopo contatto |
| backoff_mm | Allontana e riavvicina per ripetibilità |
| offset_after_fc_mm | Quota software di zero dopo FC (es. 30 mm) |
| zero_offset_mm | Ritocco fine taratura |
| settle_ms / debounce_ms | Stabilizzazione lettura induttivo |
| use_index_z | Opzionale: impulso Z encoder |

Canale fisico: `digital_inputs.fc_min` (default Modulo #1 IN1).

## 2) Calibrazione lineare a due punti

Su guide tonde la quota encoder può scostarsi sulla lunga distanza.

**Utility → 4. Calibrazione carro**:

1. Vai a ~400 mm → **Cattura encoder** → misura reale (metro/laser)
2. Vai a ~3600 mm → **Cattura encoder** → misura reale
3. **Calcola correzione** → `correction_factor = Δmisura / Δencoder`
4. **Applica e salva** → aggiorna `pulses_per_mm_effective`

Formula:

```
ppm_eff = ppm_nom / correction_factor
quota_corretta ≈ quota_encoder_raw * correction_factor
```

File: `data/hardware_config.json` → sezioni `carriage_homing`, `carriage_calibration`.

## 3) Micro SX/DX = conteggio + fine ciclo

Gli stessi microswitch:

- contano i pezzi
- segnalano rientro testa
- chiudono il ciclo di taglio (`cut_done` / `blade_pulse` software)

Config: `cut_cycle.blade_pulse_source = "piece_count"` (default).

**Quadro elettrico:** l’uscita lama deve essere abilitata solo con lama ON (contatti ausiliari / relè). Il software inibisce le lame via OUT5/OUT6; l’interlock meccanico/elettrico resta in quadro.

### Modalità speciali (proposta operativa)

1. Posiziona step N → aspetta `cut_done` dal micro della testa usata  
2. Conta pezzo solo se la testa non era inibita  
3. Conferma operatore (START) per lo step successivo  
4. Verificare sullo schema i contatti ausiliari lama→EV uscita testa  

Dettaglio cablaggio: `docs/WIRING_SENSORS_RPI.md`.
