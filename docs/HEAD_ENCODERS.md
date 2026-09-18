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
- `HeadsView` in Semi-automatico ruota le teste sull’angolo **comandato**; la misura encoder è in etichetta
- Finecorsa 0° su IN4/IN5: in **homing** si va a 0°, si attende l’assestamento, si azzerano gli encoder (carro + teste in un colpo)

Quadratura x4: 600 P/R → 2400 conteggi/giro → 0,15° se il rapporto meccanico è 1:1. Se il verso è invertito, `invert_sx` / `invert_dx`. Se c’è un offset meccanico, `zero_offset_*_deg`.

## Zero 0°: pistone 0°/45° e dove mettere il sensore

Le teste non sono un asse analogico: un pistone pneumatico le porta da un fermo all’altro (0° e 45°). I due blocchi meccanici **sono gli stop**. L’encoder incrementale serve a misurare; lo zero software sta solo sul lato 0°.

**Che sensore usare**

| Tipo | In questa macchina |
|------|---------------------|
| Induttivo M12 NPN NO 24 V (sn 4 mm, come FC_MIN) | **Sì — questa è la scelta** |
| Microswitch a leva | No: truciolo, olio, urto sul fermo lo distruggono |
| Capacitivo | No: alluminio, olio e polvere lo fanno scattare a vuoto |
| Magnetico/reed | Accettabile solo se non trovi spazio per l’induttivo |

Un solo sensore per testa, **solo a 0°**. A 45° il fermo meccanico basta: dopo lo zero a 0° l’encoder (o il comando 45°) dice già dov’è. Un secondo FC a 45° serve solo se un giorno vuoi l’interblocco «non tagliare se non è seduta».

**Dove posizionarlo**

Fisso sul telaio, **di fianco al fermo 0°**, non sul pistone e non come paraurti sul blocco.

```
  [testa ruota 45° → 0°]
       bandiera in acciaio ──►  (induttivo M12 sul telaio)
                                      gap 1–2 mm
       blocco meccanico 0°  ◄── la testa ci arriva e si ferma
```

- Bandiera (lamierino 2–3 mm) sul corpo testa, o la fusione se è ferrosa.
- Traferro 1–2 mm con M12 sn 4 mm; a testa **seduta sul fermo 0°** la faccia del sensore deve essere ben coperta (segnale pieno ON, non sul filo).
- Allinea così: a 45° il sensore è sicuramente OFF; durante gli ultimi gradi verso 0° può già andare ON. **Va bene.** Non inseguire il millimetro del fermo.
- Non mettere il sensore sul fermo come cosa da urtare. Il pistone deve battere sul blocco meccanico, il sensore guarda la bandiera da lato.

**Perché un ritardo (e non lo zero al contatto)**

Se il FC scatta 5–15° prima, il pistone sta ancora spingendo. Azzzerare lì darebbe 0° troppo presto, poi l’encoder salirebbe di quei gradi contro il blocco.

Questo ritardo sta **nell’homing** (un colpo: teste a 0° + carro), non a ogni movimento in Semi-automatico:

1. comando 0° (impulso EV);
2. FC ON e encoder fermo per `settle_ms` (400 ms);
3. azzera gli encoder;
4. homing carro.

I pulsanti **Azzera enc.** restano solo per taratura a banco. Futuro angolo continuo: `docs/HEAD_TILT_ACTUATORS.md`.

Cablaggio: +24 V F1, 0 V, uscita NPN su **IN4 SX / IN5 DX**. Sensori: LR12-04N1 (M12 NPN NO 4 mm) + bandiera acciaio.

Configurazione: `head_home_fc` (`settle_ms`, `homing_timeout_s`). `auto_zero` resta false.
