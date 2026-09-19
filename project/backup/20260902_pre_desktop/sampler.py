"""Parameter-Sets für Qwen3-TTS (Anforderung 49).

Qwen3-TTS darf nicht blind mit Default-Parametern laufen: wir definieren
abgestimmte Sets und eine reproduzierbare Variation für Regenerierungen.
Die endgültigen Werte verifiziert der System-Benchmark auf der Zielhardware.
"""
from __future__ import annotations

PARAM_SETS = {
    # Set          do_sample  temp  top_k  top_p  rep_pen
    "balanced":    {"do_sample": True, "temperature": 0.70, "top_k": 50,
                    "top_p": 0.90, "repetition_penalty": 1.05},
    "stable":      {"do_sample": True, "temperature": 0.55, "top_k": 40,
                    "top_p": 0.85, "repetition_penalty": 1.08},
    "expressive":  {"do_sample": True, "temperature": 0.85, "top_k": 60,
                    "top_p": 0.92, "repetition_penalty": 1.03},
    "conservative": {"do_sample": True, "temperature": 0.60, "top_k": 30,
                     "top_p": 0.80, "repetition_penalty": 1.10},
}

# Codec-Tokens des 12Hz-Tokenizers pro Sekunde Audio (12,5/s)
TOKENS_PER_SECOND = 12.5


def params_for_set(set_name: str, overrides: dict | None = None) -> dict:
    base = dict(PARAM_SETS.get(set_name, PARAM_SETS["balanced"]))
    if overrides:
        for k, v in overrides.items():
            if v is not None:
                base[k] = v
    return base


def variation_for_attempt(attempt: int, base_params: dict) -> dict:
    """Bestimmt Parameteränderungen für Regenerierungs-Versuche
    (Anforderung 44: Fehler klassifizieren, Parameter ändern, erneut
    generieren). Versuch 1 = unverändert, danach gezielt variieren."""
    out = dict(base_params)
    if attempt <= 1:
        return out
    if attempt == 2:
        # stabiler sampeln
        out["temperature"] = max(0.4, round(out.get("temperature", 0.7) - 0.15, 3))
        out["top_p"] = 0.85
        out["top_k"] = 40
        out["repetition_penalty"] = 1.08
        return out
    # Versuch 3+: konservativ + minimale Temperatur
    out.update({"temperature": 0.45, "top_p": 0.80, "top_k": 30,
                "repetition_penalty": 1.10})
    return out


def max_new_tokens_for(seconds: float) -> int:
    """Begrenzt die Generierung (verhindert Endlosschleifen/Runaway)."""
    return int((seconds + 12.0) * TOKENS_PER_SECOND + 64)


PARAM_SET_VERSION = "q3p-v1"     # Cache-Invalidierung bei Parameteränderungen
