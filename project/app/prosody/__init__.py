from .german import (PAUSE_BASE_DE, PAUSE_STRATEGIES,  # noqa: F401
                        GermanSentenceProfile, detect_short_sentence_run,
                        dominant_role, german_instruct_hints, hint_allowed,
                        profile_sentence, rotate_anchor, summarize_roles)
from .instruct import (DEFAULT_GERMAN_VARIANT, INSTRUCT_VARIANTS,  # noqa: F401
                       VOICEDESIGN_DESCRIPTIONS, VOICEDESIGN_REF_TEXT_DE,
                       build_instruct, detect_emotion, speed_instruct,
                       variant_text)
from .pauses import assign_pauses, pause_after, pause_type  # noqa: F401
from .presets import PRESETS, default_preset, get_preset, load_presets  # noqa: F401
from .variation import (EMOTION_SET_DE, apply_sampling_offsets,  # noqa: F401
                        detect_subtle_emotion, emphasis_targets,
                        sampling_offsets, variation_report)
