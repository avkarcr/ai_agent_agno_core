"""FastAPI web UI and local scheduler. Never expose publicly without authentication."""
from contextlib import asynccontextmanager
from pathlib import Path
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from .config import Settings, load_watches
from .monitor import Monitor
from .storage import Store


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    watches = load_watches(settings.watches_file)
    store = Store(settings.db_path)
    monitor = Monitor(settings, watches, store)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        scheduler = AsyncIOScheduler(timezone="UTC")
        scheduler.add_job(monitor.poll, "interval", minutes=settings.poll_minutes,
                          id="check_sources", max_instances=1, coalesce=True)
        scheduler.start()
        try:
            yield
        finally:
            scheduler.shutdown(wait=False)

    app = FastAPI(title="Agno Core", version="0.1.0", lifespan=lifespan)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (Path(__file__).parent / "static" / "index.html").read_text(encoding="utf-8")

    @app.get("/health")
    def health():
        return {"status": "ok", "sources": len(watches)}

    @app.get("/api/watches")
    def list_watches():
        states = store.list_states()
        return [
            {**watch.model_dump(mode="json"), **states.get(watch.id, {})}
            for watch in watches
        ]

    @app.get("/api/events")
    def list_events(limit: int = 50):
        return store.list_events(limit)

    @app.post("/api/run")
    async def check():
        return await monitor.poll()

    @app.post("/api/ask")
    async def ask(body: AskRequest):
        try:
            return {"answer": await monitor.agent.ask(body.question)}
        except Exception as exc:
            raise HTTPException(status_code=503,
                detail="LLM is unavailable. Check your model and provider configuration.") from exc

    return app


app = create_app()
