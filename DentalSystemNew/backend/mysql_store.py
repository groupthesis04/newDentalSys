from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any, Callable

import mysql.connector
from mysql.connector import Error as MySQLError


COLLECTIONS = (
    "users",
    "patient_profiles",
    "appointments",
    "availability",
    "records",
    "messages",
    "notifications",
    "services",
    "promos",
    "feedback",
)


SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS users (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        email VARCHAR(254) NOT NULL UNIQUE,
        phone VARCHAR(24) NOT NULL DEFAULT '',
        role ENUM('patient', 'doctor') NOT NULL,
        profile_image MEDIUMTEXT,
        password_hash VARCHAR(255) NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_users_role (role)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS patient_profiles (
        id VARCHAR(64) PRIMARY KEY,
        last_name VARCHAR(80) NOT NULL,
        first_name VARCHAR(80) NOT NULL,
        middle_name VARCHAR(80) NOT NULL DEFAULT '',
        email VARCHAR(254) NOT NULL,
        normalized_name VARCHAR(220) NOT NULL,
        birthdate DATE NOT NULL,
        age SMALLINT UNSIGNED,
        address VARCHAR(300) NOT NULL,
        nationality VARCHAR(80) NOT NULL,
        occupation VARCHAR(120) NOT NULL,
        phone_number VARCHAR(24) NOT NULL DEFAULT '',
        mobile_number VARCHAR(24) NOT NULL,
        notes TEXT,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        UNIQUE KEY uq_patient_identity (normalized_name, birthdate),
        INDEX idx_patient_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS appointments (
        id VARCHAR(64) PRIMARY KEY,
        patient_id VARCHAR(64) NOT NULL,
        patient_name VARCHAR(120) NOT NULL,
        patient_email VARCHAR(254) NOT NULL,
        patient_phone VARCHAR(24) NOT NULL DEFAULT '',
        doctor_name VARCHAR(120) NOT NULL,
        service VARCHAR(120) NOT NULL,
        appointment_date DATE NOT NULL,
        appointment_time TIME NOT NULL,
        status VARCHAR(24) NOT NULL,
        notes VARCHAR(500) NOT NULL DEFAULT '',
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_appointments_patient (patient_id),
        INDEX idx_appointments_slot (doctor_name, appointment_date, appointment_time),
        INDEX idx_appointments_status (status)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS availability (
        id VARCHAR(64) PRIMARY KEY,
        doctor_name VARCHAR(120) NOT NULL,
        availability_date DATE NOT NULL,
        availability_time TIME NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        UNIQUE KEY uq_availability_slot (doctor_name, availability_date, availability_time),
        INDEX idx_availability_date (availability_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS treatments (
        id VARCHAR(64) PRIMARY KEY,
        appointment_id VARCHAR(64) NOT NULL DEFAULT '',
        patient_id VARCHAR(64) NOT NULL,
        patient_name VARCHAR(120) NOT NULL,
        doctor_id VARCHAR(64) NOT NULL,
        doctor_name VARCHAR(120) NOT NULL,
        treatment_date DATE NOT NULL,
        tooth_numbers VARCHAR(120) NOT NULL,
        procedure_name VARCHAR(120) NOT NULL,
        amount_charged DECIMAL(12,2) NOT NULL DEFAULT 0,
        amount_paid DECIMAL(12,2) NOT NULL DEFAULT 0,
        balance DECIMAL(12,2) NOT NULL DEFAULT 0,
        payment_status VARCHAR(24) NOT NULL,
        diagnosis TEXT,
        prescription TEXT,
        remarks TEXT,
        next_visit DATE,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_treatments_patient (patient_id),
        INDEX idx_treatments_date (treatment_date),
        INDEX idx_treatments_procedure (procedure_name),
        INDEX idx_treatments_balance (balance)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS messages (
        id VARCHAR(64) PRIMARY KEY,
        sender_id VARCHAR(64) NOT NULL,
        sender_name VARCHAR(120) NOT NULL,
        recipient_id VARCHAR(64) NOT NULL,
        recipient_name VARCHAR(120) NOT NULL,
        body TEXT NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_messages_sender (sender_id),
        INDEX idx_messages_recipient (recipient_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS notifications (
        id VARCHAR(64) PRIMARY KEY,
        recipient_id VARCHAR(64) NOT NULL,
        notification_type VARCHAR(40) NOT NULL,
        title VARCHAR(120) NOT NULL,
        message VARCHAR(500) NOT NULL,
        entity_type VARCHAR(40) NOT NULL DEFAULT '',
        entity_id VARCHAR(64) NOT NULL DEFAULT '',
        is_read TINYINT(1) NOT NULL DEFAULT 0,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        read_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_notifications_recipient (recipient_id, is_read, created_at),
        INDEX idx_notifications_entity (entity_type, entity_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS services (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(120) NOT NULL UNIQUE,
        description VARCHAR(500) NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS promos (
        id VARCHAR(64) PRIMARY KEY,
        title VARCHAR(120) NOT NULL,
        description VARCHAR(500) NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
    """
    CREATE TABLE IF NOT EXISTS feedback (
        id VARCHAR(64) PRIMARY KEY,
        name VARCHAR(120) NOT NULL,
        rating TINYINT UNSIGNED NOT NULL,
        message VARCHAR(500) NOT NULL,
        created_at VARCHAR(40) NOT NULL DEFAULT '',
        updated_at VARCHAR(40) NOT NULL DEFAULT '',
        payload JSON NOT NULL,
        INDEX idx_feedback_rating (rating)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
    """,
)


@dataclass(frozen=True)
class MySQLConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    auto_initialize: bool
    ssl_ca: str

    @classmethod
    def from_environment(cls) -> "MySQLConfig":
        database = os.environ.get("DRMS_DB_NAME", "dental_clinic").strip()
        if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", database):
            raise ValueError("DRMS_DB_NAME may contain only letters, numbers, and underscores.")
        try:
            port = int(os.environ.get("DRMS_DB_PORT", "3306"))
        except ValueError as error:
            raise ValueError("DRMS_DB_PORT must be a valid port number.") from error
        if not 1 <= port <= 65535:
            raise ValueError("DRMS_DB_PORT must be between 1 and 65535.")
        return cls(
            host=os.environ.get("DRMS_DB_HOST", "127.0.0.1").strip(),
            port=port,
            user=os.environ.get("DRMS_DB_USER", "root").strip(),
            password=os.environ.get("DRMS_DB_PASSWORD", ""),
            database=database,
            auto_initialize=os.environ.get("DRMS_DB_AUTO_INIT", "1") == "1",
            ssl_ca=os.environ.get("DRMS_DB_SSL_CA", "").strip(),
        )


class MySQLStore:
    def __init__(self, config: MySQLConfig | None = None) -> None:
        self.config = config or MySQLConfig.from_environment()

    def _connection_options(self, include_database: bool = True) -> dict[str, Any]:
        options: dict[str, Any] = {
            "host": self.config.host,
            "port": self.config.port,
            "user": self.config.user,
            "password": self.config.password,
            "charset": "utf8mb4",
            "collation": "utf8mb4_unicode_ci",
            "connection_timeout": 8,
            "autocommit": False,
        }
        if include_database:
            options["database"] = self.config.database
        if self.config.ssl_ca:
            options.update({"ssl_ca": self.config.ssl_ca, "ssl_verify_cert": True})
        return options

    def connect(self):
        return mysql.connector.connect(**self._connection_options())

    def initialize(self) -> None:
        try:
            try:
                connection = self.connect()
            except MySQLError as error:
                if not self.config.auto_initialize or getattr(error, "errno", None) != 1049:
                    raise
                connection = mysql.connector.connect(**self._connection_options(False))
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        f"CREATE DATABASE IF NOT EXISTS `{self.config.database}` "
                        "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
                    )
                    connection.commit()
                finally:
                    cursor.close()
                    connection.close()
                connection = self.connect()

            cursor = connection.cursor()
            try:
                for statement in SCHEMA_STATEMENTS:
                    cursor.execute(statement)
                connection.commit()
            finally:
                cursor.close()
                connection.close()
        except MySQLError as error:
            raise RuntimeError(
                "Cannot initialize MySQL. Check DRMS_DB_HOST, DRMS_DB_PORT, "
                "DRMS_DB_USER, DRMS_DB_PASSWORD, and DRMS_DB_NAME."
            ) from error

    @staticmethod
    def _decode_payload(value: object) -> dict:
        if isinstance(value, dict):
            return value
        if isinstance(value, bytes):
            value = value.decode("utf-8")
        return json.loads(str(value))

    def load(self) -> dict[str, list[dict]]:
        result = {collection: [] for collection in COLLECTIONS}
        table_map = {"records": "treatments"}
        try:
            connection = self.connect()
            cursor = connection.cursor()
            try:
                for collection in COLLECTIONS:
                    table = table_map.get(collection, collection)
                    cursor.execute(f"SELECT payload FROM `{table}`")
                    result[collection] = [self._decode_payload(row[0]) for row in cursor.fetchall()]
            finally:
                cursor.close()
                connection.close()
        except MySQLError as error:
            raise RuntimeError("Unable to read application data from MySQL.") from error
        return result

    def is_empty(self) -> bool:
        try:
            connection = self.connect()
            cursor = connection.cursor()
            try:
                cursor.execute("SELECT EXISTS(SELECT 1 FROM users) OR EXISTS(SELECT 1 FROM patient_profiles) OR EXISTS(SELECT 1 FROM appointments) OR EXISTS(SELECT 1 FROM treatments)")
                return not bool(cursor.fetchone()[0])
            finally:
                cursor.close()
                connection.close()
        except MySQLError as error:
            raise RuntimeError("Unable to inspect the MySQL database.") from error

    @staticmethod
    def _identity(item: dict) -> str:
        parts = [
            str(item.get("first_name", "")).strip(),
            str(item.get("middle_name", "")).strip(),
            str(item.get("last_name", "")).strip(),
        ]
        name = " ".join(part for part in parts if part) or str(item.get("name", "")).strip()
        return re.sub(r"\s+", " ", name).lower()

    @staticmethod
    def _json(item: dict) -> str:
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"), allow_nan=False)

    def _collection_spec(self, collection: str) -> tuple[str, tuple[str, ...], Callable[[dict], tuple]]:
        specs: dict[str, tuple[str, tuple[str, ...], Callable[[dict], tuple]]] = {
            "users": (
                "users",
                ("id", "name", "email", "phone", "role", "profile_image", "password_hash", "created_at", "updated_at", "payload"),
                lambda item: (
                    item["id"], item.get("name", ""), item.get("email", ""), item.get("phone", ""),
                    item.get("role", "patient"), item.get("profile_image", ""), item.get("password_hash", ""),
                    item.get("created_at", ""), item.get("updated_at", ""), self._json(item),
                ),
            ),
            "patient_profiles": (
                "patient_profiles",
                (
                    "id", "last_name", "first_name", "middle_name", "email", "normalized_name", "birthdate",
                    "age", "address", "nationality", "occupation", "phone_number", "mobile_number", "notes",
                    "created_at", "updated_at", "payload",
                ),
                lambda item: (
                    item["id"], item.get("last_name", ""), item.get("first_name", ""), item.get("middle_name", ""),
                    item.get("email", ""), self._identity(item), item.get("birthdate", "1970-01-01"),
                    item.get("age") or None, item.get("address", ""), item.get("nationality", ""),
                    item.get("occupation", ""), item.get("phone_number", ""), item.get("mobile_number", ""),
                    item.get("notes", ""), item.get("created_at", ""), item.get("updated_at", ""), self._json(item),
                ),
            ),
            "appointments": (
                "appointments",
                (
                    "id", "patient_id", "patient_name", "patient_email", "patient_phone", "doctor_name", "service",
                    "appointment_date", "appointment_time", "status", "notes", "created_at", "updated_at", "payload",
                ),
                lambda item: (
                    item["id"], item.get("patient_id", ""), item.get("patient_name", ""),
                    item.get("patient_email", ""), item.get("patient_phone", ""), item.get("doctor", ""),
                    item.get("service", ""), item.get("date", "1970-01-01"), item.get("time", "00:00"),
                    item.get("status", "pending"), item.get("notes", ""), item.get("created_at", ""),
                    item.get("updated_at", ""), self._json(item),
                ),
            ),
            "availability": (
                "availability",
                (
                    "id", "doctor_name", "availability_date", "availability_time",
                    "created_at", "updated_at", "payload",
                ),
                lambda item: (
                    item["id"], item.get("doctor", ""), item.get("date", "1970-01-01"),
                    item.get("time", "00:00"), item.get("created_at", ""),
                    item.get("updated_at", ""), self._json(item),
                ),
            ),
            "records": (
                "treatments",
                (
                    "id", "appointment_id", "patient_id", "patient_name", "doctor_id", "doctor_name", "treatment_date",
                    "tooth_numbers", "procedure_name", "amount_charged", "amount_paid", "balance", "payment_status",
                    "diagnosis", "prescription", "remarks", "next_visit", "created_at", "updated_at", "payload",
                ),
                lambda item: (
                    item["id"], item.get("appointment_id", ""), item.get("patient_id", ""), item.get("patient_name", ""),
                    item.get("doctor_id", ""), item.get("doctor_name", ""), item.get("treatment_date", "1970-01-01"),
                    item.get("tooth_numbers", ""), item.get("procedure", item.get("treatment", "")),
                    item.get("amount_charged", 0), item.get("amount_paid", 0), item.get("balance", 0),
                    item.get("payment_status", "unpaid"), item.get("diagnosis", ""), item.get("prescription", ""),
                    item.get("remarks", item.get("notes", "")), item.get("next_visit") or None,
                    item.get("created_at", ""), item.get("updated_at", ""), self._json(item),
                ),
            ),
            "messages": (
                "messages",
                ("id", "sender_id", "sender_name", "recipient_id", "recipient_name", "body", "created_at", "payload"),
                lambda item: (
                    item["id"], item.get("sender_id", ""), item.get("sender_name", ""), item.get("recipient_id", ""),
                    item.get("recipient_name", ""), item.get("body", ""), item.get("created_at", ""), self._json(item),
                ),
            ),
            "notifications": (
                "notifications",
                (
                    "id", "recipient_id", "notification_type", "title", "message", "entity_type",
                    "entity_id", "is_read", "created_at", "read_at", "payload",
                ),
                lambda item: (
                    item["id"], item.get("recipient_id", ""), item.get("type", "transaction"),
                    item.get("title", ""), item.get("message", ""), item.get("entity_type", ""),
                    item.get("entity_id", ""), 1 if item.get("is_read") else 0,
                    item.get("created_at", ""), item.get("read_at", ""), self._json(item),
                ),
            ),
            "services": (
                "services",
                ("id", "name", "description", "created_at", "updated_at", "payload"),
                lambda item: (
                    item["id"], item.get("name", ""), item.get("description", ""), item.get("created_at", ""),
                    item.get("updated_at", ""), self._json(item),
                ),
            ),
            "promos": (
                "promos",
                ("id", "title", "description", "created_at", "updated_at", "payload"),
                lambda item: (
                    item["id"], item.get("title", ""), item.get("description", ""), item.get("created_at", ""),
                    item.get("updated_at", ""), self._json(item),
                ),
            ),
            "feedback": (
                "feedback",
                ("id", "name", "rating", "message", "created_at", "updated_at", "payload"),
                lambda item: (
                    item["id"], item.get("name", ""), item.get("rating", 5), item.get("message", ""),
                    item.get("created_at", ""), item.get("updated_at", ""), self._json(item),
                ),
            ),
        }
        return specs[collection]

    def _sync_collection(self, cursor, collection: str, items: list[dict]) -> None:
        table, columns, values_for = self._collection_spec(collection)
        placeholders = ", ".join(["%s"] * len(columns))
        column_sql = ", ".join(f"`{column}`" for column in columns)
        update_sql = ", ".join(
            f"`{column}` = VALUES(`{column}`)" for column in columns if column != "id"
        )
        statement = (
            f"INSERT INTO `{table}` ({column_sql}) VALUES ({placeholders}) "
            f"ON DUPLICATE KEY UPDATE {update_sql}"
        )
        ids: list[str] = []
        for item in items:
            item_id = str(item.get("id", "")).strip()
            if not item_id:
                raise ValueError(f"A {collection} item is missing its id.")
            ids.append(item_id)
            cursor.execute(statement, values_for(item))
        if ids:
            id_placeholders = ", ".join(["%s"] * len(ids))
            cursor.execute(f"DELETE FROM `{table}` WHERE id NOT IN ({id_placeholders})", tuple(ids))
        else:
            cursor.execute(f"DELETE FROM `{table}`")

    def save(self, data: dict[str, list[dict]]) -> None:
        try:
            connection = self.connect()
            cursor = connection.cursor()
            try:
                connection.start_transaction(isolation_level="SERIALIZABLE")
                for collection in COLLECTIONS:
                    self._sync_collection(cursor, collection, list(data.get(collection, [])))
                connection.commit()
            except Exception:
                connection.rollback()
                raise
            finally:
                cursor.close()
                connection.close()
        except (MySQLError, ValueError, TypeError) as error:
            raise RuntimeError("Unable to save application data to MySQL.") from error
