CREATE DATABASE IF NOT EXISTS dental_clinic
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE dental_clinic;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

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
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS services (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  description VARCHAR(500) NOT NULL,
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT '',
  payload JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS promos (
  id VARCHAR(64) PRIMARY KEY,
  title VARCHAR(120) NOT NULL,
  description VARCHAR(500) NOT NULL,
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT '',
  payload JSON NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS feedback (
  id VARCHAR(64) PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  rating TINYINT UNSIGNED NOT NULL,
  message VARCHAR(500) NOT NULL,
  created_at VARCHAR(40) NOT NULL DEFAULT '',
  updated_at VARCHAR(40) NOT NULL DEFAULT '',
  payload JSON NOT NULL,
  INDEX idx_feedback_rating (rating)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
