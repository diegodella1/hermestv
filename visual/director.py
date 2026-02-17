"""Director — converts a Script into an EDL (Edit Decision List).

Phase 2 rules:
- Wide shot at scene start (fade_black for first scene)
- Closeup of speaker while they talk
- Twoshot for rapid exchanges (same gap < 2s, different speakers)
- Wide shot inserted every WIDE_SHOT_INTERVAL lines without one
- Reaction shots (20% probability, listener closeup, silent)
- Transitions: 85% cut, 10% dissolve, 5% fade_black (weighted random)
- Camera hints from script override automatic shot selection
- Character emotion states tracked per segment
"""

import random

from visual.config import (
    WIDE_SHOT_DURATION_S,
    REACTION_PROBABILITY,
    REACTION_MIN_MS,
    REACTION_MAX_MS,
    TWOSHOT_MIN_MS,
    TWOSHOT_MAX_MS,
    WIDE_SHOT_MIN_MS,
    WIDE_SHOT_MAX_MS,
    WIDE_SHOT_INTERVAL,
    RAPID_EXCHANGE_MS,
    TRANSITION_CUT,
    TRANSITION_DISSOLVE,
    TRANSITION_FADE_BLACK,
)
from visual.models import Script, DialogLine, EDL, EDLSegment


def _closeup_shot_type(character: str, characters: list[str]) -> str:
    """Determine closeup shot type based on character position."""
    if len(characters) < 2:
        return "closeup_left"
    idx = characters.index(character) if character in characters else 0
    return "closeup_left" if idx == 0 else "closeup_right"


def _pick_transition() -> str:
    """Weighted random transition selection."""
    r = random.random()
    if r < TRANSITION_CUT:
        return "cut"
    elif r < TRANSITION_CUT + TRANSITION_DISSOLVE:
        return "dissolve"
    else:
        return "fade_black"


def _is_rapid_exchange(
    current_line: DialogLine,
    prev_line: DialogLine | None,
) -> bool:
    """Check if current + previous line form a rapid exchange."""
    if prev_line is None:
        return False
    if current_line.character == prev_line.character:
        return False
    return prev_line.duration_ms <= RAPID_EXCHANGE_MS


def _should_insert_reaction(line: DialogLine, characters: list[str]) -> bool:
    """Decide if a reaction shot should follow this line."""
    if len(characters) < 2:
        return False
    if line.duration_ms < 3000:
        return False
    return random.random() < REACTION_PROBABILITY


def _pick_listener(speaker: str, characters: list[str]) -> str | None:
    """Pick a listener character (not the speaker)."""
    others = [c for c in characters if c != speaker]
    return random.choice(others) if others else None


def _reaction_emotion(speaker_emotion: str) -> str:
    """Pick a plausible reaction emotion based on speaker's emotion."""
    reactions = {
        "excited": ["surprised", "neutral", "excited"],
        "concerned": ["concerned", "neutral"],
        "angry": ["concerned", "surprised", "neutral"],
        "surprised": ["surprised", "neutral"],
        "sad": ["concerned", "sad", "neutral"],
    }
    options = reactions.get(speaker_emotion, ["neutral"])
    return random.choice(options)


def _bg_key(base: str, shot_type: str) -> str:
    """Build background key from base + shot type."""
    if shot_type == "twoshot":
        return f"{base}_twoshot"
    return f"{base}_{shot_type}"


def _chars_for_shot(shot_type: str, speaker: str, characters: list[str]) -> list[str]:
    """Which characters appear in this shot type."""
    if shot_type in ("wide", "twoshot"):
        return list(characters)
    # Closeup: just the speaker
    return [speaker]


def generate_edl(script: Script) -> EDL:
    """Convert a script with timed dialog lines into an EDL.

    Requires that each DialogLine already has duration_ms set
    (from TTS or from the script JSON).
    """
    edl = EDL()
    seg_id = 0
    is_first_scene = True

    for scene in script.scenes:
        bg = scene.background
        chars = script.characters
        lines_since_wide = 0

        # Wide shot at scene start
        wide_ms = int(WIDE_SHOT_DURATION_S * 1000)
        transition = "fade_black" if is_first_scene else _pick_transition()
        char_states = {c: "neutral" for c in chars}

        edl.segments.append(EDLSegment(
            segment_id=seg_id,
            shot_type="wide",
            background_key=_bg_key(bg, "wide"),
            characters=list(chars),
            speaker=None,
            audio_path=None,
            duration_ms=wide_ms,
            transition=transition,
            character_states=char_states,
        ))
        seg_id += 1
        is_first_scene = False
        prev_line: DialogLine | None = None

        for i, line in enumerate(scene.lines):
            if line.duration_ms <= 0:
                continue

            # Build character states: speaker has line emotion, others neutral
            char_states = {}
            for c in chars:
                char_states[c] = line.emotion if c == line.character else "neutral"

            # Determine shot type
            if line.camera_hint:
                # Script provides explicit camera direction
                hint = line.camera_hint
                if hint == "closeup":
                    shot_type = _closeup_shot_type(line.character, chars)
                elif hint == "twoshot":
                    shot_type = "twoshot"
                elif hint == "wide":
                    shot_type = "wide"
                else:
                    shot_type = _closeup_shot_type(line.character, chars)
            elif _is_rapid_exchange(line, prev_line):
                shot_type = "twoshot"
            elif lines_since_wide >= WIDE_SHOT_INTERVAL:
                # Insert a brief wide shot before the closeup
                wide_dur = random.randint(WIDE_SHOT_MIN_MS, WIDE_SHOT_MAX_MS)
                edl.segments.append(EDLSegment(
                    segment_id=seg_id,
                    shot_type="wide",
                    background_key=_bg_key(bg, "wide"),
                    characters=list(chars),
                    speaker=None,
                    audio_path=None,
                    duration_ms=wide_dur,
                    transition=_pick_transition(),
                    character_states={c: "neutral" for c in chars},
                ))
                seg_id += 1
                lines_since_wide = 0
                shot_type = _closeup_shot_type(line.character, chars)
            else:
                shot_type = _closeup_shot_type(line.character, chars)

            # Reset wide counter
            if shot_type == "wide":
                lines_since_wide = 0
            else:
                lines_since_wide += 1

            visible_chars = _chars_for_shot(shot_type, line.character, chars)
            transition = _pick_transition()

            edl.segments.append(EDLSegment(
                segment_id=seg_id,
                shot_type=shot_type,
                background_key=_bg_key(bg, shot_type),
                characters=visible_chars,
                speaker=line.character,
                audio_path=line.audio_path,
                duration_ms=line.duration_ms,
                dialog_text=line.text,
                transition=transition,
                character_states=char_states,
            ))
            seg_id += 1

            # Reaction shot (optional, after long lines with 2+ characters)
            if _should_insert_reaction(line, chars):
                listener = _pick_listener(line.character, chars)
                if listener:
                    react_dur = random.randint(REACTION_MIN_MS, REACTION_MAX_MS)
                    react_emotion = _reaction_emotion(line.emotion)
                    react_shot = _closeup_shot_type(listener, chars)
                    react_states = {c: "neutral" for c in chars}
                    react_states[listener] = react_emotion

                    edl.segments.append(EDLSegment(
                        segment_id=seg_id,
                        shot_type=react_shot,
                        background_key=_bg_key(bg, react_shot),
                        characters=[listener],
                        speaker=None,
                        audio_path=None,
                        duration_ms=react_dur,
                        transition="cut",
                        character_states=react_states,
                        listener=listener,
                    ))
                    seg_id += 1

            prev_line = line

    print(f"[director] Generated EDL: {len(edl.segments)} segments, "
          f"{edl.total_duration_ms}ms total")
    return edl
