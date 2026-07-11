"""Occasion agent service — FastAPI entry point."""

from fastapi import FastAPI

from api.routes import approvals, chat, events, voice, webhooks

app = FastAPI(title="Occasion Agent")

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
