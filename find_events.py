#!/usr/bin/env python3
"""Find free startup events in the NC Triangle area and sync to Airtable."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

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

APPROVED_TAGS = [
    "networking", "fundraising", "pitch practice", "startup founders", "entrepreneurship",
    "technology", "AI", "life science", "small business", "happy hour", "panel discussion",
    "workshop", "mentorship", "investor relations", "marketing", "legal", "finance", "hiring",
    "celebration",
]


# ── Lila Learning ─────────────────────────────────────────────────────────────

def fetch_lila_events(today: str, end_date: str) -> list[dict]:
    """Scrape Lila Learning event list, then fetch each detail page."""
    list_url = "https://www.lilalearning.org/event-list"
    try:
        resp = requests.get(list_url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): Lila Learning — {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Collect unique event detail URLs in page order
    seen: set[str] = set()
    detail_urls: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"/event-details/")):
        href = a.get("href", "").strip()
        if href and href not in seen:
            seen.add(href)
            detail_urls.append(href)

    print(f"  Lila: {len(detail_urls)} event detail page(s) found")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for url in detail_urls:
        event = _parse_lila_detail(url, today_dt, end_dt)
        if event:
            events.append(event)
        time.sleep(0.4)

    print(f"  Lila: {len(events)} in-range in-person event(s)")
    return events


def _parse_lila_detail(url: str, today_dt: datetime, end_dt: datetime) -> dict | None:
    """Fetch and parse a single Lila event detail page."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    SKIP (fetch failed): {url} — {exc}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")

    # Event name from page title
    title_tag = soup.find("title")
    name = ""
    if title_tag:
        raw = title_tag.get_text(strip=True)
        name = raw.split("|")[0].strip()
    if not name:
        h1 = soup.find("h1")
        name = h1.get_text(strip=True) if h1 else url.split("/")[-1].replace("-", " ").title()

    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    # Skip virtual events
    if re.search(r"\bvirtual\b|\bonline\b|\bwebinar\b", text[:600], re.I):
        print(f"    SKIP (virtual): {name}")
        return None

    # Find date/time: "Jun 02, 2026, 4:30 PM – 6:30 PM"
    dt_match = re.search(
        r"(\w+ \d{1,2}, \d{4}),\s*(\d{1,2}:\d{2}\s*[AP]M)\s*[–\-]+\s*(\d{1,2}:\d{2}\s*[AP]M)",
        text,
    )
    if not dt_match:
        print(f"    SKIP (no date/time found): {name}")
        return None

    try:
        event_dt = datetime.strptime(dt_match.group(1), "%b %d, %Y")
    except ValueError:
        print(f"    SKIP (bad date): {dt_match.group(1)!r}")
        return None

    if event_dt < today_dt or event_dt > end_dt:
        return None

    date_fmt = event_dt.strftime("%Y-%m-%d")

    try:
        start_time = datetime.strptime(dt_match.group(2).strip(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        start_time = "00:00"

    try:
        end_time = datetime.strptime(dt_match.group(3).strip(), "%I:%M %p").strftime("%H:%M")
    except ValueError:
        end_time = ""

    # Location: prefer full address, fall back to venue name
    addr_match = re.search(
        r"\d+\s+\w[^\n]{5,80},\s+\w[^\n]{2,40}(?:NC|North Carolina)[^\n]{0,20}\d{5}", text
    )
    if addr_match:
        location = addr_match.group(0).strip()
    else:
        loc_match = re.search(
            r"(?:Frontier RTP|American Underground|HQ Raleigh|Launch Chapel Hill|"
            r"[A-Z][^.!\n]{3,60},\s+(?:Raleigh|Durham|Chapel Hill|Cary|RTP)[^.!\n]{0,40})",
            text,
        )
        location = loc_match.group(0).strip() if loc_match else ""

    if not location or "tbd" in location.lower():
        print(f"    NOTE: No confirmed location for {name} — including with empty location")

    # Description: "About the event" section
    about_idx = text.find("About the event")
    if about_idx != -1:
        desc_raw = text[about_idx + len("About the event"):about_idx + 500].strip()
        desc_lines = [l for l in desc_raw.splitlines() if l.strip()]
        description = " ".join(desc_lines[:3])[:350]
    else:
        lines = [l for l in text.splitlines() if l.strip()]
        description = " ".join(lines[4:8])[:350]

    tags = ["startup founders", "entrepreneurship"]
    if re.search(r"\bpitch\b|\bpitching\b", text, re.I):
        tags.append("pitch practice")
    if re.search(r"\binvest\b", text, re.I):
        tags.append("investor relations")
    if re.search(r"\bnetwork\b", text, re.I):
        tags.append("networking")
    if re.search(r"\bworkshop\b|\bhands.on\b", text, re.I):
        tags.append("workshop")

    return {
        "name": name,
        "date": date_fmt,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "topic_tags": list(dict.fromkeys(tags)),
        "description": description,
        "source_url": url,
    }


# ── Luma ──────────────────────────────────────────────────────────────────────

def _fetch_luma_event_description(event_url: str) -> str:
    """Fetch a native Luma event page and extract its About section."""
    try:
        resp = requests.get(event_url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    about_idx = text.find("About Event")
    if about_idx == -1:
        about_idx = text.find("About the Event")
    if about_idx != -1:
        snippet = text[about_idx + len("About Event"):about_idx + 600].strip()
        lines = [l for l in snippet.splitlines() if l.strip() and not l.strip().startswith("​")]
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(lines[:8]))
        return " ".join(sentences[:3])[:400]
    return ""


def fetch_luma_events(calendar_url: str, today: str, end_date: str) -> list[dict]:
    """Get the real Luma calendar API ID from the page, then call the API."""
    try:
        resp = requests.get(calendar_url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): Luma — {exc}")
        return []

    match = re.search(r'"api_id":"(cal-[^"]+)"', resp.text)
    if not match:
        print(f"  SKIP: Could not find Luma calendar API ID in page")
        return []

    cal_api_id = match.group(1)
    print(f"  Luma calendar API ID: {cal_api_id}")

    api_url = f"https://api.lu.ma/calendar/get-items?calendar_api_id={cal_api_id}&pagination_limit=50"
    try:
        api_resp = requests.get(api_url, headers={"accept": "application/json"}, timeout=30)
        api_resp.raise_for_status()
        data = api_resp.json()
    except Exception as exc:
        print(f"  SKIP: Luma API call failed — {exc}")
        return []

    entries = data.get("entries", [])
    print(f"  Luma API: {len(entries)} total entries")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for entry in entries:
        ev = entry.get("event", {})
        if not ev:
            continue

        start_raw = ev.get("start_at", "") or ""
        try:
            start_utc = datetime.fromisoformat(start_raw.replace("Z", "+00:00"))
            # Convert to Eastern (EDT = UTC-4)
            start_local = start_utc.astimezone(timezone(timedelta(hours=-4)))
            date_str = start_local.strftime("%Y-%m-%d")
            start_time_str = start_local.strftime("%H:%M")
        except (ValueError, AttributeError):
            continue

        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        if event_date < today_dt or event_date > end_dt:
            continue

        # End time from duration_interval ISO 8601
        end_time_str = ""
        duration = ev.get("duration_interval", "")
        if duration:
            dur_match = re.match(r"P.*?T(?:(\d+)H)?(?:(\d+)M)?", duration)
            if dur_match:
                hours = int(dur_match.group(1) or 0)
                minutes = int(dur_match.group(2) or 0)
                end_local = start_local + timedelta(hours=hours, minutes=minutes)
                end_time_str = end_local.strftime("%H:%M")

        geo = ev.get("geo_address_json") or ev.get("geo_address_info") or {}
        location = geo.get("address") or geo.get("full_address") or geo.get("city") or ""

        name = (ev.get("name") or ev.get("title") or "").strip()

        raw_url = ev.get("url") or ""
        if raw_url.startswith("http"):
            source_url = raw_url
        elif raw_url:
            source_url = f"https://lu.ma/{raw_url}"
        else:
            source_url = calendar_url

        description = (ev.get("description") or "").strip()
        if not description and source_url.startswith("https://lu.ma/"):
            description = _fetch_luma_event_description(source_url)
        if len(description) > 400:
            description = description[:400].rsplit(" ", 1)[0] + "…"

        events.append({
            "name": name,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "topic_tags": ["networking", "startup founders"],
            "description": description,
            "source_url": source_url,
        })

    print(f"  Luma: {len(events)} in-range event(s)")
    return events


# ── Meetup ────────────────────────────────────────────────────────────────────

def fetch_meetup_events(calendar_url: str, today: str, end_date: str) -> list[dict]:
    """Parse Meetup events from __NEXT_DATA__ Apollo state (no Playwright needed)."""
    try:
        resp = requests.get(calendar_url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): Meetup — {exc}")
        return []

    match = re.search(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        resp.text,
        re.DOTALL,
    )
    if not match:
        print(f"  SKIP: No __NEXT_DATA__ in Meetup page")
        return []

    try:
        data = json.loads(match.group(1))
        apollo = data["props"]["pageProps"]["__APOLLO_STATE__"]
    except (json.JSONDecodeError, KeyError) as exc:
        print(f"  SKIP: Could not parse Meetup Apollo state — {exc}")
        return []

    # Build venue lookup
    venues: dict[str, dict] = {}
    for key, val in apollo.items():
        if key.startswith("Venue:") and isinstance(val, dict):
            venues[key.split(":", 1)[1]] = val

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for key, ev in apollo.items():
        if not key.startswith("Event:") or not isinstance(ev, dict):
            continue
        if ev.get("isOnline") or ev.get("eventType") != "PHYSICAL":
            continue
        if ev.get("status") != "ACTIVE":
            continue
        if ev.get("feeSettings") is not None:
            continue  # paid event

        date_raw = ev.get("dateTime", "")
        if not date_raw:
            continue
        try:
            event_dt = datetime.fromisoformat(date_raw)
            date_str = event_dt.strftime("%Y-%m-%d")
            start_time_str = event_dt.strftime("%H:%M")
        except ValueError:
            continue

        event_date = datetime.strptime(date_str, "%Y-%m-%d")
        if event_date < today_dt or event_date > end_dt:
            continue

        end_time_str = ""
        end_raw = ev.get("endTime", "")
        if end_raw:
            try:
                end_time_str = datetime.fromisoformat(end_raw).strftime("%H:%M")
            except ValueError:
                pass

        venue_id = ""
        venue_ref = ev.get("venue", {})
        if isinstance(venue_ref, dict):
            ref = venue_ref.get("__ref", "")
            venue_id = ref.split(":", 1)[1] if ":" in ref else ""
        venue = venues.get(venue_id, {})
        loc_parts = [venue.get("name", ""), venue.get("address", ""), venue.get("city", ""), venue.get("state", "")]
        location = ", ".join(p for p in loc_parts if p)

        description = ev.get("description", "")
        if description:
            description = re.sub(r"\*\*(.+?)\*\*", r"\1", description)
            description = re.sub(r"\*(.+?)\*", r"\1", description)
            description = re.sub(r"[\\#\[\]]+", "", description)
            description = re.sub(r"\d+\.", "", description)
            description = re.sub(r"\n+", " ", description).strip()
            description = description[:800]

        tags = ["networking", "startup founders"]
        if re.search(r"\bai\b|artificial intelligence", description, re.I):
            tags.append("AI")
        if re.search(r"\bfound", description, re.I):
            tags.append("entrepreneurship")

        events.append({
            "name": ev.get("title", "").strip(),
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "topic_tags": list(dict.fromkeys(tags)),
            "description": description,
            "source_url": ev.get("eventUrl", calendar_url),
        })

    print(f"  Meetup: {len(events)} in-range in-person free event(s)")
    return events


# ── 1 Million Cups (Playwright + Claude) ──────────────────────────────────────

def fetch_1mc_events(
    calendar_url: str, client: anthropic.Anthropic, today: str, end_date: str
) -> list[dict]:
    """Render 1MC page with Playwright, then extract events via Claude."""
    print(f"  Launching Playwright for 1MC…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
            page.goto(calendar_url, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(5000)
            text = page.inner_text("body")
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            browser.close()
    except Exception as exc:
        print(f"  SKIP (Playwright failed): 1MC — {exc}")
        return []

    lines = [l for l in text.splitlines() if l.strip()]
    page_text = "\n".join(lines)[:12000]

    if links:
        event_links = [l for l in dict.fromkeys(links) if "1millioncups.com" in l and l != calendar_url]
        if event_links:
            page_text += "\n\nLINKS FOUND ON PAGE:\n" + "\n".join(event_links[:50])

    if not page_text.strip() or len(page_text) < 100:
        print(f"  SKIP: 1MC page returned no content")
        return []

    print(f"  1MC page: {len(page_text)} chars — sending to Claude…")

    prompt = (
        f"Extract all upcoming in-person events from this 1 Million Cups page content. "
        f"1 Million Cups is a free weekly program for entrepreneurs. "
        f"Today is {today}. Only include events between {today} and {end_date}. "
        f"Return ONLY a valid JSON array starting with [ and ending with ]. "
        f"Each object must have: name (string), date (YYYY-MM-DD), "
        f"start_time (HH:MM or 00:00 if unknown), end_time (HH:MM or empty string), "
        f"location (venue name and full address), "
        f"topic_tags (array using only: {', '.join(APPROVED_TAGS)}), "
        f"description (1-3 sentences about the event), "
        f"source_url (direct URL to the specific event — look in LINKS FOUND ON PAGE for individual "
        f"event URLs, NOT the calendar page {calendar_url!r}). "
        f"Return [] if no upcoming in-person events found.\n\n"
        f"Page content:\n{page_text}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"  ERROR: Claude call failed for 1MC — {exc}")
        return []

    raw = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            raw += block.text

    events = parse_events(raw)
    print(f"  1MC: {len(events)} event(s) extracted by Claude")
    return events


# ── Shared utilities ───────────────────────────────────────────────────────────

def parse_events(text: str) -> list[dict]:
    """Extract JSON array from Claude response text."""
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
    """Return (lowercased_name, date) tuples for all Airtable events."""
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
    """Write a single event to Airtable."""
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


# ── Description summarization ─────────────────────────────────────────────────

def _summarize_one(name: str, description: str, client: anthropic.Anthropic) -> str:
    """Ask Claude for a single one-sentence event summary."""
    prompt = (
        f"Write exactly ONE sentence (20–35 words) telling a potential attendee what they will "
        f"specifically do or learn at this event. Be concrete, not generic.\n\n"
        f"Event: {name}\nDescription: {description[:700]}\n\nOne sentence:"
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=80,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(b.text for b in response.content if hasattr(b, "text")).strip()
    except Exception as exc:
        print(f"    WARNING: Summary failed for {name!r} — {exc}")
        return description


def summarize_descriptions(events: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """Replace raw descriptions with Claude-generated one-sentence summaries."""
    count = 0
    for ev in events:
        if ev.get("description", "").strip():
            ev["description"] = _summarize_one(ev["name"], ev["description"], client)
            count += 1
            time.sleep(0.1)
    if count:
        print(f"  Summarized {count} description(s)")
    return events


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")
    if not AIRTABLE_API_KEY:
        sys.exit("ERROR: AIRTABLE_API_KEY is not set.")

    today = datetime.now().strftime("%Y-%m-%d")
    end_date = (datetime.now() + timedelta(days=90)).strftime("%Y-%m-%d")
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"Triangle Startup Events — {today} → {end_date}\n")
    all_events: list[dict] = []

    print("[1/4] Lila Learning (requests + BeautifulSoup)…")
    all_events.extend(fetch_lila_events(today, end_date))

    print("\n[2/4] Luma (API)…")
    all_events.extend(fetch_luma_events("https://lu.ma/raleighdurhamstartupweek", today, end_date))

    print("\n[3/4] Meetup (requests + Apollo state)…")
    all_events.extend(fetch_meetup_events("https://www.meetup.com/triangle-startup-collective/", today, end_date))

    print("\n[4/4] 1 Million Cups (Playwright + Claude)…")
    all_events.extend(fetch_1mc_events(
        "https://www.1millioncups.com/s/account/0014W00002AqQfOQAV/durham-nc",
        client, today, end_date,
    ))

    print(f"\nTotal events found across all sources: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    print("\nGenerating one-sentence descriptions via Claude…")
    all_events = summarize_descriptions(all_events, client)

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
            time.sleep(0.25)  # Airtable 5 req/s limit
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            print(f"  ERROR adding {event.get('name')!r}: {exc}  —  {body[:300]}")
            errors += 1

    print(f"\nFinished. Added: {added} | Skipped: {skipped} | Errors: {errors}")


if __name__ == "__main__":
    main()
