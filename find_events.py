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

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = "apprt7MFT8PcVhFY4"
AIRTABLE_TABLE_NAME = "Events"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"

# Phase 1 sources — add new URLs here, or add a new fetcher function for Phase 2 (Eventbrite, Meetup)
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


def fetch_events_from_url(client: anthropic.Anthropic, url: str, today: str, end_date: str) -> list[dict]:
    """Ask Claude to fetch and parse events from a single URL."""
    prompt = (
        f"Fetch and read this page: {url}. "
        f"Extract all upcoming in-person events and return ONLY a valid JSON array. "
        f"Each object must have: name (string), date (YYYY-MM-DD), start_time (HH:MM or 00:00), "
        f"end_time (HH:MM or empty string), location (string), "
        f"topic_tags (array, only use: {', '.join(APPROVED_TAGS)}), "
        f"description (1-3 sentences), source_url (the RSVP or event detail URL). "
        f"Only include events from today {today} through {end_date}. "
        f"Return [ ] if no events found. Start response with [ and end with ]."
    )

    messages = [{"role": "user", "content": prompt}]
    collected_text = ""

    for _ in range(10):
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            tools=[{"type": "web_search_20260209", "name": "web_search", "allowed_callers": ["direct"]}],
            messages=messages,
        )

        if response.stop_reason == "end_turn":
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    collected_text += block.text
            break

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    collected_text += block.text
            continue

        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                collected_text += block.text
        break

    events = parse_events(collected_text)
    print(f"  Found {len(events)} event(s) from {url}")
    return events


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

    print(f"Fetching events from {len(SOURCES)} source(s) ({today} → {end_date})…")
    all_events: list[dict] = []
    for url in SOURCES:
        print(f"Fetching: {url}")
        events = fetch_events_from_url(client, url, today, end_date)
        all_events.extend(events)

    print(f"\nTotal events found: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    print("Fetching existing Airtable events…")
    existing = get_existing_events()
    print(f"Airtable has {len(existing)} existing event(s).")

    added = skipped = errors = 0

    for event in all_events:
        ok, reason = is_valid_event(event)
        if not ok:
            print(f"  SKIP (invalid — {reason}): {event}")
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
