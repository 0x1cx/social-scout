# social-scout: notes for AI

Read-only social media research CLI. Python 3.11+, managed by uv, one runtime dependency (yt-dlp). Stdlib `urllib` for HTTP.

## Commands
- `uv sync` | `uv run social-scout -h` | from elsewhere: `uv run --project "path/to/social-scout" social-scout ...`
- `uv run pytest -q` (offline, fixtures) | `uv run python scripts/smoke.py` (live, one call per source)

## Layout
- `social_scout/core.py`: `fetch_json` (cache in `.cache/`, per-host throttle, retry), `_transport` (only network call; tests patch it), `item()` normalized shape, `render()`.
- `social_scout/reddit.py` (Arctic Shift + optional official OAuth), `youtube.py` (yt-dlp), `others.py` (HN, Lemmy, Bluesky, DevForum), `cli.py`.

## Conventions
- Read-only, legitimate public APIs only. Honest User-Agent. No login automation, CAPTCHA solving, browser impersonation.
- Every source returns `core.item(...)` dicts. New source = function returning items + a fixture + a test + a smoke line.
- Secrets only in gitignored `.env` (see `.env.example`); never print them. Tests never touch the network.
- Limits and verified API status live in README "Sources and limits"; update it when a source changes.
