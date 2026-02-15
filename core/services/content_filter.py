"""Content filter — validates LLM-generated radio scripts."""


BLOCKED_WORDS = [
    "buy", "sell", "invest", "price target", "prediction",
    "http", "www.", ".com", ".org", ".net",
    "click", "visit", "subscribe", "go to", "check out",
    "breaking news",  # avoid if not actually breaking
]

MIN_WORDS = 15
MAX_WORDS = 100
MAX_CHARS = 600


def validate(script: str, is_breaking: bool = False) -> tuple[bool, str]:
    """
    Validate a generated script.
    Returns (is_valid, reason).
    """
    if not script or not script.strip():
        return False, "empty script"

    words = script.split()

    min_w = 10 if is_breaking else MIN_WORDS
    max_w = 50 if is_breaking else MAX_WORDS

    if len(words) < min_w:
        return False, f"too short ({len(words)} words, min {min_w})"

    if len(words) > max_w:
        return False, f"too long ({len(words)} words, max {max_w})"

    if len(script) > MAX_CHARS:
        return False, f"exceeds {MAX_CHARS} chars"

    lower = script.lower()

    blocked = BLOCKED_WORDS.copy()
    if is_breaking:
        # Allow "breaking news" in actual breaking segments
        blocked = [w for w in blocked if w != "breaking news"]

    for word in blocked:
        if word in lower:
            return False, f"blocked word: '{word}'"

    return True, "ok"
