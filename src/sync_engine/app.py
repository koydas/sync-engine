import os

from fastapi import FastAPI, HTTPException, Request

from sync_engine.exceptions import DuplicateEventError, WebhookSignatureError
from sync_engine.store.base import SyncStore
from sync_engine.store.memory import InMemoryStore
from sync_engine.webhook.handler import WebhookHandler


def create_app(store: SyncStore | None = None, secret: str | None = None) -> FastAPI:
    store = store or InMemoryStore()
    secret = secret if secret is not None else os.environ["WEBHOOK_SECRET"]
    handler = WebhookHandler(store, secret)

    app = FastAPI(title="sync-engine")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "last_sync_at": store.get_last_sync_at()}

    @app.post("/webhooks")
    async def receive_webhook(request: Request) -> dict:
        event_id = request.headers.get("X-Event-Id")
        if not event_id:
            raise HTTPException(status_code=400, detail="Missing X-Event-Id header")

        raw_bytes = await request.body()
        signature = request.headers.get("X-Hub-Signature-256", "")

        try:
            payload = await request.json()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

        try:
            handler.handle(event_id, payload, raw_bytes, signature)
        except WebhookSignatureError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc
        except DuplicateEventError:
            return {"status": "duplicate"}

        return {"status": "accepted"}

    return app
