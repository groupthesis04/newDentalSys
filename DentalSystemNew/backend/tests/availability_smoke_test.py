from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from backend import core  # Loads the project environment.
from backend.mysql_store import MySQLStore


def client():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
    )


def request(opener, base_url: str, path: str, method: str = "GET", payload=None, csrf: str = ""):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json", "X-Requested-With": "DentalSystem"}
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Origin"] = base_url
    if csrf:
        headers["X-CSRF-Token"] = csrf
    target = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        response = opener.open(target, timeout=10)
        return response.status, json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def expect(status: int, expected: int, label: str) -> None:
    if status != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, received HTTP {status}")


def cleanup(emails: set[str], doctor_name: str) -> None:
    store = MySQLStore()
    store.initialize()
    data = store.load()
    user_ids = {
        user.get("id")
        for user in data["users"]
        if user.get("email", "").casefold() in {email.casefold() for email in emails}
    }
    related_entity_ids = {
        item.get("id")
        for item in [*data.get("appointments", []), *data.get("records", [])]
        if item.get("patient_id") in user_ids
    }
    data["users"] = [user for user in data["users"] if user.get("id") not in user_ids]
    data["appointments"] = [
        item
        for item in data["appointments"]
        if item.get("patient_id") not in user_ids
        and item.get("patient_email", "").casefold() not in {email.casefold() for email in emails}
    ]
    data["records"] = [item for item in data["records"] if item.get("patient_id") not in user_ids]
    data["messages"] = [
        item
        for item in data["messages"]
        if item.get("sender_id") not in user_ids and item.get("recipient_id") not in user_ids
    ]
    data["notifications"] = [
        item
        for item in data.get("notifications", [])
        if item.get("recipient_id") not in user_ids
        and item.get("entity_id") not in related_entity_ids
    ]
    data["availability"] = [
        item for item in data["availability"] if item.get("doctor") != doctor_name
    ]
    store.save(data)


def main() -> None:
    parser = argparse.ArgumentParser(description="Verify admin-controlled appointment availability")
    parser.add_argument("--url", default="http://127.0.0.1:8123")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")
    suffix = int(time.time())
    email = f"availability.patient.{suffix}@example.test"
    competing_email = f"availability.competing.{suffix}@example.test"
    doctor_email = f"availability.doctor.{suffix}@example.test"
    doctor_name = "Dr. Availability QA"
    slot_date = (date.today() + timedelta(days=120)).isoformat()
    batch_start = (date.today() + timedelta(days=180)).replace(day=5)
    batch_dates = [batch_start.isoformat(), (batch_start + timedelta(days=1)).isoformat()]
    original_time = "16:17"
    updated_time = "16:23"

    try:
        doctor = client()
        status, logged_in = request(
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
        doctor_csrf = logged_in["csrf_token"]

        status, created = request(
            doctor,
            base_url,
            "/api/availability",
            "POST",
            {"doctor": "Dr. Ignored Client Value", "date": slot_date, "time": original_time, "_website": ""},
            doctor_csrf,
        )
        expect(status, 201, "availability creation")
        if created["availability"].get("doctor") != doctor_name:
            raise AssertionError("availability was not assigned to the authenticated clinic doctor")
        availability_id = created["availability"]["id"]

        patient = client()
        status, registered = request(
            patient,
            base_url,
            "/api/register",
            "POST",
            {
                "name": "Availability Test Patient",
                "phone": "09171234567",
                "email": email,
                "password": "StrongPass123!",
                "role": "patient",
                "_website": "",
            },
        )
        expect(status, 201, "patient registration")
        patient_csrf = registered["csrf_token"]

        status, available = request(patient, base_url, "/api/availability")
        expect(status, 200, "patient availability list")
        if not any(item["id"] == availability_id for item in available["availability"]):
            raise AssertionError("new admin availability was not visible to the patient")

        status, services = request(patient, base_url, "/api/services")
        expect(status, 200, "service list")
        service_name = services["services"][0]["name"]
        status, booked = request(
            patient,
            base_url,
            "/api/appointments",
            "POST",
            {
                "doctor": doctor_name,
                "service": service_name,
                "date": slot_date,
                "time": original_time,
                "notes": "Availability integration test",
                "_website": "",
            },
            patient_csrf,
        )
        expect(status, 201, "appointment booking")
        appointment_id = booked["appointment"]["id"]

        competing_patient = client()
        status, competing_registered = request(
            competing_patient,
            base_url,
            "/api/register",
            "POST",
            {
                "name": "Competing Test Patient",
                "phone": "09171234569",
                "email": competing_email,
                "password": "StrongPass123!",
                "role": "patient",
                "_website": "",
            },
        )
        expect(status, 201, "competing patient registration")
        competing_csrf = competing_registered["csrf_token"]
        status, competing_booking = request(
            competing_patient,
            base_url,
            "/api/appointments",
            "POST",
            {
                "doctor": doctor_name,
                "service": service_name,
                "date": slot_date,
                "time": original_time,
                "notes": "Competing availability integration test",
                "_website": "",
            },
            competing_csrf,
        )
        expect(status, 201, "competing appointment booking")
        competing_appointment_id = competing_booking["appointment"]["id"]

        status, available = request(patient, base_url, "/api/availability")
        expect(status, 200, "pending availability list")
        if not any(item["id"] == availability_id for item in available["availability"]):
            raise AssertionError("a pending request incorrectly closed the slot")

        status, doctor_availability = request(doctor, base_url, "/api/availability")
        expect(status, 200, "doctor pending availability list")
        pending_slot = next(
            item for item in doctor_availability["availability"] if item["id"] == availability_id
        )
        if pending_slot["booked"] or pending_slot["pending_count"] != 2:
            raise AssertionError("pending appointment requests were not counted correctly")

        status, accepted = request(
            doctor,
            base_url,
            "/api/appointments",
            "PATCH",
            {"id": appointment_id, "status": "approved"},
            doctor_csrf,
        )
        expect(status, 200, "appointment acceptance")
        if competing_appointment_id not in accepted.get("cancelled_appointment_ids", []):
            raise AssertionError("accepting a request did not cancel the competing pending request")

        status, available = request(patient, base_url, "/api/availability")
        expect(status, 200, "accepted availability list")
        if any(item["id"] == availability_id for item in available["availability"]):
            raise AssertionError("accepted availability remained visible to the patient")

        status, appointments = request(doctor, base_url, "/api/appointments")
        expect(status, 200, "appointment status list")
        competing_status = next(
            item["status"]
            for item in appointments["appointments"]
            if item["id"] == competing_appointment_id
        )
        if competing_status != "cancelled":
            raise AssertionError("the competing appointment was not cancelled")

        status, _ = request(
            doctor,
            base_url,
            "/api/availability",
            "DELETE",
            {"id": availability_id},
            doctor_csrf,
        )
        expect(status, 409, "booked availability deletion protection")

        status, _ = request(
            patient,
            base_url,
            "/api/appointments",
            "PATCH",
            {"id": appointment_id, "status": "cancelled"},
            patient_csrf,
        )
        expect(status, 200, "appointment cancellation")

        status, available = request(patient, base_url, "/api/availability")
        expect(status, 200, "reopened availability list")
        if not any(item["id"] == availability_id for item in available["availability"]):
            raise AssertionError("cancelled appointment did not reopen its availability")

        status, updated = request(
            doctor,
            base_url,
            "/api/availability",
            "PATCH",
            {"id": availability_id, "doctor": doctor_name, "date": slot_date, "time": updated_time},
            doctor_csrf,
        )
        expect(status, 200, "availability update")
        if updated["availability"]["time"] != updated_time:
            raise AssertionError("availability time was not updated")

        status, _ = request(
            doctor,
            base_url,
            "/api/availability",
            "DELETE",
            {"id": availability_id},
            doctor_csrf,
        )
        expect(status, 200, "availability deletion")

        status, batch = request(
            doctor,
            base_url,
            "/api/availability",
            "POST",
            {
                "doctor": doctor_name,
                "dates": ",".join(batch_dates),
                "time_in": "08:00",
                "time_out": "10:00",
                "interval": "30",
                "_website": "",
            },
            doctor_csrf,
        )
        expect(status, 201, "monthly availability batch creation")
        if batch.get("created_count") != 8 or len(batch.get("availability_created", [])) != 8:
            raise AssertionError("batch schedule did not create four time slots for each selected date")
        print("Availability smoke checks passed.")
    finally:
        cleanup({email, competing_email, doctor_email}, doctor_name)


if __name__ == "__main__":
    main()
