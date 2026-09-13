"""Deterministische RNG-Setzung für Synthese-Aufrufe.

Problem, das wir beobachten:
  - Ein neues torch-manual_seed setzt nur den *globalen* CPU- und den
    current-device-CUDA-Generator. Modellbibliotheken (transformers-,
    flash-attn-, SDPA- und Blackwell-Kernel) beziehen Zufallszahlen aber
    teilweise aus per-device CUDA-Generatoren und/oder aus einem explizit
    übergebenen ``torch.Generator``.
  - Ohne einen sauberen Reset laufen Retries deshalb im gleichen
    CUDA-RNG-Nachlauf wie der vorherige Versuch – was sich in den
    0.16s-/Silence-/noise_like-Wiederholungen mit identischen Metriken
    auch bei unterschiedlichen Seeds äußert.

Dieses Modul hält die Seed-Logik zentral, damit alle Engines sie
konsistent anwenden. Keine Änderung an Sampling/QC/Rezepten.
"""
from __future__ import annotations

from .logging_setup import get_logger

log = get_logger("tts.rng")


def set_deterministic_seed(seed: int):
    """Setzt CPU- und *alle* CUDA-Generatoren auf ``seed`` und synchronisiert.

    Muss VOR jedem Synthese-Aufruf (und vor jedem Retry) mit dem jeweiligen
    Request-Seed aufgerufen werden. Wir geben einen ``torch.Generator``
    zurück, der an ``model.generate`` o.ä. durchgereicht werden KANN
    (transformers/accelerate unterstützen ``generator=``), falls die
    aufrufende Engine das will.
    """
    import torch

    seed = int(seed) & 0xFFFF_FFFF  # torch akzeptiert nur uint32-Seeds

    torch.manual_seed(seed)

    gen = torch.Generator(device="cpu")
    gen.manual_seed(seed)

    if torch.cuda.is_available():
        # Auf allen sichtbaren CUDA-Geräten denselben Seed setzen – sonst
        # bleibt bei Gerät>0 / bei Modell-Shards der alte RNG-Zustand aktiv.
        if not torch.cuda.is_initialized():
            torch.cuda.init()
        for dev in range(torch.cuda.device_count()):
            torch.cuda.manual_seed(seed)  # current
            with torch.cuda.device(dev):
                torch.cuda.manual_seed(seed)
        # RTX 5060 (Blackwell, sm_120) mit torch 2.11+cu128 hat einen
        # Philox-CUDA-RNG, der nach dem leeren Tensor-Return eines fehl-
        # geschlagenen Versuchs nicht mehr sauber neu aufsetzt, wenn wir
        # nicht explizit synchronisieren.
        try:
            torch.cuda.synchronize()
        except Exception:  # pragma: no cover - synchronize ist best-effort
            pass

    return gen
