"""Content filter — validates LLM-generated radio scripts."""


BLOCKED_WORDS = [
    "buy", "sell", "invest", "price target", "prediction",
    "http", "www.", ".com", ".org", ".net",
    "click", "visit", "subscribe", "go to", "check out",
    "breaking news",  # avoid if not actually breaking
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

    blocked = BLOCKED_WORDS.copy()
    if is_breaking:
        # Allow "breaking news" in actual breaking segments
        blocked = [w for w in blocked if w != "breaking news"]

    for word in blocked:
        if word in lower:
            return False, f"blocked word: '{word}'"

    return True, "ok"
