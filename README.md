# PrepNxt CRM — Django Backend

## Setup

```bash
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Server runs at http://127.0.0.1:8000/

## Endpoints (Phase 1: CSV Import)

### POST /api/leads/import-csv/
Imports leads from a CSV. Accepts EITHER:
- `multipart/form-data` with a `file` field (CSV file upload), or
- a `csv_text` field (pasted Excel/CSV rows — comma or tab delimited, auto-detected)

Expected CSV header columns:
```
SL No., Current Organization, Job Title, Result, Total Years Of Experience,
Current Salary, Attended, Time, First Name, Last Name, Email, Phone Number,
SPOC, Lead Status, Follow up 1, Follow up 2, ... Follow up 7
```

Mapping rules:
- `First Name` + `Last Name` -> `name`
- Each non-empty `Follow up N` becomes a separate Activity (type "Follow-up", completion status "Completed")
- Imported leads are always created with `is_new = true`
- `Lead Status` is matched case-insensitively against known statuses (New, Contacted, Hot, Warm, Cold, Converted, Not Interested, Lost); unrecognized text is kept as-is (slugified)

Example (file upload):
```bash
curl -X POST http://127.0.0.1:8000/api/leads/import-csv/ \
  -F "file=@leads.csv"
```

Example (pasted rows):
```bash
curl -X POST http://127.0.0.1:8000/api/leads/import-csv/ \
  --data-urlencode "csv_text@pasted_rows.txt"
```

Response (201):
```json
{
  "leads_created": 3,
  "activities_created": 3,
  "rows_processed": 3,
  "errors": [],
  "leads": [ ... ]
}
```

### GET /api/leads/
Lists all leads (for verifying an import landed correctly). Full Leads/Activities CRUD endpoints come in the next pass.

### GET /api/leads/<id>/
Lead detail with its activity timeline.

## CORS
`http://localhost:3000` and `http://127.0.0.1:3000` are allowed by default (the CRA frontend's dev server). Update `CORS_ALLOWED_ORIGINS` in `config/settings.py` if your frontend runs elsewhere.

## Notes
- SQLite for local dev (Phase 1) — swap `DATABASES` in `config/settings.py` for Postgres when ready.
- `python manage.py createsuperuser` to access `/admin/` and browse imported data visually.
