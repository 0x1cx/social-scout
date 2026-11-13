"""Offline tests: every HTTP call is answered from tests/fixtures (recorded live on 2026-11-13)."""
import io
import json
import urllib.error
from pathlib import Path

import pytest

from social_scout import cli, core, others, reddit, youtube

FIX = Path(__file__).parent / "fixtures"
RECORDED = {d["url"]: d["body"] for d in (json.loads(f.read_text(encoding="utf-8")) for f in FIX.glob("*.json")) if "body" in d}


@pytest.fixture(autouse=True)
def offline(monkeypatch, tmp_path):
    def transport(req):
        if req.full_url not in RECORDED:
            raise AssertionError(f"no fixture for {req.full_url}")
        return json.dumps(RECORDED[req.full_url]).encode()
    monkeypatch.setattr(core, "_transport", transport)
    monkeypatch.setattr(core, "_throttle", lambda host: None)
    monkeypatch.setattr(core, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(youtube, "CACHE_DIR", tmp_path)
    monkeypatch.setenv("SOCIAL_SCOUT_NO_CACHE", "1")


def shape_ok(items, source):
    assert items, "no items"
    for i in items:
        assert tuple(i) == core.FIELDS
        assert i["source"] == source and i["kind"] in ("post", "comment", "video")
        assert i["url"].startswith("https://")
    return items


def test_reddit_search_paginates_and_ranks_by_score():
    items = reddit.arctic_search("boring", sub="99NightsInTheForest", since="2025-06", top=5, scan=200)
    shape_ok(items, "reddit")
    scores = [i["score"] for i in items]
    assert len(items) == 5 and scores == sorted(scores, reverse=True)
    assert items[0]["title"] == "Farming diamonds is a boring and time-consuming process"


def test_reddit_thread_post_then_top_comments():
    items = reddit.arctic_thread("https://www.reddit.com/r/99nightsintheforest/comments/1p2uw52/x/", top=3, max_depth=1)
    shape_ok(items, "reddit")
    assert items[0]["kind"] == "post" and items[0]["num_comments"] == 19
    roots = [i for i in items[1:] if i["depth"] == 0]
    assert [r["score"] for r in roots] == [6, 5, 4]
    assert all(i["depth"] <= 1 for i in items)


def test_reddit_text_search_needs_sub():
    with pytest.raises(ValueError):
        reddit.arctic_search("99 nights")


@pytest.mark.parametrize("ref", ["https://www.reddit.com/r/x/comments/1p2uw52/slug/", "https://redd.it/1p2uw52", "t3_1p2uw52", "1p2uw52"])
def test_thread_id(ref):
    assert reddit.thread_id(ref) == "1p2uw52"


def test_hn():
    shape_ok(others.hn_search("roblox", since="2025", top=2), "hackernews")
    t = shape_ok(others.hn_thread("45000000", top=2, max_depth=0), "hackernews")
    assert t[0]["id"] == "45000000"


def test_lemmy_bluesky_devforum():
    shape_ok(others.lemmy_search("roblox", top=2), "lemmy")
    b = shape_ok(others.bsky_search("99 nights in the forest", top=2), "bluesky")
    assert b[0]["url"].startswith("https://bsky.app/profile/")
    d = shape_ok(others.devforum_search("99 nights", since="2025-06", top=2), "devforum")
    assert "/t/" in d[0]["url"]


def test_youtube(monkeypatch):
    fx = {k: json.loads((FIX / f"youtube-{k}.json").read_text(encoding="utf-8")) for k in ("search", "comments")}
    monkeypatch.setattr(youtube, "_ydl", lambda opts, url: fx["search" if url.startswith("ytsearch") else "comments"])
    shape_ok(youtube.search("99 nights in the forest review", top=3), "youtube")
    c = shape_ok(youtube.comments("https://www.youtube.com/watch?v=pCPwj9P0N6E", top=5), "youtube")
    assert c[0]["kind"] == "video" and c[1]["kind"] == "comment" and c[1]["score"] == 1000


def test_retry_on_arctic_slow_down(monkeypatch):
    calls = []

    def flaky(req):
        calls.append(1)
        if len(calls) == 1:
            raise urllib.error.HTTPError(req.full_url, 422, "x", {}, io.BytesIO(b'{"error":"Timeout. Maybe slow down a bit"}'))
        return b'{"data": []}'
    monkeypatch.setattr(core, "_transport", flaky)
    monkeypatch.setattr(core.time, "sleep", lambda s: None)
    assert core.fetch_json("https://arctic-shift.photon-reddit.com/api/x") == {"data": []}
    assert len(calls) == 2


def test_cli_json_and_md(capsys):
    assert cli.main(["reddit", "thread", "1p2uw52", "--top", "2", "--depth", "0", "-f", "json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["count"] == 3 and out["items"][0]["kind"] == "post"
    assert cli.main(["hn", "search", "roblox", "--since", "2025", "--top", "2"]) == 0
    assert "news.ycombinator.com/item?id=" in capsys.readouterr().out
    assert cli.main(["reddit", "search"]) == 2  # nothing to search


def test_dotenv_never_overrides(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("SS_TEST_A=1\nSS_TEST_B='2'\n# c\n")
    monkeypatch.setenv("SS_TEST_A", "keep")
    monkeypatch.delenv("SS_TEST_B", raising=False)
    core.load_dotenv(env)
    import os
    assert os.environ["SS_TEST_A"] == "keep" and os.environ["SS_TEST_B"] == "2"


def test_reddit_local_match_on_listing(monkeypatch):
    rows = [{"id": "a1", "title": "Please add a SAVE feature", "selftext": "", "score": 5, "subreddit": "x", "created_utc": 1},
            {"id": "a2", "title": "frogs", "selftext": "we need to save runs", "score": 9, "subreddit": "x", "created_utc": 2},
            {"id": "a3", "title": "unrelated", "selftext": "", "score": 99, "subreddit": "x", "created_utc": 3}]
    seen = []
    monkeypatch.setattr(reddit, "_arctic_scan", lambda kind, sub, author, query, *a: seen.append(query) or rows)
    got = reddit.arctic_search("save", sub="x", local=True)
    assert [i["id"] for i in got] == ["a2", "a1"] and seen == [None]
    assert [i["id"] for i in reddit.arctic_search("save", sub="x", local=True, title_only=True)] == ["a1"]


def test_reddit_falls_back_to_local_when_text_search_times_out(monkeypatch):
    def scan(kind, sub, author, query, *a):
        if query:
            raise core.FetchError("HTTP 422 slow down")
        return [{"id": "b1", "title": "save pls", "score": 1, "subreddit": "x", "created_utc": 1}]
    monkeypatch.setattr(reddit, "_arctic_scan", scan)
    assert [i["id"] for i in reddit.arctic_search("save", sub="x")] == ["b1"]
