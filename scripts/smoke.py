"""Live smoke check: one real call per source (needs network; not part of pytest). Run: uv run python scripts/smoke.py"""
import os
import sys
import time

os.environ["SOCIAL_SCOUT_NO_CACHE"] = "1"
from social_scout import others, reddit, youtube  # noqa: E402
from social_scout.core import load_dotenv  # noqa: E402

load_dotenv()
CHECKS = {
    "reddit/arctic search": lambda: reddit.arctic_search(None, sub="roblox", top=3, scan=100, since="2026-11"),
    "reddit/arctic thread": lambda: reddit.arctic_thread("1p2uw52", top=3),
    "reddit/official search": lambda: reddit.official_search("roblox", sub="roblox", top=3, scan=100)
    if reddit.official_available() else "SKIP (no REDDIT_CLIENT_ID/SECRET in .env)",
    "youtube search": lambda: youtube.search("roblox devforum", top=2),
    "youtube comments": lambda: youtube.comments("https://www.youtube.com/watch?v=pCPwj9P0N6E", top=3),
    "hackernews": lambda: others.hn_search("roblox", top=2),
    "lemmy": lambda: others.lemmy_search("roblox", top=2),
    "bluesky": lambda: others.bsky_search("roblox", top=2),
    "devforum": lambda: others.devforum_search("datastore", top=2),
}
failed = 0
for name, fn in CHECKS.items():
    t = time.monotonic()
    try:
        r = fn()
        status = r if isinstance(r, str) else (f"ok ({len(r)} items)" if r else "EMPTY")
    except Exception as e:  # report and continue
        status = f"FAIL {type(e).__name__}: {e}"
    failed += status.startswith(("FAIL", "EMPTY"))
    print(f"{name:24} {time.monotonic() - t:5.1f}s  {status}")
sys.exit(1 if failed else 0)
