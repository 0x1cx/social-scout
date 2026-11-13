# social-scout

Read-only social media research CLI for AI research sessions. One command pulls posts and top comments from
Reddit, YouTube, Hacker News, Lemmy, Bluesky and the Roblox DevForum through legitimate public APIs and prints
clean Markdown (default) or JSON in one normalized shape. Responses are cached on disk (6 h) and every host is
rate limited. Nothing here logs in, posts, solves CAPTCHAs or pretends to be a browser.

## Build and run

Needs [uv](https://docs.astral.sh/uv/) (dependencies stay in the project `.venv`; nothing global).

```bash
uv sync
uv run social-scout -h
```

From any folder (how other sessions should call it):

```bash
uv run --project "path/to/social-scout" social-scout reddit search "boring" --sub 99NightsInTheForest --since 2025-06 --top 20
```

## Commands

| Command | What it does |
|---|---|
| `reddit search [QUERY] --sub S [--author A] [--since 2025-06] [--until 2026-01] [--top 50] [--sort top\|new] [--comments] [--title-only]` | Posts (or comment bodies with `--comments`) ranked by score |
| `reddit thread <url\|id> [--top 50] [--depth 2]` | Post + top-scored comments with replies |
| `youtube search QUERY [--top 20] [--sort new]` | Videos (score = likes, text starts with view count) |
| `youtube video <url>` | One video's metadata |
| `youtube comments <url> [--top 100] [--replies 0]` | Video + top comments (score = likes) |
| `hn search QUERY [--comments]` / `hn thread <id>` | Hacker News via Algolia |
| `lemmy search QUERY [--instance lemmy.world] [--comments]` | Lemmy (federated) |
| `bluesky search QUERY [--since]` | Bluesky public AppView |
| `devforum search QUERY [--since]` / `devforum thread <url\|id>` | devforum.roblox.com (Discourse JSON) |

Every command takes `--top N`, `-f md|json|jsonl`, `--text-len N`. Dates are UTC; `--until` is exclusive.

Item shape (every source): `source, kind (post|comment|video), id, title, author, score, num_comments, created, url, text, community, parent_id, depth`.

## Sources and limits (verified live 2026-11-13)

| Source | Route | Status / limits |
|---|---|---|
| Reddit (default) | [Arctic Shift](https://github.com/ArthurHeitmann/arctic_shift) archive API, no auth | Works. Text search needs `--sub` or `--author`. Huge subs (r/roblox) time out on text search even for a 2-week window: search the game's own sub, or list r/roblox without a query plus `--since`. No server-side score sort, so the tool scans up to `--scan` (500) matches and ranks locally. Scores are archive snapshots and can lag live Reddit. Too many requests returns HTTP 422 "slow down": the tool waits 1.5 s between calls and retries with backoff. |
| Reddit (optional) | Official API, application-only OAuth (`--backend official`, or `auto` falls back to it) | Not tested live (no app yet). Needs a Reddit "script" app; see below. Live scores, but no date filters or comment search. |
| Reddit | PullPush (`api.pullpush.io`) | Down on 2026-11-13 (HTTP 526). Not implemented. |
| Reddit | `reddit.com/*.json` logged out | HTTP 403. Not used. |
| YouTube | `yt-dlp` (project dependency) | Works. Comment dates are approximate (YouTube only shows "1 year ago"), shown with `~`. If YouTube breaks it: `uv lock --upgrade-package yt-dlp; uv sync`. |
| Hacker News | `hn.algolia.com/api/v1` | Works, no key. |
| Lemmy | `<instance>/api/v3/search` | Works; results depend on the instance's federation. |
| Bluesky | `api.bsky.app/xrpc/app.bsky.feed.searchPosts` | Works logged out. (`public.api.bsky.app` returns 403 for search.) |
| Roblox DevForum | `devforum.roblox.com/search.json`, `/t/<id>.json` | Works; 50 results per search page. |
| TikTok, Instagram, X | none (no logged-out API) | Use Claude in Chrome by hand: [docs/chrome-social.md](docs/chrome-social.md). |

### Optional: official Reddit API

1. You (not an AI) create a "script" app at <https://www.reddit.com/prefs/apps> (Reddit may ask for an API access request first).
2. Copy `.env.example` to `.env` and fill `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`, `REDDIT_USERNAME`. `.env` is gitignored; secrets are read from it and never printed.
3. Check: `uv run python scripts/smoke.py` (the official line stops saying SKIP).

## Tests

```bash
uv run pytest -q              # offline, recorded fixtures in tests/fixtures
uv run python scripts/smoke.py  # live: one real call per source
```

Re-record fixtures: set `SOCIAL_SCOUT_RECORD=<dir>` and `SOCIAL_SCOUT_NO_CACHE=1`, run the CLI, copy the files into `tests/fixtures`.

Env vars: `SOCIAL_SCOUT_NO_CACHE=1`, `SOCIAL_SCOUT_CACHE_TTL` (seconds), `SOCIAL_SCOUT_CACHE` (dir).
