"""HTTP (cache + per-host rate limit + retry), the normalized item shape, and rendering."""
import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

VERSION = "0.1.0"
# Honest identification: this is a script, not a browser.
USER_AGENT = f"social-scout/{VERSION} (read-only research CLI)"
ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = Path(os.environ.get("SOCIAL_SCOUT_CACHE", ROOT / ".cache"))
CACHE_TTL = int(os.environ.get("SOCIAL_SCOUT_CACHE_TTL", 6 * 3600))
# Minimum seconds between requests to one host. Arctic Shift asks clients to "slow down".
MIN_INTERVAL = {"arctic-shift.photon-reddit.com": 1.5, "oauth.reddit.com": 1.0, "www.reddit.com": 2.0}
DEFAULT_INTERVAL = 0.5
_last_call: dict[str, float] = {}


class FetchError(Exception):
    pass


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Read KEY=VALUE lines from the gitignored .env into os.environ (never overrides, never prints)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def _throttle(host: str) -> None:
    wait = MIN_INTERVAL.get(host, DEFAULT_INTERVAL) - (time.monotonic() - _last_call.get(host, 0))
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.monotonic()


def _cache_path(key: str) -> Path:
    return CACHE_DIR / (hashlib.sha256(key.encode()).hexdigest()[:32] + ".json")


def _transport(req: urllib.request.Request) -> bytes:
    """The only line that touches the network (tests replace it with recorded fixtures)."""
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def fetch_json(url: str, params: dict | None = None, headers: dict | None = None,
               data: bytes | None = None, cache: bool = True, retries: int = 2):
    """GET (or POST when data is set) JSON with disk cache, throttle and retry on 429/5xx/Arctic 'slow down'."""
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v not in (None, "")})
    use_cache = cache and data is None and not os.environ.get("SOCIAL_SCOUT_NO_CACHE")
    cp = _cache_path(url)
    if use_cache and cp.exists() and time.time() - cp.stat().st_mtime < CACHE_TTL:
        return json.loads(cp.read_text(encoding="utf-8"))
    host = urllib.parse.urlsplit(url).hostname or ""
    hdrs = {"User-Agent": os.environ.get("SOCIAL_SCOUT_UA", USER_AGENT), "Accept": "application/json"}
    hdrs.update(headers or {})
    for attempt in range(retries + 1):
        _throttle(host)
        try:
            body = json.loads(_transport(urllib.request.Request(url, data=data, headers=hdrs)).decode("utf-8"))
            break
        except urllib.error.HTTPError as e:
            text = e.read().decode("utf-8", "replace")[:300]
            retryable = e.code in (429, 500, 502, 503, 504) or (e.code == 422 and "slow down" in text)
            if retryable and attempt < retries:
                time.sleep(5 * (attempt + 1) ** 2)
                continue
            raise FetchError(f"HTTP {e.code} from {host}: {text.strip()}") from None
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < retries:
                time.sleep(3)
                continue
            raise FetchError(f"network error for {host}: {e}") from None
    if use_cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cp.write_text(json.dumps(body), encoding="utf-8")
    if rec := os.environ.get("SOCIAL_SCOUT_RECORD"):  # dev only: save raw responses as test fixtures
        Path(rec).mkdir(parents=True, exist_ok=True)
        (Path(rec) / (host.replace(".", "_") + "-" + cp.name)).write_text(
            json.dumps({"url": url, "body": body}, ensure_ascii=False), encoding="utf-8")
    return body


# ---- normalized shape -------------------------------------------------------
FIELDS = ("source", "kind", "id", "title", "author", "score", "num_comments",
          "created", "url", "text", "community", "parent_id", "depth")


def item(**kw) -> dict:
    """Every source returns dicts with exactly these keys. kind: post | comment | video."""
    unknown = set(kw) - set(FIELDS)
    assert not unknown, unknown
    d = {k: kw.get(k) for k in FIELDS}
    d["depth"] = d["depth"] or 0
    return d


def iso(ts) -> str | None:
    """epoch seconds or ISO string -> 'YYYY-MM-DD HH:MM' UTC."""
    if ts in (None, ""):
        return None
    if isinstance(ts, (int, float)):
        return datetime.fromtimestamp(ts, timezone.utc).strftime("%Y-%m-%d %H:%M")
    return str(ts).replace("T", " ")[:16]


def date_arg(s: str | None) -> str | None:
    """'2025-06' -> '2025-06-01'; '2025' -> '2025-01-01'; full dates pass through."""
    if not s:
        return None
    return {4: s + "-01-01", 7: s + "-01"}.get(len(s), s)


def epoch(s: str | None) -> int | None:
    s = date_arg(s)
    return int(datetime.fromisoformat(s).replace(tzinfo=timezone.utc).timestamp()) if s else None


# ---- rendering --------------------------------------------------------------
def _clip(s: str | None, n: int) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def render(items: list[dict], fmt: str = "md", header: str = "", text_len: int = 400) -> str:
    if fmt == "json":
        return json.dumps({"query": header, "count": len(items), "items": items}, ensure_ascii=False, indent=1)
    if fmt == "jsonl":
        return "\n".join(json.dumps(i, ensure_ascii=False) for i in items)
    out = [f"## {header}", f"_{len(items)} items, fetched {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC_", ""] if header else []
    for i in items:
        meta = " | ".join(str(x) for x in (
            i["community"], i["author"] and f"u/{i['author']}" if i["source"] == "reddit" else i["author"],
            i["score"] is not None and f"score {i['score']}",
            i["num_comments"] is not None and f"{i['num_comments']} comments", i["created"]) if x)
        pad = "  " * i["depth"]
        if i["kind"] == "comment":
            out.append(f"{pad}- **{meta}**: {_clip(i['text'], text_len)}" + (f" ([link]({i['url']}))" if i["url"] and i["depth"] == 0 else ""))
        else:
            out.append(f"{pad}- **[{_clip(i['title'] or i['text'], 160) or '(untitled)'}]({i['url']})**  \n{pad}  {meta}")
            if i["text"] and i["title"]:
                out.append(f"{pad}  > {_clip(i['text'], text_len)}")
    return "\n".join(out)
