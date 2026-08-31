from __future__ import annotations

import json
from http import HTTPStatus

from ..core import DATA_LOCK, load_data, save_data, utc_now, validate_identifier


class NotificationRoutes:
    def list_notifications(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            notifications = [
                dict(item)
                for item in data.get("notifications", [])
                if item.get("recipient_id") == user["id"]
            ]
            notifications.sort(key=lambda item: item.get("created_at", ""), reverse=True)
            notifications = notifications[:50]
            unread_count = sum(1 for item in notifications if not item.get("is_read"))
        self.send_json(
            HTTPStatus.OK,
            {"notifications": notifications, "unread_count": unread_count},
        )

    def mark_notifications_read(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        mark_all = str(payload.get("mark_all", "")).strip().lower() == "true"
        notification_id = str(payload.get("id", "")).strip()
        if not mark_all:
            try:
                notification_id = validate_identifier(notification_id, "notification")
            except ValueError as error:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                return

        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            owned = [
                item
                for item in data.get("notifications", [])
                if item.get("recipient_id") == user["id"]
            ]
            targets = owned if mark_all else [
                item for item in owned if item.get("id") == notification_id
            ]
            if not mark_all and not targets:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Notification not found.")
                return
            read_at = utc_now()
            changed = 0
            for item in targets:
                if item.get("is_read"):
                    continue
                item["is_read"] = True
                item["read_at"] = read_at
                changed += 1
            if changed:
                save_data(data)
            unread_count = sum(1 for item in owned if not item.get("is_read"))
        self.send_json(
            HTTPStatus.OK,
            {"ok": True, "marked_count": changed, "unread_count": unread_count},
        )
