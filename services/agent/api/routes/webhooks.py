"""Webhook routes — durably record inbound events from external services.

No processor consumes these yet (vendor email replies, distribution platforms, and
payment providers are all future producers), so the honest v1 is an audit log:
every delivery lands verbatim in webhook_events before any interpretation exists.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.dependencies import get_db
from database import models as orm

router = APIRouter()


@router.post("/{source}")
def receive_webhook(source: str, payload: dict, db: Session = Depends(get_db)) -> dict:
    db.add(orm.WebhookEventRow(source=source, payload=payload))
    db.commit()
    return {"source": source, "received": True}
