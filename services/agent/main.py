"""Occasion agent service — FastAPI entry point."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import approvals, chat, computer_use, events, voice, webhooks

app = FastAPI(title="Occasion Agent")

# The web app calls this service straight from the browser during local dev.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(chat.router, prefix="/chat", tags=["chat"])
app.include_router(approvals.router, prefix="/approvals", tags=["approvals"])
app.include_router(voice.router, prefix="/voice", tags=["voice"])
app.include_router(webhooks.router, prefix="/webhooks", tags=["webhooks"])
app.include_router(computer_use.router, prefix="/api/computer-use", tags=["computer-use"])


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
