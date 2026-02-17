"""Script generator — uses GPT-4o-mini to create structured dialog scripts."""

import json
import os

from visual.models import Script, Scene, DialogLine

SYSTEM_PROMPT = """You are a TV news show scriptwriter. Generate a short dialog script
for a 2-person news break. Output valid JSON matching this structure:

{
  "title": "Breaking News Title",
  "characters": ["alex", "maya"],
  "scenes": [
    {
      "scene_id": "scene_1",
      "background": "studio",
      "lines": [
        {"character": "alex", "text": "Good evening, I'm Alex..."},
        {"character": "maya", "text": "And I'm Maya..."}
      ]
    }
  ]
}

Rules:
- 2 characters: alex and maya
- 4-8 dialog lines total
- Each line: 1-2 sentences, conversational news anchor style
- background is always "studio" for Phase 1
- Keep it under 30 seconds when spoken aloud
"""


def generate_script(topic: str) -> Script:
    """Generate a dialog script for a given news topic using OpenAI."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY required for script generation")

    from openai import OpenAI
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Write a news break script about: {topic}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.7,
        max_tokens=800,
    )

    raw = json.loads(response.choices[0].message.content)
    return _parse_script(raw)


def load_script(path: str) -> Script:
    """Load a script from a JSON file."""
    with open(path) as f:
        raw = json.load(f)
    return _parse_script(raw)


def _parse_script(raw: dict) -> Script:
    """Parse raw JSON dict into Script dataclass."""
    scenes = []
    for s in raw.get("scenes", []):
        lines = [
            DialogLine(
                character=l["character"],
                text=l["text"],
                audio_path=l.get("audio_path"),
                duration_ms=l.get("duration_ms", 0),
                emotion=l.get("emotion", "neutral"),
                camera_hint=l.get("camera_hint"),
            )
            for l in s.get("lines", [])
        ]
        scenes.append(Scene(
            scene_id=s.get("scene_id", "scene_1"),
            background=s.get("background", "studio"),
            lines=lines,
        ))

    return Script(
        title=raw.get("title", "Untitled"),
        characters=raw.get("characters", ["alex", "maya"]),
        scenes=scenes,
    )
