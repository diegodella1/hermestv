"""CLI entry point: python -m visual

Usage:
  python -m visual --script test_data/sample_script.json --assets assets/ --output test.mp4
  python -m visual --topic "Bitcoin hits 200k" --assets assets/ --output test.mp4
  python -m visual --script test_data/sample_script.json --assets assets/ --output test.mp4 --skip-tts
  python -m visual --topic "Bitcoin breaks 200K" --characters alex,maya --assets assets/ --output test.mp4
"""

import argparse
import sys
import tempfile
import time
from pathlib import Path

from visual.config import DEFAULT_ASSETS_DIR, DEFAULT_OUTPUT_DIR, FPS


def main():
    parser = argparse.ArgumentParser(
        description="Hermes Visual Module — render animated news breaks"
    )
    parser.add_argument("--script", help="Path to script JSON file")
    parser.add_argument("--topic", help="Generate script from topic (requires OpenAI)")
    parser.add_argument("--characters", default="alex,maya",
                        help="Comma-separated character IDs for dialog generation")
    parser.add_argument("--assets", default=str(DEFAULT_ASSETS_DIR),
                        help="Assets directory")
    parser.add_argument("--output", default="output.mp4", help="Output MP4 path")
    parser.add_argument("--skip-tts", action="store_true",
                        help="Skip TTS — use durations from script JSON")
    parser.add_argument("--tts-provider", default="piper",
                        choices=["piper", "openai"], help="TTS provider")
    parser.add_argument("--tts-voice", default="", help="TTS voice ID")
    parser.add_argument("--tts-model", default="", help="TTS model name")

    args = parser.parse_args()

    if not args.script and not args.topic:
        parser.error("Either --script or --topic is required")

    t0 = time.time()

    # 1. Load or generate script
    from visual.script_generator import load_script, generate_script

    if args.script:
        print(f"[visual] Loading script: {args.script}")
        script = load_script(args.script)
    else:
        print(f"[visual] Generating script for: {args.topic}")
        script = generate_script(args.topic)

    print(f"[visual] Script: '{script.title}' — {len(script.scenes)} scenes, "
          f"characters: {script.characters}")

    # 2. Load assets
    from visual.assets import AssetPack

    assets = AssetPack(Path(args.assets))
    assets.load(script.characters)

    # 3. TTS — synthesize audio for each line
    if not args.skip_tts:
        from visual.tts_standalone import synthesize_line
        from visual.bridge import CHARACTER_VOICE

        audio_dir = Path(tempfile.mkdtemp(prefix="hermes_tts_"))
        print(f"[visual] TTS output dir: {audio_dir}")

        for scene in script.scenes:
            for line in scene.lines:
                voice_cfg = CHARACTER_VOICE.get(line.character, {})
                model = args.tts_model or voice_cfg.get("piper_model", "")
                voice = args.tts_voice

                audio_path, duration = synthesize_line(
                    text=line.text,
                    character=line.character,
                    output_dir=str(audio_dir),
                    provider=args.tts_provider,
                    voice=voice,
                    model=model,
                )
                line.audio_path = audio_path
                line.duration_ms = duration
    else:
        print("[visual] Skipping TTS — using durations from script")
        for scene in script.scenes:
            for line in scene.lines:
                if line.duration_ms <= 0:
                    line.duration_ms = 3000  # default 3s per line

    t_tts = time.time()
    print(f"[visual] TTS phase: {t_tts - t0:.1f}s")

    # 4. Generate EDL
    from visual.director import generate_edl

    edl = generate_edl(script)

    # 5. Render segments
    from visual.compositor import render_segment, concatenate_segments
    from visual.bridge import _extract_transitions

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="hermes_render_") as render_dir:
        segment_paths = []
        for segment in edl.segments:
            mp4_path = render_segment(segment, assets, render_dir)
            segment_paths.append(mp4_path)

        # 6. Concatenate with per-pair transitions from EDL
        transitions = _extract_transitions(edl)
        concatenate_segments(
            segment_paths, output_path,
            temp_dir=render_dir, transitions=transitions,
        )

    t_render = time.time()
    print(f"[visual] Render phase: {t_render - t_tts:.1f}s")
    print(f"[visual] Total: {t_render - t0:.1f}s")
    print(f"[visual] Output: {output_path} "
          f"({edl.total_duration_ms / 1000:.1f}s @ {FPS}fps)")


if __name__ == "__main__":
    main()
