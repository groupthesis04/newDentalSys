from __future__ import annotations

import datetime as dt
import json
import re
from http import HTTPStatus

from ..core import (
    DATA_LOCK,
    load_data,
    make_id,
    parse_date,
    save_data,
    utc_now,
    validate_identifier,
    validate_person_name,
)


TIME_PATTERN = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


def validate_availability_time(value: object) -> str:
    appointment_time = str(value or "").strip()
    if not TIME_PATTERN.fullmatch(appointment_time):
        raise ValueError("Choose a valid appointment time.")
    return appointment_time


def appointment_uses_slot(appointment: dict, slot: dict) -> bool:
    return (
        appointment.get("status") != "cancelled"
        and appointment.get("doctor", "").casefold() == slot.get("doctor", "").casefold()
        and appointment.get("date") == slot.get("date")
        and appointment.get("time") == slot.get("time")
    )


def appointment_reserves_slot(appointment: dict, slot: dict) -> bool:
    return appointment.get("status") in {"approved", "completed"} and appointment_uses_slot(
        appointment, slot
    )


def clinic_doctor_name(data: dict) -> str:
    doctor = next(
        (user for user in data.get("users", []) if user.get("role") == "doctor"),
        None,
    )
    return str(doctor.get("name", "")).strip() if doctor else ""


class AvailabilityRoutes:
    def list_availability(self) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.current_user(data)
            today = dt.date.today().isoformat()
            slots = [
                {
                    **slot,
                    "booked": any(
                        appointment_reserves_slot(item, slot) for item in data["appointments"]
                    ),
                    "pending_count": sum(
                        1
                        for item in data["appointments"]
                        if item.get("status") == "pending" and appointment_uses_slot(item, slot)
                    ),
                }
                for slot in data["availability"]
                if slot.get("date", "") >= today
            ]
            slots.sort(key=lambda item: (item.get("date", ""), item.get("time", ""), item.get("doctor", "")))
            if not user or user["role"] == "patient":
                slots = [slot for slot in slots if not slot["booked"]]
            clinic_doctor = clinic_doctor_name(data)
        self.send_json(
            HTTPStatus.OK,
            {"availability": slots, "clinic_doctor": clinic_doctor},
        )

    def create_availability(self, payload: dict) -> None:
        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            validated_payload = {**payload, "doctor": user["name"]}
            try:
                slots = (
                    self._validated_batch(validated_payload)
                    if validated_payload.get("dates")
                    else [self._validated_slot(validated_payload)]
                )
            except ValueError as error:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                return
            created = []
            skipped_count = 0
            now = utc_now()
            for slot in slots:
                if self._duplicate_slot(data, slot):
                    skipped_count += 1
                    continue
                availability = {
                    "id": make_id("avail"),
                    **slot,
                    "created_at": now,
                    "updated_at": now,
                }
                data["availability"].append(availability)
                created.append(availability)
            if not created:
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "All selected dentist, date, and time slots already exist.",
                )
                return
            save_data(data)
        self.send_json(
            HTTPStatus.CREATED,
            {
                "availability": created[0],
                "availability_created": created,
                "created_count": len(created),
                "skipped_count": skipped_count,
            },
        )

    def update_availability(self) -> None:
        try:
            payload = self.read_json()
            availability_id = validate_identifier(payload.get("id"), "availability")
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            try:
                slot_values = self._validated_slot({**payload, "doctor": user["name"]})
            except ValueError as error:
                self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
                return
            availability = next(
                (item for item in data["availability"] if item.get("id") == availability_id),
                None,
            )
            if not availability:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Availability not found.")
                return
            if any(appointment_uses_slot(item, availability) for item in data["appointments"]):
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "This availability has an appointment. Cancel or complete it before changing the slot.",
                )
                return
            if self._duplicate_slot(data, slot_values, exclude_id=availability_id):
                self.send_error_json(HTTPStatus.CONFLICT, "That dentist availability already exists.")
                return
            availability.update(slot_values)
            availability["updated_at"] = utc_now()
            save_data(data)
        self.send_json(HTTPStatus.OK, {"availability": availability})

    def delete_availability(self) -> None:
        try:
            payload = self.read_json()
            availability_id = validate_identifier(payload.get("id"), "availability")
        except (ValueError, json.JSONDecodeError) as error:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(error))
            return

        with DATA_LOCK:
            data = load_data()
            user = self.require_doctor(data)
            if not user:
                return
            availability = next(
                (item for item in data["availability"] if item.get("id") == availability_id),
                None,
            )
            if not availability:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Availability not found.")
                return
            if any(appointment_uses_slot(item, availability) for item in data["appointments"]):
                self.send_error_json(
                    HTTPStatus.CONFLICT,
                    "This availability has an appointment and cannot be deleted.",
                )
                return
            data["availability"] = [
                item for item in data["availability"] if item.get("id") != availability_id
            ]
            save_data(data)
        self.send_json(HTTPStatus.OK, {"ok": True})

    @staticmethod
    def _validated_slot(payload: dict) -> dict:
        doctor = validate_person_name(payload.get("doctor"), "dentist", minimum=3)
        availability_date = parse_date(payload.get("date"), "availability date", required=True)
        appointment_time = validate_availability_time(payload.get("time"))
        AvailabilityRoutes._validate_availability_date(availability_date)
        return {"doctor": doctor, "date": availability_date, "time": appointment_time}

    @staticmethod
    def _validate_availability_date(availability_date: str) -> None:
        day = dt.date.fromisoformat(availability_date)
        today = dt.date.today()
        if day < today:
            raise ValueError("Availability date cannot be in the past.")
        if day > today + dt.timedelta(days=365):
            raise ValueError("Availability date must be within one year.")

    @staticmethod
    def _validated_batch(payload: dict) -> list[dict]:
        doctor = validate_person_name(payload.get("doctor"), "dentist", minimum=3)
        raw_dates = str(payload.get("dates", "")).strip()
        dates = sorted(
            {
                parse_date(value, "availability date", required=True)
                for value in raw_dates.split(",")
                if value.strip()
            }
        )
        if not dates:
            raise ValueError("Select at least one available date.")
        if len(dates) > 31:
            raise ValueError("Select no more than 31 dates at a time.")
        if len({value[:7] for value in dates}) != 1:
            raise ValueError("Selected availability dates must be in the same month.")
        for availability_date in dates:
            AvailabilityRoutes._validate_availability_date(availability_date)

        time_in = validate_availability_time(payload.get("time_in"))
        time_out = validate_availability_time(payload.get("time_out"))
        try:
            interval = int(str(payload.get("interval", "30")).strip())
        except ValueError as error:
            raise ValueError("Choose a valid appointment interval.") from error
        if interval not in {15, 30, 60}:
            raise ValueError("Appointment interval must be 15, 30, or 60 minutes.")

        start_minutes = AvailabilityRoutes._time_minutes(time_in)
        end_minutes = AvailabilityRoutes._time_minutes(time_out)
        if end_minutes <= start_minutes:
            raise ValueError("Doctor time-out must be later than time-in.")
        times = []
        cursor = start_minutes
        while cursor + interval <= end_minutes:
            times.append(f"{cursor // 60:02d}:{cursor % 60:02d}")
            cursor += interval
        if not times:
            raise ValueError("The selected time range is shorter than the appointment interval.")
        if len(dates) * len(times) > 1000:
            raise ValueError("The selected schedule creates too many slots. Use a shorter range.")
        return [
            {"doctor": doctor, "date": availability_date, "time": appointment_time}
            for availability_date in dates
            for appointment_time in times
        ]

    @staticmethod
    def _time_minutes(value: str) -> int:
        hours, minutes = (int(part) for part in value.split(":"))
        return hours * 60 + minutes

    @staticmethod
    def _duplicate_slot(data: dict, slot: dict, exclude_id: str = "") -> bool:
        return any(
            item.get("id") != exclude_id
            and item.get("doctor", "").casefold() == slot["doctor"].casefold()
            and item.get("date") == slot["date"]
            and item.get("time") == slot["time"]
            for item in data["availability"]
        )
