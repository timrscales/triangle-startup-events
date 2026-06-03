#!/usr/bin/env python3
"""
Generate a weekly Triangle Startup Events LinkedIn post and email it to Tim.

Pulls approved, non-archived events (next 9 days) from Airtable,
formats them as plain-text LinkedIn copy, and sends to tim@timscales.com.

Required env vars:
  ANTHROPIC_API_KEY
  AIRTABLE_API_KEY
  GMAIL_CREDENTIALS_FILE  — path to OAuth2 credentials JSON
  GMAIL_TOKEN_FILE        — path to cached token (defaults to gmail_token.json)
"""
from __future__ import annotations

import base64
import os
import re
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import requests

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"
GMAIL_CREDENTIALS = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
GMAIL_TOKEN       = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")
SENDER_EMAIL      = "tim@timscales.com"
CALENDAR_URL      = "https://events.timscales.com"
EVENT_WINDOW_DAYS = 9

# ── Airtable ──────────────────────────────────────────────────────────────────

AT_HEADERS = lambda: {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}


def fetch_upcoming_events(start: date, end: date) -> list[dict]:
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Events"
    formula = (
        f"AND("
        f"IS_AFTER({{Date}}, '{start - timedelta(days=1)}'), "
        f"IS_BEFORE({{Date}}, '{end + timedelta(days=1)}')"
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
            "Location", "City", "Description", "Source URL",
            "Paid", "Organization", "Approved", "Archived",
        ],
    }
    records = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=AT_HEADERS(), params=params, timeout=30)
        if not resp.ok:
            print(f"Airtable error {resp.status_code}: {resp.text}", file=sys.stderr)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        offset = data.get("offset")
        if not offset:
            break

    org_ids = {oid for r in records for oid in r.get("fields", {}).get("Organization", [])}
    org_names = _fetch_org_names(org_ids)

    events = []
    for r in records:
        f = r.get("fields", {})
        org_id = (f.get("Organization") or [None])[0]
        events.append({
            "name":        f.get("Name", ""),
            "date":        f.get("Date", ""),
            "start_time":  f.get("Start Time", ""),
            "end_time":    f.get("End Time", ""),
            "location":    f.get("Location", ""),
            "city":        f.get("City", ""),
            "description": f.get("Description", ""),
            "source_url":  f.get("Source URL", ""),
            "paid":        bool(f.get("Paid", False)),
            "organizer":   org_names.get(org_id, ""),
            "approved":    bool(f.get("Approved", False)),
            "archived":    bool(f.get("Archived", False)),
        })
    return [e for e in events if e["approved"] and not e["archived"]]


def _fetch_org_names(org_ids: set[str]) -> dict[str, str]:
    if not org_ids:
        return {}
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"
    names = {}
    for oid in org_ids:
        try:
            resp = requests.get(f"{url}/{oid}", headers=AT_HEADERS(), timeout=15)
            resp.raise_for_status()
            names[oid] = resp.json().get("fields", {}).get("Organization Name", "")
        except Exception:
            names[oid] = ""
    return names


# ── Formatting helpers ────────────────────────────────────────────────────────

_ADDRESS_RE = re.compile(r",\s*\d+\s+\w")


def friendly_location(location: str) -> str:
    if not location:
        return location
    parts = [p.strip() for p in location.split(",")]
    if len(parts) <= 1:
        return location
    first_is_address = bool(re.match(r"^\d+\s+", parts[0]))
    if first_is_address:
        city = next((p for p in parts[1:] if not re.match(r"^\d", p.strip())
                     and not re.match(r"^[A-Z]{2}\b", p.strip())
                     and not re.match(r"^\d{5}", p.strip())), None)
        return f"{parts[0]}, {city.strip()}" if city else parts[0]
    else:
        has_address = any(bool(re.match(r"^\d+\s+", p.strip())) for p in parts[1:])
        return parts[0] if has_address else location


def fmt_time(t: str) -> str:
    if not t:
        return ""
    try:
        dt = datetime.strptime(t, "%H:%M")
        if dt.minute == 0:
            return dt.strftime("%-I%p").lower()
        return dt.strftime("%-I:%M%p").lower()
    except ValueError:
        return t


def fmt_date_range(date_str: str, start_time: str, end_time: str) -> str:
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        day_str = d.strftime("%A, %B %-d")
    except ValueError:
        day_str = date_str
    start = fmt_time(start_time)
    end   = fmt_time(end_time)
    if start and end:
        return f"{day_str} from {start}–{end}"
    elif start:
        return f"{day_str} at {start}"
    return day_str


def shorten_description(desc: str, client) -> str:
    if not desc:
        return desc
    sentences = re.split(r"(?<=[.!?])\s+", desc.strip())
    if len(sentences) <= 1:
        return desc
    if not client:
        return sentences[0]
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=80,
        messages=[{"role": "user", "content": (
            "Summarize the following event description in one concise sentence "
            "that tells the reader what the event is about at a high level. "
            "Write only the sentence, no quotes, no preamble.\n\n"
            f"{desc}"
        )}],
    )
    return message.content[0].text.strip()


# ── Post builder ──────────────────────────────────────────────────────────────

def event_to_text(event: dict, client) -> str:
    name      = event["name"]
    organizer = event["organizer"]
    paid      = event["paid"]
    date_line = fmt_date_range(event["date"], event["start_time"], event["end_time"])
    location  = friendly_location(event["location"])
    city      = event["city"]
    desc      = shorten_description(event["description"], client)
    url       = event["source_url"]

    # Title line: name + organizer + paid marker
    title = name
    if organizer:
        title += f" | {organizer}"
    if paid:
        title += " ($Paid Event)"

    # Date + location line: prefer friendly venue name, fall back to city
    where_line = date_line
    venue = location or city
    if venue:
        # Use "at Venue" if it's a named place, "in City" if it's just a city
        preposition = "in" if venue == city and not location else "at"
        where_line += f" {preposition} {venue}"

    lines = [f"👉 {title}"]
    lines.append(f"🗓️ {where_line}")
    if desc:
        lines.append(f"ℹ️ {desc}")
    if url:
        lines.append(f"🔗 {url}")

    return "\n".join(lines)


def build_post(events: list[dict], client) -> str:
    header = (
        "Looking for startup events in the Triangle? "
        "Here are some highlights for the week ahead.\n\n"
        f"Check out the full calendar and get weekly updates at {CALENDAR_URL}"
    )

    event_blocks = "\n\n".join(event_to_text(e, client) for e in events)

    footer = f"------\n{CALENDAR_URL}"

    return f"{header}\n\n{event_blocks}\n\n{footer}"


# ── Gmail send ────────────────────────────────────────────────────────────────

def get_gmail_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Gmail dependencies not installed.")
        print("Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
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


def send_email(service, subject: str, body: str) -> None:
    # Send as HTML with <pre> so emojis copy-paste correctly from Gmail
    html_body = (
        f'<html><body>'
        f'<pre style="font-family:Arial,sans-serif;font-size:14px;white-space:pre-wrap">'
        f'{body}'
        f'</pre></body></html>'
    )
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = SENDER_EMAIL
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(
        userId="me",
        body={"raw": raw},
    ).execute()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set")
        sys.exit(1)

    today    = date.today()
    end_date = today + timedelta(days=EVENT_WINDOW_DAYS)

    print(f"Fetching events from {today} to {end_date}...")
    events = fetch_upcoming_events(today, end_date)
    print(f"  {len(events)} approved events")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None

    print("Building LinkedIn post...")
    post = build_post(events, client)

    print("Authenticating with Gmail...")
    service = get_gmail_service()

    print("Sending email...")
    send_email(service, "Weekly Events LinkedIn Post", post)
    print("Done. Check your inbox.")


if __name__ == "__main__":
    main()
