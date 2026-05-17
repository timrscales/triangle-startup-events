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


def search_events() -> str:
    """Call Claude with web search to find startup events, then format as JSON."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")

    # First call: search the web for events
    search_prompt = f"""Search the web for free in-person events for startup founders and entrepreneurs in Raleigh, Durham, Chapel Hill, Cary, and Research Triangle Park, North Carolina between {today} and {end_date}.

Search Meetup.com, lu.ma, eventbrite.com, nctech.org, ffvcnc.org, americanunderground.com, wraltechwire.com, and any other relevant local sources.

List every free in-person startup or entrepreneur event you find with as much detail as possible: name, date, time, location, description, and URL."""

    messages = [{"role": "user", "content": search_prompt}]
    raw_text = ""

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
                    raw_text += block.text
            break

        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            for block in response.content:
                if hasattr(block, "type") and block.type == "text":
                    raw_text += block.text
            continue

        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                raw_text += block.text
        break

    print(f"DEBUG raw search text length: {len(raw_text)} chars")
    print(f"DEBUG raw search preview: {raw_text[:500]}")

    if not raw_text:
        return "[]"

    # Second call: format the raw text as clean JSON
    format_prompt = f"""Convert the following event information into a JSON array. Return ONLY the JSON array starting with [ and ending with ]. No other text before or after.

Each event object must have these exact keys:
  "name", "date" (YYYY-MM-DD), "start_time" (HH:MM or "00:00"), "end_time" (HH:MM or ""), "location", "topic_tags" (array of strings), "description", "source_url"

Only include free in-person events for startup founders or entrepreneurs in the Triangle NC area between {today} and {end_date}.
If a field is unknown use your best estimate. Never omit an event just because some fields are missing.

Event information to convert:
{raw_text}"""

    format_response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        messages=[{"role": "user", "content": format_prompt}],
    )

    for block in format_response.content:
        if hasattr(block, "type") and block.type == "text":
            print(f"DEBUG format response preview: {block.text[:500]}")
            return block.text

    return "[]"


def parse_events(text: str) -> list[dict]:
    """Extract the JSON events array from Claude's response text."""
    text = text.strip()

    # Try direct parse first
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
    except (json.JSONDecodeError, ValueError):
        pass

    # Try extracting from markdown code blocks
    match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", text)
    if match:
        try:
            data = json.loads(match.group(1))
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    # Find the first [ and last ] and extract everything between
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end+1])
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    print(f"WARNING: Could not parse JSON from response:\n{text[:800]}")
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

    print("Searching for events via Claude + web search…")
    raw = search_events()

    events = parse_events(raw)
    print(f"Claude returned {len(events)} event(s).")

    if not events:
        print("Nothing to add.")
        return

    print("Fetching existing Airtable events…")
    existing = get_existing_events()
    print(f"Airtable has {len(existing)} existing event(s).")

    added = skipped = errors = 0

    for event in events:
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
