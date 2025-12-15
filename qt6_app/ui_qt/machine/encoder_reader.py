"""
Encoder Reader per lettura posizione via GPIO Raspberry Pi.

Caratteristiche:
- Lettura encoder in modalità quadratura x4
- Hardware interrupt tramite pigpio
- Calcolo posizione in mm real-time
- Reset e calibrazione
- Compatibile con encoder NPN open-collector e push-pull
"""
import logging
from typing import Optional

try:
    import pigpio
    PIGPIO_AVAILABLE = True
except ImportError:
    pigpio = None
    PIGPIO_AVAILABLE = False


class EncoderReader:
    """
    Legge encoder via GPIO Raspberry Pi in modalità quadratura x4.
    
    Usa pigpio per hardware interrupt ad alta velocità.
    Supporta fino a 500kHz di frequenza encoder.
    """
    
    def __init__(self, gpio_a: int = 17, gpio_b: int = 18, mm_per_pulse: float = 0.047125):
        """
        Inizializza lettore encoder.
        
        Args:
            gpio_a: Pin GPIO per canale A encoder (default: GPIO17)
            gpio_b: Pin GPIO per canale B encoder (default: GPIO18)
            mm_per_pulse: Millimetri per impulso (da configurazione trasmissione)
        """
        self.gpio_a = gpio_a
        self.gpio_b = gpio_b
        self.mm_per_pulse = mm_per_pulse
        
        self._pulse_count = 0
        self._last_a = 0
        self._last_b = 0
        self._pi: Optional[object] = None
        self._connected = False
        self._cb_a = None
        self._cb_b = None
        
        self.logger = logging.getLogger("blitz.encoder")
        
        # Verifica disponibilità pigpio
        if not PIGPIO_AVAILABLE:
            self.logger.warning("⚠️ pigpio non disponibile. Installare: sudo pip install pigpio")
            self.logger.warning("   Avviare daemon: sudo pigpiod")
            return
        
        # Connessione al daemon pigpio
        try:
            self._pi = pigpio.pi()
            if not self._pi.connected:
                self.logger.error("❌ Impossibile connettersi al daemon pigpio.")
                self.logger.error("   Avviare con: sudo pigpiod")
                self._pi = None
                return
            
            # Setup GPIO come input
            self._pi.set_mode(self.gpio_a, pigpio.INPUT)
            self._pi.set_mode(self.gpio_b, pigpio.INPUT)
            
            # Pull-up interno per encoder NPN open-collector
            self._pi.set_pull_up_down(self.gpio_a, pigpio.PUD_UP)
            self._pi.set_pull_up_down(self.gpio_b, pigpio.PUD_UP)
            
            # Leggi stato iniziale
            self._last_a = self._pi.read(self.gpio_a)
            self._last_b = self._pi.read(self.gpio_b)
            
            # Callback su entrambi i canali (quadratura x4)
            self._cb_a = self._pi.callback(self.gpio_a, pigpio.EITHER_EDGE, self._pulse_callback)
            self._cb_b = self._pi.callback(self.gpio_b, pigpio.EITHER_EDGE, self._pulse_callback)
            
            self._connected = True
            self.logger.info(f"✅ Encoder reader inizializzato: GPIO_A={gpio_a}, GPIO_B={gpio_b}")
            self.logger.info(f"   Risoluzione: {mm_per_pulse:.6f} mm/impulso (quadratura x4)")
            
        except Exception as e:
            self.logger.error(f"❌ Errore inizializzazione encoder: {e}")
            self._pi = None
            self._connected = False
    
    def _pulse_callback(self, gpio, level, tick):
        """
        Callback interrupt per conteggio impulsi in modalità quadratura x4.
        
        Logica Gray code quadrature decoding:
        - Ogni cambio di A o B incrementa/decrementa contatore
        - Direzione determinata da sequenza Gray code
        
        Gray code CW:  00 → 01 → 11 → 10 → 00
        Gray code CCW: 00 → 10 → 11 → 01 → 00
        """
        if not self._pi:
            if self._connected:
                self.logger.warning("⚠️ Callback ricevuto ma connessione persa")
                self._connected = False
            return
        
        try:
            # Leggi stato corrente entrambi i canali
            level_a = self._pi.read(self.gpio_a)
            level_b = self._pi.read(self.gpio_b)
            
            # Determina quale canale è cambiato e direzione
            if gpio == self.gpio_a:
                # Canale A cambiato
                if level_a != self._last_a:
                    if level_a == level_b:
                        self._pulse_count -= 1  # CCW
                    else:
                        self._pulse_count += 1  # CW
                    self._last_a = level_a
            else:
                # Canale B cambiato
                if level_b != self._last_b:
                    if level_a == level_b:
                        self._pulse_count += 1  # CW
                    else:
                        self._pulse_count -= 1  # CCW
                    self._last_b = level_b
                    
        except Exception as e:
            self.logger.error(f"❌ Errore callback encoder: {e}")
    
    def is_connected(self) -> bool:
        """Verifica se encoder è connesso e funzionante."""
        return self._connected and self._pi is not None and self._pi.connected
    
    def get_position_mm(self) -> Optional[float]:
        """
        Legge posizione corrente in mm.
        
        Returns:
            Posizione in mm o None se non connesso
        """
        if not self.is_connected():
            return None
        
        return self._pulse_count * self.mm_per_pulse
    
    def get_pulse_count(self) -> int:
        """
        Restituisce conteggio impulsi raw.
        
        Returns:
            Numero di impulsi contati (può essere negativo)
        """
        return self._pulse_count
    
    def reset(self):
        """Azzera contatore posizione (homing)."""
        old_count = self._pulse_count
        self._pulse_count = 0
        self.logger.info(f"🏠 Encoder azzerato (era a {old_count * self.mm_per_pulse:.2f} mm)")
    
    def set_position(self, position_mm: float):
        """
        Imposta posizione corrente (calibrazione).
        
        Args:
            position_mm: Nuova posizione in mm
        """
        old_pos = self._pulse_count * self.mm_per_pulse
        self._pulse_count = round(position_mm / self.mm_per_pulse)
        self.logger.info(f"📍 Posizione encoder: {old_pos:.2f}mm → {position_mm:.2f}mm")
    
    def get_resolution_mm(self) -> float:
        """Restituisce risoluzione in mm/impulso."""
        return self.mm_per_pulse
    
    def get_info(self) -> dict:
        """
        Restituisce informazioni encoder.
        
        Returns:
            Dizionario con info encoder
        """
        return {
            "gpio_a": self.gpio_a,
            "gpio_b": self.gpio_b,
            "mm_per_pulse": self.mm_per_pulse,
            "connected": self._connected,
            "position_mm": self.get_position_mm(),
            "pulse_count": self._pulse_count,
            "pigpio_available": PIGPIO_AVAILABLE
        }
    
    def close(self):
        """Chiude connessione pigpio e libera risorse."""
        if self._pi:
            try:
                # Cancella callbacks
                if self._cb_a:
                    self._cb_a.cancel()
                    self._cb_a = None
                if self._cb_b:
                    self._cb_b.cancel()
                    self._cb_b = None
                
                # Chiudi connessione
                self._pi.stop()
                self.logger.info("✅ Encoder reader chiuso")
            except Exception as e:
                self.logger.error(f"❌ Errore chiusura encoder: {e}")
            finally:
                self._pi = None
                self._connected = False
    
    def __del__(self):
        """Cleanup automatico."""
        self.close()
    
    def __repr__(self):
        """Rappresentazione stringa."""
        status = "connected" if self._connected else "disconnected"
        pos = self.get_position_mm()
        pos_str = f"{pos:.2f}mm" if pos is not None else "N/A"
        return f"EncoderReader(GPIO{self.gpio_a}/{self.gpio_b}, {status}, pos={pos_str})"


# Test standalone
if __name__ == "__main__":
    import time
    
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    print("=== Test Encoder Reader ===")
    print("GPIO 17 = Canale A")
    print("GPIO 18 = Canale B")
    print("\nGira l'encoder manualmente...")
    print("CTRL+C per uscire\n")
    
    # Crea encoder reader
    encoder = EncoderReader(gpio_a=17, gpio_b=18, mm_per_pulse=0.047125)
    
    if not encoder.is_connected():
        print("❌ Encoder non connesso. Verifica:")
        print("   1. sudo pigpiod è attivo?")
        print("   2. Encoder cablato su GPIO 17/18?")
        exit(1)
    
    print(f"✅ {encoder}\n")
    
    try:
        last_pos = 0.0
        while True:
            pos = encoder.get_position_mm()
            pulses = encoder.get_pulse_count()
            
            if pos != last_pos:
                direction = "→" if pos > last_pos else "←"
                print(f"{direction} Posizione: {pos:8.2f} mm  |  Impulsi: {pulses:6d}")
                last_pos = pos
            
            time.sleep(0.05)
            
    except KeyboardInterrupt:
        print("\n\n=== Test terminato ===")
        print(f"Posizione finale: {encoder.get_position_mm():.2f} mm")
        print(f"Impulsi totali: {encoder.get_pulse_count()}")
        encoder.close()
