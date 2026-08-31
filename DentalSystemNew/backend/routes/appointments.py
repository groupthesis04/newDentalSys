from __future__ import annotations

import datetime as dt
import json
from http import HTTPStatus
from ..core import (
    DATA_LOCK,
    find_appointment,
    load_data,
    make_id,
    parse_date,
    save_data,
    utc_now,
    validate_identifier,
    validate_person_name,
)
from .availability import validate_availability_time
from ..notifications import add_notification, notify_doctors


class AppointmentRoutes:
    def list_appointments(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            if user["role"] == "doctor":
                appointments = data["appointments"]
            else:
                appointments = [
                    item for item in data["appointments"] if item["patient_id"] == user["id"]
                ]
            appointments = sorted(
                appointments,
                key=lambda item: (
                    item.get("created_at", ""),
                    item.get("date", ""),
                    item.get("time", ""),
                ),
                reverse=True,
            )
        self.send_json(HTTPStatus.OK, {"appointments": appointments})

    def create_appointment(self, payload: dict) -> None:
        doctor = str(payload.get("doctor", "")).strip()
        service = str(payload.get("service", "")).strip()
        notes = str(payload.get("notes", "")).strip()

        if not doctor or not service:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Complete the appointment details.")
            return
        try:
            doctor = validate_person_name(doctor, "dentist", minimum=3)
            appointment_date = parse_date(payload.get("date", ""), "appointment date", required=True)
            appointment_time = validate_availability_time(payload.get("time"))
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        appointment_day = dt.date.fromisoformat(appointment_date)
        if appointment_day < dt.date.today():
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Appointment date cannot be in the past.")
            return
        if appointment_day > dt.date.today() + dt.timedelta(days=365):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Appointment date must be within one year.")
            return
        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            if user["role"] != "patient":
                self.send_error_json(HTTPStatus.FORBIDDEN, "Only patient accounts can book appointments.")
                return
            if not any(item.get("name", "").casefold() == service.casefold() for item in data["services"]):
                self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid dental service.")
                return
            is_available = any(
                item.get("doctor", "").casefold() == doctor.casefold()
                and item.get("date") == appointment_date
                and item.get("time") == appointment_time
                for item in data["availability"]
            )
            if not is_available:
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "That dentist, date, and time are not available. Choose a clinic-approved slot.",
                )
                return
            slot_taken = any(
                appointment["doctor"].casefold() == doctor.casefold()
                and appointment["date"] == appointment_date
                and appointment["time"] == appointment_time
                and appointment["status"] in {"approved", "completed"}
                for appointment in data["appointments"]
            )
            if slot_taken:
                self.send_error_json(HTTPStatus.CONFLICT, "That doctor and time slot are already booked.")
                return
            duplicate_request = any(
                appointment.get("patient_id") == user["id"]
                and appointment.get("doctor", "").casefold() == doctor.casefold()
                and appointment.get("date") == appointment_date
                and appointment.get("time") == appointment_time
                and appointment.get("status") in {"pending", "approved"}
                for appointment in data["appointments"]
            )
            if duplicate_request:
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "You already requested this dentist, date, and time.",
                )
                return
            appointment = {
                "id": make_id("apt"),
                "patient_id": user["id"],
                "patient_name": user["name"],
                "patient_email": user["email"],
                "patient_phone": user.get("phone", ""),
                "doctor": doctor,
                "service": service,
                "date": appointment_date,
                "time": appointment_time,
                "notes": notes,
                "status": "pending",
                "created_at": utc_now(),
                "updated_at": utc_now(),
            }
            data["appointments"].append(appointment)
            add_notification(
                data,
                user["id"],
                "appointment_created",
                "Appointment request submitted",
                f"{service} with {doctor} on {appointment_date} at {appointment_time} is pending approval.",
                entity_type="appointment",
                entity_id=appointment["id"],
            )
            notify_doctors(
                data,
                "appointment_created",
                "New appointment request",
                f"{user['name']} requested {service} on {appointment_date} at {appointment_time}.",
                entity_type="appointment",
                entity_id=appointment["id"],
            )
            save_data(data)
        self.send_json(HTTPStatus.CREATED, {"appointment": appointment})

    def update_appointment(self) -> None:
        try:
            payload = self.read_json()
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        appointment_id = str(payload.get("id", "")).strip()
        status = str(payload.get("status", "")).strip().lower()
        allowed_statuses = {"pending", "approved", "completed", "cancelled"}
        try:
            appointment_id = validate_identifier(appointment_id, "appointment")
        except ValueError as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return
        if status not in allowed_statuses:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Choose a valid status.")
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_user(data)
            if not user:
                return
            appointment = find_appointment(data, appointment_id)
            if not appointment:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Appointment not found.")
                return
            if user["role"] == "patient":
                if appointment["patient_id"] != user["id"] or status != "cancelled":
                    self.send_error_json(HTTPStatus.FORBIDDEN, "Patients can only cancel their own appointment.")
                    return
            elif user["role"] != "doctor":
                self.send_error_json(HTTPStatus.FORBIDDEN, "Unauthorized appointment update.")
                return
            if user["role"] == "doctor" and status in {"approved", "completed"}:
                competing_booking = next(
                    (
                        item
                        for item in data["appointments"]
                        if item.get("id") != appointment_id
                        and item.get("doctor", "").casefold()
                        == appointment.get("doctor", "").casefold()
                        and item.get("date") == appointment.get("date")
                        and item.get("time") == appointment.get("time")
                        and item.get("status") in {"approved", "completed"}
                    ),
                    None,
                )
                if competing_booking:
                    self.send_error_json(
                        HTTPStatus.CONFLICT,
                        "Another appointment has already been accepted for this dentist and time.",
                    )
                    return
            previous_status = appointment.get("status", "pending")
            appointment["status"] = status
            appointment["updated_at"] = utc_now()
            cancelled_ids = []
            if user["role"] == "doctor" and status == "approved":
                for item in data["appointments"]:
                    if (
                        item.get("id") != appointment_id
                        and item.get("doctor", "").casefold()
                        == appointment.get("doctor", "").casefold()
                        and item.get("date") == appointment.get("date")
                        and item.get("time") == appointment.get("time")
                        and item.get("status") == "pending"
                    ):
                        item["status"] = "cancelled"
                        item["updated_at"] = utc_now()
                        cancelled_ids.append(item["id"])
                        add_notification(
                            data,
                            item["patient_id"],
                            "appointment_status",
                            "Appointment cancelled",
                            f"{item.get('service', 'Appointment')} on {item.get('date', '')} at {item.get('time', '')} was cancelled because the slot was assigned to another request.",
                            entity_type="appointment",
                            entity_id=item["id"],
                        )
            if status != previous_status:
                status_labels = {
                    "pending": "Pending",
                    "approved": "Accepted",
                    "completed": "Completed",
                    "cancelled": "Cancelled",
                }
                status_label = status_labels[status]
                add_notification(
                    data,
                    appointment["patient_id"],
                    "appointment_status",
                    f"Appointment {status_label.lower()}",
                    f"{appointment.get('service', 'Appointment')} with {appointment.get('doctor', 'the dentist')} on {appointment.get('date', '')} at {appointment.get('time', '')} is now {status_label}.",
                    entity_type="appointment",
                    entity_id=appointment["id"],
                )
                notify_doctors(
                    data,
                    "appointment_status",
                    "Appointment status updated",
                    f"{appointment.get('patient_name', 'Patient')}'s {appointment.get('service', 'appointment')} is now {status_label}.",
                    entity_type="appointment",
                    entity_id=appointment["id"],
                )
            save_data(data)
        self.send_json(
            HTTPStatus.OK,
            {"appointment": appointment, "cancelled_appointment_ids": cancelled_ids},
        )
