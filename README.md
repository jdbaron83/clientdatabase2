# Client records

A web app and PostgreSQL database for client records, episodes of care, funding sources,
authorizations (with OCAs), MAT medications and the waitlist. Built with Django 5.2.

## Run it with Docker (server or cloud VM)

1. Copy `.env.example` to `.env` and fill in every value. Generate the encryption key with
   `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   and **back it up**. Without it, stored SSNs can't be decrypted.
2. `docker compose up -d --build`
3. Create the first login: `docker compose exec web python manage.py createsuperuser`
4. Load the spreadsheet (one time). Put the workbook in `./data/`, then:
   `docker compose exec web python manage.py seed_from_masterlog "/data/MasterLog.xlsx" --review /tmp/seed_review.csv`
   Add `--dry-run` to test without saving, or `--reset` to wipe and reload.
5. The app listens on `127.0.0.1:8000`. Put it behind HTTPS (Caddy, nginx, or your cloud's load balancer)
   and set `DJANGO_ALLOWED_HOSTS` / `DJANGO_CSRF_TRUSTED_ORIGINS` to the public hostname.

Managed hosting works too (Azure App Service + Azure Database for PostgreSQL, AWS, Render, etc.):
build the image from the Dockerfile and point the `POSTGRES_*` variables at the managed database.
Pick a host that will sign a HIPAA BAA.

## Users and permissions

Create staff logins in **Admin → Users**. Use groups to control access, for example:
- *Intake*: add/change clients, waitlist entries and episodes.
- *Billing*: add/change authorizations.
- *Supervisors*: everything above, plus "Can view full SSN" and "Can view audit log".

Everyone else sees only the last 4 digits of SSNs. Sessions time out after 30 minutes idle.

## What's in the database

| Table | What it holds |
|---|---|
| Funding source | SFBHN, SFBHNMH, VA GPD, CBO - Residential, ... with level of care and bed capacity |
| OCA | Sub-funding codes (MS003, MSOTR, MH001, ...) that apply under SFBHN and SFBHNMH |
| Client | Name, DOB, SSN (encrypted), Medicaid ID, demographics |
| Episode | One admission: record ID (R07-121-2), funding source, admit/discharge dates and reason, bed |
| Authorization | Auth number, funding source, OCA, start/end, days authorized |
| Waitlist entry | Status (waiting / on hold / admitted / declined), rank, referral, notes |
| Medication | MAT prescriptions and fills |
| Audit log | Every create, change, delete and record view, with the user and time |

## The seed import

Reads these sheets from the MasterLog workbook: **Master Log**, **MAT Outpatient Log (2)**, **Waitlist**,
**Waitlist Archive**. All other tabs are ignored.

- People are matched across rows by SSN, then by name + date of birth. `.2`/`.3` readmit suffixes are stripped.
- Funding source spellings are merged (`Self-pay` → `Self-Pay`, `MBPD` → `MB PD`, `OMB2` → `OMB 2`).
- The OCA column is loaded only when it holds an OCA code and the row's funding source is SFBHN or SFBHNMH.
  Older rows that have a counselor name in that column are skipped.
- Rows that can't be loaded cleanly are written to the review CSV. It contains client names, so keep it private.

## Development

```
cp .env.example .env   # set DJANGO_DEBUG=1 and the Postgres/encryption values
pip install -r requirements.txt
python manage.py migrate
python manage.py test records
python manage.py runserver
```
