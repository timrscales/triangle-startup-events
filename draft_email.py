#!/usr/bin/env python3
"""
Draft a weekly Triangle Startup Events email in Gmail.

Pulls upcoming events (next 7 days from today) and subscriber emails
from Airtable, generates an opener via Claude Haiku, formats an HTML
email, and saves it as a Gmail draft for Tim to review and send.

Required env vars:
  ANTHROPIC_API_KEY
  AIRTABLE_API_KEY
  GMAIL_CREDENTIALS_FILE  — path to OAuth2 credentials JSON downloaded
                            from Google Cloud Console
  GMAIL_TOKEN_FILE        — path where the OAuth2 token will be cached
                            (created on first run; defaults to token.json)
"""
from __future__ import annotations

import base64
import json
import os
import sys
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import anthropic
import requests

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY  = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY   = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID   = "apprt7MFT8PcVhFY4"
GMAIL_CREDENTIALS  = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
GMAIL_TOKEN        = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")
SENDER_EMAIL       = "tim@timscales.com"
EMAIL_SUBJECT_TPL  = "Triangle Startup Events — Week of {date}"

# How many days ahead to include events (from today / Monday send day)
EVENT_WINDOW_DAYS  = 9

# ── Airtable helpers ──────────────────────────────────────────────────────────

AT_HEADERS = lambda: {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}


def fetch_upcoming_events(start: date, end: date) -> list[dict]:
    """Fetch Events from Airtable between start and end dates (inclusive)."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Events"
    formula = (
        f"AND("
        f"IS_AFTER({{Date}}, DATEADD('{start - timedelta(days=1)}', 0, 'days')), "
        f"IS_BEFORE({{Date}}, DATEADD('{end + timedelta(days=1)}', 0, 'days'))"
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
            "Paid", "Organizer", "Approved", "Archived",
        ],
    }
    records = []
    offset = None
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

    # Resolve organizer linked-record names in one batch
    org_ids = set()
    for r in records:
        for oid in r.get("fields", {}).get("Organizer", []):
            org_ids.add(oid)
    org_names = _fetch_org_names(org_ids)

    events = []
    for r in records:
        f = r.get("fields", {})
        org_id = (f.get("Organizer") or [None])[0]
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
    """Return {record_id: org_name} for a set of Airtable org record IDs."""
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


def fetch_subscriber_emails() -> list[str]:
    """Fetch emails from Contacts table where Weekly Email Subscriber is checked."""
    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Contacts"
    params = {
        "filterByFormula": "{Weekly Email Subscriber}",
        "fields[]": ["Email"],
    }
    emails = []
    offset = None
    while True:
        if offset:
            params["offset"] = offset
        resp = requests.get(url, headers=AT_HEADERS(), params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("records", []):
            email = r.get("fields", {}).get("Email", "").strip()
            if email:
                emails.append(email)
        offset = data.get("offset")
        if not offset:
            break
    return emails


# ── Event formatting ──────────────────────────────────────────────────────────

import re as _re

# Matches a street number followed by a street name — signals an address is present
_ADDRESS_RE = _re.compile(r",\s*\d+\s+\w")

def friendly_location(location: str) -> str:
    """Strip street address from location, keeping just the venue name.

    Rules:
    - "Venue Name, 123 Main St, City, ST 12345" → "Venue Name"
    - "123 Main St, City, ST" (no venue name) → "123 Main St, City"
    - "Venue Name" (no address) → "Venue Name"
    """
    if not location:
        return location
    parts = [p.strip() for p in location.split(",")]
    if len(parts) <= 1:
        return location

    # Check if first part looks like a street address (starts with a number)
    first_is_address = bool(_re.match(r"^\d+\s+", parts[0]))

    if first_is_address:
        # No venue name prefix — keep "number street, city" only
        # Find the city part: first non-address-looking segment after the street
        city = next((p for p in parts[1:] if not _re.match(r"^\d", p.strip())
                     and not _re.match(r"^[A-Z]{2}\b", p.strip())
                     and not _re.match(r"^\d{5}", p.strip())), None)
        if city:
            return f"{parts[0]}, {city.strip()}"
        return parts[0]
    else:
        # Venue name is first — check if there's an address after it
        has_address = any(bool(_re.match(r"^\d+\s+", p.strip())) for p in parts[1:])
        if has_address:
            return parts[0]
        return location


def shorten_description(desc: str, client) -> str:
    """If desc is more than one sentence, use Claude Haiku to summarize it in one sentence."""
    if not desc:
        return desc
    # Rough sentence count: split on period/exclamation/question followed by space or end
    sentences = _re.split(r"(?<=[.!?])\s+", desc.strip())
    if len(sentences) <= 1:
        return desc

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


def fmt_date_range(date_str: str, start_time: str, end_time: str) -> str:
    """Return e.g. 'Sunday, June 7 from 3:00pm–5:00pm'"""
    try:
        d = datetime.strptime(date_str, "%Y-%m-%d")
        day_str = d.strftime("%A, %B %-d")
    except ValueError:
        day_str = date_str

    def fmt_t(t: str) -> str:
        if not t:
            return ""
        try:
            dt = datetime.strptime(t, "%H:%M")
            if dt.minute == 0:
                return dt.strftime("%-I%p").lower()
            return dt.strftime("%-I:%M%p").lower()
        except ValueError:
            return t

    start = fmt_t(start_time)
    end   = fmt_t(end_time)
    if start and end:
        return f"{day_str} from {start}–{end}"
    elif start:
        return f"{day_str} at {start}"
    return day_str


def event_to_html(event: dict, client, is_last: bool = False) -> str:
    """Render a single event as an HTML block matching the spec."""
    name      = event["name"]
    organizer = event["organizer"]
    date_line = fmt_date_range(event["date"], event["start_time"], event["end_time"])
    location  = friendly_location(event["location"])
    desc      = shorten_description(event["description"], client)
    url       = event["source_url"]

    where_line = date_line
    if location:
        where_line += f" at {location}"

    lines = [
        f'<p style="margin:0 0 4px 0">👉 <strong>{name}</strong>{(" | " + organizer) if organizer else ""}</p>',
        f'<p style="margin:0 0 4px 0">🗓️ {where_line}</p>',
    ]
    if desc:
        lines.append(f'<p style="margin:0 0 4px 0">ℹ️ {desc}</p>')
    if url:
        lines.append(f'<p style="margin:0 0 4px 0"><a href="{url}">Learn more and RSVP &gt;&gt;</a></p>')
    else:
        lines[-1] = lines[-1].replace("margin:0 0 4px 0", "margin:0 0 8px 0")

    if not is_last:
        lines.append('<p style="margin:0 0 8px 0">--</p>')
    return "\n".join(lines)


# ── Claude opener ─────────────────────────────────────────────────────────────

def make_claude_client():
    if not ANTHROPIC_API_KEY:
        return None
    return anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def generate_opener(events: list[dict], send_date: date, client) -> str:
    """Use Claude Haiku to draft a one-sentence friendly opener."""
    if not client:
        return "Hope you're having a great week — lots of exciting events coming up!"

    event_names = [e["name"] for e in events[:8]]
    names_str   = "\n".join(f"- {n}" for n in event_names)
    week_str    = send_date.strftime("%B %-d")

    prompt = (
        f"You're writing a one-sentence opener for a weekly email newsletter called "
        f"Triangle Startup Events. The email goes out on {week_str}. "
        f"The tone is warm, welcoming, and enthusiastic — like a friendly community organizer. "
        f"Make it feel personal and excited about the week ahead. "
        f"Highlight ONE specific event from the list below (pick the most interesting-sounding one). "
        f"Keep it to a single sentence, no longer than 30 words.\n\n"
        f"Upcoming events this week:\n{names_str}\n\n"
        f"Write only the sentence, no quotes, no preamble."
    )

    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=100,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text.strip()


# ── HTML email builder ────────────────────────────────────────────────────────

SUBSCRIBE_URL = "https://airtable.com/apprt7MFT8PcVhFY4/pagz7K3Bc4Se3QGPC/form"
CALENDAR_URL  = "https://events.timscales.com"
DIVIDER       = '<p>—————————</p>'

def build_html_email(opener: str, free_events: list[dict], paid_events: list[dict], client) -> str:

    def section_html(header: str, events: list[dict]) -> str:
        if not events:
            return ""
        event_blocks = "\n".join(
            event_to_html(e, client, is_last=(i == len(events) - 1))
            for i, e in enumerate(events)
        )
        return (
            f'{DIVIDER}\n'
            f'<h2 style="font-size:20px;font-weight:bold">{header}</h2>\n'
            f'{event_blocks}'
        )

    # Intro block
    intro = (
        f'<p>Hey y\'all,</p>\n'
        f'<p>{opener}</p>\n'
        f'<p>Tim</p>\n'
        f'<p><em>ps — Forwarded this email? Subscribe <a href="{SUBSCRIBE_URL}">here</a>.</em></p>'
    )

    free_section = section_html("Upcoming Free Events", free_events)
    paid_section = section_html("Upcoming Paid Events", paid_events) if paid_events else ""

    # Footer: divider after last section, then calendar CTA
    footer = (
        f'{DIVIDER}\n'
        f'<p><strong>Want more events?</strong> '
        f'<a href="{CALENDAR_URL}">See all upcoming events on the calendar &gt;&gt;</a></p>'
    )

    body = "\n".join(s for s in [intro, free_section, paid_section, footer] if s)

    return f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body>
{body}
</body>
</html>"""


# ── Gmail draft ───────────────────────────────────────────────────────────────

def get_gmail_service():
    """Return an authenticated Gmail API service object."""
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        print("ERROR: Gmail dependencies not installed.")
        print("Run: pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client --break-system-packages")
        sys.exit(1)

    SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]
    creds = None

    if os.path.exists(GMAIL_TOKEN):
        creds = Credentials.from_authorized_user_file(GMAIL_TOKEN, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(GMAIL_CREDENTIALS):
                print(f"ERROR: Gmail credentials file not found at {GMAIL_CREDENTIALS}")
                print("Download OAuth2 credentials from Google Cloud Console and set GMAIL_CREDENTIALS_FILE.")
                sys.exit(1)
            flow = InstalledAppFlow.from_client_secrets_file(GMAIL_CREDENTIALS, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(GMAIL_TOKEN, "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def create_gmail_draft(
    service,
    bcc_addresses: list[str],
    subject: str,
    html_body: str,
) -> str:
    """Create a Gmail draft and return its ID."""
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = SENDER_EMAIL
    if bcc_addresses:
        msg["Bcc"] = ", ".join(bcc_addresses)

    msg.attach(MIMEText(html_body, "html"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    draft = service.users().drafts().create(
        userId="me",
        body={"message": {"raw": raw}},
    ).execute()
    return draft["id"]


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set")
        sys.exit(1)

    today     = date.today()
    end_date  = today + timedelta(days=EVENT_WINDOW_DAYS)
    week_str  = today.strftime("%B %-d")
    subject   = EMAIL_SUBJECT_TPL.format(date=week_str)

    print(f"Fetching events from {today} to {end_date}...")
    all_events = fetch_upcoming_events(today, end_date)
    free_events = [e for e in all_events if not e["paid"]]
    paid_events = [e for e in all_events if e["paid"]]
    print(f"  {len(free_events)} free, {len(paid_events)} paid")

    print("Fetching subscribers...")
    subscribers = fetch_subscriber_emails()
    print(f"  {len(subscribers)} subscribers")

    if not subscribers:
        print("WARNING: No subscribers found — draft will have no recipients.")

    client = make_claude_client()

    print("Generating opener with Claude Haiku...")
    opener = generate_opener(free_events + paid_events, today, client)
    print(f"  Opener: {opener}")

    print("Building HTML email...")
    html = build_html_email(opener, free_events, paid_events, client)

    print("Authenticating with Gmail...")
    service = get_gmail_service()

    print("Creating Gmail draft...")
    draft_id = create_gmail_draft(service, subscribers, subject, html)
    print(f"  Draft created: {draft_id}")
    print(f"  Subject: {subject}")
    print(f"  To: {SENDER_EMAIL}, BCC: {len(subscribers)} subscribers")
    print("Done. Open Gmail drafts to review and send.")


if __name__ == "__main__":
    main()
