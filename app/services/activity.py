from fastapi import Request
from sqlalchemy.orm import Session

from app.models import ActivityLog, User


def log_activity(
    db: Session,
    *,
    user: User | None,
    action: str,
    description: str | None = None,
    request: Request | None = None,
) -> None:
    """Add an audit entry to the session. It is committed together with the business change."""
    ip = request.client.host if request is not None and request.client is not None else None
    db.add(
        ActivityLog(
            user_id=user.user_id if user else None,
            action=action,
            description=description,
            ip_address=ip,
        )
    )
