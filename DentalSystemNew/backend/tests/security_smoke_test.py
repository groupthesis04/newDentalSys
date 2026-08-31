from __future__ import annotations

import argparse
import http.cookiejar
import json
import os
import time
import urllib.error
import urllib.request
from datetime import date


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
    req = urllib.request.Request(base_url + path, data=body, headers=headers, method=method)
    try:
        response = opener.open(req, timeout=10)
        return response.status, dict(response.headers), json.loads(response.read() or b"{}")
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), json.loads(error.read() or b"{}")


def expect_status(actual: int, expected: int, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected HTTP {expected}, received HTTP {actual}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Dental System security smoke checks")
    parser.add_argument("--url", default="http://127.0.0.1:8130")
    args = parser.parse_args()
    base_url = args.url.rstrip("/")

    public = client()
    status, headers, session = request(public, base_url, "/api/session")
    expect_status(status, 200, "public session")
    required_headers = {
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Content-Security-Policy",
        "Permissions-Policy",
    }
    missing = sorted(header for header in required_headers if header not in headers)
    if missing:
        raise AssertionError(f"missing security headers: {', '.join(missing)}")
    if session.get("authenticated"):
        raise AssertionError("fresh client must not be authenticated")

    status, _, _ = request(
        public,
        base_url,
        "/api/feedback",
        "POST",
        {"name": "Bot", "rating": "5", "message": "Automated submission text", "_website": "https://spam.invalid"},
    )
    expect_status(status, 400, "honeypot rejection")

    status, _, _ = request(
        public,
        base_url,
        "/api/feedback",
        "POST",
        {"name": "Visitor", "rating": "5", "message": "<script>alert(1)</script>"},
    )
    expect_status(status, 400, "HTML input rejection")

    suffix = int(time.time())
    registration = client()
    status, _, registered = request(
        registration,
        base_url,
        "/api/register",
        "POST",
        {
            "name": "Security Test Patient",
            "phone": "09171234567",
            "email": f"security.patient.{suffix}@example.test",
            "password": "StrongPass123!",
            "role": "patient",
            "_website": "",
        },
    )
    expect_status(status, 201, "secure registration")
    if not registered.get("csrf_token"):
        raise AssertionError("registration must return a CSRF token")

    doctor = client()
    status, _, logged_in = request(
        doctor,
        base_url,
        "/api/login",
        "POST",
        {
            "email": os.environ.get("DRMS_TEST_DOCTOR_EMAIL", "admin@dental.local"),
            "password": os.environ["DRMS_TEST_DOCTOR_PASSWORD"],
            "_website": "",
        },
    )
    expect_status(status, 200, "doctor login")
    csrf = logged_in.get("csrf_token", "")
    if not csrf:
        raise AssertionError("login must return a CSRF token")

    status, _, _ = request(
        doctor,
        base_url,
        "/api/profile",
        "PATCH",
        {"name": "Clinic Administrator", "email": "admin@dental.local", "phone": ""},
    )
    expect_status(status, 403, "CSRF rejection")

    status, _, patient_response = request(
        doctor,
        base_url,
        "/api/patients",
        "POST",
        {
            "first_name": "Security",
            "middle_name": "",
            "last_name": "Patient",
            "birthdate": "1990-01-01",
            "address": "123 Test Street",
            "nationality": "Filipino",
            "occupation": "Tester",
            "phone_number": "",
            "mobile_number": "09171234567",
            "email": f"record.patient.{suffix}@example.test",
            "notes": "Created by the security smoke test.",
            "_website": "",
        },
        csrf,
    )
    expect_status(status, 201, "patient creation")
    patient_id = patient_response["patient"]["id"]

    status, _, record_response = request(
        doctor,
        base_url,
        "/api/records",
        "POST",
        {
            "patient_id": patient_id,
            "appointment_id": "",
            "treatment_date": date.today().isoformat(),
            "tooth_numbers": "11, 12",
            "procedure": "Oral Prophylaxis",
            "treatment": "Oral Prophylaxis",
            "diagnosis": "Oral Prophylaxis",
            "amount_charged": "1000",
            "amount_paid": "250",
            "remarks": "Security smoke test treatment.",
            "_website": "",
        },
        csrf,
    )
    expect_status(status, 201, "treatment creation")
    if record_response["record"].get("balance") != 750.0:
        raise AssertionError("treatment balance was not calculated by the server")

    status, _, _ = request(
        doctor, base_url, "/api/patients", "DELETE", {"id": patient_id}, csrf
    )
    expect_status(status, 200, "patient cleanup")

    limited = False
    for _ in range(6):
        status, headers, _ = request(
            client(),
            base_url,
            "/api/login",
            "POST",
            {"email": "nobody@example.test", "password": "WrongPassword1!", "_website": ""},
        )
        if status == 429:
            limited = True
            if "Retry-After" not in headers:
                raise AssertionError("rate-limited response must include Retry-After")
            break
    if not limited:
        raise AssertionError("login rate limit did not activate")

    print("Security smoke checks passed.")


if __name__ == "__main__":
    main()
