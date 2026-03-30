#!/usr/bin/env python3
"""
Fetch WakaTime stats, ask Gemini (text) for a 3-panel comic script, then
generate each panel with a Gemini Nano Banana image model. Updates README
between COMIC_STORY delimiters and writes assets/comic/latest/*.png
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
ASSETS_DIR = ROOT / "assets" / "comic" / "latest"
HASH_FILE = ROOT / ".github" / ".last_wakatime_hash"

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"
TEXT_MODEL = os.environ.get("GEMINI_TEXT_MODEL", "gemini-2.5-flash")
IMAGE_MODEL = os.environ.get(
    "GEMINI_IMAGE_MODEL", "gemini-2.5-flash-image"
)


def die(msg: str, code: int = 1) -> None:
    print(msg, file=sys.stderr)
    sys.exit(code)


def http_json(
    url: str,
    payload: dict | None,
    headers: dict[str, str],
    method: str = "GET",
) -> dict:
    data = None
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers = {**headers, "Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        die(f"HTTP {e.code} {url}: {err_body[:2000]}")
    except urllib.error.URLError as e:
        die(f"Request failed: {e}")
    return json.loads(body) if body else {}


def wakatime_stats(api_key: str) -> dict:
    url = "https://wakatime.com/api/v1/users/current/stats/last_7_days"
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    headers = {"Authorization": f"Basic {token}"}
    return http_json(url, None, headers)


def gemini_text(api_key: str, model: str, user_text: str) -> str:
    url = f"{GEMINI_BASE}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.85,
            "responseMimeType": "application/json",
        },
    }
    out = http_json(url, payload, {})
    parts = (
        out.get("candidates", [{}])[0]
        .get("content", {})
        .get("parts", [])
    )
    texts = [p.get("text", "") for p in parts if p.get("text")]
    if not texts:
        die(f"No text in Gemini response: {json.dumps(out)[:1500]}")
    return "".join(texts).strip()


def gemini_image_png(api_key: str, model: str, prompt: str) -> bytes:
    url = f"{GEMINI_BASE}/models/{model}:generateContent?key={api_key}"
    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["IMAGE"],
            "imageConfig": {
                "aspectRatio": "1:1",
            },
        },
    }
    if "3.1-flash-image" in model or "3-pro-image" in model:
        payload["generationConfig"]["imageConfig"]["imageSize"] = "1K"

    out = http_json(url, payload, {})
    cand = out.get("candidates", [{}])[0]
    parts = cand.get("content", {}).get("parts", [])
    for part in parts:
        if part.get("thought"):
            continue
        inline = part.get("inlineData") or part.get("inline_data")
        if not inline:
            continue
        mime = (inline.get("mimeType") or inline.get("mime_type") or "").lower()
        raw = inline.get("data")
        if not raw or "image" not in mime:
            continue
        try:
            return base64.b64decode(raw)
        except Exception:
            continue
    die(f"No image bytes in Gemini image response: {json.dumps(out)[:2000]}")


def parse_comic_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"\{[\s\S]*\}\s*$", text)
    if m:
        text = m.group(0)
    return json.loads(text)


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
    owner: str, repo: str, branch: str, title: str, panels: list[dict]
) -> str:
    base = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/assets/comic/latest"
    lines = [
        f"### {title}",
        "",
        "*Auto-generated weekly from WakaTime + [Gemini Nano Banana](https://ai.google.dev/gemini-api/docs/image-generation) image models.*",
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
    if not waka_key:
        die("WAKATIME_API_KEY is required")

    repo_full = os.environ.get("GITHUB_REPOSITORY", "yogeshvar/yogeshvar")
    owner, repo = repo_full.split("/", 1)
    branch = os.environ.get("DEFAULT_BRANCH", "master").strip() or "master"

    stats = wakatime_stats(waka_key)
    facts = facts_from_wakatime(stats)
    payload = json.dumps(facts, indent=2)
    h = hashlib.sha256(payload.encode()).hexdigest()
    if HASH_FILE.exists():
        old = HASH_FILE.read_text().strip()
        if old == h:
            print("WakaTime stats unchanged; skipping comic regeneration.")
            return

    system_instructions = """You are writing a short funny 3-panel developer comic for a GitHub profile.
The humor must be grounded ONLY in the JSON stats provided (languages, time, editors). No invented employers or projects.
Return ONLY valid JSON with this shape:
{
  "title": "short title",
  "panels": [
    { "caption": "one line joke for under the image", "image_prompt": "detailed single-panel illustration prompt" },
    { "caption": "...", "image_prompt": "..." },
    { "caption": "...", "image_prompt": "..." }
  ]
}
Rules:
- image_prompt: describe ONE comic panel scene, same recurring character (cartoon developer at a desk), same art style across all three: bold outlines, flat colors, simple background, no readable text inside the image, no logos, no real people's faces.
- Keep captions witty and self-deprecating, PG-rated."""

    user_msg = f"{system_instructions}\n\nSTATS_JSON:\n{payload}"
    raw = gemini_text(gemini_key, TEXT_MODEL, user_msg)
    comic = parse_comic_json(raw)
    panels = comic.get("panels") or []
    if len(panels) != 3:
        die(f"Expected 3 panels, got {len(panels)}: {raw[:800]}")
    title = (comic.get("title") or "This week in code").strip()

    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    style_suffix = (
        " Same character and style as other panels: simple comic strip, "
        "thick black outlines, flat colors, office/desk setting, no text in image."
    )
    for i, p in enumerate(panels, start=1):
        ip = (p.get("image_prompt") or "").strip() + style_suffix
        png = gemini_image_png(gemini_key, IMAGE_MODEL, ip)
        (ASSETS_DIR / f"{i}.png").write_bytes(png)
        print(f"Wrote panel {i} ({len(png)} bytes)")

    if not README.exists():
        die(f"Missing {README}")
    readme_body = README.read_text(encoding="utf-8")
    block = build_readme_block(owner, repo, branch, title, panels)
    new_readme = replace_delimited_block(readme_body, block)
    README.write_text(new_readme, encoding="utf-8")

    HASH_FILE.parent.mkdir(parents=True, exist_ok=True)
    HASH_FILE.write_text(h, encoding="utf-8")
    print("README and comic assets updated.")


if __name__ == "__main__":
    main()
