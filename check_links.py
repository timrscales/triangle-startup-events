#!/usr/bin/env python3
"""
Dead link checker for Triangle Startup Events + Grants & Programs.

Pulls all upcoming approved, non-archived events from Airtable and checks
each Source URL. Also checks Program URLs for Active/Unverified programs.
Handles soft-404s from Luma and Meetup (which return HTTP 200 but show
"event not found" pages). Sends an email to Tim only if dead links are found.

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
from urllib.parse import urlparse

# ── Config ────────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"
GMAIL_CREDENTIALS = os.environ.get("GMAIL_CREDENTIALS_FILE", "gmail_credentials.json")
GMAIL_TOKEN       = os.environ.get("GMAIL_TOKEN_FILE", "gmail_token.json")
SENDER_EMAIL      = "tim@timscales.com"

AIRTABLE_PROGRAMS_TABLE = "tblyikQu0nqYi43YN"

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


def _is_same_domain_redirect(original_url: str, final_url: str) -> bool:
    """Return True if the redirect is just http→https or non-www↔www on the same domain."""
    try:
        orig = urlparse(original_url)
        final = urlparse(final_url)
        orig_host  = orig.netloc.lower().lstrip("www.")
        final_host = final.netloc.lower().lstrip("www.")
        return orig_host == final_host
    except Exception:
        return False


def _is_js_shell(resp: requests.Response) -> bool:
    """Return True if the response looks like a JS-only shell with no real text content."""
    content_type = resp.headers.get("Content-Type", "")
    if "text/html" not in content_type:
        return False
    text = resp.text[:10000]
    # Very little visible text but a lot of script tags = JS shell
    script_count = text.lower().count("<script")
    visible_text = re.sub(r"<[^>]+>", " ", text)
    visible_text = re.sub(r"\s+", " ", visible_text).strip()
    return script_count >= 3 and len(visible_text) < 200


def check_url_with_retry(url: str) -> tuple[bool, str, bool]:
    """
    Check a URL with one retry on failure.
    Returns (is_dead, reason, is_js_shell).
    is_js_shell=True means the page may render via JS — don't mark dead, note retry.
    """
    for attempt in range(2):
        try:
            resp = requests.get(
                url,
                headers=BROWSER_HEADERS,
                timeout=REQUEST_TIMEOUT,
                allow_redirects=True,
            )
        except requests.exceptions.Timeout:
            if attempt == 0:
                continue
            return True, "Request timed out", False
        except requests.exceptions.ConnectionError as e:
            if attempt == 0:
                continue
            return True, f"Connection error: {e}", False
        except requests.exceptions.RequestException as e:
            if attempt == 0:
                continue
            return True, f"Request error: {e}", False

        # Treat same-domain http→https or www redirects as OK
        if resp.history and _is_same_domain_redirect(url, resp.url):
            pass  # continue to content checks

        if resp.status_code >= 400:
            if attempt == 0:
                continue
            return True, f"HTTP {resp.status_code}", False

        content_type = resp.headers.get("Content-Type", "")
        if "text/html" in content_type:
            if _is_js_shell(resp):
                return False, "JS shell — no real text", True
            text = resp.text[:50_000]
            match = _check_soft_404(text)
            if match:
                if attempt == 0:
                    continue
                return True, f'Soft-404 — page contains: "{match}"', False

        return False, "OK", False

    return False, "OK", False


# ── Programs link checking ─────────────────────────────────────────────────────

def fetch_programs_to_check() -> list[dict]:
    """Fetch Active and Unverified programs from the Grants & Programs table."""
    url     = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_PROGRAMS_TABLE}"
    formula = "OR({Status}='Active', {Status}='Unverified')"
    params  = {
        "filterByFormula": formula,
        "fields[]": ["Program Name", "Program URL", "Status",
                     "Application Deadline", "Pending Changes"],
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

    programs = []
    for r in records:
        f   = r.get("fields", {})
        src = f.get("Program URL", "").strip()
        if src:
            programs.append({
                "id":               r["id"],
                "name":             f.get("Program Name", ""),
                "status":           f.get("Status", ""),
                "program_url":      src,
                "deadline":         f.get("Application Deadline", ""),
                "pending_changes":  f.get("Pending Changes", ""),
            })
    return programs


def _append_pending_change(existing: str, note: str) -> str:
    """Append a dated note to Pending Changes without overwriting."""
    today = date.today().isoformat()
    new_note = f"[{today}] {note}"
    if existing:
        return existing.rstrip() + "\n" + new_note
    return new_note


def _update_program_record(record_id: str, fields: dict) -> None:
    """PATCH a program record in Airtable."""
    url     = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_PROGRAMS_TABLE}/{record_id}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type":  "application/json",
    }
    resp = requests.patch(url, headers=headers, json={"fields": fields}, timeout=30)
    resp.raise_for_status()


def check_programs() -> list[dict]:
    """Check Program URLs and deadline freshness; update Airtable records in place."""
    programs = fetch_programs_to_check()
    print(f"  {len(programs)} program(s) to check")

    dead_programs = []
    today = date.today()

    for i, prog in enumerate(programs, 1):
        url  = prog["program_url"]
        name = prog["name"]
        print(f"  [{i}/{len(programs)}] {name[:50]}…")

        is_dead, reason, is_js_shell = check_url_with_retry(url)

        update_fields: dict = {"Last Verified": today.isoformat()}
        pending = prog["pending_changes"]

        if is_dead:
            print(f"    DEAD: {reason}")
            update_fields["Status"] = "Dead Link"
            pending = _append_pending_change(pending, f"Dead link: {reason}")
            dead_programs.append({**prog, "reason": reason})
        elif is_js_shell:
            print(f"    JS shell — noting retry next week")
            pending = _append_pending_change(pending, "JS shell with no real text — retry next week")
        else:
            print(f"    OK")

        # Deadline freshness check
        deadline_str = prog.get("deadline", "").strip()
        if deadline_str:
            try:
                # Airtable date fields come back as YYYY-MM-DD
                deadline_date = date.fromisoformat(deadline_str[:10])
                if deadline_date < today:
                    pending = _append_pending_change(
                        pending,
                        f"DEADLINE PASSED {deadline_str[:10]}: verify next cycle",
                    )
            except ValueError:
                pass

        if pending != prog["pending_changes"]:
            update_fields["Pending Changes"] = pending

        try:
            _update_program_record(prog["id"], update_fields)
        except Exception as exc:
            print(f"    WARNING: Could not update program record {prog['id']}: {exc}")

    return dead_programs


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


def send_alert(service, dead_links: list[dict], dead_programs: list[dict]) -> None:
    total   = len(dead_links) + len(dead_programs)
    subject = f"⚠️ {total} dead link{'s' if total > 1 else ''} — Triangle Startup Events"

    lines = []

    if dead_links:
        count = len(dead_links)
        lines.append(f"{count} upcoming event{'s have' if count > 1 else ' has'} a broken Source URL:\n")
        for item in dead_links:
            lines.append(f"• {item['name']} ({item['date']})")
            lines.append(f"  URL: {item['source_url']}")
            lines.append(f"  Reason: {item['reason']}")
            lines.append("")

    if dead_programs:
        count = len(dead_programs)
        lines.append(f"{count} program{'s have' if count > 1 else ' has'} a broken Program URL:\n")
        for item in dead_programs:
            lines.append(f"• {item['name']}")
            lines.append(f"  URL: {item['program_url']}")
            lines.append(f"  Reason: {item['reason']}")
            lines.append("")

    lines.append("Review and update in Airtable:")
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
            print(f"    DEAD: {reason}")
            dead_links.append({**event, "reason": reason})
        else:
            print(f"    OK")

    print(f"\n{len(dead_links)} dead event link(s) found.")

    print("\nChecking Grants & Programs URLs...")
    dead_programs = check_programs()
    print(f"{len(dead_programs)} dead program link(s) found.")

    if not dead_links and not dead_programs:
        print("No email sent.")
        return

    print("Authenticating with Gmail...")
    service = get_gmail_service()
    print("Sending alert email...")
    send_alert(service, dead_links, dead_programs)
    print("Done.")


if __name__ == "__main__":
    main()
