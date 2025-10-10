from __future__ import annotations
import threading
import time
from typing import Callable, Optional

class ProbeService:
    """
    Servizio tastatore profili (simulato in sviluppo).
    Simula una misurazione dello spessore e ritorna il valore letto.
    """
    def __init__(self, machine):
        self.machine = machine
        self._busy = False

    def is_busy(self) -> bool:
        return self._busy

    def measure_thickness_async(self, done_cb: Optional[Callable[[bool, float | None, str], None]] = None):
        """
        Avvia una misura simulata. Ritorna via callback (ok, value_mm, msg).
        """
        if self._busy:
            if done_cb: done_cb(False, None, "Già in esecuzione")
            return
        # prerequisiti minimi
        if getattr(self.machine, "emergency_active", False):
            if done_cb: done_cb(False, None, "EMERGENZA")
            return
        if not getattr(self.machine, "machine_homed", False):
            if done_cb: done_cb(False, None, "Eseguire Azzera")
            return

        self._busy = True

        def run():
            try:
                # Simula una breve sequenza di contatto
                # In futuro: leggi un input analogico/digitale dal tastatore reale
                time.sleep(1.0)
                # Produci una misura fittizia con leggero rumore
                base = float(getattr(self.machine, "profile_thickness", 50.0))
                measured = max(0.0, base + (1.5 - 3.0 * (time.time() % 1)))  # +-1.5mm pseudo
                if done_cb:
                    done_cb(True, float(f"{measured:.1f}"), "OK")
            except Exception as e:
                if done_cb:
                    done_cb(False, None, f"ERR: {e!s}")
            finally:
                self._busy = False

        threading.Thread(target=run, daemon=True).start()
