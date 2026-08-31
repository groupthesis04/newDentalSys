from __future__ import annotations

import json
from http import HTTPStatus
from ..core import (
    DATA_LOCK,
    calculate_age,
    find_patient_profile_by_id,
    find_user_by_email,
    find_user_by_id,
    load_data,
    make_id,
    normalize_money,
    normalize_patient_identity,
    public_patient_profile,
    public_user,
    save_data,
    split_name,
    treatment_balance,
    utc_now,
    validate_birthdate,
    validate_email,
    validate_identifier,
    validate_person_name,
    validate_phone,
)


class PatientRoutes:
    def create_patient(self, payload: dict) -> None:
        first_name = str(payload.get("first_name", "")).strip()
        middle_name = str(payload.get("middle_name", "")).strip()
        last_name = str(payload.get("last_name", "")).strip()
        legacy_name = str(payload.get("name", "")).strip()
        if legacy_name and not (first_name or last_name):
            last_name, first_name, middle_name = split_name(legacy_name)
        sex = str(payload.get("sex", "")).strip()
        try:
            first_name = validate_person_name(first_name, "first name")
            last_name = validate_person_name(last_name, "last name")
            middle_name = validate_person_name(middle_name, "middle name") if middle_name else ""
            email = validate_email(payload.get("email", ""))
            phone_number = validate_phone(payload.get("phone_number", payload.get("phone", "")))
            mobile_number = validate_phone(
                payload.get("mobile_number", payload.get("phone", "")), required=True
            )
            birthdate = validate_birthdate(payload.get("birthdate", ""))
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        name = " ".join(part for part in (first_name, middle_name, last_name) if part).strip()
        address = str(payload.get("address", "")).strip()
        nationality = str(payload.get("nationality", "")).strip()
        occupation = str(payload.get("occupation", "")).strip()
        notes = str(payload.get("notes", "")).strip()

        if len(address) < 5:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's home address.")
            return
        if len(nationality) < 2:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's nationality.")
            return
        if len(occupation) < 2:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's occupation.")
            return
        if sex and sex.lower() not in {"male", "female", "other", "prefer not to say"}:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid sex value.")
            return

        with DATA_LOCK:
            data = load_data()
            doctor = self.require_doctor(data)
            if not doctor:
                return
            duplicate_account = find_user_by_email(data, email) if email else None
            duplicate_profile = next(
                (
                    profile
                    for profile in data["patient_profiles"]
                    if email and profile.get("email", "").lower() == email
                ),
                None,
            )
            if duplicate_account or duplicate_profile:
                self.send_error_json(HTTPStatus.CONFLICT, "An account already uses that email.")
                return
            identity = normalize_patient_identity(name, birthdate)
            duplicate_identity = any(
                normalize_patient_identity(public_patient_profile(profile)["name"], profile.get("birthdate", ""))
                == identity
                for profile in data["patient_profiles"]
            )
            if duplicate_identity:
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "A patient with the same full name and birthdate already exists.",
                )
                return
            profile = {
                "id": make_id("pat"),
                "name": name,
                "last_name": last_name[:90],
                "first_name": first_name[:90],
                "middle_name": middle_name[:90],
                "email": email,
                "phone": mobile_number or phone_number,
                "phone_number": phone_number[:40],
                "mobile_number": mobile_number[:40],
                "sex": sex[:40],
                "birthdate": birthdate,
                "age": calculate_age(birthdate),
                "address": address[:300],
                "nationality": nationality[:90],
                "occupation": occupation[:120],
                "notes": notes[:700],
                "created_by": doctor["id"],
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            data["patient_profiles"].append(profile)
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"patient": public_patient_profile(profile)})

    def update_patient(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        patient_id = str(payload.get("id", "")).strip()
        first_name = str(payload.get("first_name", "")).strip()
        middle_name = str(payload.get("middle_name", "")).strip()
        last_name = str(payload.get("last_name", "")).strip()
        legacy_name = str(payload.get("name", "")).strip()
        if legacy_name and not (first_name or last_name):
            last_name, first_name, middle_name = split_name(legacy_name)
        sex = str(payload.get("sex", "")).strip()
        try:
            patient_id = validate_identifier(patient_id, "patient to edit")
            first_name = validate_person_name(first_name, "first name")
            last_name = validate_person_name(last_name, "last name")
            middle_name = validate_person_name(middle_name, "middle name") if middle_name else ""
            email = validate_email(payload.get("email", ""))
            phone_number = validate_phone(payload.get("phone_number", payload.get("phone", "")))
            mobile_number = validate_phone(
                payload.get("mobile_number", payload.get("phone", "")), required=True
            )
            birthdate = validate_birthdate(payload.get("birthdate", ""))
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        name = " ".join(part for part in (first_name, middle_name, last_name) if part).strip()
        address = str(payload.get("address", "")).strip()
        nationality = str(payload.get("nationality", "")).strip()
        occupation = str(payload.get("occupation", "")).strip()
        notes = str(payload.get("notes", "")).strip()

        if len(address) < 5:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's home address.")
            return
        if len(nationality) < 2:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's nationality.")
            return
        if len(occupation) < 2:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Enter the patient's occupation.")
            return
        if sex and sex.lower() not in {"male", "female", "other", "prefer not to say"}:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid sex value.")
            return

        with DATA_LOCK:
            data = load_data()
            doctor = self.require_doctor(data)
            if not doctor:
                return
            profile = find_patient_profile_by_id(data, patient_id)
            if not profile:
                self.send_error_json(
                    HTTPStatus.FORBIDDEN,
                    "Only clinic patient records can be edited here. Patient login accounts manage their own profile.",
                )
                return
            duplicate_account = find_user_by_email(data, email)
            duplicate_profile = next(
                (
                    item
                    for item in data["patient_profiles"]
                    if item["id"] != patient_id and item.get("email", "").lower() == email
                ),
                None,
            )
            if duplicate_account or duplicate_profile:
                self.send_error_json(HTTPStatus.CONFLICT, "An account already uses that email.")
                return
            identity = normalize_patient_identity(name, birthdate)
            duplicate_identity = any(
                item["id"] != patient_id
                and normalize_patient_identity(public_patient_profile(item)["name"], item.get("birthdate", ""))
                == identity
                for item in data["patient_profiles"]
            )
            if duplicate_identity:
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "A patient with the same full name and birthdate already exists.",
                )
                return

            profile.update(
                {
                    "name": name,
                    "last_name": last_name[:90],
                    "first_name": first_name[:90],
                    "middle_name": middle_name[:90],
                    "email": email,
                    "phone": mobile_number or phone_number,
                    "phone_number": phone_number[:40],
                    "mobile_number": mobile_number[:40],
                    "sex": sex[:40],
                    "birthdate": birthdate,
                    "age": calculate_age(birthdate),
                    "address": address[:300],
                    "nationality": nationality[:90],
                    "occupation": occupation[:120],
                    "notes": notes[:700],
                    "updated_at": utc_now(),
                }
            )
            for record in data["records"]:
                if record["patient_id"] == patient_id:
                    record["patient_name"] = name
            save_data(data)
        self.send_json(HTTPStatus.OK, {"patient": public_patient_profile(profile)})

    def delete_patient(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        patient_id = str(payload.get("id", "")).strip()
        try:
            patient_id = validate_identifier(patient_id, "patient")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            patient = find_patient_profile_by_id(data, patient_id)
            if not patient:
                account = find_user_by_id(data, patient_id)
                if account and account["role"] == "patient":
                    self.send_error_json(
                        HTTPStatus.FORBIDDEN,
                        "Patient login accounts cannot be deleted from the patient records section.",
                    )
                    return
                self.send_error_json(HTTPStatus.NOT_FOUND, "Patient not found.")
                return
            data["patient_profiles"] = [
                item for item in data["patient_profiles"] if item["id"] != patient_id
            ]
            data["records"] = [
                item for item in data["records"] if item["patient_id"] != patient_id
            ]
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})

    def list_patients(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            patients = []
            def patient_summary(patient_id: str) -> dict:
                patient_records = [record for record in data["records"] if record["patient_id"] == patient_id]
                total_charged = round(sum(normalize_money(record.get("amount_charged")) for record in patient_records), 2)
                total_paid = round(sum(normalize_money(record.get("amount_paid")) for record in patient_records), 2)
                total_balance = round(sum(treatment_balance(record) for record in patient_records), 2)
                dates = [
                    record.get("treatment_date") or record.get("created_at", "")[:10]
                    for record in patient_records
                    if record.get("treatment_date") or record.get("created_at")
                ]
                return {
                    "last_visit": max(dates) if dates else "",
                    "total_amount_charged": total_charged,
                    "total_amount_paid": total_paid,
                    "total_balance": total_balance,
                }

            for patient in data["users"]:
                if patient["role"] != "patient":
                    continue
                appointment_count = sum(
                    1 for item in data["appointments"] if item["patient_id"] == patient["id"]
                )
                record_count = sum(
                    1 for item in data["records"] if item["patient_id"] == patient["id"]
                )
                safe_patient = public_user(patient)
                last_name, first_name, middle_name = split_name(patient.get("name", ""))
                safe_patient.update(
                    {
                        "source": "account",
                        "last_name": last_name,
                        "first_name": first_name,
                        "middle_name": middle_name,
                        "sex": "",
                        "birthdate": "",
                        "age": "",
                        "address": "",
                        "nationality": "",
                        "occupation": "",
                        "phone_number": patient.get("phone", ""),
                        "mobile_number": patient.get("phone", ""),
                        "notes": "",
                        "appointment_count": appointment_count,
                        "record_count": record_count,
                        **patient_summary(patient["id"]),
                    }
                )
                patients.append(safe_patient)
            for profile in data["patient_profiles"]:
                appointment_count = sum(
                    1 for item in data["appointments"] if item["patient_id"] == profile["id"]
                )
                record_count = sum(
                    1 for item in data["records"] if item["patient_id"] == profile["id"]
                )
                safe_profile = public_patient_profile(profile)
                safe_profile.update(
                    {
                        "appointment_count": appointment_count,
                        "record_count": record_count,
                        **patient_summary(profile["id"]),
                    }
                )
                patients.append(safe_profile)
        self.send_json(HTTPStatus.OK, {"patients": patients})
