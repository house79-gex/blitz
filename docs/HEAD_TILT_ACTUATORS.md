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

## Requisiti attuatore (da misurare sul cilindro attuale)

- Corsa = corsa del cilindro (stessi perni)
- Forza statica ≥ spinta del cilindro a 0° e a 45° (non “coppia” da catalogo: è forza × braccio)
- Velocità: i cilindri sono rapidi; un elettrico è più lento — va bene in setup, da valutare in automatico
- Tenuta a macchina ferma (vite irreversibile o freno): durante il taglio la testa non deve arretrare
- 24 V se resti sul quadro attuale, o 48 V se serve più forza

`data/hardware_config.json` → `head_tilt.mode`:

- `pneumatic_2pos` (default, oggi)
- `linear_actuator` (quando ci sarà il driver; ora è uno stub)

Software: `qt6_app/ui_qt/hardware/head_tilt_drive.py` (`LinearActuatorTiltDrive` non comanda I/O finché `enabled` è false).

## Cosa non fare ora

Non comprare gli attuatori prima di aver misurato corsa e forza sui cilindri, e prima di aver deciso se il fermo 45° resta. L’homing a 0° con i due LR12-04N1 si fa già con i cilindri attuali.
