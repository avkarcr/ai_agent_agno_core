"""Pure data collection and deterministic change detection."""
import feedparser
import httpx
from .config import Watch


async def collect(watch: Watch, client: httpx.AsyncClient) -> dict:
    response = await client.get(str(watch.url))
    response.raise_for_status()
    if watch.kind == "json":
        value = response.json()
        for key in (watch.json_path or "").split("."):
            if not isinstance(value, dict) or key not in value:
                raise ValueError(f"JSON path not found: {watch.json_path}")
            value = value[key]
        if value is None or isinstance(value, (dict, list)):
            raise ValueError("JSON path must resolve to a scalar")
        return {"value": value}
    feed = feedparser.parse(response.content)
    entries = []
    for entry in feed.entries[:watch.max_items]:
        title = str(entry.get("title", "Untitled"))[:250]
        url = str(entry.get("link") or watch.url)[:2000]
        key = str(entry.get("id") or url)[:2000]
        entries.append({"id": key, "title": title, "url": url})
    if feed.bozo and not entries:
        raise ValueError("RSS response is not a valid feed")
    return {"entries": entries}


def detect_changes(watch: Watch, old: dict | None, new: dict) -> tuple[dict, list[dict]]:
    """First observation creates a baseline without notifications."""
    if watch.kind == "rss":
        current = new["entries"]
        previous = (old or {}).get("seen", [])
        seen = set(previous)
        changes = [] if old is None else [
            {"title": entry["title"], "detail": "New item in RSS", "url": entry["url"]}
            for entry in reversed(current) if entry["id"] not in seen
        ]
        merged = list(dict.fromkeys(previous + [entry["id"] for entry in current]))[-300:]
        return {"seen": merged}, changes

    value = new["value"]
    if old is None:
        return new, []
    before = old["value"]
    if type(value) in (int, float) and type(before) in (int, float):
        changed = abs(value - before) >= watch.min_delta if watch.min_delta else value != before
    else:
        changed = value != before
    if not changed:
        return old, []
    return new, [{"title": f"{watch.title} changed", "detail": f"{before!r} → {value!r}", "url": str(watch.url)}]
