from __future__ import annotations

from http import HTTPStatus
from ..core import (
    DATA_LOCK,
    find_user_by_id,
    load_data,
    make_id,
    public_user,
    save_data,
    utc_now,
    validate_identifier,
)


class MessageRoutes:
    def message_contacts(self, data: dict, user: dict) -> list[dict]:
        if user["role"] == "patient":
            contacts = [public_user(item) for item in data["users"] if item["role"] == "doctor"]
        elif user["role"] == "doctor":
            contacts = [public_user(item) for item in data["users"] if item["role"] == "patient"]
        else:
            contacts = []
        return sorted(contacts, key=lambda item: item["name"].lower())

    def list_messages(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            messages = [
                message
                for message in data["messages"]
                if message["sender_id"] == user["id"] or message["recipient_id"] == user["id"]
            ]
            messages = sorted(messages, key=lambda item: item["created_at"])
            contacts = self.message_contacts(data, user)
        self.send_json(HTTPStatus.OK, {"messages": messages, "contacts": contacts})

    def create_message(self, payload: dict) -> None:
        recipient_id = str(payload.get("recipient_id", "")).strip()
        body = str(payload.get("body", "")).strip()

        try:
            recipient_id = validate_identifier(recipient_id, "message recipient")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        if len(body) < 1:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter a message.")
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            recipient = find_user_by_id(data, recipient_id)
            if not recipient:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Recipient not found.")
                return
            valid_pair = (
                user["role"] == "patient"
                and recipient["role"] == "doctor"
            ) or (
                user["role"] == "doctor"
                and recipient["role"] == "patient"
            )
            if not valid_pair:
                self.send_error_json(
                    HTTPStatus.FORBIDDEN,
                    "Patients and doctors can only message each other.",
                )
                return
            message = {
                "id": make_id("msg"),
                "sender_id": user["id"],
                "sender_name": user["name"],
                "recipient_id": recipient["id"],
                "recipient_name": recipient["name"],
                "body": body[:1000],
                "created_at": utc_now(),
            }
            data["messages"].append(message)
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"message": message})
