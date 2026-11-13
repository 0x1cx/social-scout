"""Reddit via Arctic Shift (no auth, archive) or the official OAuth API (optional, creds from .env)."""
import base64
import os
import re

from .core import FetchError, epoch, fetch_json, iso, item, VERSION

ARCTIC = "https://arctic-shift.photon-reddit.com/api"
POST_FIELDS = "id,title,author,score,num_comments,created_utc,subreddit,selftext"
COMMENT_FIELDS = "id,body,author,score,created_utc,subreddit,link_id,parent_id"


def thread_id(ref: str) -> str:
    """Accept a full reddit URL, a redd.it short link, 't3_xxx' or a bare id."""
    m = re.search(r"/comments/([a-z0-9]+)", ref) or re.search(r"redd\.it/([a-z0-9]+)", ref)
    if m:
        return m.group(1)
    ref = ref.removeprefix("t3_")
    if not re.fullmatch(r"[a-z0-9]{4,10}", ref):
        raise ValueError(f"not a reddit thread url/id: {ref}")
    return ref


def _post(d: dict) -> dict:
    return item(source="reddit", kind="post", id=d["id"], title=d.get("title"), author=d.get("author"),
                score=d.get("score"), num_comments=d.get("num_comments"), created=_iso(d.get("created_utc")),
                url=f"https://www.reddit.com/r/{d.get('subreddit')}/comments/{d['id']}/",
                text=d.get("selftext") or None, community="r/" + d["subreddit"] if d.get("subreddit") else None)


def _comment(d: dict, depth: int = 0) -> dict:
    link = d.get("link_id", "").removeprefix("t3_")
    url = ("https://www.reddit.com" + d["permalink"]) if d.get("permalink") else (
        f"https://www.reddit.com/comments/{link}/_/{d['id']}/" if link else None)
    return item(source="reddit", kind="comment", id=d["id"], author=d.get("author"), score=d.get("score"),
                created=_iso(d.get("created_utc")), url=url, text=d.get("body"),
                community="r/" + d["subreddit"] if d.get("subreddit") else None,
                parent_id=d.get("parent_id"), depth=depth)


def _iso(ts):
    return iso(int(float(ts))) if ts not in (None, "") else None


def flatten(children: list, depth: int = 0, max_depth: int = 99) -> list[dict]:
    """Reddit listing children (t1 + replies) -> flat list in thread order; skips 'more' stubs and removed text."""
    out = []
    for c in children:
        if c.get("kind") != "t1":
            continue
        d = c["data"]
        if d.get("body") not in ("[removed]", "[deleted]"):
            out.append(_comment(d, depth))
        r = d.get("replies")
        if isinstance(r, dict) and depth < max_depth:
            out += flatten(r["data"]["children"], depth + 1, max_depth)
    return out


def _rank(items: list[dict], sort: str, top: int) -> list[dict]:
    key = (lambda i: i["score"] or 0) if sort == "top" else (lambda i: i["created"] or "")
    return sorted(items, key=key, reverse=True)[:top]


# ---- Arctic Shift -----------------------------------------------------------
def arctic_search(query: str | None, sub: str | None = None, author: str | None = None,
                  since: str | None = None, until: str | None = None, kind: str = "posts",
                  top: int = 25, sort: str = "top", scan: int = 500, title_only: bool = False) -> list[dict]:
    """Arctic Shift cannot sort by score, so scan up to `scan` matches oldest->newest and rank locally.
    Full-text search needs --sub or --author; huge subs (r/roblox) time out on text search: narrow dates."""
    if query and not (sub or author):
        raise ValueError("Arctic Shift text search needs --sub or --author (or use --backend official)")
    textkey = "body" if kind == "comments" else ("title" if title_only else "query")
    after, before, rows = epoch(since), epoch(until), []
    while len(rows) < scan:
        page = fetch_json(f"{ARCTIC}/{kind}/search", {
            "subreddit": sub, "author": author, textkey: query, "after": after, "before": before,
            "limit": 100, "sort": "asc", "fields": COMMENT_FIELDS if kind == "comments" else POST_FIELDS})
        data = page.get("data") or []
        if page.get("error"):
            raise FetchError(f"Arctic Shift: {page['error']}")
        rows += data
        if len(data) < 100:
            break
        after = int(data[-1]["created_utc"])  # next page starts after the newest row seen
    conv = _comment if kind == "comments" else _post
    return _rank([conv(r) for r in rows], sort, top)


def arctic_thread(ref: str, top: int = 50, max_depth: int = 3) -> list[dict]:
    tid = thread_id(ref)
    posts = fetch_json(f"{ARCTIC}/posts/ids", {"ids": tid, "fields": POST_FIELDS}).get("data") or []
    tree = fetch_json(f"{ARCTIC}/comments/tree", {"link_id": tid, "limit": 9999}).get("data") or []
    return [_post(p) for p in posts] + _top_comments(tree, top, max_depth)


def _top_comments(children: list, top: int, max_depth: int) -> list[dict]:
    """Keep the `top` highest-scored top-level comments, each with its replies (to max_depth)."""
    roots = sorted((c for c in children if c.get("kind") == "t1"),
                   key=lambda c: c["data"].get("score") or 0, reverse=True)[:top]
    return flatten(roots, 0, max_depth)


# ---- official API (optional) -------------------------------------------------
_token: str | None = None


def official_available() -> bool:
    return bool(os.environ.get("REDDIT_CLIENT_ID") and os.environ.get("REDDIT_CLIENT_SECRET"))


def _official(path: str, params: dict) -> dict | list:
    """Application-only OAuth (client_credentials): read-only, no user password involved."""
    global _token
    if not official_available():
        raise FetchError("official backend needs REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET in .env (see README)")
    ua = f"script:social-scout:{VERSION} (by /u/{os.environ.get('REDDIT_USERNAME', 'unknown')})"
    if not _token:
        basic = base64.b64encode(f"{os.environ['REDDIT_CLIENT_ID']}:{os.environ['REDDIT_CLIENT_SECRET']}".encode()).decode()
        tok = fetch_json("https://www.reddit.com/api/v1/access_token", data=b"grant_type=client_credentials",
                         headers={"Authorization": "Basic " + basic, "User-Agent": ua,
                                  "Content-Type": "application/x-www-form-urlencoded"}, cache=False)
        _token = tok.get("access_token") or ""
        if not _token:
            raise FetchError(f"reddit token request failed: {tok.get('error', 'no token')}")
    return fetch_json("https://oauth.reddit.com" + path, {**params, "raw_json": 1},
                      headers={"Authorization": "Bearer " + _token, "User-Agent": ua})


def official_search(query, sub=None, author=None, since=None, until=None, kind="posts",
                    top=25, sort="top", scan=500, title_only=False) -> list[dict]:
    if kind == "comments":
        raise ValueError("official API has no comment search; use --backend arctic")
    q = " ".join(x for x in (f'title:"{query}"' if title_only and query else query,
                             author and f"author:{author}") if x)
    path = f"/r/{sub}/search" if sub else "/search"
    lo, hi = epoch(since) or 0, epoch(until) or 2**40
    rows, after = [], None
    while len(rows) < scan:
        res = _official(path, {"q": q, "restrict_sr": 1 if sub else None, "sort": sort,
                                "t": "all", "limit": 100, "after": after})
        kids = res["data"]["children"]
        rows += [k["data"] for k in kids if lo <= k["data"]["created_utc"] < hi]
        after = res["data"].get("after")
        if not after or not kids:
            break
    return _rank([_post(r) for r in rows], sort, top)


def official_thread(ref: str, top: int = 50, max_depth: int = 3) -> list[dict]:
    post_l, com_l = _official(f"/comments/{thread_id(ref)}", {"sort": "top", "limit": 500})
    return [_post(post_l["data"]["children"][0]["data"])] + _top_comments(com_l["data"]["children"], top, max_depth)


def pick(backend: str):
    """auto = Arctic Shift, falling back to the official API when it fails and creds exist."""
    def run(arctic_fn, official_fn, *a, **kw):
        if backend == "official":
            return official_fn(*a, **kw)
        try:
            return arctic_fn(*a, **kw)
        except FetchError:
            if backend == "auto" and official_available():
                return official_fn(*a, **kw)
            raise
    return run
