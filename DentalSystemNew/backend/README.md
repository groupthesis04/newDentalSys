# Dental Record Management System

This project uses a Python HTTP backend, a responsive HTML/CSS/JavaScript frontend, and MySQL persistence.

## Project layout

- `frontend/` - HTML pages, JavaScript, styles, and browser assets
- `backend/` - HTTP server, routes, MySQL adapter, tests, tools, and configuration
- `database/` - MySQL schema and legacy JSON migration data

## Requirements

- Python 3.11 or newer
- MySQL Server 8.x
- Python packages from `backend/requirements.txt`

```powershell
python -m pip install -r backend/requirements.txt
```

## MySQL setup

Run `database/schema.sql` from MySQL Workbench or the MySQL command line using an administrator account. Then create a restricted application account and grant it access to the clinic database.

```sql
CREATE USER 'dental_app'@'localhost' IDENTIFIED BY 'replace-with-a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX
  ON dental_clinic.* TO 'dental_app'@'localhost';
FLUSH PRIVILEGES;
```

Copy `backend/.env.example` to `backend/.env`, then replace every placeholder secret. The server reads that file automatically.

```text
DRMS_STORAGE=mysql
DRMS_DB_HOST=127.0.0.1
DRMS_DB_PORT=3306
DRMS_DB_NAME=dental_clinic
DRMS_DB_USER=dental_app
DRMS_DB_PASSWORD=your-strong-database-password
DRMS_STAFF_CODE=your-long-random-staff-registration-code
```

`DRMS_DB_AUTO_INIT=1` creates missing tables when the database account has permission. Set it to `0` after running `database/schema.sql` if schema creation should be administrator-controlled.

## Existing data migration

To import the current JSON records into an empty MySQL database:

```powershell
python backend/tools/migrate_json_to_mysql.py --source database/data/app_data.json
```

The migration refuses to replace existing clinic data. Use `--force` only after making a database backup and intentionally choosing replacement.

## Run

```powershell
python backend/server.py --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`. The first doctor account can be created through Sign Up by selecting `Doctor / Staff` and entering the configured `DRMS_STAFF_CODE`.

Doctor accounts manage clinic schedules from **Appointments > Clinic availability**. An admin can select multiple dates in one month, set the dentist's time-in and time-out, and generate 15-, 30-, or 60-minute appointment slots in one batch. Pending requests leave a slot open; accepting one request closes that exact dentist, date, and time to patients and cancels competing pending requests. Cancelling the accepted appointment makes the slot available again.

For isolated migration or automated tests only, JSON storage remains available explicitly:

```powershell
python backend/server.py --storage json --data-file database/data/test.json --port 8000
```

## Security controls

- Central server-side field allowlists, size limits, normalization, and validation
- Client-side native constraints and JavaScript verification
- PBKDF2 password hashing with per-password salts
- Session-bound CSRF tokens and strict same-site cookies
- Same-origin enforcement and restrictive browser security headers
- Endpoint-specific IP rate limiting with `429` and `Retry-After`
- Off-screen honeypots on all submitted forms
- Role checks for doctor-only and patient-only operations

Set `DRMS_COOKIE_SECURE=1` when the application is served over HTTPS. Keep `.env` out of source control and use a dedicated MySQL account rather than `root` in production.
