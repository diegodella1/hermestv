"""Content filter — validates LLM-generated scripts."""

import re

# Two lists: exact word-boundary matches vs substring matches
BLOCKED_PHRASES = [
    "buy", "sell", "invest", "investing", "price target", "prediction",
    "click", "subscribe", "go to", "check out",
    "breaking news",  # avoid if not actually breaking
]

# These need substring matching (URLs/domains)
BLOCKED_SUBSTRINGS = [
    "http", "www.", ".com", ".org", ".net",
]

DEFAULT_MIN_WORDS = 15
DEFAULT_MAX_WORDS = 100
DEFAULT_MAX_CHARS = 600
DEFAULT_BREAKING_MIN_WORDS = 10
DEFAULT_BREAKING_MAX_WORDS = 50


def validate(
    script: str,
    is_breaking: bool = False,
    min_words: int | None = None,
    max_words: int | None = None,
    max_chars: int | None = None,
) -> tuple[bool, str]:
    """
    Validate a generated script.
    Returns (is_valid, reason).
    """
    if not script or not script.strip():
        return False, "empty script"

    words = script.split()

    if is_breaking:
        min_w = min_words if min_words is not None else DEFAULT_BREAKING_MIN_WORDS
        max_w = max_words if max_words is not None else DEFAULT_BREAKING_MAX_WORDS
    else:
        min_w = min_words if min_words is not None else DEFAULT_MIN_WORDS
        max_w = max_words if max_words is not None else DEFAULT_MAX_WORDS

    max_c = max_chars if max_chars is not None else DEFAULT_MAX_CHARS

    if len(words) < min_w:
        return False, f"too short ({len(words)} words, min {min_w})"

    if len(words) > max_w:
        return False, f"too long ({len(words)} words, max {max_w})"

    if len(script) > max_c:
        return False, f"exceeds {max_c} chars"

    lower = script.lower()

    # Word-boundary matching for phrases (won't match "investigation" for "invest")
    phrases = BLOCKED_PHRASES.copy()
    if is_breaking:
        phrases = [w for w in phrases if w != "breaking news"]

    for phrase in phrases:
        if re.search(r'\b' + re.escape(phrase) + r'\b', lower):
            return False, f"blocked word: '{phrase}'"

    # Substring matching for URLs/domains
    for sub in BLOCKED_SUBSTRINGS:
        if sub in lower:
            return False, f"blocked pattern: '{sub}'"

    return True, "ok"
