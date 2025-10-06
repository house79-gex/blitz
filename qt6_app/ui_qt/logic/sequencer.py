from PySide6.QtCore import QObject, QTimer, Signal

class Sequencer(QObject):
    """
    Esegue una lista di steps pianificati.
    Ogni step simula un'operazione di taglio chiamando i metodi di MachineState se disponibili.
    """
    step_started = Signal(int, dict)
    step_finished = Signal(int, dict)
    finished = Signal()

    def __init__(self, appwin, steps: list[dict] | None = None, interval_ms: int = 600):
        super().__init__(appwin)
        self.appwin = appwin
        self.machine = appwin.machine
        self.steps = steps or []
        self.idx = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.interval_ms = interval_ms
        self.running = False

    def load_plan(self, steps: list[dict]):
        self.steps = steps or []
        self.idx = 0

    def start(self):
        if not self.steps:
            self._toast("Nessun piano da eseguire", "warn")
            return
        self.running = True
        self.timer.start(self.interval_ms)

    def pause(self):
        self.timer.stop()
        self.running = False

    def resume(self):
        if self.steps and not self.running:
            self.running = True
            self.timer.start(self.interval_ms)

    def stop(self):
        self.timer.stop()
        self.running = False
        self.idx = 0

    def _tick(self):
        if self.idx >= len(self.steps):
            self.stop()
            self.finished.emit()
            self._toast("Sequenza completata", "ok")
            return
        step = self.steps[self.idx]
        self.step_started.emit(self.idx, step)
        # Simula l'operazione di taglio
        try:
            if hasattr(self.machine, "simulate_cut_pulse"):
                self.machine.simulate_cut_pulse()
            elif hasattr(self.machine, "decrement_current_remaining"):
                self.machine.decrement_current_remaining()
        except Exception:
            pass
        self.step_finished.emit(self.idx, step)
        self.idx += 1

    def _toast(self, msg, level="info"):
        if hasattr(self.appwin, "toast"):
            self.appwin.toast.show(msg, level, 2200)
