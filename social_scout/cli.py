"""social-scout: read-only social media research CLI. Run `social-scout -h`."""
import argparse
import sys

from . import others, reddit, youtube
from .core import FetchError, load_dotenv, render


def _common(p, dates=True, sort=True):
    p.add_argument("--top", type=int, default=25, help="max items (default 25)")
    p.add_argument("--format", "-f", choices=["md", "json", "jsonl"], default="md")
    p.add_argument("--text-len", type=int, default=400, help="clip text in md output")
    if dates:
        p.add_argument("--since", help="YYYY | YYYY-MM | YYYY-MM-DD (UTC)")
        p.add_argument("--until", help="exclusive end date, same formats")
    if sort:
        p.add_argument("--sort", choices=["top", "new"], default="top")


def build_parser():
    ap = argparse.ArgumentParser(prog="social-scout", description=__doc__)
    src = ap.add_subparsers(dest="source", required=True)

    r = src.add_parser("reddit").add_subparsers(dest="cmd", required=True)
    s = r.add_parser("search", help="posts (or --comments) matching QUERY; QUERY optional with --sub")
    s.add_argument("query", nargs="?")
    s.add_argument("--sub", help="subreddit without r/")
    s.add_argument("--author")
    s.add_argument("--comments", action="store_true", help="search comment bodies instead of posts")
    s.add_argument("--title-only", action="store_true")
    s.add_argument("--scan", type=int, default=500, help="Arctic: max matches to scan before ranking")
    _common(s)
    t = r.add_parser("thread", help="post + top comments for a URL / id")
    t.add_argument("ref")
    t.add_argument("--depth", type=int, default=2, help="reply depth (0 = top-level only)")
    _common(t, dates=False, sort=False)
    for x in (s, t):
        x.add_argument("--backend", choices=["auto", "arctic", "official"], default="auto",
                       help="auto: Arctic Shift, then official API if creds exist")

    y = src.add_parser("youtube").add_subparsers(dest="cmd", required=True)
    s = y.add_parser("search"); s.add_argument("query"); _common(s, dates=False)
    s = y.add_parser("video"); s.add_argument("url"); _common(s, dates=False, sort=False)
    s = y.add_parser("comments"); s.add_argument("url")
    s.add_argument("--replies", type=int, default=0, help="replies kept per top comment")
    _common(s, dates=False, sort=False)

    h = src.add_parser("hn").add_subparsers(dest="cmd", required=True)
    s = h.add_parser("search"); s.add_argument("query"); s.add_argument("--comments", action="store_true"); _common(s)
    s = h.add_parser("thread"); s.add_argument("ref"); s.add_argument("--depth", type=int, default=2)
    _common(s, dates=False, sort=False)

    s = src.add_parser("lemmy").add_subparsers(dest="cmd", required=True).add_parser("search")
    s.add_argument("query"); s.add_argument("--instance", default="lemmy.world")
    s.add_argument("--comments", action="store_true"); _common(s, dates=False)

    s = src.add_parser("bluesky").add_subparsers(dest="cmd", required=True).add_parser("search")
    s.add_argument("query"); _common(s)

    d = src.add_parser("devforum").add_subparsers(dest="cmd", required=True)
    s = d.add_parser("search"); s.add_argument("query"); _common(s)
    s = d.add_parser("thread"); s.add_argument("ref"); _common(s, dates=False, sort=False)
    return ap


def run(a) -> list[dict]:
    k = "comments" if getattr(a, "comments", False) else "posts"
    match a.source, a.cmd:
        case "reddit", "search":
            if not (a.query or a.sub or a.author):
                raise ValueError("give a QUERY, --sub or --author")
            return reddit.pick(a.backend)(reddit.arctic_search, reddit.official_search, a.query, a.sub, a.author,
                                          a.since, a.until, k, a.top, a.sort, a.scan, a.title_only)
        case "reddit", "thread":
            return reddit.pick(a.backend)(reddit.arctic_thread, reddit.official_thread, a.ref, a.top, a.depth)
        case "youtube", "search":
            return youtube.search(a.query, a.top, a.sort == "new")
        case "youtube", "video":
            return youtube.video(a.url)
        case "youtube", "comments":
            return youtube.comments(a.url, a.top, a.replies)
        case "hn", "search":
            return others.hn_search(a.query, a.since, a.until, a.top, a.sort, k)
        case "hn", "thread":
            return others.hn_thread(a.ref, a.top, a.depth)
        case "lemmy", "search":
            return others.lemmy_search(a.query, a.instance, a.top, a.sort, k)
        case "bluesky", "search":
            return others.bsky_search(a.query, a.since, a.until, a.top, a.sort)
        case "devforum", "search":
            return others.devforum_search(a.query, a.since, a.until, a.top, a.sort)
        case "devforum", "thread":
            return others.devforum_thread(a.ref, a.top)
    raise ValueError(f"unknown command {a.source} {a.cmd}")


def main(argv=None) -> int:
    load_dotenv()
    a = build_parser().parse_args(argv)
    header = " ".join(sys.argv[1:] if argv is None else argv)
    try:
        items = run(a)
    except (FetchError, ValueError) as e:
        print(f"social-scout: {e}", file=sys.stderr)
        return 2
    sys.stdout.reconfigure(encoding="utf-8")
    print(render(items, a.format, header, a.text_len))
    return 0


if __name__ == "__main__":
    sys.exit(main())
