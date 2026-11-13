"""YouTube search, metadata and comments through yt-dlp (project-local dependency)."""
import hashlib
import json
import os
import time

from .core import CACHE_DIR, CACHE_TTL, item, iso


def _ydl(opts: dict, url: str) -> dict:
    """Run yt-dlp extract_info with a disk cache (comment pulls are slow)."""
    cp = CACHE_DIR / ("yt-" + hashlib.sha256((url + json.dumps(opts, sort_keys=True)).encode()).hexdigest()[:32] + ".json")
    if not os.environ.get("SOCIAL_SCOUT_NO_CACHE") and cp.exists() and time.time() - cp.stat().st_mtime < CACHE_TTL:
        return json.loads(cp.read_text(encoding="utf-8"))
    import yt_dlp  # imported lazily: other sources work without it
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "skip_download": True, **opts}) as y:
        info = y.sanitize_info(y.extract_info(url, download=False))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(info), encoding="utf-8")
    return info


def _video(v: dict) -> dict:
    views = v.get("view_count")
    desc = v.get("description") or ""
    return item(source="youtube", kind="video", id=v.get("id"), title=v.get("title"),
                author=v.get("channel") or v.get("uploader"), score=v.get("like_count"),
                num_comments=v.get("comment_count"),
                created=iso(v.get("timestamp")) or _ymd(v.get("upload_date")),
                url=v.get("webpage_url") or v.get("url") or f"https://www.youtube.com/watch?v={v.get('id')}",
                text=(f"{views:,} views. " if views else "") + desc[:1000] or None, community=None)


def _ymd(s: str | None) -> str | None:
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if s and len(s) == 8 else None


def search(query: str, top: int = 20, newest: bool = False) -> list[dict]:
    info = _ydl({"extract_flat": "in_playlist"}, f"ytsearch{'date' if newest else ''}{top}:{query}")
    return [_video(e) for e in info.get("entries") or []]


def video(url: str) -> list[dict]:
    return [_video(_ydl({}, url))]


def comments(url: str, top: int = 100, replies: int = 0) -> list[dict]:
    """Top-sorted comments; `replies` = max replies kept per top-level comment. score = likes."""
    info = _ydl({"getcomments": True, "extractor_args": {"youtube": {
        "comment_sort": ["top"], "max_comments": [str(top * (replies + 1)), str(top), "all", str(replies)]}}}, url)
    out = [_video(info)]
    out[0]["num_comments"] = None  # yt-dlp overwrites comment_count with the number fetched
    for c in info.get("comments") or []:
        reply = c.get("parent") not in (None, "root")
        out.append(item(source="youtube", kind="comment", id=c.get("id"), author=c.get("author"),
                        score=c.get("like_count"),
                        # YouTube only says "1 year ago"; yt-dlp turns that into an approximate date
                        created=c.get("timestamp") and "~" + iso(c["timestamp"])[:10],
                        url=f"{info.get('webpage_url')}&lc={c.get('id')}", text=c.get("text"),
                        parent_id=c.get("parent"), depth=1 if reply else 0))
    return out
