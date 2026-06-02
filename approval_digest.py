#!/usr/bin/env python3
"""
Approval digest for Triangle Startup Events.

Pulls all pending (unapproved, non-archived) upcoming events from Airtable
and emails them to Tim with a direct link to each record. Only sends if
there are events to review. Run this after the daily scraper.

Required env vars:
  AIRTABLE_API_KEY
  GMAIL_CREDENTIALS_FILE
  GMAIL_TOKEN_FILE  (defaults to gmail_token.json)
"""
from __future__ import annotations

import base64
import os
import sys
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import requests

# ── Config ────────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"
GMAIL_CREDENTIALS = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
GMAIL_TOKEN       = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")
SENDER_EMAIL      = "tim@timscales.com"

# Deep link to a specific Airtable record
AIRTABLE_RECORD_URL = "https://airtable.com/{base}/{record}"

# ── Airtable ──────────────────────────────────────────────────────────────────

AT_HEADERS = lambda: {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}


def fetch_pending_events() -> list[dict]:
    """Fetch upcoming events that are not yet approved and not archived."""
    url      = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Events"
    today    = date.today()
    end_date = today + timedelta(days=90)
    formula  = (
        f"AND("
        f"NOT({{Approved}}), "
        f"NOT({{Archived}}), "
        f"IS_AFTER({{Date}}, DATEADD('{today - timedelta(days=1)}', 0, 'days')), "
        f"IS_BEFORE({{Date}}, DATEADD('{end_date + timedelta(days=1)}', 0, 'days'))"
        f")"
    )
    params = {
        "filterByFormula": formula,
        "sort[0][field]": "Date",
        "sort[0][direction]": "asc",
        "sort[1][field]": "Start Time",
        "sort[1][direction]": "asc",
        "fields[]": [
            "Name", "Date", "Start Time", "End Time",
            "Location", "Description", "Source URL", "Paid", "Organizer",
        ],
    }
    records = []
    offset  = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=AT_HEADERS(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    # Resolve organizer names
    org_ids = {oid for r in records for oid in r.get("fields", {}).get("Organizer", [])}
    org_names = _fetch_org_names(org_ids)

    events = []
    for r in records:
        f      = r.get("fields", {})
        org_id = (f.get("Organizer") or [None])[0]
        events.append({
            "record_id":   r["id"],
            "name":        f.get("Name", ""),
            "date":        f.get("Date", ""),
            "start_time":  f.get("Start Time", ""),
            "end_time":    f.get("End Time", ""),
            "location":    f.get("Location", ""),
            "description": f.get("Description", ""),
            "source_url":  f.get("Source URL", ""),
            "paid":        bool(f.get("Paid", False)),
            "organizer":   org_names.get(org_id, ""),
        })
    return events


def _fetch_org_names(org_ids: set[str]) -> dict[str, str]:
    if not org_ids:
        return {}
    url   = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"
    names = {}
    for oid in org_ids:
        try:
            resp = requests.get(f"{url}/{oid}", headers=AT_HEADERS(), timeout=15)
            resp.raise_for_status()
            names[oid] = resp.json().get("fields", {}).get("Organization Name", "")
        except Exception:
            names[oid] = ""
    return names


# ── Formatting ────────────────────────────────────────────────────────────────

AIRTABLE_EDIT_URL = "https://airtable.com/apprt7MFT8PcVhFY4/pagn5NtFKrCDtz2Eb"

def _fmt_time(t: str) -> str:
    from datetime import datetime
    if not t or t == "00:00":
        return ""
    try:
        dt = datetime.strptime(t, "%H:%M")
        return dt.strftime("%-I%p").lower() if dt.minute == 0 else dt.strftime("%-I:%M%p").lower()
    except ValueError:
        return t


def _fmt_date(date_str: str, start: str, end: str) -> str:
    from datetime import datetime
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %-d")
    except ValueError:
        d = date_str
    s, e = _fmt_time(start), _fmt_time(end)
    if s and e:
        return f"{d} from {s}–{e}"
    if s:
        return f"{d} at {s}"
    return d


def _friendly_location(location: str) -> str:
    """Strip street address, keep venue name (mirrors logic in draft_email.py)."""
    import re
    if not location:
        return location
    parts = [p.strip() for p in location.split(",")]
    if len(parts) <= 1:
        return location
    if re.match(r"^\d+\s+", parts[0]):
        city = next((p for p in parts[1:] if not re.match(r"^\d", p.strip())
                     and not re.match(r"^[A-Z]{2}\b", p.strip())
                     and not re.match(r"^\d{5}", p.strip())), None)
        return f"{parts[0]}, {city.strip()}" if city else parts[0]
    return parts[0] if any(re.match(r"^\d+\s+", p.strip()) for p in parts[1:]) else location


def _issues(event: dict) -> list[str]:
    problems = []
    if not event["start_time"] or event["start_time"] == "00:00":
        problems.append("⚠️ missing start time")
    if not event["end_time"]:
        problems.append("⚠️ missing end time")
    if not event["description"] or len(event["description"]) < 20:
        problems.append("⚠️ missing/short description")
    if not event["organizer"]:
        problems.append("⚠️ no organizer linked")
    if not event["location"]:
        problems.append("⚠️ no location")
    return problems


def _event_preview(ev: dict) -> str:
    """Render an event exactly as it would appear in the weekly email."""
    name      = ev["name"]
    organizer = ev["organizer"]
    date_line = _fmt_date(ev["date"], ev["start_time"], ev["end_time"])
    location  = _friendly_location(ev["location"])
    city      = ev.get("city", "")
    desc      = ev["description"]
    url       = ev["source_url"]
    paid      = ev["paid"]

    venue = location or city
    where_line = date_line
    if venue:
        where_line += f" at {venue}"

    title = f"<strong>{name}</strong>"
    if organizer:
        title += f" | {organizer}"
    if paid:
        title += " <em>($Paid)</em>"

    lines = [f'<p style="margin:0 0 4px 0">👉 {title}</p>']
    lines.append(f'<p style="margin:0 0 4px 0">🗓️ {where_line}</p>')
    if desc:
        lines.append(f'<p style="margin:0 0 4px 0">ℹ️ {desc}</p>')
    if url:
        lines.append(f'<p style="margin:0 0 0 0">🔗 <a href="{url}" style="color:#0e6b6b">{url}</a></p>')

    return "\n".join(lines)


# ── Email ─────────────────────────────────────────────────────────────────────

def build_html(events: list[dict]) -> str:
    rows = []
    for ev in events:
        record_id = ev["record_id"]
        edit_url  = f"{AIRTABLE_EDIT_URL}?recordId={record_id}"

        issues     = _issues(ev)
        preview    = _event_preview(ev)

        issue_html = ""
        if issues:
            issue_html = (
                '<div style="margin:10px 0 0 0;padding:8px 10px;background:#fff8f0;'
                'border-left:3px solid #e67e22;font-size:12px;color:#c0392b">'
                + " &nbsp;·&nbsp; ".join(issues)
                + "</div>"
            )

        rows.append(f"""
<div style="border:1px solid #ddd;padding:16px;margin-bottom:16px;font-family:Arial,sans-serif;font-size:14px;line-height:1.6">
  {preview}
  {issue_html}
  <div style="margin-top:12px">
    <a href="{edit_url}" style="display:inline-block;background:#0e6b6b;color:white;padding:5px 14px;text-decoration:none;font-size:12px;font-weight:bold">Review</a>
  </div>
</div>""")

    count   = len(events)
    heading = f"{count} event{'s' if count > 1 else ''} pending approval"

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:24px;background:#f5f5f5;font-family:Arial,sans-serif">
  <div style="max-width:620px;margin:0 auto">
    <h2 style="font-size:18px;font-weight:bold;color:#0e6b6b;margin:0 0 16px 0">
      Triangle Startup Events — {heading}
    </h2>
    {"".join(rows)}
  </div>
</body>
</html>"""


# ── Gmail ─────────────────────────────────────────────────────────────────────

def get_gmail_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
    creds  = None

    if os.path.exists(GMAIL_TOKEN):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GMAIL_CREDENTIALS):
                print(f"ERROR: Gmail credentials file not found at {GMAIL_CREDENTIALS}")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def send_digest(service, events: list[dict]) -> None:
    count   = len(events)
    subject = f"🗓️ {count} event{'s' if count > 1 else ''} pending approval — Triangle Startup Events"
    html    = build_html(events)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = SENDER_EMAIL
    msg.attach(MIMEText(html, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set")
        sys.exit(1)

    print("Fetching pending events from Airtable...")
    events = fetch_pending_events()
    print(f"  {len(events)} pending")

    if not events:
        print("Nothing to review. No email sent.")
        return

    print("Authenticating with Gmail...")
    service = get_gmail_service()

    print("Sending digest...")
    send_digest(service, events)
    print(f"Done. Digest sent for {len(events)} event(s).")


if __name__ == "__main__":
    main()
