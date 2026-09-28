import logging
import time
from datetime import timedelta

from sqlalchemy import delete, select

from .database import SessionLocal
from .integrations import cache_client
from .models import AuditEvent, AuthToken, Conversation, Message, now

logging.basicConfig(level=logging.INFO, format='{"level":"%(levelname)s","logger":"maintenance","message":"%(message)s"}')
log = logging.getLogger("maintenance")


def sweep():
    with SessionLocal() as db:
        expired = list(db.scalars(select(Conversation).where(Conversation.purge_after.is_not(None), Conversation.purge_after <= now())))
        for item in expired:
            db.execute(delete(Message).where(Message.conversation_id == item.id))
            db.add(AuditEvent(tenant_id=item.tenant_id, user_id=item.user_id, action="session.retention_purge", target_type="session", target_id=item.id))
            db.delete(item)
        db.execute(delete(AuthToken).where(AuthToken.expires_at <= now()))
        db.commit()
        cache_client().setex("heartbeat:maintenance", 150, str(now()))
        if expired: log.info("purged_sessions count=%s", len(expired))


def run():
    while True:
        try: sweep()
        except Exception: log.exception("maintenance_sweep_failed")
        time.sleep(60)


if __name__ == "__main__": run()
