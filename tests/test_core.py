from agno_core.config import Watch
from agno_core.probes import detect_changes
from agno_core.storage import Store


def watch(kind="json", **kwargs):
    values = {"id": "test", "title": "Test", "kind": kind,
              "url": "https://example.org/feed"}
    if kind == "json":
        values["json_path"] = "value"
    values.update(kwargs)
    return Watch(**values)


def test_json_baseline_and_delta():
    source = watch(min_delta=2)
    baseline, events = detect_changes(source, None, {"value": 10})
    assert events == [] and baseline == {"value": 10}
    next_state, events = detect_changes(source, baseline, {"value": 11})
    assert events == [] and next_state == baseline
    final, events = detect_changes(source, next_state, {"value": 12})
    assert final == {"value": 12} and len(events) == 1


def test_rss_only_new_items():
    source = watch("rss")
    initial = {"entries": [{"id": "a", "title": "First", "url": "https://example.org/a"}]}
    baseline, events = detect_changes(source, None, initial)
    assert events == []
    later = {"entries": initial["entries"] + [
        {"id": "b", "title": "Second", "url": "https://example.org/b"}]}
    state, events = detect_changes(source, baseline, later)
    assert len(events) == 1 and events[0]["title"] == "Second"
    _, again = detect_changes(source, state, later)
    assert again == []


def test_store_roundtrip(tmp_path):
    path = tmp_path / "core.sqlite3"
    store = Store(path)
    store.set_state("x", {"value": 1})
    store.set_error("x", "connection failed")
    assert Store(path).get_state("x") == {"value": 1}
    assert store.list_states()["x"]["error"] == "connection failed"
    store.set_state("x", {"value": 2})
    assert store.list_states()["x"]["error"] is None
    event_id = store.add_event("x", "Changed", "1 to 2", "https://example.org")
    store.update_event(event_id, "Summary", "local")
    assert store.list_events()[0]["analysis"] == "Summary"
