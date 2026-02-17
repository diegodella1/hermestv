"""Data models for the visual pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DialogLine:
    """A single line of dialogue in the script."""
    character: str
    text: str
    audio_path: str | None = None
    duration_ms: int = 0
    emotion: str = "neutral"
    camera_hint: str | None = None  # "wide" | "closeup" | "twoshot" | None


@dataclass
class Scene:
    """A scene groups dialogue lines that share a setting."""
    scene_id: str
    background: str  # key into backgrounds, e.g. "studio"
    lines: list[DialogLine] = field(default_factory=list)


@dataclass
class Script:
    """Full show script — list of scenes with character definitions."""
    title: str
    characters: list[str]  # character IDs, e.g. ["alex", "maya"]
    scenes: list[Scene] = field(default_factory=list)


@dataclass
class CharacterConfig:
    """Loaded character asset bundle."""
    char_id: str
    label: str
    idle_path: Path = Path()
    talking_path: Path = Path()
    # Default position (legacy, used as fallback)
    position_x: float = 0.5
    position_y: float = 0.7  # anchor bottom
    scale: float = 1.0
    # Per-shot-type positions: {"wide": [x, y, scale], "closeup": [...], ...}
    positions: dict = field(default_factory=dict)
    # Emotion states: {"neutral": {"idle": Path, "talking": Path}, "excited": {...}}
    states: dict = field(default_factory=dict)


@dataclass
class EDLSegment:
    """One segment in the Edit Decision List."""
    segment_id: int
    shot_type: str  # "wide" | "closeup_left" | "closeup_right" | "twoshot"
    background_key: str  # e.g. "studio_wide", "studio_closeup_left"
    characters: list[str]  # character IDs visible in this shot
    speaker: str | None  # who's talking (None = nobody)
    audio_path: str | None  # path to audio file for this segment
    duration_ms: int  # total duration of this segment
    dialog_text: str = ""
    transition: str = "cut"  # "cut" | "dissolve" | "fade_black"
    # Emotion per character: {"alex": "excited", "maya": "neutral"}
    character_states: dict = field(default_factory=dict)
    listener: str | None = None  # for reaction shots


@dataclass
class EDL:
    """Edit Decision List — ordered segments to render."""
    segments: list[EDLSegment] = field(default_factory=list)

    @property
    def total_duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.segments)
