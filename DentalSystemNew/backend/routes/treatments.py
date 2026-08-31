from __future__ import annotations

import datetime as dt
import json
from http import HTTPStatus
from ..core import (
    DATA_LOCK,
    find_appointment,
    find_patient_for_record,
    find_record,
    load_data,
    make_id,
    normalize_money,
    parse_date,
    parse_money,
    payment_status,
    save_data,
    treatment_balance,
    utc_now,
    validate_identifier,
    validate_tooth_numbers,
)
from ..notifications import add_notification, notify_doctors, patient_account_id


class TreatmentRoutes:
    def list_records(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            if user["role"] == "doctor":
                records = data["records"]
            else:
                records = [item for item in data["records"] if item["patient_id"] == user["id"]]
            normalized_records = []
            for record in records:
                safe_record = dict(record)
                safe_record["treatment_date"] = safe_record.get("treatment_date") or safe_record.get("created_at", "")[:10]
                safe_record["procedure"] = safe_record.get("procedure") or safe_record.get("treatment") or safe_record.get("diagnosis", "")
                safe_record["tooth_numbers"] = safe_record.get("tooth_numbers", "")
                safe_record["amount_charged"] = normalize_money(safe_record.get("amount_charged"))
                safe_record["amount_paid"] = normalize_money(safe_record.get("amount_paid"))
                safe_record["balance"] = treatment_balance(safe_record)
                safe_record["payment_status"] = safe_record.get("payment_status") or payment_status(safe_record["balance"])
                safe_record["remarks"] = safe_record.get("remarks", safe_record.get("notes", ""))
                normalized_records.append(safe_record)
            records = sorted(
                normalized_records,
                key=lambda item: (item.get("treatment_date", ""), item.get("created_at", "")),
                reverse=True,
            )
        self.send_json(HTTPStatus.OK, {"records": records})

    def create_record(self, payload: dict) -> None:
        appointment_id = str(payload.get("appointment_id", "")).strip()
        patient_id = str(payload.get("patient_id", "")).strip()
        diagnosis = str(payload.get("diagnosis", payload.get("procedure", ""))).strip()
        treatment = str(payload.get("treatment", "")).strip()
        procedure = str(payload.get("procedure", treatment)).strip()
        tooth_numbers = str(payload.get("tooth_numbers", "")).strip()
        prescription = str(payload.get("prescription", "")).strip()
        remarks = str(payload.get("remarks", payload.get("notes", ""))).strip()
        try:
            if appointment_id:
                appointment_id = validate_identifier(appointment_id, "appointment")
            patient_id = validate_identifier(patient_id, "patient")
            tooth_numbers = validate_tooth_numbers(tooth_numbers)
            treatment_date = parse_date(payload.get("treatment_date", ""), "treatment date", required=True)
            next_visit = parse_date(payload.get("next_visit", ""), "next visit")
            amount_charged = parse_money(payload.get("amount_charged", 0), "Amount charged")
            amount_paid = parse_money(payload.get("amount_paid", 0), "Amount paid")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        if amount_paid > amount_charged:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Amount paid cannot exceed amount charged.")
            return
        if dt.date.fromisoformat(treatment_date) > dt.date.today():
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Treatment date cannot be in the future.")
            return
        if next_visit and dt.date.fromisoformat(next_visit) < dt.date.fromisoformat(treatment_date):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Next visit cannot be before the treatment date.")
            return
        balance = round(amount_charged - amount_paid, 2)

        if not procedure:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Procedure or service is required.")
            return
        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return

            if not any(item.get("name", "").casefold() == procedure.casefold() for item in data["services"]):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid dental service.")
                return

            appointment = find_appointment(data, appointment_id) if appointment_id else None
            if appointment:
                patient_id = appointment["patient_id"]
            patient = find_patient_for_record(data, patient_id)
            if not patient:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid patient.")
                return

            record = {
                "id": make_id("rec"),
                "appointment_id": appointment["id"] if appointment else "",
                "patient_id": patient["id"],
                "patient_name": patient["name"],
                "doctor_id": user["id"],
                "doctor_name": user["name"],
                "treatment_date": treatment_date,
                "tooth_numbers": tooth_numbers[:120],
                "procedure": procedure[:120],
                "amount_charged": amount_charged,
                "amount_paid": amount_paid,
                "balance": balance,
                "payment_status": payment_status(balance),
                "diagnosis": diagnosis[:700],
                "treatment": procedure[:700],
                "prescription": prescription[:700],
                "notes": remarks[:1000],
                "remarks": remarks[:1000],
                "next_visit": next_visit,
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            data["records"].append(record)
            if appointment:
                appointment["status"] = "completed"
                appointment["updated_at"] = utc_now()
            recipient_id = patient_account_id(data, patient["id"])
            if recipient_id:
                add_notification(
                    data,
                    recipient_id,
                    "treatment_created",
                    "Treatment record added",
                    f"{procedure} was recorded with a charge of PHP {amount_charged:,.2f} and a balance of PHP {balance:,.2f}.",
                    entity_type="treatment",
                    entity_id=record["id"],
                )
            notify_doctors(
                data,
                "treatment_created",
                "Treatment transaction recorded",
                f"{procedure} was added for {patient['name']} with a balance of PHP {balance:,.2f}.",
                entity_type="treatment",
                entity_id=record["id"],
            )
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"record": record})

    def update_record(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        record_id = str(payload.get("id", "")).strip()
        patient_id = str(payload.get("patient_id", "")).strip()
        appointment_id = str(payload.get("appointment_id", "")).strip()
        diagnosis = str(payload.get("diagnosis", payload.get("procedure", ""))).strip()
        procedure = str(payload.get("procedure", payload.get("treatment", ""))).strip()
        tooth_numbers = str(payload.get("tooth_numbers", "")).strip()
        prescription = str(payload.get("prescription", "")).strip()
        remarks = str(payload.get("remarks", payload.get("notes", ""))).strip()
        try:
            record_id = validate_identifier(record_id, "treatment record")
            if patient_id:
                patient_id = validate_identifier(patient_id, "patient")
            if appointment_id:
                appointment_id = validate_identifier(appointment_id, "appointment")
            tooth_numbers = validate_tooth_numbers(tooth_numbers)
            treatment_date = parse_date(payload.get("treatment_date", ""), "treatment date", required=True)
            next_visit = parse_date(payload.get("next_visit", ""), "next visit")
            amount_charged = parse_money(payload.get("amount_charged", 0), "Amount charged")
            amount_paid = parse_money(payload.get("amount_paid", 0), "Amount paid")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        if amount_paid > amount_charged:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Amount paid cannot exceed amount charged.")
            return
        if dt.date.fromisoformat(treatment_date) > dt.date.today():
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Treatment date cannot be in the future.")
            return
        if next_visit and dt.date.fromisoformat(next_visit) < dt.date.fromisoformat(treatment_date):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Next visit cannot be before the treatment date.")
            return
        balance = round(amount_charged - amount_paid, 2)

        if not procedure:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Procedure or service is required.")
            return
        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            record = find_record(data, record_id)
            if not record:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Treatment record not found.")
                return
            if not any(item.get("name", "").casefold() == procedure.casefold() for item in data["services"]):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid dental service.")
                return
            appointment = find_appointment(data, appointment_id) if appointment_id else None
            if appointment:
                patient_id = appointment["patient_id"]
            patient = find_patient_for_record(data, patient_id or record.get("patient_id", ""))
            if not patient:
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid patient.")
                return

            record.update(
                {
                    "appointment_id": appointment["id"] if appointment else appointment_id,
                    "patient_id": patient["id"],
                    "patient_name": patient["name"],
                    "doctor_id": user["id"],
                    "doctor_name": user["name"],
                    "treatment_date": treatment_date,
                    "tooth_numbers": tooth_numbers[:120],
                    "procedure": procedure[:120],
                    "amount_charged": amount_charged,
                    "amount_paid": amount_paid,
                    "balance": balance,
                    "payment_status": payment_status(balance),
                    "diagnosis": diagnosis[:700],
                    "treatment": procedure[:700],
                    "prescription": prescription[:700],
                    "notes": remarks[:1000],
                    "remarks": remarks[:1000],
                    "next_visit": next_visit,
                    "updated_at": utc_now(),
                }
            )
            if appointment:
                appointment["status"] = "completed"
                appointment["updated_at"] = utc_now()
            recipient_id = patient_account_id(data, patient["id"])
            if recipient_id:
                add_notification(
                    data,
                    recipient_id,
                    "treatment_updated",
                    "Treatment record updated",
                    f"{procedure} now shows PHP {amount_paid:,.2f} paid and PHP {balance:,.2f} remaining.",
                    entity_type="treatment",
                    entity_id=record["id"],
                )
            notify_doctors(
                data,
                "treatment_updated",
                "Treatment transaction updated",
                f"{patient['name']}'s {procedure} record now has a balance of PHP {balance:,.2f}.",
                entity_type="treatment",
                entity_id=record["id"],
            )
            save_data(data)
        self.send_json(HTTPStatus.OK, {"record": record})

    def delete_record(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        record_id = str(payload.get("id", "")).strip()
        try:
            record_id = validate_identifier(record_id, "treatment record")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            record = find_record(data, record_id)
            if not record:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Treatment record not found.")
                return
            before = len(data["records"])
            data["records"] = [record for record in data["records"] if record["id"] != record_id]
            if len(data["records"]) == before:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Treatment record not found.")
                return
            recipient_id = patient_account_id(data, record.get("patient_id", ""))
            if recipient_id:
                add_notification(
                    data,
                    recipient_id,
                    "treatment_deleted",
                    "Treatment record removed",
                    f"The {record.get('procedure', record.get('treatment', 'treatment'))} record was removed by clinic staff.",
                    entity_type="treatment",
                    entity_id=record_id,
                )
            notify_doctors(
                data,
                "treatment_deleted",
                "Treatment transaction removed",
                f"The {record.get('procedure', record.get('treatment', 'treatment'))} record for {record.get('patient_name', 'the patient')} was removed.",
                entity_type="treatment",
                entity_id=record_id,
            )
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})
