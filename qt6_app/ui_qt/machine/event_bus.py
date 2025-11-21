from __future__ import annotations
from typing import Callable, Dict, List, Any
import threading

class EventBus:
    """Semplice bus eventi per decoupling (facoltativo)."""
    def __init__(self):
        self._subs: Dict[str, List[Callable[[Any], None]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, topic: str, cb: Callable[[Any], None]) -> None:
        with self._lock:
            self._subs.setdefault(topic, []).append(cb)

    def publish(self, topic: str, payload: Any = None) -> None:
        with self._lock:
            subs = list(self._subs.get(topic, []))
        for cb in subs:
            try: cb(payload)
            except Exception: pass
