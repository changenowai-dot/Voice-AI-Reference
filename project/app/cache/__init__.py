"""App-Cache-Paket (segment-audio-Cache für Resume/Reuse).

Dieses Modul ist TEIL DES SOURCE-CODES und darf nicht durch eine
top-level .gitignore-Regel für Daten-Caches verschwinden.
"""
from .manager import CacheManager, segment_cache_key  # noqa: F401
