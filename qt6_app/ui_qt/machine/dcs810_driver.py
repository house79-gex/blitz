"""
Driver comunicazione RS232 per Leadshine DCS810.

Gestisce:
- Comandi movimento assoluto/relativo
- Lettura posizione encoder real-time
- Gestione allarmi e stato
- Stop emergenza

Nota: Il protocollo specifico deve essere implementato secondo il manuale DCS810.
Questa implementazione fornisce una struttura base funzionante.
"""
import time
import threading
from typing import Optional, Dict, Any

try:
    import serial
except ImportError:
    serial = None


class DCS810Driver:
    """
    Driver per controller motore Leadshine DCS810 via RS232.
    
    Caratteristiche:
    - Comunicazione RS232 (tipicamente 115200 baud)
    - Comandi movimento posizionale
    - Lettura encoder in tempo reale
    - Gestione allarmi hardware
    """
    
    def __init__(self, port: str, baudrate: int = 115200, timeout: float = 1.0):
        """
        Inizializza connessione con DCS810.
        
        Args:
            port: Porta seriale (es. /dev/ttyUSB1 su Linux, COM3 su Windows)
            baudrate: Velocità comunicazione (default 115200)
            timeout: Timeout lettura in secondi
        """
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        
        self._ser: Optional[object] = None
        self._lock = threading.Lock()
        self._connected = False
        self._position_mm = 0.0
        self._alarm_active = False
        self._moving = False
        
        # Verifica disponibilità pyserial
        if serial is None:
            print(f"[DCS810] Modulo 'serial' non disponibile. Installare: pip install pyserial")
            self._connected = False
            return
        
        # Tentativo connessione
        try:
            self._ser = serial.Serial(
                port=port,
                baudrate=baudrate,
                timeout=timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE
            )
            self._connected = True
            print(f"[DCS810] ✅ Connesso a {port} @ {baudrate} baud")
        except Exception as e:
            self._ser = None
            self._connected = False
            print(f"[DCS810] ❌ Errore connessione: {e}")
    
    def is_connected(self) -> bool:
        """Verifica se la connessione è attiva."""
        return self._connected and self._ser is not None
    
    def send_command(self, cmd: str) -> Optional[str]:
        """
        Invia comando e legge risposta.
        
        Args:
            cmd: Comando da inviare (senza terminatore)
            
        Returns:
            Risposta del driver o None se errore
        """
        if not self.is_connected():
            return None
        
        with self._lock:
            try:
                # Aggiungi terminatore CRLF
                if not cmd.endswith('\r\n'):
                    cmd = cmd + '\r\n'
                
                # Invia comando
                self._ser.write(cmd.encode('ascii'))
                self._ser.flush()
                
                # Attendi e leggi risposta
                time.sleep(0.05)
                response = self._ser.readline().decode('ascii', errors='ignore').strip()
                
                return response if response else None
            except Exception as e:
                print(f"[DCS810] Errore comunicazione: {e}")
                return None
    
    def move_absolute(self, position_mm: float, speed_mm_s: float = 1000.0) -> bool:
        """
        Movimento assoluto a posizione target.
        
        NOTA: Implementazione base. Adattare al protocollo DCS810 reale.
        
        Args:
            position_mm: Posizione target in mm
            speed_mm_s: Velocità di movimento in mm/s
            
        Returns:
            True se comando accettato
        """
        # Protocollo placeholder - DA IMPLEMENTARE secondo manuale DCS810
        # Esempio: "PA 1000.5 500.0" per posizione assoluta 1000.5mm a 500mm/s
        
        cmd = f"PA {position_mm:.3f} {speed_mm_s:.1f}"
        resp = self.send_command(cmd)
        
        if resp:
            self._moving = True
            return True
        return False
    
    def move_relative(self, distance_mm: float, speed_mm_s: float = 1000.0) -> bool:
        """
        Movimento relativo di una distanza.
        
        Args:
            distance_mm: Distanza da percorrere in mm (può essere negativa)
            speed_mm_s: Velocità di movimento in mm/s
            
        Returns:
            True se comando accettato
        """
        # Protocollo placeholder
        cmd = f"PR {distance_mm:.3f} {speed_mm_s:.1f}"
        resp = self.send_command(cmd)
        
        if resp:
            self._moving = True
            return True
        return False
    
    def stop(self) -> bool:
        """
        Arresto immediato del movimento.
        
        Returns:
            True se comando accettato
        """
        resp = self.send_command("ST")
        if resp:
            self._moving = False
            return True
        return False
    
    def read_position(self) -> Optional[float]:
        """
        Legge posizione corrente dall'encoder.
        
        Returns:
            Posizione in mm o None se errore
        """
        resp = self.send_command("?POS")
        if resp:
            try:
                # Risposta attesa: "POS=1234.56" o solo "1234.56"
                if '=' in resp:
                    resp = resp.split('=')[1]
                pos = float(resp)
                self._position_mm = pos
                return pos
            except ValueError:
                return None
        return None
    
    def read_alarm(self) -> bool:
        """
        Legge stato allarme.
        
        Returns:
            True se allarme attivo
        """
        resp = self.send_command("?ALM")
        if resp:
            # Risposta attesa: "ALM=1" (allarme) o "ALM=0" (ok)
            try:
                if '=' in resp:
                    resp = resp.split('=')[1]
                alarm = int(resp) != 0
                self._alarm_active = alarm
                return alarm
            except ValueError:
                return False
        return False
    
    def clear_alarm(self) -> bool:
        """
        Azzera allarme driver.
        
        Returns:
            True se comando accettato
        """
        resp = self.send_command("CLRALM")
        if resp:
            self._alarm_active = False
            return True
        return False
    
    def set_speed(self, speed_mm_s: float) -> bool:
        """
        Imposta velocità di default.
        
        Args:
            speed_mm_s: Velocità in mm/s
            
        Returns:
            True se comando accettato
        """
        cmd = f"SPEED {speed_mm_s:.1f}"
        resp = self.send_command(cmd)
        return resp is not None
    
    def set_acceleration(self, accel_mm_s2: float) -> bool:
        """
        Imposta accelerazione.
        
        Args:
            accel_mm_s2: Accelerazione in mm/s²
            
        Returns:
            True se comando accettato
        """
        cmd = f"ACCEL {accel_mm_s2:.1f}"
        resp = self.send_command(cmd)
        return resp is not None
    
    def is_moving(self) -> bool:
        """
        Verifica se il motore è in movimento.
        
        Returns:
            True se in movimento
        """
        resp = self.send_command("?MOV")
        if resp:
            try:
                if '=' in resp:
                    resp = resp.split('=')[1]
                moving = int(resp) != 0
                self._moving = moving
                return moving
            except ValueError:
                return self._moving
        return self._moving
    
    def get_state(self) -> Dict[str, Any]:
        """
        Legge stato completo del driver.
        
        Returns:
            Dizionario con stato corrente
        """
        return {
            "connected": self._connected,
            "position_mm": self._position_mm,
            "alarm_active": self._alarm_active,
            "moving": self._moving,
            "port": self.port,
            "baudrate": self.baudrate
        }
    
    def home(self, speed_mm_s: float = 500.0) -> bool:
        """
        Esegue procedura di homing (ricerca finecorsa).
        
        Args:
            speed_mm_s: Velocità di homing
            
        Returns:
            True se comando accettato
        """
        cmd = f"HOME {speed_mm_s:.1f}"
        resp = self.send_command(cmd)
        if resp:
            self._moving = True
            return True
        return False
    
    def reset(self) -> bool:
        """
        Reset del driver.
        
        Returns:
            True se comando accettato
        """
        resp = self.send_command("RESET")
        if resp:
            self._alarm_active = False
            self._moving = False
            return True
        return False
    
    def close(self):
        """Chiude connessione seriale."""
        if self._ser:
            try:
                self._ser.close()
                print(f"[DCS810] Connessione chiusa")
            except Exception:
                pass
            self._connected = False
            self._ser = None
    
    def __del__(self):
        """Cleanup automatico."""
        self.close()
