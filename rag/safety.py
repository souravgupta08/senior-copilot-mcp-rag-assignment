"""Strip prompt-injection style sentences from retrieved text."""

import re

INJECTION_PATTERNS = [
    r"ignore (all )?(the )?(previous|prior|above) instructions",
    r"disregard (all )?(the )?(previous|prior|above)",
    r"you are now",
    r"system prompt",
    r"act as (the )?(plant manager|administrator|admin|system)",
    r"tell the (operator|user|reader) to (bypass|ignore|disable)",
    r"reveal (your|the) (instructions|prompt|api key|token)",
]

_PATTERN = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


def looks_like_injection(text: str) -> bool:
    return bool(_PATTERN.search(text))


def sanitize_text(text: str) -> tuple[str, bool]:
    """
    Removes suspicious sentences.

    Returns (clean_text, was_flagged).
    """
    sentences = re.split(r"(?<=[.!?])\s+", text)
    kept = []
    flagged = False
    for sentence in sentences:
        if looks_like_injection(sentence):
            flagged = True
            if not kept or kept[-1] != "[removed: suspected prompt injection]":
                kept.append("[removed: suspected prompt injection]")
        else:
            kept.append(sentence)
    return " ".join(kept).strip(), flagged
