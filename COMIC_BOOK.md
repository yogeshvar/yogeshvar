# Weekly dev comic — archive

The [profile README](README.md) always shows the **latest** strip. When the calendar **week** changes, the workflow copies that week’s strip into `assets/comic/archive/{year}-W{nn}/` and appends a chapter below so the book grows over time (chronological order).

If you **regenerate** during the same week (different stats or `COMIC_FORCE`), the outgoing strip is saved under `assets/comic/archive/snapshots/{year}-W{nn}_{UTC-time}/` so older versions are not lost (those folders are not auto-appended here—only weekly chapters are).

---
