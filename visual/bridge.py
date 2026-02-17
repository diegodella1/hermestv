"""Bridge — converts Hermes radio breaks into visual renders.

Supports two modes:
- Monologue: single host + single audio → MP4 (legacy, used by break_builder)
- Dialog: multi-character script → per-line TTS → MP4 (new, Character Engine)
"""

import os
import tempfile
import time
from pathlib import Path

from visual.assets import AssetPack
from visual.compositor import render_segment, concatenate_segments
from visual.config import DEFAULT_ASSETS_DIR
from visual.director import generate_edl
from visual.ffmpeg_utils import probe_duration_ms
from visual.models import Script, Scene, DialogLine

# Map host IDs to visual character IDs
HOST_TO_CHARACTER = {
    "host_a": "alex",   # Luna → alex
    "host_b": "maya",   # Max → maya
}

# Voice config per character (piper model names)
CHARACTER_VOICE = {
    "alex": {"piper_model": "en_US-lessac-high"},
    "maya": {"piper_model": "en_US-ryan-high"},
    "rolo": {"piper_model": "en_US-lessac-high"},  # placeholder
}


def _extract_transitions(edl) -> list[str]:
    """Extract per-pair transition list from EDL segments."""
    transitions = []
    for seg in edl.segments[1:]:
        transitions.append(seg.transition)
    return transitions


def render_break_video(
    script_text: str,
    audio_path: str,
    host_id: str,
    break_id: str,
    output_dir: str | None = None,
    assets_dir: str | None = None,
) -> str | None:
    """Render a monologue radio break as an MP4 video.

    Args:
        script_text: The monologue script text
        audio_path: Path to the TTS audio file (MP3)
        host_id: Host ID from DB (e.g. "host_a")
        break_id: Break ID for filename
        output_dir: Where to save the MP4 (defaults to same dir as audio)
        assets_dir: Visual assets directory

    Returns:
        Path to the rendered MP4, or None on failure.
    """
    t0 = time.time()

    try:
        char_id = HOST_TO_CHARACTER.get(host_id, "alex")
        duration_ms = probe_duration_ms(audio_path)

        script = Script(
            title=break_id,
            characters=[char_id],
            scenes=[Scene(
                scene_id="scene_1",
                background="studio",
                lines=[DialogLine(
                    character=char_id,
                    text=script_text,
                    audio_path=audio_path,
                    duration_ms=duration_ms,
                )],
            )],
        )

        assets = AssetPack(Path(assets_dir or DEFAULT_ASSETS_DIR))
        assets.load(script.characters)

        edl = generate_edl(script)

        out_dir = Path(output_dir or os.path.dirname(audio_path))
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{break_id}.mp4"

        with tempfile.TemporaryDirectory(prefix="hermes_vis_") as render_dir:
            segment_paths = []
            for segment in edl.segments:
                mp4 = render_segment(segment, assets, render_dir)
                segment_paths.append(mp4)

            transitions = _extract_transitions(edl)
            concatenate_segments(
                segment_paths, output_path,
                temp_dir=render_dir, transitions=transitions,
            )

        elapsed = time.time() - t0
        print(f"[visual:bridge] Rendered {break_id} in {elapsed:.1f}s → {output_path}")
        return str(output_path)

    except Exception as e:
        print(f"[visual:bridge] Render failed: {e}")
        return None


def synthesize_dialog(dialog_script: dict, output_dir: str) -> dict:
    """Synthesize TTS audio for each line in a dialog script.

    Uses per-character voice config. Updates audio_path and duration_ms
    in each line of the script dict.

    Args:
        dialog_script: Script dict with scenes/lines
        output_dir: Directory to write audio files

    Returns:
        Updated dialog_script dict with audio_path/duration_ms filled in.
    """
    from visual.tts_standalone import synthesize_line

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    line_idx = 0
    for scene in dialog_script.get("scenes", []):
        for line in scene.get("lines", []):
            char_id = line["character"]
            voice_cfg = CHARACTER_VOICE.get(char_id, CHARACTER_VOICE["alex"])

            audio_path, duration_ms = synthesize_line(
                text=line["text"],
                character=char_id,
                output_dir=str(out),
                provider="piper",
                model=voice_cfg["piper_model"],
            )
            line["audio_path"] = audio_path
            line["duration_ms"] = duration_ms
            line_idx += 1
            print(f"[bridge:tts] Line {line_idx} ({char_id}): {duration_ms}ms")

    return dialog_script


def render_dialog_video(
    dialog_script: dict,
    break_id: str,
    output_dir: str,
    assets_dir: str | None = None,
) -> str | None:
    """Render a multi-character dialog script as an MP4 video.

    Args:
        dialog_script: Script dict (with audio_path/duration_ms per line)
        break_id: ID for the output filename
        output_dir: Where to save the MP4
        assets_dir: Visual assets directory

    Returns:
        Path to the rendered MP4, or None on failure.
    """
    t0 = time.time()

    try:
        from visual.script_generator import _parse_script

        script = _parse_script(dialog_script)

        assets = AssetPack(Path(assets_dir or DEFAULT_ASSETS_DIR))
        assets.load(script.characters)

        edl = generate_edl(script)

        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        output_path = out_dir / f"{break_id}.mp4"

        with tempfile.TemporaryDirectory(prefix="hermes_vis_") as render_dir:
            segment_paths = []
            for segment in edl.segments:
                mp4 = render_segment(segment, assets, render_dir)
                segment_paths.append(mp4)

            transitions = _extract_transitions(edl)
            concatenate_segments(
                segment_paths, output_path,
                temp_dir=render_dir, transitions=transitions,
            )

        elapsed = time.time() - t0
        print(f"[visual:bridge] Rendered dialog {break_id} in {elapsed:.1f}s → {output_path}")
        return str(output_path)

    except Exception as e:
        print(f"[visual:bridge] Dialog render failed: {e}")
        return None
