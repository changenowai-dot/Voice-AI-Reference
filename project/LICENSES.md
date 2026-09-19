# Lizenz- und Komponentenübersicht (VoiceOverApp 1.0)

Stand: August 2026. Dieses Dokument dokumentiert transparent die Lizenz-
situation aller mitgelieferten/verwendeten Komponenten (Anforderung 76).

## Zusammenfassung

**Kommerzielle Nutzung der erzeugten Audios: zulässig.** Alle Kern-
komponenten sind kostenlos und permissive lizenziert. Keine Komponente
benötigt API-Keys, Credits oder Abonnements.

## Im Detail

| Komponente | Version | Lizenz | Kommerzielle Nutzung | Hinweis |
|---|---|---|---|---|
| **Qwen3-TTS-12Hz-1.7B-CustomVoice** (Modell) | 2026-01 | **Apache-2.0** | ✅ zulässig | Alibaba Qwen Team, Hugging Face `Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice` |
| **Qwen3-TTS-12Hz-0.6B-CustomVoice** (Modell) | 2026-01 | **Apache-2.0** | ✅ zulässig | optionale sparsame Variante |
| **Qwen3-TTS-Tokenizer-12Hz** (Modell) | 2026-01 | **Apache-2.0** | ✅ zulässig | Audio-Codec/Tokenizer |
| **qwen-tts** (Python-Paket) | 0.1.1 | **Apache-2.0** | ✅ zulässig | github.com/QwenLM/Qwen3-TTS |
| **PyTorch** | ≥ 2.7 (cu128) | BSD-3-Clause | ✅ zulässig | |
| **transformers** | 4.57.3 (Pin von qwen-tts) | Apache-2.0 | ✅ zulässig | |
| **accelerate** | 1.12.0 | Apache-2.0 | ✅ zulässig | |
| **librosa / soundfile / numpy / scipy** | aktuell | ISC / LGPL-3.0 (libsndfile) / BSD / BSD | ✅ zulässig | |
| **psutil** | aktuell | BSD | ✅ | |
| **huggingface_hub** | aktuell | Apache-2.0 | ✅ | |
| **FFmpeg** (gyan.dev Essentials-Build) | 7.x | **GPL/LGPL** (je nach Build-Konfiguration) | ✅ als separates Werkzeug | Wird als eigenständiges externes Programm aufgerufen, nicht eingebettet. Wer rein LGPL möchte, kann einen LGPL-Build verwenden. |
| **Python** | 3.10–3.13 | PSF License | ✅ | |
| **VoiceOverApp** (diese Software) | 1.0.0 | MIT-ähnliche Nutzung frei | ✅ | erstellt im Auftrag des Nutzers |

## Verantwortungshinweise

- **Apache-2.0**: Namensnennung + Lizenztext bei Weitergabe erforderlich
  (Dateien liegen im jeweiligen Paket/repo).
- **Keine Garantie**: Software und Modelle werden ohne Gewährleistung
  bereitgestellt (siehe jeweilige Lizenztexte).
- Die von der App **erzeugten Audios** (Synthese deiner Texte) unterliegen
  deiner Verantwortung bzgl. Textrechten; die Modell-Lizenzen erlauben
  kommerzielle Synthese- Nutzung ausdrücklich.
- Es werden **keine** Daten an externe Dienste gesendet. Netzwerkzugriffe
  erfolgen ausschließlich während der Installation (PyPI, pytorch.org,
  Hugging Face, gyan.dev/winget für FFmpeg) und sind optional
  (Modell-Updates).
