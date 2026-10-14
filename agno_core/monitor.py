"""Single-process polling. Persist observations before notifications."""
import asyncio
import logging
import httpx
from .agent import Analyst
from .config import Settings, Watch
from .probes import collect, detect_changes
from .storage import Store

log = logging.getLogger(__name__)


async def notify(settings: Settings, text: str) -> str:
    if not (settings.telegram_bot_token and settings.telegram_chat_id):
        return "local"
    async with httpx.AsyncClient(timeout=15) as client:
        result = await client.post(
            f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage",
            json={"chat_id": settings.telegram_chat_id, "text": text[:3500], "disable_web_page_preview": True},
        )
        result.raise_for_status()
    return "sent"


class Monitor:
    def __init__(self, settings: Settings, watches: list[Watch], store: Store):
        self.settings, self.watches, self.store = settings, watches, store
        self.agent = Analyst(settings, store)
        self.lock = asyncio.Lock()

    async def poll(self) -> dict:
        if self.lock.locked():
            return {"status": "already_running", "new_events": 0, "errors": {}}
        async with self.lock:
            new_events = 0
            errors = {}
            async with httpx.AsyncClient(timeout=20, follow_redirects=False,
                                         headers={"User-Agent": "AgnoCore/0.1"}) as client:
                for watch in self.watches:
                    try:
                        data = await collect(watch, client)
                        prior = self.store.get_state(watch.id)
                        state, events = detect_changes(watch, prior, data)
                        self.store.set_state(watch.id, state)
                        for event in events:
                            event_id = self.store.add_event(watch.id, event["title"], event["detail"], event["url"])
                            new_events += 1
                            analysis = None
                            if self.settings.analyze_changes:
                                try:
                                    analysis = await self.agent.summarize(event["title"], event["detail"], event["url"])
                                except Exception:
                                    log.exception("AI analysis failed for event %s", event_id)
                            message = (f"{watch.title}\n{event['title']}\n"
                                       f"{analysis or event['detail']}\n{event['url']}")
                            try:
                                delivery = await notify(self.settings, message)
                            except Exception:
                                delivery = "failed"
                                log.exception("Telegram failed for event %s", event_id)
                            self.store.update_event(event_id, analysis, delivery)
                    except Exception as exc:
                        errors[watch.id] = f"{type(exc).__name__}: {exc}"[:200]
                        self.store.set_error(watch.id, errors[watch.id])
                        log.warning("Poll failed for %s: %s", watch.id, exc)
            return {"status": "completed", "new_events": new_events, "errors": errors}
