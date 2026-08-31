from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import core  # Loads the project environment.
from backend.tests.availability_smoke_test import cleanup, client, expect, request


def find_notification(payload: dict, notification_type: str) -> dict:
    return next(
        (
            item
            for item in payload.get("notifications", [])
            if item.get("type") == notification_type
        ),
        {},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify transaction notifications")
    parser.add_argument("--url", default="http://127.0.0.1:8124")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    suffix = int(time.time())
    doctor_email = f"notification.doctor.{suffix}@example.test"
    patient_email = f"notification.patient.{suffix}@example.test"
    doctor_name = "Dr. Notification QA"
    emails = {doctor_email, patient_email}
    appointment_date = (date.today() + timedelta(days=45)).isoformat()
    appointment_time = "15:47"

    try:
        doctor = client()
        status, doctor_registration = request(
            doctor,
            base_url,
            "/api/register",
            "POST",
            {
                "name": doctor_name,
                "phone": "09171234568",
                "email": doctor_email,
                "password": "StrongPass123!",
                "role": "doctor",
                "staff_code": os.environ["DRMS_STAFF_CODE"],
                "_website": "",
            },
        )
        expect(status, 201, "doctor registration")
        doctor_csrf = doctor_registration["csrf_token"]

        patient = client()
        status, patient_registration = request(
            patient,
            base_url,
            "/api/register",
            "POST",
            {
                "name": "Notification Test Patient",
                "phone": "09171234567",
                "email": patient_email,
                "password": "StrongPass123!",
                "role": "patient",
                "_website": "",
            },
        )
        expect(status, 201, "patient registration")
        patient_csrf = patient_registration["csrf_token"]
        patient_id = patient_registration["user"]["id"]

        status, _ = request(
            doctor,
            base_url,
            "/api/availability",
            "POST",
            {
                "doctor": doctor_name,
                "date": appointment_date,
                "time": appointment_time,
                "_website": "",
            },
            doctor_csrf,
        )
        expect(status, 201, "availability creation")

        status, appointment_response = request(
            patient,
            base_url,
            "/api/appointments",
            "POST",
            {
                "doctor": doctor_name,
                "service": "Consultation",
                "date": appointment_date,
                "time": appointment_time,
                "notes": "Notification smoke test",
                "_website": "",
            },
            patient_csrf,
        )
        expect(status, 201, "appointment creation")
        appointment_id = appointment_response["appointment"]["id"]

        status, patient_notifications = request(patient, base_url, "/api/notifications")
        expect(status, 200, "patient notification list")
        patient_created = find_notification(patient_notifications, "appointment_created")
        if not patient_created or patient_notifications.get("unread_count") != 1:
            raise AssertionError("patient did not receive the appointment submission notification")

        status, doctor_notifications = request(doctor, base_url, "/api/notifications")
        expect(status, 200, "doctor notification list")
        doctor_created = find_notification(doctor_notifications, "appointment_created")
        if not doctor_created or doctor_notifications.get("unread_count") != 1:
            raise AssertionError("doctor did not receive the new appointment notification")

        status, _ = request(
            patient,
            base_url,
            "/api/notifications",
            "PATCH",
            {"id": doctor_created["id"]},
            patient_csrf,
        )
        expect(status, 404, "cross-account notification update")

        status, _ = request(
            doctor,
            base_url,
            "/api/appointments",
            "PATCH",
            {"id": appointment_id, "status": "approved"},
            doctor_csrf,
        )
        expect(status, 200, "appointment acceptance")

        status, patient_after_accept = request(patient, base_url, "/api/notifications")
        expect(status, 200, "patient accepted notification list")
        if not find_notification(patient_after_accept, "appointment_status"):
            raise AssertionError("patient did not receive the appointment status notification")

        status, _ = request(
            doctor,
            base_url,
            "/api/records",
            "POST",
            {
                "patient_id": patient_id,
                "appointment_id": appointment_id,
                "treatment_date": date.today().isoformat(),
                "tooth_numbers": "11",
                "procedure": "Consultation",
                "amount_charged": 500,
                "amount_paid": 200,
                "remarks": "Notification transaction test",
                "_website": "",
            },
            doctor_csrf,
        )
        expect(status, 201, "treatment creation")

        status, patient_after_treatment = request(patient, base_url, "/api/notifications")
        expect(status, 200, "patient treatment notification list")
        treatment_notice = find_notification(patient_after_treatment, "treatment_created")
        if not treatment_notice:
            raise AssertionError("patient did not receive the treatment transaction notification")

        unread_before = patient_after_treatment["unread_count"]
        status, marked = request(
            patient,
            base_url,
            "/api/notifications",
            "PATCH",
            {"id": treatment_notice["id"]},
            patient_csrf,
        )
        expect(status, 200, "single notification read")
        if marked.get("unread_count") != unread_before - 1:
            raise AssertionError("single notification did not reduce the unread count")

        status, marked_all = request(
            doctor,
            base_url,
            "/api/notifications",
            "PATCH",
            {"mark_all": True},
            doctor_csrf,
        )
        expect(status, 200, "mark all doctor notifications read")
        if marked_all.get("unread_count") != 0:
            raise AssertionError("doctor notifications were not all marked as read")

        print("Notification smoke checks passed.")
    finally:
        cleanup(emails, doctor_name)


if __name__ == "__main__":
    main()
