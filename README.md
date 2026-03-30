# Hi, I'm Yogeshvar

Welcome to my GitHub profile.

## Coding time

[![Wakatime](https://wakatime.com/badge/user/YOUR_WAKATIME_USER_ID.svg)](https://wakatime.com/@YOUR_WAKATIME_USER_ID)

Replace the badge `user/...` segment with your Wakatime public user id (from your Wakatime profile URL).

## This week: a tiny comic

<!-- COMIC_STORY_START -->
### My First 30 Mins in Dev

*Demo run: placeholder dev stats (no WakaTime key, API error, empty week, or manual demo mode) + [Gemini Nano Banana](https://ai.google.dev/gemini-api/docs/image-generation).*

![Panel 1](https://raw.githubusercontent.com/yogeshvar/yogeshvar/master/assets/comic/latest/1.png)

*My dev career started strong! Well, for exactly 30 minutes, anyway.*

![Panel 2](https://raw.githubusercontent.com/yogeshvar/yogeshvar/master/assets/comic/latest/2.png)

*Turns out, 40% of my 'coding' is just expertly navigating Stack Overflow.*

![Panel 3](https://raw.githubusercontent.com/yogeshvar/yogeshvar/master/assets/comic/latest/3.png)

*And the other 60%? Crafting Dockerfiles like they're ancient scrolls, all within my trusty Cursor.*

<!-- COMIC_STORY_END -->

---

Setup (once):

1. Repo secret: **`GEMINI_API_KEY`** ([Google AI Studio](https://aistudio.google.com/apikey)). Optional: **`WAKATIME_API_KEY`** (Wakatime → Settings → API key). If WakaTime is missing, the API errors, or the week has no stats, the workflow uses **random demo “stats”** so the comic still generates.
2. Optional: set `GEMINI_IMAGE_MODEL` to `gemini-3.1-flash-image-preview` (Nano Banana 2) in the workflow `env` for newer image quality—see [Nano Banana image generation](https://ai.google.dev/gemini-api/docs/image-generation).
3. Run **Actions → Profile comic → Run workflow**. For a quick test without real telemetry, enable **“Skip WakaTime; use random demo stats”**. To refresh when WakaTime has not changed, enable **“Regenerate even when WakaTime stats are unchanged”**. Or wait for the weekly schedule.

Local test (only `GEMINI_API_KEY` required):

```bash
export GEMINI_API_KEY=...
# optional: export WAKATIME_API_KEY=...
python scripts/generate_profile_comic.py
# force new strip with real WakaTime: COMIC_FORCE=1 python scripts/generate_profile_comic.py
# ignore WakaTime: COMIC_USE_PLACEHOLDER=1 python scripts/generate_profile_comic.py
```

Images are committed under `assets/comic/latest/` and linked via `raw.githubusercontent.com` so the profile README stays fast and cache-friendly.
