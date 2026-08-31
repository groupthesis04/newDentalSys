from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import math
import os
import re
import secrets
import threading
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

from .mysql_store import MySQLStore


BACKEND_DIR = Path(__file__).resolve().parent
BASE_DIR = BACKEND_DIR.parent
PUBLIC_DIR = BASE_DIR / "frontend"
DATABASE_DIR = BASE_DIR / "database"


def load_environment_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_environment_file(BACKEND_DIR / ".env")

configured_data_file = os.environ.get("DRMS_DATA_FILE")
DATA_FILE = (
    Path(configured_data_file)
    if configured_data_file
    else DATABASE_DIR / "data" / "app_data.json"
)
if not DATA_FILE.is_absolute():
    DATA_FILE = BASE_DIR / DATA_FILE
SESSION_COOKIE = "drms_session"
SESSION_STORE: dict[str, dict[str, object]] = {}
SESSION_LOCK = threading.Lock()
DATA_LOCK = threading.Lock()
DATA_STORE: MySQLStore | None = None
STAFF_ACCESS_CODE = os.environ.get("DRMS_STAFF_CODE", "")
COOKIE_SECURE = os.environ.get("DRMS_COOKIE_SECURE", "0") == "1"
SESSION_TTL_SECONDS = 12 * 60 * 60
REMEMBER_SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
MAX_REQUEST_BYTES = 3_000_000

EMAIL_PATTERN = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,63}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z][a-z0-9]*_[A-Za-z0-9_-]{1,48}$")
HTML_TAG_PATTERN = re.compile(r"<\s*/?\s*[A-Za-z][^>]*>")
PHONE_PATTERN = re.compile(r"^[0-9+() .-]{7,24}$")
TOOTH_PATTERN = re.compile(r"^[0-9#,.\-\s/]{1,120}$")
SENSITIVE_FIELDS = {"password", "staff_code"}
MULTILINE_FIELDS = {
    "address", "notes", "message", "body", "description", "diagnosis",
    "prescription", "remarks",
}
FIELD_LIMITS = {
    "id": 64,
    "patient_id": 64,
    "appointment_id": 64,
    "recipient_id": 64,
    "name": 120,
    "first_name": 80,
    "middle_name": 80,
    "last_name": 80,
    "email": 254,
    "phone": 24,
    "phone_number": 24,
    "mobile_number": 24,
    "sex": 24,
    "birthdate": 10,
    "age": 3,
    "address": 300,
    "nationality": 80,
    "occupation": 120,
    "notes": 1000,
    "profile_image": 2_500_000,
    "password": 128,
    "role": 16,
    "staff_code": 256,
    "remember": 8,
    "service": 120,
    "doctor": 120,
    "date": 10,
    "dates": 340,
    "time": 8,
    "time_in": 8,
    "time_out": 8,
    "interval": 3,
    "rating": 1,
    "message": 1000,
    "body": 1000,
    "treatment_date": 10,
    "tooth_numbers": 120,
    "procedure": 120,
    "amount_charged": 20,
    "amount_paid": 20,
    "diagnosis": 700,
    "treatment": 700,
    "prescription": 700,
    "remarks": 1000,
    "next_visit": 10,
    "status": 24,
    "title": 120,
    "description": 500,
    "mark_all": 5,
    "_website": 200,
}
ALLOWED_PAYLOAD_FIELDS = frozenset(FIELD_LIMITS)


class RateLimiter:
    def __init__(self) -> None:
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window_seconds: int) -> int:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                return max(1, int(window_seconds - (now - events[0])) + 1)
            events.append(now)
            if len(self._events) > 10_000:
                stale = [bucket for bucket, values in self._events.items() if not values or values[-1] <= cutoff]
                for bucket in stale[:1000]:
                    self._events.pop(bucket, None)
        return 0


RATE_LIMITER = RateLimiter()

DEFAULT_SERVICES = [
    {
        "id": "svc_oral_prophylaxis",
        "name": "Oral Prophylaxis",
        "description": "Routine cleaning and plaque removal for healthier gums.",
    },
    {
        "id": "svc_extraction",
        "name": "Tooth Extraction",
        "description": "Assessment and safe tooth removal when needed.",
    },
    {
        "id": "svc_dental_filling",
        "name": "Dental Filling",
        "description": "Tooth-colored or restorative fillings for cavities and minor damage.",
    },
    {
        "id": "svc_root_canal_treatment",
        "name": "Root Canal Treatment",
        "description": "Treatment for infected pulp while preserving the tooth.",
    },
    {
        "id": "svc_dental_crown",
        "name": "Dental Crown",
        "description": "Crown restoration for damaged or weakened teeth.",
    },
    {
        "id": "svc_dental_bridge",
        "name": "Dental Bridge",
        "description": "Fixed bridge treatment for replacing missing teeth.",
    },
    {
        "id": "svc_dentures",
        "name": "Dentures",
        "description": "Partial and complete denture services.",
    },
    {
        "id": "svc_orthodontics_braces",
        "name": "Orthodontics (Braces)",
        "description": "Orthodontic evaluation, adjustment, and braces treatment planning.",
    },
    {
        "id": "svc_teeth_whitening",
        "name": "Teeth Whitening",
        "description": "Cosmetic whitening options for a brighter smile.",
    },
    {
        "id": "svc_dental_xray",
        "name": "Dental X-ray",
        "description": "Dental imaging to support diagnosis and treatment planning.",
    },
    {
        "id": "svc_consultation",
        "name": "Consultation",
        "description": "General dental consultation and care planning.",
    },
    {
        "id": "svc_fluoride_treatment",
        "name": "Fluoride Treatment",
        "description": "Preventive fluoride care for stronger tooth enamel.",
    },
    {
        "id": "svc_dental_sealants",
        "name": "Dental Sealants",
        "description": "Protective sealants for cavity prevention.",
    },
    {
        "id": "svc_others",
        "name": "Others",
        "description": "Other dental procedures and clinic services.",
    },
]

DEFAULT_PROMOS = [
    {
        "id": "promo_new_patient",
        "title": "New Patient Starter",
        "description": "Free dental assessment with your first cleaning appointment.",
    },
    {
        "id": "promo_family_smile",
        "title": "Family Smile Day",
        "description": "Save 15% when three or more family members book checkups.",
    },
    {
        "id": "promo_whitening_bundle",
        "title": "Whitening Bundle",
        "description": "Consultation plus whitening plan at a reduced package rate.",
    },
]


def reject_duplicate_json_keys(pairs: list[tuple[str, object]]) -> dict:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON field: {key}.")
        result[key] = value
    return result


def sanitize_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise ValueError("The request body must be a JSON object.")
    if len(payload) > 40:
        raise ValueError("The request contains too many fields.")

    sanitized: dict[str, object] = {}
    for key, value in payload.items():
        if key not in ALLOWED_PAYLOAD_FIELDS:
            raise ValueError(f"Unexpected field: {key}.")
        if value is None:
            sanitized[key] = ""
            continue
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError(f"{key.replace('_', ' ').title()} has an invalid value.")

        text = str(value)
        limit = FIELD_LIMITS[key]
        if len(text) > limit:
            raise ValueError(f"{key.replace('_', ' ').title()} is too long.")
        if "\x00" in text:
            raise ValueError("Null characters are not allowed.")
        if key in SENSITIVE_FIELDS:
            sanitized[key] = text
            continue
        if key == "profile_image":
            sanitized[key] = text.strip()
            continue

        text = unicodedata.normalize("NFKC", text)
        allowed_controls = {"\n", "\r", "\t"} if key in MULTILINE_FIELDS else set()
        text = "".join(
            character
            for character in text
            if ord(character) >= 32 or character in allowed_controls
        )
        if key in MULTILINE_FIELDS:
            text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
        else:
            text = re.sub(r"\s+", " ", text).strip()
        if key != "_website" and HTML_TAG_PATTERN.search(text):
            raise ValueError(f"HTML is not allowed in {key.replace('_', ' ')}.")
        sanitized[key] = text
    return sanitized


def validate_email(value: object) -> str:
    email = str(value or "").strip().lower()
    if len(email) > 254 or not EMAIL_PATTERN.fullmatch(email):
        raise ValueError("Enter a valid email address.")
    return email


def validate_person_name(value: object, label: str = "name", minimum: int = 2) -> str:
    name = re.sub(r"\s+", " ", str(value or "").strip())
    if len(name) < minimum or len(name) > 120 or not any(character.isalpha() for character in name):
        raise ValueError(f"Enter a complete {label}.")
    if any(character.isdigit() for character in name):
        raise ValueError(f"The {label} cannot contain numbers.")
    return name


def validate_phone(value: object, required: bool = False) -> str:
    phone = str(value or "").strip()
    if not phone and not required:
        return ""
    if not PHONE_PATTERN.fullmatch(phone):
        raise ValueError("Enter a valid phone or mobile number.")
    digits = re.sub(r"\D", "", phone)
    if not 7 <= len(digits) <= 15:
        raise ValueError("Enter a valid phone or mobile number.")
    return phone


def validate_password_strength(password: object) -> str:
    value = str(password or "")
    if len(value) < 10:
        raise ValueError("Password must be at least 10 characters.")
    if len(value) > 128:
        raise ValueError("Password must be 128 characters or fewer.")
    requirements = (
        any(character.islower() for character in value),
        any(character.isupper() for character in value),
        any(character.isdigit() for character in value),
        any(not character.isalnum() for character in value),
    )
    if not all(requirements):
        raise ValueError("Password must include uppercase, lowercase, number, and symbol characters.")
    return value


def validate_identifier(value: object, label: str = "item") -> str:
    identifier = str(value or "").strip()
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ValueError(f"Choose a valid {label}.")
    return identifier


def validate_tooth_numbers(value: object) -> str:
    tooth_numbers = str(value or "").strip()
    if not TOOTH_PATTERN.fullmatch(tooth_numbers):
        raise ValueError("Enter valid tooth numbers using numbers, commas, spaces, #, /, or hyphens.")
    numbers = [int(number) for number in re.findall(r"\d+", tooth_numbers)]
    if not numbers or any(number < 1 or number > 85 for number in numbers):
        raise ValueError("Enter valid tooth numbers between 1 and 85.")
    return tooth_numbers


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def make_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(6)}"


def default_services() -> list[dict]:
    now = utc_now()
    return [{**service, "created_at": now, "updated_at": now} for service in DEFAULT_SERVICES]


def default_promos() -> list[dict]:
    now = utc_now()
    return [{**promo, "created_at": now, "updated_at": now} for promo in DEFAULT_PROMOS]


def parse_date(value: object, label: str = "date", required: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        if required:
            raise ValueError(f"Enter a valid {label}.")
        return ""
    for date_format in ("%Y-%m-%d", "%m/%d/%Y"):
        try:
            return dt.datetime.strptime(text, date_format).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Enter a valid {label}.")


def validate_birthdate(value: object) -> str:
    birthdate = parse_date(value, "birthdate", required=True)
    born = dt.date.fromisoformat(birthdate)
    today = dt.date.today()
    if born > today:
        raise ValueError("Birthdate cannot be in the future.")
    if calculate_age(birthdate) > 130:
        raise ValueError("Birthdate must be within the last 130 years.")
    return birthdate


def calculate_age(birthdate: str) -> int | str:
    if not birthdate:
        return ""
    born = dt.date.fromisoformat(birthdate)
    today = dt.date.today()
    return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


def parse_money(value: object, label: str) -> float:
    try:
        amount = round(float(str(value or "0").replace(",", "").strip() or 0), 2)
    except ValueError as error:
        raise ValueError(f"{label} must be a valid amount.") from error
    if not math.isfinite(amount):
        raise ValueError(f"{label} must be a finite amount.")
    if amount < 0:
        raise ValueError(f"{label} cannot be negative.")
    if amount > 100_000_000:
        raise ValueError(f"{label} is too large.")
    return amount


def normalize_money(value: object) -> float:
    try:
        return round(float(value or 0), 2)
    except (TypeError, ValueError):
        return 0.0


def split_name(name: str) -> tuple[str, str, str]:
    parts = [part for part in str(name or "").strip().split() if part]
    if not parts:
        return "", "", ""
    if len(parts) == 1:
        return parts[0], "", ""
    if len(parts) == 2:
        return parts[1], parts[0], ""
    return parts[-1], parts[0], " ".join(parts[1:-1])


def patient_full_name(profile: dict) -> str:
    existing = str(profile.get("name", "")).strip()
    first = str(profile.get("first_name", "")).strip()
    middle = str(profile.get("middle_name", "")).strip()
    last = str(profile.get("last_name", "")).strip()
    full = " ".join(part for part in (first, middle, last) if part)
    return full or existing


def normalize_patient_identity(name: str, birthdate: str) -> tuple[str, str]:
    compact_name = re.sub(r"\s+", " ", str(name or "").strip()).lower()
    return compact_name, str(birthdate or "").strip()


def treatment_balance(record: dict) -> float:
    charged = normalize_money(record.get("amount_charged"))
    paid = normalize_money(record.get("amount_paid"))
    return round(charged - paid, 2)


def payment_status(balance: float) -> str:
    return "completed" if balance <= 0 else "unpaid"


def hash_password(password: str) -> str:
    iterations = 600_000
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), iterations
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${digest}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iteration_text, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt),
            int(iteration_text),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = hash_password("InvalidPassword1!")


def public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "phone": user.get("phone", ""),
        "role": user["role"],
        "profile_image": user.get("profile_image", ""),
        "created_at": user.get("created_at", ""),
    }


def ensure_data_defaults(data: dict) -> bool:
    changed = False
    for key, default in (
        ("users", []),
        ("appointments", []),
        ("availability", []),
        ("records", []),
        ("patient_profiles", []),
        ("messages", []),
        ("notifications", []),
        ("feedback", []),
    ):
        if key not in data:
            data[key] = default
            changed = True
    if "services" not in data:
        data["services"] = default_services()
        changed = True
    else:
        existing_service_names = {
            service.get("name", "").strip().lower() for service in data.get("services", [])
        }
        for service in default_services():
            if service["name"].strip().lower() not in existing_service_names:
                data["services"].append(service)
                existing_service_names.add(service["name"].strip().lower())
                changed = True
    if "promos" not in data:
        data["promos"] = default_promos()
        changed = True
    else:
        existing_promo_titles = {
            promo.get("title", "").strip().lower() for promo in data.get("promos", [])
        }
        for promo in default_promos():
            if promo["title"].strip().lower() not in existing_promo_titles:
                data["promos"].append(promo)
                existing_promo_titles.add(promo["title"].strip().lower())
                changed = True
    return changed


def seed_data() -> dict:
    users = []
    seed_password = os.environ.get("DRMS_SEED_DOCTOR_PASSWORD", "")
    if seed_password:
        validate_password_strength(seed_password)
        users.append(
            {
                "id": "usr_doctor_seed",
                "name": os.environ.get("DRMS_SEED_DOCTOR_NAME", "Clinic Administrator"),
                "email": validate_email(
                    os.environ.get("DRMS_SEED_DOCTOR_EMAIL", "admin@dental.local")
                ),
                "phone": "",
                "role": "doctor",
                "password_hash": hash_password(seed_password),
                "created_at": utc_now(),
            }
        )
    return {
        "users": users,
        "appointments": [],
        "availability": [],
        "records": [],
        "patient_profiles": [],
        "messages": [],
        "notifications": [],
        "services": default_services(),
        "promos": default_promos(),
        "feedback": [
            {
                "id": "fb_seed_1",
                "name": "Arielle M.",
                "rating": 5,
                "message": "Clean clinic, calm dentist, and appointment updates were easy to follow.",
                "created_at": utc_now(),
            },
            {
                "id": "fb_seed_2",
                "name": "Marco L.",
                "rating": 5,
                "message": "My cleaning visit was organized from booking to follow-up records.",
                "created_at": utc_now(),
            },
        ],
    }


def load_data() -> dict:
    if DATA_STORE is not None:
        data = DATA_STORE.load()
        if ensure_data_defaults(data):
            DATA_STORE.save(data)
        return data
    if not DATA_FILE.exists():
        data = seed_data()
        save_data(data)
        return data
    with DATA_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if ensure_data_defaults(data):
        save_data(data)
    return data


def save_data(data: dict) -> None:
    if DATA_STORE is not None:
        DATA_STORE.save(data)
        return
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp_file = DATA_FILE.with_suffix(".tmp")
    with temp_file.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2)
    temp_file.replace(DATA_FILE)


def find_user_by_email(data: dict, email: str) -> dict | None:
    normalized = email.strip().lower()
    return next((user for user in data["users"] if user["email"] == normalized), None)


def find_user_by_id(data: dict, user_id: str) -> dict | None:
    return next((user for user in data["users"] if user["id"] == user_id), None)


def public_patient_profile(profile: dict) -> dict:
    last_name = str(profile.get("last_name", "")).strip()
    first_name = str(profile.get("first_name", "")).strip()
    middle_name = str(profile.get("middle_name", "")).strip()
    if not first_name and not last_name:
        last_name, first_name, middle_name = split_name(profile.get("name", ""))
    birthdate = profile.get("birthdate", "")
    age = calculate_age(birthdate) if birthdate else ""
    phone_number = profile.get("phone_number", profile.get("phone", ""))
    mobile_number = profile.get("mobile_number", profile.get("phone", ""))
    return {
        "id": profile["id"],
        "name": patient_full_name({**profile, "last_name": last_name, "first_name": first_name, "middle_name": middle_name}),
        "last_name": last_name,
        "first_name": first_name,
        "middle_name": middle_name,
        "email": profile.get("email", ""),
        "phone": mobile_number or phone_number,
        "phone_number": phone_number,
        "mobile_number": mobile_number,
        "role": "patient",
        "source": "record",
        "sex": profile.get("sex", ""),
        "birthdate": birthdate,
        "age": age,
        "address": profile.get("address", ""),
        "nationality": profile.get("nationality", ""),
        "occupation": profile.get("occupation", ""),
        "notes": profile.get("notes", ""),
        "created_at": profile.get("created_at", ""),
        "updated_at": profile.get("updated_at", ""),
    }


def find_patient_profile_by_id(data: dict, patient_id: str) -> dict | None:
    return next(
        (profile for profile in data.get("patient_profiles", []) if profile["id"] == patient_id),
        None,
    )


def find_patient_for_record(data: dict, patient_id: str) -> dict | None:
    user = find_user_by_id(data, patient_id)
    if user and user["role"] == "patient":
        patient = public_user(user)
        patient["source"] = "account"
        return patient
    profile = find_patient_profile_by_id(data, patient_id)
    return public_patient_profile(profile) if profile else None


def normalize_profile_image(value: object) -> str:
    image = str(value or "").strip()
    if not image:
        return ""
    if len(image) > 2_500_000:
        raise ValueError("Profile picture is too large.")
    if image.startswith("https://"):
        return image
    if re.match(r"^data:image/(png|jpeg|jpg|webp);base64,[A-Za-z0-9+/=\s]+$", image):
        return image
    raise ValueError("Use a PNG, JPG, WEBP image, or an HTTPS image URL.")


def find_appointment(data: dict, appointment_id: str) -> dict | None:
    return next(
        (
            appointment
            for appointment in data["appointments"]
            if appointment["id"] == appointment_id
        ),
        None,
    )


def find_record(data: dict, record_id: str) -> dict | None:
    return next(
        (record for record in data.get("records", []) if record["id"] == record_id),
        None,
    )
