#!/usr/bin/env python3
"""
Dead link checker for Triangle Startup Events.

Pulls all upcoming approved, non-archived events from Airtable and checks
each Source URL. Handles soft-404s from Luma and Meetup (which return HTTP
200 but show "event not found" pages). Sends an email to Tim only if dead
links are found.

Required env vars:
  AIRTABLE_API_KEY
  GMAIL_CREDENTIALS_FILE
  GMAIL_TOKEN_FILE  (defaults to gmail_token.json)
"""
from __future__ import annotations

import base64
import os
import re
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

REQUEST_TIMEOUT   = 15  # seconds per URL
EVENT_WINDOW_DAYS = 30  # how far ahead to check

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# ── Airtable ──────────────────────────────────────────────────────────────────

AT_HEADERS = lambda: {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}


def fetch_upcoming_events() -> list[dict]:
    """Fetch approved, non-archived upcoming events with their Source URLs."""
    url      = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Events"
    today    = date.today()
    end_date = today + timedelta(days=EVENT_WINDOW_DAYS)
    formula  = (
        f"AND("
        f"{{Approved}}, "
        f"NOT({{Archived}}), "
        f"IS_AFTER({{Date}}, DATEADD('{today - timedelta(days=1)}', 0, 'days')), "
        f"IS_BEFORE({{Date}}, DATEADD('{end_date + timedelta(days=1)}', 0, 'days'))"
        f")"
    )
    params = {
        "filterByFormula": formula,
        "fields[]": ["Name", "Date", "Source URL"],
        "sort[0][field]": "Date",
        "sort[0][direction]": "asc",
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

    events = []
    for r in records:
        f = r.get("fields", {})
        src = f.get("Source URL", "").strip()
        if src:
            events.append({
                "id":         r["id"],
                "name":       f.get("Name", ""),
                "date":       f.get("Date", ""),
                "source_url": src,
            })
    return events


# ── Link checking ─────────────────────────────────────────────────────────────

# Patterns in page text that indicate a soft-404
_SOFT_404_PATTERNS = [
    # Luma
    re.compile(r"this event (has been |is )?(cancelled|removed|deleted|ended)", re.I),
    re.compile(r"event (not found|no longer available|has passed)", re.I),
    re.compile(r"page (not found|doesn.t exist)", re.I),
    # Meetup
    re.compile(r"(this group|this event) (no longer exists|has been removed|doesn.t exist)", re.I),
    re.compile(r"we couldn.t find (that page|this event)", re.I),
    # Generic — require "404" to appear in an error context, not just anywhere on the page
    re.compile(r"(error|http)\s*404", re.I),
    re.compile(r"404\s*(not found|error|page)", re.I),
    re.compile(r"(oops|uh.?oh)[^.]*not found", re.I),
]


def _check_soft_404(text: str) -> str | None:
    """Return matching pattern string if page looks like a soft-404, else None."""
    for pattern in _SOFT_404_PATTERNS:
        m = pattern.search(text)
        if m:
            return m.group(0)
    return None


def check_url(url: str) -> tuple[bool, str]:
    """
    Check a single URL. Returns (is_dead, reason).
    is_dead=True means the link is broken.
    """
    try:
        resp = requests.get(
            url,
            headers=BROWSER_HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )
    except requests.exceptions.Timeout:
        return True, "Request timed out"
    except requests.exceptions.ConnectionError as e:
        return True, f"Connection error: {e}"
    except requests.exceptions.RequestException as e:
        return True, f"Request error: {e}"

    # Hard HTTP errors
    if resp.status_code >= 400:
        return True, f"HTTP {resp.status_code}"

    # Soft-404: page returned 200 but content signals it's gone
    # Only check text/html responses, and cap at 50KB to keep it fast
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" in content_type:
        text = resp.text[:50_000]
        match = _check_soft_404(text)
        if match:
            return True, f'Soft-404 — page contains: "{match}"'

    return False, "OK"


# ── Email ─────────────────────────────────────────────────────────────────────

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


def send_alert(service, dead_links: list[dict]) -> None:
    count   = len(dead_links)
    subject = f"⚠️ {count} dead link{'s' if count > 1 else ''} — Triangle Startup Events"

    lines = [f"{count} upcoming event{'s have' if count > 1 else ' has'} a broken Source URL:\n"]
    for item in dead_links:
        lines.append(f"• {item['name']} ({item['date']})")
        lines.append(f"  URL: {item['source_url']}")
        lines.append(f"  Reason: {item['reason']}")
        lines.append("")

    lines.append("Archive or update these events in Airtable:")
    lines.append(f"https://airtable.com/{AIRTABLE_BASE_ID}")

    body = "\n".join(lines)
    html = (
        f'<html><body>'
        f'<pre style="font-family:Arial,sans-serif;font-size:14px;white-space:pre-wrap">{body}</pre>'
        f'</body></html>'
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = SENDER_EMAIL
    msg["To"]      = SENDER_EMAIL
    msg.attach(MIMEText(body, "plain", "utf-8"))
    msg.attach(MIMEText(html,  "html",  "utf-8"))

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
    service.users().messages().send(userId="me", body={"raw": raw}).execute()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not AIRTABLE_API_KEY:
        print("ERROR: AIRTABLE_API_KEY not set")
        sys.exit(1)

    print("Fetching upcoming events from Airtable...")
    events = fetch_upcoming_events()
    print(f"  {len(events)} events to check")

    dead_links = []
    for i, event in enumerate(events, 1):
        url  = event["source_url"]
        name = event["name"]
        print(f"  [{i}/{len(events)}] {name[:50]}...")
        is_dead, reason = check_url(url)
        if is_dead:
            print(f"    ❌ DEAD: {reason}")
            dead_links.append({**event, "reason": reason})
        else:
            print(f"    ✓ OK")

    print(f"\n{len(dead_links)} dead link(s) found.")

    if not dead_links:
        print("No email sent.")
        return

    print("Authenticating with Gmail...")
    service = get_gmail_service()
    print("Sending alert email...")
    send_alert(service, dead_links)
    print("Done.")


if __name__ == "__main__":
    main()
