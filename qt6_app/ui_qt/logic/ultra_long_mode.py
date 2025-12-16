"""
Modalità Ultra-Lunga per pezzi > corsa utile macchina. 

Sequenza 3 step:
1. Intestatura con TESTA MOBILE DX a posizione sicurezza
2. Arretramento testa DX (trascina barra con pressore DX)
3. Posizionamento finale e taglio con TESTA FISSA SX

Esempio: Pezzo 5000mm (corsa max 4000mm)
- Step 1: Testa DX @ 2000mm, taglia con lama DX (intestatura)
- Step 2: Testa DX arretra a 1000mm (offset 1000mm)
- Step 3: Testa DX @ 4000mm, taglia con lama SX (finale)
- Risultato: 4000mm + 1000mm = 5000mm
"""
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger("ultra_long_mode")


@dataclass
class UltraLongConfig:
    """Configurazione modalità ultra-lunga."""
    max_travel_mm: float = 4000.0      # Corsa utile macchina
    stock_length_mm: float = 6500.0    # Lunghezza stock
    safe_head_mm: float = 2000.0       # Posizione intestatura
    min_offset_mm: float = 500.0       # Offset minimo sicurezza


@dataclass
class UltraLongSequence:
    """Sequenza step per pezzo ultra-lungo."""
    enabled: bool
    target_length_mm: float
    
    # === STEP 1: INTESTATURA con TESTA MOBILE DX ===
    pos_head_cut_dx: float              # Posizione testa DX (es.  2000mm)
    angle_head_cut_dx: float            # Angolo intestatura su TESTA DX
    
    # Lame Step 1
    blade_left_inhibit: bool = True     # ❌ Lama SX (FISSA) inibita
    blade_right_enable: bool = True     # ✅ Lama DX (MOBILE) abilitata
    
    # Morse Step 1
    morse_left_lock: bool = True      # ✅ Morsa SX bloccata
    morse_right_lock: bool = True     # ✅ Morsa DX bloccata (ENTRAMBI!)
    
    # === STEP 2: ARRETRAMENTO TESTA DX ===
    offset_mm: float                    # Offset arretramento (es. 1000mm)
    pos_after_retract_dx: float         # Posizione dopo arretramento (es. 1000mm)
    
    # Morse Step 2 (PRIMA movimento)
    morse_left_lock_step2: bool = True    # ✅ SX rimane bloccato
    morse_right_release_step2: bool = True # ❌ DX sbloccato (testa scorre)
    morse_switch_delay_ms: int = 100      # Ritardo sblocco DX
    
    # === STEP 3: TAGLIO FINALE con TESTA FISSA SX ===
    pos_final_cut_dx: float             # Posizione finale DX (es. 4000mm)
    angle_final_cut_sx: float           # Angolo finale su TESTA SX
    
    # Lame Step 3
    blade_left_enable: bool = True      # ✅ Lama SX (FISSA) abilitata
    blade_right_inhibit_step3: bool = True # ❌ Lama DX (MOBILE) inibita
    
    # Morse Step 3 (NON simultaneo)
    morse_right_lock_step3: bool = True   # ✅ 1.  Blocca DX prima
    morse_left_release_step3: bool = True # ❌ 2. Sblocca SX dopo (con ritardo)
    
    # Tracking
    current_step: int = 0


def calculate_ultra_long_sequence(
    target_length_mm: float,
    angle_sx: float,
    angle_dx: float,
    config: UltraLongConfig
) -> Optional[UltraLongSequence]:
    """
    Calcola sequenza ultra-lunga se necessaria.
    
    Args:
        target_length_mm: Lunghezza pezzo richiesta
        angle_sx:  Angolo testa sinistra (fissa)
        angle_dx: Angolo testa destra (mobile)
        config: Configurazione limiti macchina
        
    Returns:
        Sequenza step o None se modalità non necessaria
    """
    # Verifica se modalità necessaria
    if target_length_mm <= config.max_travel_mm:
        return None  # Pezzo normale
    
    if target_length_mm > config.stock_length_mm:
        logger.error(f"❌ Pezzo {target_length_mm:. 0f}mm > stock {config.stock_length_mm:.0f}mm")
        return None
    
    # Calcola parametri
    offset = target_length_mm - config.max_travel_mm
    
    if offset < config.min_offset_mm:
        logger.error(f"❌ Offset {offset:.0f}mm < minimo {config.min_offset_mm:.0f}mm")
        return None
    
    pos_intestatura_dx = config.safe_head_mm
    pos_dopo_arretramento_dx = pos_intestatura_dx - offset
    pos_finale_dx = config.max_travel_mm
    
    # Verifica posizione dopo arretramento
    if pos_dopo_arretramento_dx < 250: 
        logger.error(f"❌ Arretramento porta a {pos_dopo_arretramento_dx:.0f}mm < 250mm (zero macchina)")
        return None
    
    logger.info(f"🔧 Modalità ULTRA-LUNGA: {target_length_mm:.0f}mm")
    logger.info(f"   Step 1: Intestatura TESTA DX @ {pos_intestatura_dx:.0f}mm")
    logger.info(f"   Step 2: Arretramento TESTA DX -{offset:.0f}mm → {pos_dopo_arretramento_dx:.0f}mm")
    logger.info(f"   Step 3: Finale TESTA SX, DX @ {pos_finale_dx:.0f}mm (effettivo: {target_length_mm:.0f}mm)")
    
    return UltraLongSequence(
        enabled=True,
        target_length_mm=target_length_mm,
        
        # Step 1: Intestatura con TESTA DX
        pos_head_cut_dx=pos_intestatura_dx,
        angle_head_cut_dx=angle_dx,  # Angolo su TESTA DX
        
        # Step 2: Arretramento
        offset_mm=offset,
        pos_after_retract_dx=pos_dopo_arretramento_dx,
        morse_switch_delay_ms=100,
        
        # Step 3: Taglio finale con TESTA SX
        pos_final_cut_dx=pos_finale_dx,
        angle_final_cut_sx=angle_sx,  # Angolo su TESTA SX
        
        current_step=0
    )


def get_step_description(seq: UltraLongSequence) -> str:
    """Ottiene descrizione step corrente."""
    if not seq.enabled:
        return "Modalità ultra-lunga disabilitata"
    
    steps = {
        0: "IDLE - Pronto per intestatura",
        1: f"STEP 1/3: Intestatura TESTA DX @ {seq. pos_head_cut_dx:. 0f}mm (angolo {seq.angle_head_cut_dx:.1f}°)",
        2: f"STEP 2/3: Arretramento TESTA DX -{seq. offset_mm:.0f}mm → {seq.pos_after_retract_dx:.0f}mm",
        3: f"STEP 3/3: Taglio finale TESTA SX @ DX_pos={seq.pos_final_cut_dx:.0f}mm (totale {seq.target_length_mm:. 0f}mm)"
    }
    
    return steps.get(seq.current_step, "Step sconosciuto")
