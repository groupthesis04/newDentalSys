from __future__ import annotations

from .core import make_id, utc_now


def add_notification(
    data: dict,
    recipient_id: str,
    notification_type: str,
    title: str,
    message: str,
    *,
    entity_type: str = "",
    entity_id: str = "",
) -> dict | None:
    recipient = next(
        (user for user in data.get("users", []) if user.get("id") == recipient_id),
        None,
    )
    if not recipient:
        return None
    notification = {
        "id": make_id("ntf"),
        "recipient_id": recipient_id,
        "type": str(notification_type)[:40],
        "title": str(title).strip()[:120],
        "message": str(message).strip()[:500],
        "entity_type": str(entity_type)[:40],
        "entity_id": str(entity_id)[:64],
        "is_read": False,
        "created_at": utc_now(),
        "read_at": "",
    }
    data.setdefault("notifications", []).append(notification)
    return notification


def notify_doctors(
    data: dict,
    notification_type: str,
    title: str,
    message: str,
    *,
    entity_type: str = "",
    entity_id: str = "",
) -> list[dict]:
    notifications = []
    for user in data.get("users", []):
        if user.get("role") != "doctor":
            continue
        notification = add_notification(
            data,
            user["id"],
            notification_type,
            title,
            message,
            entity_type=entity_type,
            entity_id=entity_id,
        )
        if notification:
            notifications.append(notification)
    return notifications


def patient_account_id(data: dict, patient_id: str) -> str:
    user = next(
        (
            item
            for item in data.get("users", [])
            if item.get("id") == patient_id and item.get("role") == "patient"
        ),
        None,
    )
    return user["id"] if user else ""
