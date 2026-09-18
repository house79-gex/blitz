# Attuatori lineari per inclinazione teste (imbastitura)

Sì, è fattibile: si sostituiscono i due cilindri (stessi attacchi, stessa corsa) con due attuatori lineari e si usa l’**encoder di rotazione** già previsto come feedback d’angolo.

Oggi l’hardware è **due posizioni** (0° e 45°) con fermo meccanico. Gli attuatori servono solo se vuoi angoli intermedi (es. 10°, 22°, 30°) in continuo.

## Cosa resta uguale

| Pezzo | Ruolo |
|--------|--------|
| Fermo 0° + induttivo LR12-04N1 | Homing (zero encoder) |
| Encoder testa 600 P/R | Misura angolo, anello chiuso |
| Homing unico | Teste a 0° → FC assestato → zero encoder → carro |

Non serve un FC a 45° per l’homing. Il fermo 45° si può lasciare come fine corsa meccanico di sicurezza, oppure togliere se l’attuatore ha corsa limitata in software.

## Cosa cambia

La corsa dell’attuatore **non è lineare** con i gradi (leva / snodo). Non si comanda “mm = k × gradi” alla cieca.

Percorso corretto:

1. Homing a 0° (come oggi).
2. Target in **gradi** (0–45).
3. PID (o tabella mm↔°) sull’encoder testa, l’attuatore è solo il muscolo.

## Requisiti attuatore (misurati sul cilindro attuale)

- Corsa effettiva **85 mm** (0°→45° tra i perni)
- Tempo pneumatico **~4 s**, avanzamento dolce → **~21 mm/s**
- Attuatore candidato: **100 mm**, 48 V, vite autobloccante, IP66 (es. HAKIWO). A 20 mm/s su 85 mm ≈ **4,3 s** (pari al cilindro)
- Forza cilindro Ø 80 mm a 7 bar ≈ **3500 N**; 6500–12000 N di catalogo sono sufficienti
- Tenuta a macchina ferma: vite irreversibile (scheda: autobloccante a motore spento)
- Feedback angolo: encoder testa, non il potenziometro dell’asta

`data/hardware_config.json` → `head_tilt.mode`:

- `pneumatic_2pos` (default, oggi)
- `linear_actuator` (quando ci sarà il driver; ora è uno stub)

Software: `qt6_app/ui_qt/hardware/head_tilt_drive.py` (`LinearActuatorTiltDrive` non comanda I/O finché `enabled` è false).

## Cosa non fare ora

Non comprare 200 mm: la corsa vera è 85 mm. Montare i 100 mm con **~5–10 mm liberi** a ogni estremo, così 0° e 45° arrivano sui fermi testa **prima** dei finecorsa interni dell’asta. Lo zero resta FC 0° + encoder.
