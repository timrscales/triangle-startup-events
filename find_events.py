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
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = "apprt7MFT8PcVhFY4"
AIRTABLE_TABLE_NAME = "Events"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"

BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# Phase 1 sources — add new URLs here, or add a custom fetcher function for Phase 2
SOURCES = [
    "https://www.lilalearning.org/event-list",
    "https://www.1millioncups.com/s/account/0014W00002AqQfOQAV/durham-nc",
    "https://lu.ma/raleighdurhamstartupweek",
    "https://www.meetup.com/triangle-startup-collective/",
]

APPROVED_TAGS = [
    "networking", "fundraising", "pitch practice", "startup founders", "entrepreneurship",
    "technology", "AI", "life science", "small business", "happy hour", "panel discussion",
    "workshop", "mentorship", "investor relations", "marketing", "legal", "finance", "hiring",
]

MAX_PAGE_CHARS = 15000


def fetch_page_text(url: str, max_chars: int = MAX_PAGE_CHARS) -> str | None:
    """Render a URL with Playwright (headless Chromium) and return body text + links, or None on failure."""
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_USER_AGENT)
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(6000)  # Extra buffer for late-rendering JS
            text = page.inner_text("body")
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            browser.close()
    except Exception as exc:
        print(f"  ERROR fetching {url}: {exc}")
        return None

    lines = [line for line in text.splitlines() if line.strip()]
    cleaned = "\n".join(lines)

    if links:
        unique_links = list(dict.fromkeys(links))  # deduplicate, preserve order
        links_section = "\n\nLINKS FOUND ON PAGE:\n" + "\n".join(unique_links)
        cleaned = cleaned[:max_chars - len(links_section)] + links_section
    else:
        cleaned = cleaned[:max_chars]

    return cleaned


def is_luma_url(url: str) -> bool:
    return urlparse(url).netloc in ("lu.ma", "www.lu.ma")


def fetch_luma_events(calendar_url: str, today: str, end_date: str) -> list[dict]:
    """Fetch events directly from the Luma calendar API and map to our schema."""
    slug = urlparse(calendar_url).path.strip("/")
    api_url = f"https://api.lu.ma/calendar/get-items?calendar_api_id={slug}&pagination_limit=50"

    try:
        resp = requests.get(api_url, headers={"accept": "application/json"}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        print(f"  ERROR fetching Luma API for {calendar_url}: {exc}")
        return []

    entries = data.get("entries", [])
    print(f"  Luma API returned {len(entries)} entries for {calendar_url}")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for entry in entries:
        ev = entry.get("event", {})
        if not ev:
            continue

        start_raw = ev.get("start_at", "") or ""
        end_raw = ev.get("end_at", "") or ""

        try:
            start_dt = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            date_str = start_dt.strftime("%Y-%m-%d")
            start_time_str = start_dt.strftime("%H:%M")
        except (ValueError, AttributeError):
            date_str = ""
            start_time_str = "00:00"

        if date_str:
            event_date = datetime.strptime(date_str, "%Y-%m-%d")
            if event_date < today_dt or event_date > end_dt:
                continue

        try:
            end_dt_obj = datetime.fromisoformat(end_raw.replace("Z", "+00:00"))
            end_time_str = end_dt_obj.strftime("%H:%M")
        except (ValueError, AttributeError):
            end_time_str = ""

        geo = ev.get("geo_address_json") or ev.get("geo_address_info") or {}
        location = (
            geo.get("full_address")
            or geo.get("address")
            or geo.get("city")
            or ""
        )

        name = ev.get("name") or ev.get("title") or ""
        description = ev.get("description") or ev.get("description_md") or ""
        if isinstance(description, str) and len(description) > 500:
            description = description[:500].rsplit(" ", 1)[0] + "…"

        event_api_id = ev.get("api_id") or ev.get("url") or ""
        if event_api_id and not event_api_id.startswith("http"):
            source_url = f"https://lu.ma/{event_api_id}"
        elif event_api_id:
            source_url = event_api_id
        else:
            source_url = calendar_url

        events.append({
            "name": name.strip(),
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location.strip() if location else "",
            "topic_tags": ["networking", "startup founders"],
            "description": description.strip(),
            "source_url": source_url,
        })

    print(f"  Mapped {len(events)} in-range event(s) from Luma API")
    return events


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
        f"source_url (string). IMPORTANT: source_url must be the direct permalink URL for that "
        f"specific individual event — not the calendar or listing page URL ({source_url!r}). "
        f"Look for links in the page content that point to individual event pages "
        f"(e.g. paths like /event/xyz, /e/slug, /events/123, or full URLs on the same domain). "
        f"If you find such a link for an event, use it as source_url. "
        f"Only fall back to {source_url!r} if no individual event link exists. "
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


def enrich_event(event: dict, client: anthropic.Anthropic, today: str, calendar_url: str = "") -> dict:
    """Fetch the event's source_url and fill in missing date, start_time, end_time, location, description."""
    needs_start = str(event.get("start_time", "")).strip() in ("", "00:00")
    needs_end = str(event.get("end_time", "")).strip() == ""
    needs_date = str(event.get("date", "")).strip() == ""
    if not (needs_start or needs_end or needs_date):
        return event

    source_url = str(event.get("source_url", "")).strip()
    if not source_url:
        return event

    def _norm(u: str) -> str:
        return u.rstrip("/").lower()

    if _norm(source_url) == _norm(calendar_url) or _norm(source_url) in [_norm(s) for s in SOURCES]:
        event_name = str(event.get("name", "unknown")).strip()
        print(f"  SKIP ENRICH (source_url is a calendar page): {event_name!r}")
        return event

    event_name = str(event.get("name", "unknown")).strip()
    print(f"  Enriching: {event_name} from {source_url}")

    page_content = fetch_page_text(source_url, max_chars=8000)
    if not page_content:
        print(f"    ENRICH fetch failed for {source_url}")
        return event

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

    print(f"Sources configured: {SOURCES}")
    print(f"Processing {len(SOURCES)} source(s) ({today} → {end_date})…")
    all_events: list[dict] = []

    for url in SOURCES:
        print(f"Fetching: {url}")
        if is_luma_url(url):
            events = fetch_luma_events(url, today, end_date)
        else:
            page_text = fetch_page_text(url)
            if not page_text:
                print(f"  SKIP (fetch failed or empty): {url}")
                continue
            print(f"  Got {len(page_text)} chars — sending to Claude…")
            events = extract_events_from_text(client, page_text, url, today, end_date)
        for event in events:
            event["_calendar_url"] = url  # track origin for enrichment guard
        all_events.extend(events)

    print(f"\nTotal events found: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    print("Enriching events with missing time/location details…")
    enriched_events: list[dict] = []
    for event in all_events:
        calendar_url = event.pop("_calendar_url", "")
        enriched = enrich_event(event, client, today, calendar_url=calendar_url)
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
