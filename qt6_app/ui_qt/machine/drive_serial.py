import threading, time
import serial
from typing import Optional, Callable

class DriveSerial:
    """
    Gestione porta RS232 del DCS810 (canale FT4232HL).
    Riceve linee o frame testuali (adattare al protocollo reale).
    callback(line) chiamata su ogni messaggio completo.
    """
    def __init__(self, port: str, baud: int = 115200, line_callback: Optional[Callable[[str], None]] = None):
        self.port = port
        self.baud = baud
        self._ser = serial.Serial(port=self.port, baudrate=self.baud, timeout=0.1)
        self._cb = line_callback
        self._rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        self._closed = False
        self._rx_thread.start()

    def _rx_loop(self):
        buf = ""
        while not self._closed:
            try:
                chunk = self._ser.read(128)
                if chunk:
                    buf += chunk.decode(errors="ignore")
                    # parsing semplice a linee
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        if line and self._cb:
                            self._cb(line)
                else:
                    time.sleep(0.02)
            except Exception:
                time.sleep(0.2)

    def send_command(self, cmd: str) -> None:
        """
        Invia comando al drive. Aggiunge terminatore CRLF se non presente.
        """
        if not cmd.endswith("\r\n"):
            cmd = cmd.rstrip("\r\n") + "\r\n"
        try:
            self._ser.write(cmd.encode())
        except Exception:
            pass

    def close(self):
        self._closed = True
        try: self._ser.close()
        except Exception: pass
