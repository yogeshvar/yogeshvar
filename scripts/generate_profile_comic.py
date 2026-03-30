#!/usr/bin/env python3
"""
Fetch WakaTime stats, ask Gemini (text) for a 3-panel comic script, then
generate each panel with a Gemini image model via the google-genai SDK.
Updates README between COMIC_STORY delimiters and writes assets/comic/latest/*.png
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import random
import sys
import urllib.error
import urllib.request
from pathlib import Path

from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets" / "comic" / "latest"
HASH_FILE = ROOT / ".github" / ".last_wakatime_hash"

# gemini-2.0-flash is retired for new API keys; we try 2.5 first, then 1.5.
DEFAULT_TEXT_MODEL_CHAIN = ("gemini-2.5-flash", "gemini-1.5-flash")
IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"
)


def text_models_to_try() -> list[str]:
    override = os.environ.get("GEMINI_TEXT_MODEL", "").strip()
    if override:
        return [override]
    return list(DEFAULT_TEXT_MODEL_CHAIN)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes")


def http_json_get_soft(url: str, headers: dict[str, str]) -> dict | None:
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        print(f"WakaTime HTTP {e.code} (will try placeholder stats if needed).", file=sys.stderr)
        return None
    except urllib.error.URLError as e:
        print(f"WakaTime request failed: {e}", file=sys.stderr)
        return None
    return json.loads(body) if body else None


def wakatime_stats_soft(api_key: str) -> dict | None:
    url = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    return http_json_get_soft(url, headers)


# Synthetic "last 7 days" shapes for first-week / empty API / local testing.
FALLBACK_FACT_SCENARIOS: list[dict] = [
    {
        "total_seconds": 42,
        "daily_average_seconds": 6,
        "human_readable_total": "42 secs",
        "languages": [
            {"name": "GitHub Actions YAML", "percent": 88.0, "text": "1 min"},
            {"name": "Bash", "percent": 12.0, "text": "5 secs"},
        ],
        "editors": [{"name": "CI Terminal", "percent": 100.0}],
        "_label": "yaml_golfer",
    },
    {
        "total_seconds": 0,
        "daily_average_seconds": 0,
        "human_readable_total": "0 secs",
        "languages": [],
        "editors": [],
        "_label": "absolute_zero",
    },
    {
        "total_seconds": 86400 * 2,
        "daily_average_seconds": 28800,
        "human_readable_total": "48 hrs",
        "languages": [
            {"name": "TypeScript", "percent": 40.0, "text": "19 hrs"},
            {"name": "JSON", "percent": 35.0, "text": "17 hrs"},
            {"name": "Markdown", "percent": 25.0, "text": "12 hrs"},
        ],
        "editors": [{"name": "VS Code", "percent": 70.0}, {"name": "Vim", "percent": 30.0}],
        "_label": "config_engineer",
    },
    {
        "total_seconds": 3600,
        "daily_average_seconds": 514,
        "human_readable_total": "1 hr",
        "languages": [
            {"name": "Other", "percent": 100.0, "text": "1 hr"},
        ],
        "editors": [{"name": "Unknown", "percent": 100.0}],
        "_label": "mystery_meat",
    },
    {
        "total_seconds": 72000,
        "daily_average_seconds": 10286,
        "human_readable_total": "20 hrs",
        "languages": [
            {"name": "Python", "percent": 50.0, "text": "10 hrs"},
            {"name": "Rust", "percent": 30.0, "text": "6 hrs"},
            {"name": "TOML", "percent": 20.0, "text": "4 hrs"},
        ],
        "editors": [{"name": "Neovim", "percent": 100.0}],
        "_label": "rewrite_week",
    },
    {
        "total_seconds": 1800,
        "daily_average_seconds": 257,
        "human_readable_total": "30 mins",
        "languages": [
            {"name": "Dockerfile", "percent": 60.0, "text": "18 mins"},
            {"name": "Stack Overflow paste", "percent": 40.0, "text": "12 mins"},
        ],
        "editors": [{"name": "Cursor", "percent": 100.0}],
        "_label": "container_chaos",
    },
]


def facts_are_sparse(facts: dict) -> bool:
    langs = facts.get("languages") or []
    total = facts.get("total_seconds")
    if len(langs) == 0:
        return True
    if total is None:
        return True
    try:
        t = int(total)
    except (TypeError, ValueError):
        return True
    return t <= 0


def pick_fallback_facts() -> dict:
    scenario = random.choice(FALLBACK_FACT_SCENARIOS)
    out = {k: v for k, v in scenario.items() if not k.startswith("_")}
    out["_placeholder"] = True
    out["_label"] = scenario.get("_label", "random")
    return out


def comic_plan_schema() -> types.Schema:
    panel = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "caption": types.Schema(type=types.Type.STRING),
            "image_prompt": types.Schema(type=types.Type.STRING),
        },
        required=["caption", "image_prompt"],
    )
    return types.Schema(
        type=types.Type.OBJECT,
        properties={
            "title": types.Schema(type=types.Type.STRING),
            "character_design": types.Schema(type=types.Type.STRING),
            "panels": types.Schema(type=types.Type.ARRAY, items=panel),
        },
        required=["title", "character_design", "panels"],
    )


def fetch_comic_plan(client: genai.Client, user_text: str) -> dict:
    config = types.GenerateContentConfig(
        temperature=0.85,
        response_mime_type="application/json",
        response_schema=comic_plan_schema(),
    )
    errors: list[str] = []
    for model in text_models_to_try():
        try:
            resp = client.models.generate_content(
                model=model,
                contents=user_text,
                config=config,
            )
        except Exception as e:
            msg = f"{model}: {e}"
            errors.append(msg)
            print(f"Gemini text {msg}", file=sys.stderr)
            continue

        raw = (resp.text or "").strip()
        if not raw:
            fr = None
            if resp.candidates:
                fr = resp.candidates[0].finish_reason
            msg = f"{model}: empty text (finish_reason={fr!r})"
            errors.append(msg)
            print(msg, file=sys.stderr)
            continue

        print(f"Using Gemini text model {model}", file=sys.stderr)
        try:
            return json.loads(raw)
        except json.JSONDecodeError as e:
            die(f"Invalid JSON from {model} despite schema: {e}\n{raw[:1200]}")

    die(
        "Gemini text failed for all configured models:\n"
        + "\n".join(errors)
        + "\nSet GEMINI_TEXT_MODEL to a model your key supports (Google AI Studio)."
    )


def gemini_image_png(
    client: genai.Client,
    model: str,
    *,
    scene_prompt: str,
    character_design: str | None,
    reference_png: bytes | None,
) -> bytes:
    image_config = types.ImageConfig(aspect_ratio="1:1")
    if "3.1-flash-image" in model or "3-pro-image" in model:
        image_config.image_size = "1K"
    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=image_config,
    )

    if reference_png is None:
        if not (character_design or "").strip():
            die("character_design is required for the first panel")
        text = (
            "Single square comic panel.\n\n"
            "CHARACTER — draw exactly this design; it must stay consistent "
            "across a 3-panel strip:\n"
            f"{character_design.strip()}\n\n"
            f"SCENE:\n{scene_prompt}"
        )
        contents: str | list[types.Part] = text
    else:
        text = (
            "The attached image is panel 1 of the same comic strip. "
            "Keep the protagonist IDENTICAL: same face shape, features, hair, "
            "glasses, skin tone, body proportions, clothing, and colors. "
            "Same outline thickness and flat-color style. Do not invent a new character.\n\n"
            "Draw only the next panel (one new frame), same canvas style:\n"
            f"{scene_prompt}"
        )
        contents = [
            types.Part.from_text(text=text),
            types.Part.from_bytes(data=reference_png, mime_type="image/png"),
        ]

    resp = client.models.generate_content(
        model=model,
        contents=contents,
        config=config,
    )
    for part in resp.parts or []:
        if part.thought:
            continue
        if part.inline_data is not None and part.inline_data.data:
            mime = (part.inline_data.mime_type or "").lower()
            if "image" in mime:
                data = part.inline_data.data
                if isinstance(data, str):
                    return base64.b64decode(data)
                return bytes(data)
    die(f"No image in Gemini response (model={model}).")


def facts_from_wakatime(stats: dict) -> dict:
    data = stats.get("data") or {}
    langs = []
    for row in data.get("languages") or []:
        name = row.get("name")
        if not name:
            continue
        langs.append(
            {
                "name": name,
                "percent": row.get("percent"),
                "text": row.get("text"),
            }
        )
    langs = sorted(
        langs, key=lambda x: float(x.get("percent") or 0), reverse=True
    )[:8]
    editors = [
        {"name": e.get("name"), "percent": e.get("percent")}
        for e in (data.get("editors") or [])[:5]
        if e.get("name")
    ]
    return {
        "total_seconds": data.get("total_seconds"),
        "daily_average_seconds": data.get("daily_average"),
        "human_readable_total": data.get("human_readable_total"),
        "languages": langs,
        "editors": editors,
    }


def build_readme_block(
    owner: str,
    repo: str,
    branch: str,
    title: str,
    panels: list[dict],
    *,
    used_placeholder: bool,
) -> str:
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/assets/comic/latest"
    if used_placeholder:
        data_line = (
            "*Demo run: placeholder dev stats (no WakaTime key, API error, empty week, "
            "or manual demo mode) + "
            "[Gemini Nano Banana](https://ai.google.dev/gemini-api/docs/image-generation).*"
        )
    else:
        data_line = (
            "*Auto-generated from WakaTime + "
            "[Gemini Nano Banana](https://ai.google.dev/gemini-api/docs/image-generation).*"
        )
    lines = [
        f"### {title}",
        "",
        data_line,
        "",
    ]
    for i, p in enumerate(panels, start=1):
        cap = p.get("caption", "").strip()
        lines.append(f"![Panel {i}]({base}/{i}.png)")
        lines.append("")
        if cap:
            lines.append(f"*{cap}*")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def replace_delimited_block(readme: str, new_inner: str) -> str:
    start = "<!-- COMIC_STORY_START -->"
    end = "<!-- COMIC_STORY_END -->"
    if start not in readme or end not in readme:
        die(f"README must contain {start} and {end}")
    pre, rest = readme.split(start, 1)
    _, post = rest.split(end, 1)
    return pre + start + "\n" + new_inner + "\n" + end + post


def main() -> None:
    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    waka_key = os.environ.get("WAKATIME_API_KEY", "").strip()
    if not gemini_key:
        die("GEMINI_API_KEY is required")
    client = genai.Client(api_key=gemini_key)

    force = _truthy_env("COMIC_FORCE")
    use_placeholder = _truthy_env("COMIC_USE_PLACEHOLDER")

    repo_full = os.environ.get("GITHUB_REPOSITORY", "yogeshvar/yogeshvar")
    owner, repo = repo_full.split("/", 1)
    branch = os.environ.get("DEFAULT_BRANCH", "master").strip() or "master"

    used_placeholder = False
    facts: dict

    if use_placeholder:
        facts = pick_fallback_facts()
        used_placeholder = True
        print("Using random demo stats (COMIC_USE_PLACEHOLDER).", file=sys.stderr)
    elif not waka_key:
        facts = pick_fallback_facts()
        used_placeholder = True
        print("No WAKATIME_API_KEY; using random demo stats.", file=sys.stderr)
    else:
        stats = wakatime_stats_soft(waka_key)
        if stats is None:
            facts = pick_fallback_facts()
            used_placeholder = True
            print("WakaTime request failed; using random demo stats.", file=sys.stderr)
        else:
            facts = facts_from_wakatime(stats)
            if facts_are_sparse(facts):
                facts = pick_fallback_facts()
                used_placeholder = True
                print("WakaTime stats empty or zero; using random demo stats.", file=sys.stderr)

    facts_clean = {k: v for k, v in facts.items() if not str(k).startswith("_")}
    payload = json.dumps(facts_clean, indent=2)
    h = hashlib.sha256(payload.encode()).hexdigest()

    if (
        not force
        and not used_placeholder
        and HASH_FILE.exists()
        and HASH_FILE.read_text().strip() == h
    ):
        print("WakaTime stats unchanged; skipping comic regeneration.")
        print("Set COMIC_FORCE=1 to regenerate anyway.", file=sys.stderr)
        return

    system_instructions = """You are writing a short funny 3-panel developer comic for a GitHub profile.
The humor must be grounded ONLY in the JSON stats provided (languages, time, editors). No invented employers or projects.
Return ONLY valid JSON with this shape:
{
  "title": "short title",
  "character_design": "one paragraph, fixed forever for all 3 panels",
  "panels": [
    { "caption": "one line joke for under the image", "image_prompt": "detailed single-panel illustration prompt" },
    { "caption": "...", "image_prompt": "..." },
    { "caption": "...", "image_prompt": "..." }
  ]
}
Rules:
- character_design: ONE dense paragraph naming a single recurring protagonist. Include species (human cartoon), approximate age vibe, hair (color, length, style), face (glasses yes/no, eye style), skin tone as simple cartoon palette, outfit (shirt color, layers), and one memorable prop if any (e.g. coffee mug). This text is copied verbatim into the image generator; be specific so every panel matches.
- image_prompt: ONLY the action, pose, expression, props, and background for THAT panel. Do NOT redesign or re-describe the character's face, hair, or clothes — refer to them as "the developer" or "they" if needed. Same art direction always: bold black outlines, flat colors, simple background, no readable text in the image, no logos, no real people's faces.
- Keep captions witty and self-deprecating, PG-rated."""

    demo_note = ""
    if used_placeholder:
        demo_note = (
            "\nNOTE: These stats are fictional demo/placeholder data (e.g. first week of WakaTime or CI testing). "
            "Still treat the numbers and language names literally for jokes.\n"
        )

    user_msg = f"{system_instructions}{demo_note}\n\nSTATS_JSON:\n{payload}"
    comic = fetch_comic_plan(client, user_msg)
    panels = comic.get("panels") or []
    if len(panels) != 3:
        die(f"Expected 3 panels, got {len(panels)}: {json.dumps(comic)[:800]}")
    title = (comic.get("title") or "This week in code").strip()
    character_design = (comic.get("character_design") or "").strip()
    if not character_design:
        die("Comic plan missing character_design (needed for consistent character).")

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    style_suffix = (
        " Office/desk developer setting unless the joke needs a tiny background change; "
        "thick black outlines, flat colors, no text or logos in the frame."
    )
    reference_png: bytes | None = None
    for i, p in enumerate(panels, start=1):
        scene = (p.get("image_prompt") or "").strip() + style_suffix
        png = gemini_image_png(
            client,
            IMAGE_MODEL,
            scene_prompt=scene,
            character_design=character_design if reference_png is None else None,
            reference_png=reference_png,
        )
        (ASSETS_DIR / f"{i}.png").write_bytes(png)
        print(f"Wrote panel {i} ({len(png)} bytes)")
        if reference_png is None:
            reference_png = png

    if not README.exists():
        die(f"Missing {README}")
    readme_body = README.read_text(encoding="utf-8")
    block = build_readme_block(
        owner, repo, branch, title, panels, used_placeholder=used_placeholder
    )
    new_readme = replace_delimited_block(readme_body, block)
    README.write_text(new_readme, encoding="utf-8")

    if used_placeholder:
        if HASH_FILE.exists():
            HASH_FILE.unlink()
            print("Cleared WakaTime hash file (demo run).", file=sys.stderr)
    else:
        HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
        HASH_FILE.write_text(h, encoding="utf-8")
    print("README and comic assets updated.")


if __name__ == "__main__":
    main()
