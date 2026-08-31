from __future__ import annotations

import json
from http import HTTPStatus
from ..core import (
    DATA_LOCK,
    load_data,
    make_id,
    save_data,
    utc_now,
    validate_identifier,
    validate_person_name,
)


class ServiceRoutes:
    def list_services(self) -> None:
        with DATA_LOCK:
            data = load_data()
            services = sorted(data["services"], key=lambda item: item["created_at"])
        self.send_json(HTTPStatus.OK, {"services": services})

    def list_promos(self) -> None:
        with DATA_LOCK:
            data = load_data()
            promos = sorted(data["promos"], key=lambda item: item["created_at"])
        self.send_json(HTTPStatus.OK, {"promos": promos})

    def list_feedback(self) -> None:
        with DATA_LOCK:
            data = load_data()
            feedback = sorted(
                data["feedback"],
                key=lambda item: item["created_at"],
                reverse=True,
            )
        self.send_json(HTTPStatus.OK, {"feedback": feedback})

    def create_service(self, payload: dict) -> None:
        name = str(payload.get("name", "")).strip()
        description = str(payload.get("description", "")).strip()

        if len(name) < 3:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Service name must be at least 3 characters.")
            return
        if len(description) < 10:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Service description must be at least 10 characters.")
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            duplicate = any(
                service["name"].strip().lower() == name.lower()
                for service in data["services"]
            )
            if duplicate:
                self.send_error_json(HTTPStatus.CONFLICT, "A service with that name already exists.")
                return
            service = {
                "id": make_id("svc"),
                "name": name[:90],
                "description": description[:350],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            data["services"].append(service)
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"service": service})

    def create_promo(self, payload: dict) -> None:
        title = str(payload.get("title", "")).strip()
        description = str(payload.get("description", "")).strip()

        if len(title) < 3:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Promo title must be at least 3 characters.")
            return
        if len(description) < 10:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Promo description must be at least 10 characters.")
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            promo = {
                "id": make_id("promo"),
                "title": title[:90],
                "description": description[:350],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            data["promos"].append(promo)
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"promo": promo})

    def delete_service(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        service_id = str(payload.get("id", "")).strip()
        try:
            service_id = validate_identifier(service_id, "service")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            before = len(data["services"])
            data["services"] = [
                service for service in data["services"] if service["id"] != service_id
            ]
            if len(data["services"]) == before:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Service not found.")
                return
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})

    def delete_promo(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        promo_id = str(payload.get("id", "")).strip()
        try:
            promo_id = validate_identifier(promo_id, "promo")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            before = len(data["promos"])
            data["promos"] = [promo for promo in data["promos"] if promo["id"] != promo_id]
            if len(data["promos"]) == before:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Promo not found.")
                return
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})

    def delete_feedback(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        feedback_id = str(payload.get("id", "")).strip()
        try:
            feedback_id = validate_identifier(feedback_id, "feedback")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            before = len(data["feedback"])
            data["feedback"] = [
                feedback for feedback in data["feedback"] if feedback["id"] != feedback_id
            ]
            if len(data["feedback"]) == before:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Feedback not found.")
                return
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})

    def update_feedback(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        feedback_id = str(payload.get("id", "")).strip()
        message = str(payload.get("message", "")).strip()
        try:
            rating = int(payload.get("rating", 5))
        except (TypeError, ValueError):
            rating = 0

        try:
            feedback_id = validate_identifier(feedback_id, "feedback")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        if rating not in {1, 2, 3, 4, 5}:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a rating from 1 to 5.")
            return
        if len(message) < 10:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Feedback must be at least 10 characters.")
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            feedback = next(
                (item for item in data["feedback"] if item["id"] == feedback_id),
                None,
            )
            if not feedback:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Feedback not found.")
                return
            feedback["rating"] = rating
            feedback["message"] = message[:500]
            feedback["updated_at"] = utc_now()
            feedback["updated_by"] = user["id"]
            save_data(data)
        self.send_json(HTTPStatus.OK, {"feedback": feedback})

    def create_feedback(self, payload: dict) -> None:
        name = str(payload.get("name", "")).strip()
        message = str(payload.get("message", "")).strip()
        try:
            rating = int(payload.get("rating", 5))
        except (TypeError, ValueError):
            rating = 0
        if rating not in {1, 2, 3, 4, 5}:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a rating from 1 to 5.")
            return
        if name:
            try:
                name = validate_person_name(name)
            except ValueError as error:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                return

        with DATA_LOCK:
            data = load_data()
            user = self.current_user(data)
            if user:
                name = user["name"]
            if not name:
                name = "Clinic Visitor"
            if len(message) < 10:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Feedback must be at least 10 characters.")
                return
            feedback = {
                "id": make_id("fb"),
                "name": name[:80],
                "rating": rating,
                "message": message[:500],
                "created_at": utc_now(),
            }
            data["feedback"].append(feedback)
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"feedback": feedback})
