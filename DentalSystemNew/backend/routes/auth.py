from __future__ import annotations

import hmac
import json
from http import HTTPStatus
from ..core import (
    COOKIE_SECURE,
    DATA_LOCK,
    DUMMY_PASSWORD_HASH,
    SESSION_COOKIE,
    SESSION_LOCK,
    SESSION_STORE,
    STAFF_ACCESS_CODE,
    find_user_by_email,
    hash_password,
    load_data,
    make_id,
    normalize_profile_image,
    public_user,
    save_data,
    utc_now,
    validate_email,
    validate_password_strength,
    validate_person_name,
    validate_phone,
    verify_password,
)


class AuthRoutes:
    def register(self, payload: dict) -> None:
        try:
            name = validate_person_name(payload.get("name", ""))
            email = validate_email(payload.get("email", ""))
            phone = validate_phone(payload.get("phone", ""))
            profile_image = normalize_profile_image(payload.get("profile_image", ""))
            password = validate_password_strength(payload.get("password", ""))
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        role = str(payload.get("role", "patient")).strip().lower()

        if role not in {"patient", "doctor"}:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid account type.")
            return
        if role == "doctor":
            provided_code = str(payload.get("staff_code", ""))
            if not STAFF_ACCESS_CODE:
                self.send_error_json(
                    HTTPStatus.SERVICE_UNAVAILABLE,
                    "Staff registration is disabled until DRMS_STAFF_CODE is configured.",
                )
                return
            if not hmac.compare_digest(provided_code, STAFF_ACCESS_CODE):
                self.send_error_json(HTTPStatus.FORBIDDEN, "Invalid staff access code.")
                return

        with DATA_LOCK:
            data = load_data()
            if find_user_by_email(data, email):
                self.send_error_json(HTTPStatus.CONFLICT, "A patient record or account already uses that email.")
                return
            user = {
                "id": make_id("usr"),
                "name": name,
                "email": email,
                "phone": phone,
                "role": role,
                "profile_image": profile_image,
                "password_hash": hash_password(password),
                "created_at": utc_now(),
            }
            data["users"].append(user)
            save_data(data)

        remember = str(payload.get("remember", "")).lower() in {"1", "true", "yes", "on"}
        token, csrf_token, max_age = self.create_session(user["id"], remember)
        self.send_json(
            HTTPStatus.CREATED,
            {"user": public_user(user), "csrf_token": csrf_token},
            {"Set-Cookie": self.session_cookie(token, max_age)},
        )

    def login(self, payload: dict) -> None:
        email = str(payload.get("email", "")).strip().lower()
        password = str(payload.get("password", ""))
        with DATA_LOCK:
            data = load_data()
            user = find_user_by_email(data, email)

        encoded = user.get("password_hash", "") if user else DUMMY_PASSWORD_HASH
        password_matches = verify_password(password, encoded)
        if not user or not password_matches:
            self.send_error_json(HTTPStatus.UNAUTHORIZED, "Email or password is incorrect.")
            return

        remember = str(payload.get("remember", "")).lower() in {"1", "true", "yes", "on"}
        token, csrf_token, max_age = self.create_session(user["id"], remember)
        self.send_json(
            HTTPStatus.OK,
            {"user": public_user(user), "csrf_token": csrf_token},
            {"Set-Cookie": self.session_cookie(token, max_age)},
        )

    def logout(self) -> None:
        active = self.current_session()
        if active and not self.valid_csrf_token(active[1]):
            self.send_error_json(
                HTTPStatus.FORBIDDEN,
                "Security token expired. Refresh the page and try again.",
            )
            return
        token = active[0] if active else self.cookie_token()
        if token:
            with SESSION_LOCK:
                SESSION_STORE.pop(token, None)
        expired_cookie = f"{SESSION_COOKIE}=; Path=/; Max-Age=0; HttpOnly; SameSite=Strict"
        if COOKIE_SECURE:
            expired_cookie += "; Secure"
        self.send_json(
            HTTPStatus.OK,
            {"ok": True},
            {"Set-Cookie": expired_cookie},
        )

    def update_profile(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        try:
            name = validate_person_name(payload.get("name", ""))
            email = validate_email(payload.get("email", ""))
            phone = validate_phone(payload.get("phone", ""))
            profile_image = normalize_profile_image(payload.get("profile_image", ""))
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            duplicate = find_user_by_email(data, email)
            if duplicate and duplicate["id"] != user["id"]:
                self.send_error_json(HTTPStatus.CONFLICT, "An account already uses that email.")
                return

            old_name = user["name"]
            old_email = user["email"]
            user["name"] = name
            user["email"] = email
            user["phone"] = phone
            user["profile_image"] = profile_image
            user["updated_at"] = utc_now()

            if user["role"] == "patient":
                for appointment in data["appointments"]:
                    if appointment["patient_id"] == user["id"]:
                        appointment["patient_name"] = name
                        appointment["patient_email"] = email
                        appointment["patient_phone"] = phone
                for record in data["records"]:
                    if record["patient_id"] == user["id"]:
                        record["patient_name"] = name
            elif user["role"] == "doctor":
                for record in data["records"]:
                    if record["doctor_id"] == user["id"]:
                        record["doctor_name"] = name
                for appointment in data["appointments"]:
                    if appointment.get("doctor") == old_name:
                        appointment["doctor"] = name
                    if appointment.get("doctor") == old_email:
                        appointment["doctor"] = name

            save_data(data)
        self.send_json(HTTPStatus.OK, {"user": public_user(user)})
