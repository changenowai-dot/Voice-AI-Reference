"""VRAM-Wächter: überwacht freien VRAM und löst Schutzmaßnahmen aus,
statt Abstürze zu riskieren (Anforderung 4).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

from .detector import vram_snapshot
from ..logging_setup import get_logger

log = get_logger("vram")


@dataclass
class ResourcePolicy:
    """Adaptive Ressourcen-Steuerung während der Synthese."""

    batch_size: int = 1
    max_segment_chars: int = 700
    vram_reserve_gb: float = 0.8      # Puffer, der immer frei bleiben soll
    history: List[float] = field(default_factory=list)

    def note_vram(self, free_gb: float) -> None:
        self.history.append(free_gb)
        if len(self.history) > 64:
            self.history.pop(0)

    def should_reduce(self, free_gb: float) -> bool:
        return free_gb < self.vram_reserve_gb + 0.3


class VRAMGuard:
    """Thread-sicherer Wächter. Vor jedem TTS-Aufruf prüfen; bei Knappheit
    Maßnahmen ergreifen (Cache leeren, Batch reduzieren, Segment teilen)."""

    def __init__(self, policy: Optional[ResourcePolicy] = None,
                 watchdog_interval: float = 5.0):
        self.policy = policy or ResourcePolicy()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._watchdog_interval = watchdog_interval
        self._actions_taken: List[str] = []

    # -- polling watchdog ---------------------------------------------------
    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._watch, daemon=True,
                                        name="vram-watchdog")
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=self._watchdog_interval + 1)
            self._thread = None
        self._stop.clear()

    def _watch(self) -> None:
        while not self._stop.wait(self._watchdog_interval):
            free, _ = vram_snapshot()
            if free > 0:
                self.policy.note_vram(free)
                if self.policy.should_reduce(free):
                    self.emergency_cleanup()

    # -- Maßnahmen ----------------------------------------------------------
    def emergency_cleanup(self) -> str:
        action = "torch.cuda.empty_cache()"
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                import gc
                gc.collect()
                torch.cuda.empty_cache()
        except Exception as e:  # pragma: no cover
            action += f" (Fehler: {e})"
        self._actions_taken.append(f"{time.strftime('%H:%M:%S')} {action}")
        log.warning("VRAM knapp – Maßnahme: %s", action)
        return action

    def before_call(self) -> dict:
        """Vor jedem Modellaufruf aufrufen; gibt Empfehlung zurück."""
        free, total = vram_snapshot()
        self.policy.note_vram(free)
        rec = {"batch_size": self.policy.batch_size,
               "max_segment_chars": self.policy.max_segment_chars,
               "free_gb": free}
        if free == 0.0:          # CPU-Modus
            return rec
        if free < self.policy.vram_reserve_gb:
            self.emergency_cleanup()
            free2, _ = vram_snapshot()
            if free2 < self.policy.vram_reserve_gb:
                if self.policy.batch_size > 1:
                    self.policy.batch_size = 1
                    log.warning("VRAM dauerhaft knapp -> batch_size=1")
                rec["batch_size"] = self.policy.batch_size
        return rec

    @property
    def actions_taken(self) -> List[str]:
        return list(self._actions_taken)
