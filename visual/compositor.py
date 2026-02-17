"""Compositor — renders EDL segments to MP4 using Pillow + FFmpeg.

Rendering approach (no frame-by-frame Python rendering):
1. Pillow composes 2 PNGs per segment: frame_idle + frame_talking
2. numpy lip-sync data → run-length encoding → FFmpeg concat file
3. FFmpeg concat demuxer alternates between images + mixes audio
4. Final concatenation: -c copy for all-cut, xfade for dissolve/fade_black
"""

import os
import tempfile
from pathlib import Path

from PIL import Image

from visual.assets import AssetPack
from visual.audio_analysis import analyze_lipsync
from visual.config import (
    WIDTH, HEIGHT, FPS, CROSSFADE_DURATION_S,
    DISSOLVE_DURATION_S, FADE_BLACK_DURATION_S,
)
from visual.ffmpeg_utils import run_ffmpeg, get_encoder_args, detect_encoder, probe_duration_ms
from visual.models import EDL, EDLSegment

# Module-level encoder (detected once)
_encoder: str | None = None


def _get_encoder() -> str:
    global _encoder
    if _encoder is None:
        _encoder = detect_encoder()
    return _encoder


def compose_frame(
    bg_path: Path,
    characters: list[tuple[Path, float, float, float]],
    output_path: Path,
    speaker_name: str | None = None,
    headline: str | None = None,
) -> None:
    """Compose a single frame: background + character overlays + lower third.

    Args:
        bg_path: Background PNG path
        characters: List of (png_path, position_x, position_y, scale)
        output_path: Where to save the composed PNG
        speaker_name: Optional speaker name for lower third
        headline: Optional headline text for lower third
    """
    bg = Image.open(bg_path).convert("RGBA").resize((WIDTH, HEIGHT))

    for char_path, px, py, scale in characters:
        char_img = Image.open(char_path).convert("RGBA")
        # Scale character
        cw = int(char_img.width * scale)
        ch = int(char_img.height * scale)
        char_img = char_img.resize((cw, ch), Image.LANCZOS)
        # Position: px/py are fractions, anchor at bottom-center
        x = int(px * WIDTH - cw / 2)
        y = int(py * HEIGHT - ch)
        bg.paste(char_img, (x, y), char_img)

    result = bg.convert("RGB")

    # Lower third overlay
    if speaker_name or headline:
        from visual.lower_third import render_lower_third
        result = render_lower_third(result, speaker_name, headline)

    result.save(output_path, "PNG")


def render_segment(
    segment: EDLSegment,
    assets: AssetPack,
    temp_dir: str,
) -> Path:
    """Render a single EDL segment to MP4.

    - With audio: 2 composites (idle/talking) + concat demuxer lip-sync
    - Without audio: 1 static composite + silent audio track
    """
    seg_dir = Path(temp_dir) / f"seg_{segment.segment_id:03d}"
    seg_dir.mkdir(exist_ok=True)

    encoder = _get_encoder()
    enc_args = get_encoder_args(encoder)
    output_mp4 = seg_dir / "segment.mp4"

    bg_path = assets.get_background(segment.shot_type)

    if segment.audio_path and segment.speaker:
        return _render_with_audio(segment, assets, bg_path, seg_dir, enc_args, output_mp4)
    else:
        return _render_silent(segment, assets, bg_path, seg_dir, enc_args, output_mp4)


def _build_character_layers(
    segment: EDLSegment,
    assets: AssetPack,
    state: str,
) -> list[tuple[Path, float, float, float]]:
    """Build character layer list for a given state (idle/talking).

    Uses emotion-aware PNGs and per-shot-type positions when available.
    """
    layers = []
    for cid in segment.characters:
        emotion = segment.character_states.get(cid, "neutral")
        is_talking = (cid == segment.speaker and state == "talking")
        png = assets.get_character_png(cid, emotion, is_talking)
        px, py, scale = assets.get_character_position(cid, segment.shot_type)
        layers.append((png, px, py, scale))
    return layers


def _render_with_audio(
    segment: EDLSegment,
    assets: AssetPack,
    bg_path: Path,
    seg_dir: Path,
    enc_args: list[str],
    output_mp4: Path,
) -> Path:
    """Render segment with audio and lip-sync."""
    # Lower third info
    speaker_label = None
    if segment.speaker and segment.speaker in assets.characters:
        speaker_label = assets.characters[segment.speaker].label
    headline = segment.dialog_text if segment.dialog_text else None

    # Compose idle and talking frames
    idle_png = seg_dir / "frame_idle.png"
    talking_png = seg_dir / "frame_talking.png"

    idle_layers = _build_character_layers(segment, assets, "idle")
    talking_layers = _build_character_layers(segment, assets, "talking")

    compose_frame(bg_path, idle_layers, idle_png,
                  speaker_name=speaker_label, headline=headline)
    compose_frame(bg_path, talking_layers, talking_png,
                  speaker_name=speaker_label, headline=headline)

    # Analyze lip-sync
    lipsync = analyze_lipsync(segment.audio_path, FPS)

    if not lipsync:
        # Fallback: all talking
        total_frames = max(1, int(segment.duration_ms * FPS / 1000))
        lipsync = [True] * total_frames

    # Run-length encode → concat demuxer file
    concat_file = seg_dir / "concat.txt"
    _write_concat_file(concat_file, lipsync, idle_png, talking_png)

    # FFmpeg: concat demuxer + audio → MP4
    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-i", str(segment.audio_path),
        "-r", str(FPS),
        *enc_args,
        "-c:a", "aac", "-b:a", "128k", "-ar", "44100", "-ac", "2",
        "-shortest",
        "-movflags", "+faststart",
        str(output_mp4),
    ], desc=f"render seg {segment.segment_id} (audio)")

    return output_mp4


def _render_silent(
    segment: EDLSegment,
    assets: AssetPack,
    bg_path: Path,
    seg_dir: Path,
    enc_args: list[str],
    output_mp4: Path,
) -> Path:
    """Render a silent segment (e.g. wide shot, reaction shot)."""
    frame_png = seg_dir / "frame.png"
    layers = _build_character_layers(segment, assets, "idle")
    compose_frame(bg_path, layers, frame_png)

    duration_s = segment.duration_ms / 1000.0

    # FFmpeg: static image + silent audio → MP4
    run_ffmpeg([
        "-loop", "1", "-i", str(frame_png),
        "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo",
        "-t", f"{duration_s:.3f}",
        "-r", str(FPS),
        *enc_args,
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output_mp4),
    ], desc=f"render seg {segment.segment_id} (silent {duration_s:.1f}s)")

    return output_mp4


def _write_concat_file(
    path: Path,
    lipsync: list[bool],
    idle_png: Path,
    talking_png: Path,
) -> None:
    """Write FFmpeg concat demuxer file from lip-sync bools."""
    runs = _run_length_encode(lipsync)
    lines = ["ffconcat version 1.0"]

    for is_talking, count in runs:
        png = talking_png if is_talking else idle_png
        duration = count / FPS
        lines.append(f"file '{png}'")
        lines.append(f"duration {duration:.6f}")

    # Concat demuxer needs the last file repeated without duration
    last_talking = runs[-1][0] if runs else False
    last_png = talking_png if last_talking else idle_png
    lines.append(f"file '{last_png}'")

    path.write_text("\n".join(lines))


def _run_length_encode(bools: list[bool]) -> list[tuple[bool, int]]:
    """Run-length encode a list of bools → [(value, count), ...]."""
    if not bools:
        return []
    runs = []
    current = bools[0]
    count = 1
    for b in bools[1:]:
        if b == current:
            count += 1
        else:
            runs.append((current, count))
            current = b
            count = 1
    runs.append((current, count))
    return runs


def concatenate_segments(
    segment_paths: list[Path],
    output: Path,
    temp_dir: str | None = None,
    transitions: list[str] | None = None,
) -> None:
    """Concatenate rendered segments into final MP4.

    Args:
        segment_paths: Ordered list of segment MP4 files
        output: Final output path
        temp_dir: Temp directory for concat files
        transitions: Per-pair transition list (len = len(segments)-1).
                     Values: "cut", "dissolve", "fade_black".
                     If None, uses fast -c copy concat.
    """
    if not segment_paths:
        raise ValueError("No segments to concatenate")

    if len(segment_paths) == 1:
        import shutil
        shutil.copy2(segment_paths[0], output)
        return

    # Check if any non-cut transitions exist
    has_effects = False
    if transitions:
        has_effects = any(t != "cut" for t in transitions)

    if has_effects and transitions:
        _concatenate_with_transitions(segment_paths, output, transitions)
    else:
        _concatenate_copy(segment_paths, output, temp_dir)

    print(f"[compositor] Final output: {output}")


def _concatenate_copy(
    segment_paths: list[Path], output: Path, temp_dir: str | None
) -> None:
    """Fast concatenation with -c copy (no re-encode, no transitions)."""
    if temp_dir:
        concat_file = Path(temp_dir) / "final_concat.txt"
    else:
        import tempfile as _tf
        concat_file = Path(_tf.mktemp(suffix="_concat.txt"))

    lines = []
    for p in segment_paths:
        lines.append(f"file '{p}'")
    concat_file.write_text("\n".join(lines))

    run_ffmpeg([
        "-f", "concat", "-safe", "0", "-i", str(concat_file),
        "-c", "copy",
        "-movflags", "+faststart",
        str(output),
    ], desc="concatenate (copy)")


def _concatenate_with_transitions(
    segment_paths: list[Path],
    output: Path,
    transitions: list[str],
) -> None:
    """Concatenate with per-pair transitions (cut/dissolve/fade_black).

    Cut pairs get duration=0 (effectively instant), dissolve/fade_black
    get their configured durations via xfade filter.
    """
    n = len(segment_paths)
    encoder = _get_encoder()
    enc_args = get_encoder_args(encoder)

    # Get durations
    durations = []
    for p in segment_paths:
        dur_ms = probe_duration_ms(p)
        durations.append(dur_ms / 1000.0)

    # Build inputs
    inputs = []
    for p in segment_paths:
        inputs.extend(["-i", str(p)])

    # Build xfade filter chain
    v_filters = []
    a_filters = []

    combined_dur = durations[0]

    for i in range(n - 1):
        t = transitions[i] if i < len(transitions) else "cut"

        if t == "dissolve":
            fade_dur = DISSOLVE_DURATION_S
            xfade_type = "fade"
        elif t == "fade_black":
            fade_dur = FADE_BLACK_DURATION_S
            xfade_type = "fade"
        else:
            # Cut: minimal crossfade to avoid re-encode complexity
            # Use concat demuxer approach instead — but since we're in
            # mixed mode, use a very short fade (1 frame)
            fade_dur = 1.0 / FPS
            xfade_type = "fade"

        offset = max(combined_dur - fade_dur, 0.01)

        if i == 0:
            v_in = "[0:v][1:v]"
            a_in = "[0:a][1:a]"
        else:
            v_in = f"[vf{i-1}][{i+1}:v]"
            a_in = f"[af{i-1}][{i+1}:a]"

        v_out = f"[vf{i}]" if i < n - 2 else "[vout]"
        a_out = f"[af{i}]" if i < n - 2 else "[aout]"

        v_filters.append(
            f"{v_in}xfade=transition={xfade_type}:duration={fade_dur:.3f}:offset={offset:.3f}{v_out}"
        )
        a_filters.append(
            f"{a_in}acrossfade=d={fade_dur:.3f}:c1=tri:c2=tri{a_out}"
        )

        combined_dur = combined_dur + durations[i + 1] - fade_dur

    filter_complex = ";".join(v_filters + a_filters)

    run_ffmpeg([
        *inputs,
        "-filter_complex", filter_complex,
        "-map", "[vout]", "-map", "[aout]",
        "-r", str(FPS),
        *enc_args,
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(output),
    ], desc=f"concatenate ({n} segments, transitions)")
