#!/usr/bin/env python3
"""Find free startup events in the NC Triangle area and sync to Airtable."""

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta

import anthropic
import requests
from bs4 import BeautifulSoup

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = "apprt7MFT8PcVhFY4"
AIRTABLE_TABLE_NAME = "Events"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

# Phase 1 sources — add new URLs here, or add a custom fetcher function for Phase 2
SOURCES = [
    "https://www.lilalearning.org/event-list",
    "https://www.1millioncups.com/s/account/0014W00002AqQfOQAV/durham-nc",
    "https://lu.ma/raleighdurhamstartupweek",
]

APPROVED_TAGS = [
    "networking", "fundraising", "pitch practice", "startup founders", "entrepreneurship",
    "technology", "AI", "life science", "small business", "happy hour", "panel discussion",
    "workshop", "mentorship", "investor relations", "marketing", "legal", "finance", "hiring",
]

MAX_PAGE_CHARS = 15000


def fetch_page_text(url: str) -> str | None:
    """Fetch a URL and return cleaned body text, or None on failure."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  ERROR fetching {url}: {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)

    return cleaned[:MAX_PAGE_CHARS]


def extract_events_from_text(
    client: anthropic.Anthropic,
    page_text: str,
    source_url: str,
    today: str,
    end_date: str,
) -> list[dict]:
    """Send page text to Claude and extract structured event data."""
    prompt = (
        f"Extract all upcoming in-person events from this page content. "
        f"Today is {today}. Only include events between {today} and {end_date}. "
        f"Return ONLY a valid JSON array starting with [ and ending with ]. "
        f"Each object must have: name (string), date (YYYY-MM-DD), "
        f"start_time (HH:MM or 00:00 if unknown), end_time (HH:MM or empty string), "
        f"location (string), "
        f"topic_tags (array using only: {', '.join(APPROVED_TAGS)}), "
        f"description (1-3 sentences), "
        f"source_url (direct RSVP link if found, otherwise {source_url!r}). "
        f"For each event, the source_url must be the direct URL to that specific event's detail page, "
        f"not the calendar page URL. If you can find individual event links on the page, use those. "
        f"If not, use the source URL as fallback. "
        f"Return [] if no upcoming events found.\n\n"
        f"Page content:\n{page_text}"
    )

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}],
    )

    text = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            text += block.text

    events = parse_events(text)
    print(f"  Extracted {len(events)} event(s) from {source_url}")
    return events


def enrich_event(event: dict, client: anthropic.Anthropic, today: str) -> dict:
    """Fetch the event's source_url and fill in missing date, start_time, end_time, location, description."""
    needs_start = str(event.get("start_time", "")).strip() in ("", "00:00")
    needs_end = str(event.get("end_time", "")).strip() == ""
    needs_date = str(event.get("date", "")).strip() == ""
    if not (needs_start or needs_end or needs_date):
        return event

    source_url = str(event.get("source_url", "")).strip()
    if not source_url:
        return event

    event_name = str(event.get("name", "unknown")).strip()
    print(f"  Enriching: {event_name} from {source_url}")

    try:
        resp = requests.get(source_url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    ENRICH fetch failed for {source_url}: {exc}")
        return event

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [line for line in text.splitlines() if line.strip()]
    page_content = "\n".join(lines)[:8000]

    print(f"  Got {len(page_content)} chars from detail page")

    prompt = (
        "Extract event details from this page content and return ONLY a valid JSON object "
        "with these fields: name (string or empty), date (YYYY-MM-DD or empty string if not found), "
        "start_time (HH:MM 24-hour format or empty string if not found), "
        "end_time (HH:MM 24-hour format or empty string if not found), "
        "location (venue name and address or empty string), "
        "description (1-3 sentence summary or empty string). "
        "Return only the JSON object, nothing else.\n\n"
        f"Page content:\n{page_content}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=512,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"    ENRICH Claude call failed: {exc}")
        return event

    raw = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            raw += block.text

    raw = raw.strip()
    print(f"  Enrichment result: {raw[:500]}")

    start = raw.find("{")
    end = raw.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return event

    try:
        details = json.loads(raw[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return event

    if not isinstance(details, dict):
        return event

    enriched = dict(event)
    if needs_date and details.get("date", "").strip():
        enriched["date"] = details["date"].strip()
    if needs_start and details.get("start_time", "").strip():
        enriched["start_time"] = details["start_time"].strip()
    if needs_end and details.get("end_time", "").strip():
        enriched["end_time"] = details["end_time"].strip()
    for field in ("location", "description"):
        if not str(enriched.get(field, "")).strip() and details.get(field, "").strip():
            enriched[field] = details[field].strip()

    return enriched


def parse_events(text: str) -> list[dict]:
    """Extract the JSON events array from a text response."""
    text = text.strip()

    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    if text:
        print(f"  WARNING: Could not parse JSON:\n  {text[:400]}")
    return []


def get_existing_events() -> set[tuple[str, str]]:
    """Return a set of (lowercased_name, date) tuples for all events in Airtable."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params = {"fields[]": ["Name", "Date"]}
    existing: set[tuple[str, str]] = set()

    while True:
        resp = requests.get(AIRTABLE_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        for record in data.get("records", []):
            fields = record.get("fields", {})
            name = fields.get("Name", "").lower().strip()
            date = fields.get("Date", "").strip()
            if name and date:
                existing.add((name, date))

        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset

    return existing


def create_event_record(event: dict) -> dict:
    """Create a new Airtable record for the given event."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    fields: dict = {
        "Name": str(event.get("name", "")).strip(),
        "Date": str(event.get("date", "")).strip(),
        "Start Time": str(event.get("start_time", "")).strip(),
        "Location": str(event.get("location", "")).strip(),
        "Description": str(event.get("description", "")).strip(),
        "Source URL": str(event.get("source_url", "")).strip(),
    }

    end_time = str(event.get("end_time", "")).strip()
    if end_time:
        fields["End Time"] = end_time

    tags = event.get("topic_tags")
    if isinstance(tags, list) and tags:
        fields["Topic Tags"] = [str(t).strip() for t in tags if str(t).strip()]

    resp = requests.post(AIRTABLE_URL, headers=headers, json={"fields": fields}, timeout=30)
    resp.raise_for_status()
    return resp.json()


def is_valid_event(event: dict) -> tuple[bool, str]:
    """Return (True, '') if event dict is usable, else (False, reason)."""
    if not isinstance(event, dict):
        return False, "not a dict"
    name = str(event.get("name", "")).strip()
    date = str(event.get("date", "")).strip()
    if not name:
        return False, "empty name"
    if not date:
        return False, "empty date"
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return False, f"bad date format: {date!r}"
    return True, ""


def main():
    if not ANTHROPIC_API_KEY:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")
    if not AIRTABLE_API_KEY:
        sys.exit("ERROR: AIRTABLE_API_KEY is not set.")

    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"Processing {len(SOURCES)} source(s) ({today} → {end_date})…")
    all_events: list[dict] = []

    for url in SOURCES:
        print(f"Fetching: {url}")
        page_text = fetch_page_text(url)
        if not page_text:
            continue
        print(f"  Got {len(page_text)} chars — sending to Claude…")
        events = extract_events_from_text(client, page_text, url, today, end_date)
        all_events.extend(events)

    print(f"\nTotal events found: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    print("Enriching events with missing time/location details…")
    enriched_events: list[dict] = []
    for event in all_events:
        enriched = enrich_event(event, client, today)
        enriched_events.append(enriched)
        time.sleep(0.5)
    all_events = enriched_events

    print("Fetching existing Airtable events…")
    existing = get_existing_events()
    print(f"Airtable has {len(existing)} existing event(s).")

    added = skipped = errors = 0

    for event in all_events:
        ok, reason = is_valid_event(event)
        if not ok:
            name = event.get("name", "unknown") if isinstance(event, dict) else "unknown"
            src = event.get("source_url", "") if isinstance(event, dict) else ""
            print(f"  SKIP (invalid — {reason}): {name!r}  source_url={src}")
            skipped += 1
            continue

        key = (event["name"].lower().strip(), event["date"].strip())
        if key in existing:
            print(f"  SKIP (duplicate): {event['name']} on {event['date']}")
            skipped += 1
            continue

        try:
            create_event_record(event)
            print(f"  ADDED: {event['name']} on {event['date']}")
            existing.add(key)
            added += 1
            time.sleep(0.25)  # Stay within Airtable's 5 req/s limit
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            print(f"  ERROR adding {event.get('name')!r}: {exc}  —  {body[:300]}")
            errors += 1

    print(f"\nFinished. Added: {added} | Skipped: {skipped} | Errors: {errors}")


if __name__ == "__main__":
    main()
