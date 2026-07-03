import csv
import io
import re
import uuid
from datetime import datetime

from django.utils import timezone

from .models import ActivityType, CompletionStatus, LeadStatus

FOLLOW_UP_KEYS = [f"Follow up {i}" for i in range(1, 8)]

_STATUS_LABEL_TO_VALUE = {label.lower(): value for value, label in LeadStatus.choices}

_MONTH_PATTERN = re.compile(
    r"(\d{1,2})[-\s](Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[-\s](\d{4})",
    re.IGNORECASE,
)

# Canonical field -> every header spelling we've seen in real sheets so far.
# Matching is case-insensitive and ignores extra whitespace/periods, so
# "SL No." / "Sl No" / "sl no." all resolve the same way. Add new variants
# here rather than touching the parsing logic below.
FIELD_HEADER_ALIASES = {
    "sl_no": ["sl no", "sl no.", "s no", "serial no"],
    "organization": ["current organization", "organization", "company"],
    "job_title": ["job titile", "job title", "designation"],
    "experience": ["total years of experience", "years of experience", "experience"],
    "salary": ["current salary", "salary"],
    "attended": ["attended"],
    "time": ["time"],
    "result": ["result"],
    "first_name": ["first name"],
    "last_name": ["last name"],
    "email": ["email"],
    "phone": ["phone number", "phone"],
    "owner": ["spoc", "owner"],
    "status": ["lead status", "status"],
}


def _clean_header(h):
    return re.sub(r"\s+", " ", (h or "").strip().lower()).rstrip(".")


def _build_header_lookup(fieldnames):
    """Maps each canonical field name to the actual header string present
    in this file, so a lookup like row.get(header_lookup['job_title'])
    always hits the right column regardless of minor spelling differences."""
    cleaned_to_actual = {_clean_header(h): h for h in fieldnames}
    lookup = {}
    for field, aliases in FIELD_HEADER_ALIASES.items():
        for alias in aliases:
            actual = cleaned_to_actual.get(_clean_header(alias))
            if actual:
                lookup[field] = actual
                break
    return lookup


def _norm(value):
    if value is None:
        return ""
    return str(value).strip()


def normalize_status(raw):
    """Matches free-text CSV status against known labels (case-insensitive);
    falls back to a slugified version of the raw text, same as the frontend."""
    text = _norm(raw)
    if not text:
        return LeadStatus.NEW_LEAD
    match = _STATUS_LABEL_TO_VALUE.get(text.lower())
    if match:
        return match
    return re.sub(r"\s+", "_", text.lower())


def extract_date_from_text(text):
    """Best-effort date extraction from free-text follow-up notes
    (e.g. '12-Jan-2025: called, no response'). Returns a date or None
    if no recognizable pattern is found — caller defaults to today."""
    if not text:
        return None

    match = re.search(r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})", text)
    if match:
        day, month, year = match.groups()
        try:
            return datetime(int(year), int(month), int(day)).date()
        except ValueError:
            pass

    match = _MONTH_PATTERN.search(text)
    if match:
        day, month_name, year = match.groups()
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                return datetime.strptime(f"{day} {month_name} {year}", fmt).date()
            except ValueError:
                continue

    return None


def _sniff_dialect(csv_text):
    sample = csv_text[:2048]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",\t;")
    except csv.Error:
        dialect = csv.excel
        dialect.delimiter = "\t" if "\t" in sample and "," not in sample else ","
        return dialect


def parse_csv_text(csv_text, today=None):
    """Parses raw CSV/TSV text (file upload or pasted Excel rows) into lead
    dicts and activity dicts ready for bulk_create.

    Returns: {"leads": [...], "activities": [...], "row_count": int, "errors": [...]}
    """
    today = today or timezone.localdate()
    dialect = _sniff_dialect(csv_text)

    reader = csv.DictReader(io.StringIO(csv_text), dialect=dialect)
    reader.fieldnames = [h.strip() for h in (reader.fieldnames or [])]
    headers = _build_header_lookup(reader.fieldnames)

    leads = []
    activities = []
    errors = []
    row_count = 0

    for row in reader:
        row_count += 1
        row = {(k.strip() if k else k): v for k, v in row.items()}
        if not any(_norm(v) for v in row.values()):
            continue  # skip blank rows

        def get(field):
            header = headers.get(field)
            return _norm(row.get(header)) if header else ""

        first_name = get("first_name")
        last_name = get("last_name")
        name = " ".join(p for p in [first_name, last_name] if p) or "Unnamed Lead"
        owner = get("owner")
        status = normalize_status(row.get(headers.get("status")))
        lead_id = uuid.uuid4()
        now = timezone.now()

        leads.append(
            {
                "id": lead_id,
                "is_new": True,
                "sl_no": get("sl_no"),
                "first_name": first_name,
                "last_name": last_name,
                "name": name,
                "phone": get("phone"),
                "email": get("email"),
                "organization": get("organization"),
                "job_title": get("job_title"),
                "experience": get("experience"),
                "salary": get("salary"),
                "attended": get("attended"),
                "time": get("time"),
                "result": get("result"),
                "owner": owner,
                "status": status,
            }
        )

        for key in FOLLOW_UP_KEYS:
            text = _norm(row.get(key))
            if not text:
                continue
            due_date = extract_date_from_text(text) or today
            activities.append(
                {
                    "id": uuid.uuid4(),
                    "lead_id": lead_id,
                    "type": ActivityType.FOLLOW_UP,
                    "description": text,
                    "owner": owner,
                    "due_date": due_date,
                    "time": "",
                    "lead_status": status,
                    "completion_status": CompletionStatus.COMPLETED,
                    "completed_at": now,
                }
            )

    return {
        "leads": leads,
        "activities": activities,
        "row_count": row_count,
        "errors": errors,
    }