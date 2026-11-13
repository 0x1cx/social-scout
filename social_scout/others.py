"""Hacker News (Algolia), Lemmy, Bluesky public AppView, Roblox DevForum (Discourse JSON)."""
import html
import re

from .core import date_arg, epoch, fetch_json, item, iso


def _strip(s: str | None) -> str | None:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).strip() if s else None


# ---- Hacker News -------------------------------------------------------------
def hn_search(query, since=None, until=None, top=25, sort="top", kind="posts"):
    nf = ",".join(f for f in (since and f"created_at_i>={epoch(since)}", until and f"created_at_i<{epoch(until)}") if f)
    res = fetch_json("https://hn.algolia.com/api/v1/" + ("search" if sort == "top" else "search_by_date"),
                     {"query": query, "tags": "comment" if kind == "comments" else "story",
                      "numericFilters": nf, "hitsPerPage": min(top, 1000)})
    return [_hn(h) for h in res.get("hits", [])]


def _hn(h, depth=0):
    is_c = bool(h.get("comment_text")) or h.get("type") == "comment"
    hid = h.get("objectID") or h.get("id")
    return item(source="hackernews", kind="comment" if is_c else "post", id=str(hid), title=h.get("title"),
                author=h.get("author"), score=h.get("points"), num_comments=h.get("num_comments"),
                created=iso(h.get("created_at_i") or h.get("created_at")),
                url=f"https://news.ycombinator.com/item?id={hid}",
                text=_strip(h.get("comment_text") or h.get("story_text") or h.get("text")),
                parent_id=str(h["parent_id"]) if h.get("parent_id") else None, depth=depth)


def hn_thread(ref, top=50, max_depth=3):
    tid = re.search(r"(\d+)$", ref).group(1)
    root = fetch_json(f"https://hn.algolia.com/api/v1/items/{tid}")
    out = [_hn(root)]

    def walk(kids, d):
        for k in kids:
            if k.get("text") and len(out) <= top:
                out.append(_hn(k, d))
            if d < max_depth:
                walk(k.get("children") or [], d + 1)
    walk(root.get("children") or [], 0)
    return out


# ---- Lemmy -------------------------------------------------------------------
def lemmy_search(query, instance="lemmy.world", top=25, sort="top", kind="posts"):
    res = fetch_json(f"https://{instance}/api/v3/search", {
        "q": query, "type_": "Comments" if kind == "comments" else "Posts",
        "sort": "TopAll" if sort == "top" else "New", "limit": min(top, 50)})
    out = []
    for r in res.get("comments" if kind == "comments" else "posts", []):
        p, c = r.get("post", {}), r.get("comment")
        out.append(item(source="lemmy", kind="comment" if c else "post", id=str((c or p).get("id")),
                        title=None if c else p.get("name"), author=r.get("creator", {}).get("name"),
                        score=r.get("counts", {}).get("score"), num_comments=None if c else r.get("counts", {}).get("comments"),
                        created=iso((c or p).get("published")), url=(c or p).get("ap_id"),
                        text=c.get("content") if c else p.get("body"),
                        community="!" + r.get("community", {}).get("name", "")))
    return out


# ---- Bluesky -------------------------------------------------------------------
def bsky_search(query, since=None, until=None, top=25, sort="top"):
    # api.bsky.app serves searchPosts logged-out; public.api.bsky.app returns 403 for search.
    res = fetch_json("https://api.bsky.app/xrpc/app.bsky.feed.searchPosts", {
        "q": query, "limit": min(top, 100), "sort": "top" if sort == "top" else "latest",
        "since": since and date_arg(since) + "T00:00:00Z", "until": until and date_arg(until) + "T00:00:00Z"})
    out = []
    for p in res.get("posts", []):
        h = p["author"]["handle"]
        out.append(item(source="bluesky", kind="post", id=p["uri"], author=h, score=p.get("likeCount"),
                        num_comments=p.get("replyCount"), created=iso(p["record"].get("createdAt")),
                        url=f"https://bsky.app/profile/{h}/post/{p['uri'].rsplit('/', 1)[-1]}",
                        text=p["record"].get("text")))
    return out


# ---- Roblox DevForum (Discourse) --------------------------------------------------
DEVFORUM = "https://devforum.roblox.com"


def devforum_search(query, since=None, until=None, top=25, sort="top"):
    q = " ".join(x for x in (query, since and f"after:{date_arg(since)}", until and f"before:{date_arg(until)}",
                             "order:likes" if sort == "top" else "order:latest") if x)
    res = fetch_json(f"{DEVFORUM}/search.json", {"q": q})
    topics = {t["id"]: t for t in res.get("topics", [])}
    out = []
    for p in res.get("posts", [])[:top]:
        t = topics.get(p.get("topic_id"), {})
        out.append(item(source="devforum", kind="post" if p.get("post_number") == 1 else "comment",
                        id=str(p["id"]), title=t.get("title"), author=p.get("username"), score=p.get("like_count"),
                        num_comments=t.get("posts_count"), created=iso(p.get("created_at")),
                        url=f"{DEVFORUM}/t/{t.get('slug', '-')}/{p.get('topic_id')}/{p.get('post_number', 1)}",
                        text=p.get("blurb")))
    return out


def devforum_thread(ref, top=50, max_depth=0):
    tid = re.search(r"/t/(?:[^/]+/)?(\d+)", ref) or re.fullmatch(r"(\d+)", ref)
    t = fetch_json(f"{DEVFORUM}/t/{tid.group(1)}.json")
    out = []
    for p in t["post_stream"]["posts"][: top + 1]:
        first = p["post_number"] == 1
        out.append(item(source="devforum", kind="post" if first else "comment", id=str(p["id"]),
                        title=t["title"] if first else None, author=p.get("username"),
                        score=p.get("like_count", sum(a.get("count", 0) for a in p.get("actions_summary", []) if a.get("id") == 2)),
                        num_comments=t.get("posts_count") if first else None, created=iso(p.get("created_at")),
                        url=f"{DEVFORUM}/t/{t['slug']}/{t['id']}/{p['post_number']}", text=_strip(p.get("cooked"))))
    return out
