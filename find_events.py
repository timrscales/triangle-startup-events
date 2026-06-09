#!/usr/bin/env python3
"""Find free startup events in the NC Triangle area and sync to Airtable."""
from __future__ import annotations

import difflib
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import anthropic
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = "apprt7MFT8PcVhFY4"
AIRTABLE_TABLE_NAME = "Events"
AIRTABLE_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
AIRTABLE_ORGS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

APPROVED_TAGS = [
    "Fundraising",
    "Sales",
    "AI & Data",
    "Tech & Product",
    "Life Science",
    "Marketing",
    "Hiring",
    "Legal",
    "Finance",
    "Hardware & Deeptech",
    "Climate & Sustainability",
    "Social Impact",
    "Coworking",
    "Women Founders",
    "Black Founders",
    "Latino Founders",
    "LGBTQ+ Founders",
    "Student Founders",
]

ALLOWED_FORMAT = [
    "workshop",
    "networking",
    "pitch_practice",
    "demo_day",
    "office_hours",
    "accelerator_info_session",
]

ALLOWED_STAGE_FOCUS = [
    "Idea_Stage",
    "Building",
    "Early_Traction",
    "Scaling",
]

ALLOWED_INDUSTRY = [
    "healthtech",
    "fintech",
    "climate_tech",
    "B2B_SaaS",
    "edtech",
    "proptech",
    "supply_chain",
    "consumer",
    "marketplaces",
    "deeptech",
    "hardware",
    "AI",
    "no_specific_industry",
]

_TRIANGLE_CITIES = [
    "Raleigh", "Durham", "Chapel Hill", "RTP", "Cary", "Morrisville",
    "Carrboro", "Apex", "Wake Forest", "Hillsborough", "Pittsboro",
]


def _city_from_location(location: str) -> str:
    """Extract the primary Triangle city from a location string."""
    loc = location.lower()
    for city in _TRIANGLE_CITIES:
        if city.lower() in loc:
            return city
    return ""


_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"  # emoji: symbols, transport, faces, objects, extended
    "☀-➿"          # misc symbols + dingbats
    "️"                 # variation selector-16
    "‍"                 # zero-width joiner
    "]+",
    re.UNICODE,
)


def _strip_emojis(text: str) -> str:
    """Remove emoji characters and collapse any resulting extra whitespace."""
    return re.sub(r"\s+", " ", _EMOJI_RE.sub("", text)).strip()


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

    tags: list[str] = []

    return {
        "name": name,
        "date": date_fmt,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "topic_tags": list(dict.fromkeys(tags)),
        "description": description,
        "host": "Lila Learning",
        "city": _city_from_location(location),
        "source_url": url,
    }


# ── Luma ──────────────────────────────────────────────────────────────────────

def _fetch_luma_event_details(event_url: str) -> tuple[str, str]:
    """Fetch a native Luma event page; return (description, organizer)."""
    try:
        resp = requests.get(event_url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException:
        return "", ""

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)
    lines = [l for l in text.splitlines() if l.strip()]

    # Organizer: "Presented by\n<Name>" takes priority, fall back to "Hosted By\n<Name>"
    organizer = ""
    for label in ("Presented by", "Hosted By"):
        for i, line in enumerate(lines):
            if line.strip() == label and i + 1 < len(lines):
                organizer = lines[i + 1].strip()
                break
        if organizer:
            break

    # Description: text after "About Event"
    description = ""
    about_idx = text.find("About Event")
    if about_idx == -1:
        about_idx = text.find("About the Event")
    if about_idx != -1:
        snippet = text[about_idx + len("About Event"):about_idx + 600].strip()
        desc_lines = [l for l in snippet.splitlines() if l.strip() and not l.strip().startswith("​")]
        sentences = re.split(r"(?<=[.!?])\s+", " ".join(desc_lines[:8]))
        description = " ".join(sentences[:3])[:400]

    return description, organizer


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

    cal_name_match = re.search(r'"name":"([^"]{3,80})"', resp.text)
    calendar_name = cal_name_match.group(1) if cal_name_match else ""

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
            start_local = start_utc.astimezone(ZoneInfo("America/New_York"))
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
        city = geo.get("city") or _city_from_location(location)

        name = (ev.get("name") or ev.get("title") or "").strip()

        raw_url = ev.get("url") or ""
        if raw_url.startswith("http"):
            source_url = raw_url
        elif raw_url:
            source_url = f"https://lu.ma/{raw_url}"
        else:
            source_url = calendar_url

        description = (ev.get("description") or "").strip()
        host = ""
        if source_url.startswith("https://lu.ma/"):
            fetched_desc, host = _fetch_luma_event_details(source_url)
            if not description:
                description = fetched_desc
        if not host:
            host = calendar_name
        if len(description) > 400:
            description = description[:400].rsplit(" ", 1)[0] + "…"

        events.append({
            "name": name,
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "topic_tags": [],
            "description": description,
            "host": host,
            "city": city,
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

    # Build venue and group lookups
    venues: dict[str, dict] = {}
    groups: dict[str, str] = {}
    for key, val in apollo.items():
        if key.startswith("Venue:") and isinstance(val, dict):
            venues[key.split(":", 1)[1]] = val
        if key.startswith("Group:") and isinstance(val, dict):
            groups[key] = val.get("name", "")

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
        venue_city = venue.get("city", "")
        loc_parts = [venue.get("name", ""), venue.get("address", ""), venue_city, venue.get("state", "")]
        location = ", ".join(p for p in loc_parts if p)
        city = venue_city if TRIANGLE_TERMS.search(venue_city) else _city_from_location(location)

        description = ev.get("description", "")
        if description:
            description = re.sub(r"\*\*(.+?)\*\*", r"\1", description)
            description = re.sub(r"\*(.+?)\*", r"\1", description)
            description = re.sub(r"[\\#\[\]]+", "", description)
            description = re.sub(r"\d+\.", "", description)
            description = re.sub(r"\n+", " ", description).strip()
            description = description[:800]

        group_ref = ev.get("group", {}).get("__ref", "") if isinstance(ev.get("group"), dict) else ""
        host = groups.get(group_ref, "")

        events.append({
            "name": ev.get("title", "").strip(),
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "topic_tags": [],
            "description": description,
            "host": host,
            "city": city,
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
        f"topic_tags (array of 1-3 tags chosen strictly from: {', '.join(APPROVED_TAGS)}), "
        f"event_type (single most specific tag from the same list, must appear in topic_tags), "
        f"description (1-3 sentences about the event), "
        f"host (name of the hosting organization or person, or '1 Million Cups' if unknown), "
        f"city (city where event takes place: Raleigh, Durham, Chapel Hill, RTP, or empty string), "
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
    # Clear tags from the extraction prompt — _enrich_one will set them cleanly
    for ev in events:
        ev["topic_tags"] = []
    print(f"  1MC: {len(events)} event(s) extracted by Claude")
    return events


# ── CEDNC ─────────────────────────────────────────────────────────────────────

TRIANGLE_TERMS = re.compile(
    r"\b(Raleigh|Durham|Chapel Hill|RTP|Research Triangle|Cary|Morrisville|"
    r"Apex|Wake Forest|Carrboro|Hillsborough|Pittsboro)\b",
    re.I,
)

NON_TRIANGLE = re.compile(
    r"\bcoastal\b|\btriad\b|\bcharlotte\b|\bgreensboro\b|\bwilmington\b|\basheville\b",
    re.I,
)


def _parse_cednc_article(article, today_dt: datetime, end_dt: datetime) -> dict | None:
    """Extract event data from a single CEDNC <article> element."""
    title_tag = article.find("a", href=True)
    if not title_tag:
        return None
    name = title_tag.get_text(strip=True)
    detail_url = title_tag["href"]

    # Skip invite-only, clearly non-startup, or non-Triangle events by name
    if re.search(r"invite.?only|carrot conference", name, re.I):
        return None
    if NON_TRIANGLE.search(name):
        return None

    text = article.get_text(separator=" | ", strip=True)

    # Skip virtual events
    if re.search(r"\bvirtual\b|\bonline\b|\bwebinar\b", text, re.I):
        return None

    # Location: anything after the last "|" that looks like an address
    loc_match = re.search(r"\|\s*([^|]{10,}?,\s*[A-Z]{2}[^|]*)", text)
    location = loc_match.group(1).strip() if loc_match else ""

    # Filter to Triangle area — skip if location is non-empty and not Triangle
    if location and not TRIANGLE_TERMS.search(location):
        return None

    # Date: "May 21 @ 4:00 pm" or "May 15 | - | May 17" → use first date
    date_match = re.search(
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2})(?:\s*@\s*(\d{1,2}:\d{2}\s*[ap]m))?",
        text, re.I,
    )
    if not date_match:
        return None

    year = today_dt.year
    try:
        event_dt = datetime.strptime(f"{date_match.group(1)} {date_match.group(2)} {year}", "%B %d %Y")
        if event_dt < today_dt:
            event_dt = event_dt.replace(year=year + 1)
    except ValueError:
        return None

    if event_dt < today_dt or event_dt > end_dt:
        return None

    date_str = event_dt.strftime("%Y-%m-%d")

    start_time = "00:00"
    end_time = ""
    time_match = re.search(
        r"@\s*(\d{1,2}:\d{2}\s*[ap]m)\s*[-–]\s*(\d{1,2}:\d{2}\s*[ap]m)", text, re.I
    )
    if time_match:
        try:
            start_time = datetime.strptime(time_match.group(1).strip(), "%I:%M %p").strftime("%H:%M")
            end_time = datetime.strptime(time_match.group(2).strip(), "%I:%M %p").strftime("%H:%M")
        except ValueError:
            pass

    return {
        "name": name,
        "date": date_str,
        "start_time": start_time,
        "end_time": end_time,
        "location": location,
        "topic_tags": [],
        "description": "",
        "host": "",
        "city": _city_from_location(location),
        "source_url": detail_url,
        "_detail_url": detail_url,
    }


def _fetch_cednc_detail(event: dict) -> dict:
    """Enrich a CEDNC event with organizer from its detail page."""
    url = event.pop("_detail_url", "")
    if not url:
        return event
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        for i, line in enumerate(lines):
            if line == "Organizer" and i + 1 < len(lines):
                event["host"] = lines[i + 1]
                break
        # Use external "Website" as source_url if present
        for i, line in enumerate(lines):
            if line == "Website:" and i + 1 < len(lines):
                candidate = lines[i + 1].strip()
                if candidate.startswith("http"):
                    event["source_url"] = candidate
                break
    except Exception:
        pass
    return event


def fetch_cednc_events(calendar_url: str, today: str, end_date: str) -> list[dict]:
    """Scrape CEDNC event list and enrich each with organizer from detail page."""
    try:
        resp = requests.get("https://cednc.org/events/list/", headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): CEDNC — {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    articles = soup.find_all("article")
    print(f"  CEDNC: {len(articles)} article(s) on list page")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for art in articles:
        ev = _parse_cednc_article(art, today_dt, end_dt)
        if ev:
            ev = _fetch_cednc_detail(ev)
            events.append(ev)
            time.sleep(0.3)

    print(f"  CEDNC: {len(events)} in-range Triangle event(s)")
    return events


# ── echo-nc.org (Playwright + Claude) ─────────────────────────────────────────

def fetch_echo_events(base_url: str, client: anthropic.Anthropic, today: str, end_date: str) -> list[dict]:
    """Render echo-nc.org event detail pages with Playwright, extract via Claude."""
    print(f"  Launching Playwright for echo…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pw_page = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])

            # Step 1: render homepage to collect event detail URLs
            pw_page.goto(base_url, timeout=60000, wait_until="load")
            pw_page.wait_for_timeout(2000)
            all_links = pw_page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            event_urls = list(dict.fromkeys(
                l for l in all_links if "echo-nc.org/events/" in l
            ))
            print(f"  echo: {len(event_urls)} event link(s) found")

            # Step 2: render each detail page for full data (including times)
            detail_texts: list[tuple[str, str]] = []  # (url, page_text)
            for url in event_urls:
                try:
                    pw_page.goto(url, timeout=60000, wait_until="load")
                    pw_page.wait_for_timeout(1500)
                    text = pw_page.inner_text("body")
                    lines = [l for l in text.splitlines() if l.strip()]
                    detail_texts.append((url, "\n".join(lines)[:8000]))
                except Exception as exc:
                    print(f"    SKIP (detail fetch failed): {url} — {exc}")

            browser.close()
    except Exception as exc:
        print(f"  SKIP (Playwright failed): echo — {exc}")
        return []

    if not detail_texts:
        print(f"  SKIP: echo — no detail pages loaded")
        return []

    # Step 3: send each detail page to Claude individually
    events: list[dict] = []
    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    for source_url, page_text in detail_texts:
        prompt = (
            f"Extract the single event from this echo-nc.org event detail page. "
            f"Today is {today}. Only return the event if its date is between {today} and {end_date}. "
            f"Return ONLY a valid JSON object (not an array) with these keys: "
            f"name (string), date (YYYY-MM-DD), "
            f"start_time (HH:MM in 24h, or 00:00 if unknown), "
            f"end_time (HH:MM in 24h, or empty string if unknown), "
            f"location (venue name and full address), "
            f"description (1-3 sentences about the event), "
            f"host (always 'echo'), city (always 'Durham'). "
            f"Return null if the event is outside the date range or is virtual.\n\n"
            f"Page content:\n{page_text}"
        )
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=400,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                b.text for b in response.content
                if hasattr(b, "type") and b.type == "text"
            ).strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
            if not raw or raw.lower() == "null":
                continue
            ev = json.loads(raw)
            if not isinstance(ev, dict) or not ev.get("name") or not ev.get("date"):
                continue
            # Validate date range
            try:
                ev_dt = datetime.strptime(ev["date"], "%Y-%m-%d")
                if ev_dt < today_dt or ev_dt > end_dt:
                    continue
            except ValueError:
                continue
            ev["source_url"] = source_url
            ev["topic_tags"] = []  # _enrich_one will set cleanly
            events.append(ev)
        except Exception as exc:
            print(f"    WARNING: Claude extraction failed for {source_url} — {exc}")

    print(f"  echo: {len(events)} in-range event(s)")
    return events


# ── First Flight Venture Center (Playwright + Claude) ─────────────────────────

_FFVC_LOCATION = "First Flight Venture Center, 2 Davis Drive, Research Triangle Park, NC 27709"


def fetch_ffvc_events(calendar_url: str, client: anthropic.Anthropic, today: str, end_date: str) -> list[dict]:
    """Render FFVC events page with Playwright, then extract events via Claude."""
    print(f"  Launching Playwright for FFVC…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            pw_page = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
            pw_page.goto(calendar_url, timeout=60000, wait_until="load")
            pw_page.wait_for_timeout(3000)
            text = pw_page.inner_text("body")
            links = pw_page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            browser.close()
    except Exception as exc:
        print(f"  SKIP (Playwright failed): FFVC — {exc}")
        return []

    page_lines = [l for l in text.splitlines() if l.strip()]
    page_text = "\n".join(page_lines)[:12000]

    if links:
        detail_links = [l for l in dict.fromkeys(links) if "/events/Details/" in l]
        if detail_links:
            page_text += "\n\nEVENT DETAIL LINKS (one per occurrence):\n" + "\n".join(detail_links[:100])

    if not page_text.strip() or len(page_text) < 100:
        print(f"  SKIP: FFVC page returned no content")
        return []

    print(f"  FFVC page: {len(page_text)} chars — sending to Claude…")

    prompt = (
        f"Extract all upcoming in-person events from this First Flight Venture Center events page. "
        f"Today is {today}. Only include events between {today} and {end_date}. "
        f"Return ONLY a valid JSON array starting with [ and ending with ]. "
        f"Each object must have: name (string), date (YYYY-MM-DD), "
        f"start_time (HH:MM in 24h, or 00:00 if unknown), "
        f"end_time (HH:MM in 24h, or empty string if unknown), "
        f"description (1-2 sentences about the event), "
        f"source_url (from EVENT DETAIL LINKS — match each occurrence to its specific detail URL). "
        f"Set host='First Flight Venture Center', city='RTP', "
        f"location='{_FFVC_LOCATION}' on every event. "
        f"Each recurring event occurrence on a different date is a separate object. "
        f"Return [] if no in-range events found.\n\n"
        f"Page content:\n{page_text}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"  ERROR: Claude call failed for FFVC — {exc}")
        return []

    raw = ""
    for block in response.content:
        if hasattr(block, "type") and block.type == "text":
            raw += block.text

    events = parse_events(raw)
    for ev in events:
        ev.setdefault("topic_tags", [])
        ev.setdefault("host", "First Flight Venture Center")
        ev.setdefault("city", "RTP")
        ev.setdefault("location", _FFVC_LOCATION)

    print(f"  FFVC: {len(events)} in-range event(s)")
    return events



# ── The Loading Dock ──────────────────────────────────────────────────────────

def _parse_loading_dock_detail(url: str, today_dt: datetime, end_dt: datetime) -> list[dict]:
    """Fetch a Loading Dock detail page and return one dict per in-range date."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"    SKIP (fetch failed): {url} — {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # Title from <h1> or page <title>
    h1 = soup.find("h1")
    name = h1.get_text(strip=True) if h1 else ""
    if not name:
        t = soup.find("title")
        name = t.get_text(strip=True).split("|")[0].strip() if t else ""

    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n", strip=True)

    # Skip virtual events
    if re.search(r"\bvirtual\b|\bonline\b|\bwebinar\b", text[:600], re.I):
        return []

    # Find all "Weekday, Month D, YYYY" dates on the page (recurring events list multiple)
    date_matches = list(re.finditer(
        r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),\s+"
        r"(January|February|March|April|May|June|July|August|September|October|November|December)"
        r"\s+(\d{1,2}),\s+(\d{4})",
        text,
    ))
    if not date_matches:
        return []

    # Find all time ranges: "11:30 AM – 12:30 PM" or "11:30 AM - 12:30 PM"
    time_matches = list(re.finditer(
        r"(\d{1,2}:\d{2}\s*[AP]M)\s*[–\-]+\s*(\d{1,2}:\d{2}\s*[AP]M)", text, re.I
    ))

    # Location: prefer full address with street number
    addr_match = re.search(
        r"\d+\s+\w[^\n]{5,80},\s+\w[^\n]{2,40}(?:NC|North Carolina)[^\n]{0,30}\d{5}", text
    )
    location = addr_match.group(0).strip() if addr_match else "The Loading Dock, Raleigh, NC"

    # Description: first substantial paragraph
    desc = ""
    for line in text.splitlines():
        line = line.strip()
        if len(line) > 60 and name.lower()[:20] not in line.lower():
            desc = line[:400]
            break

    events = []
    for i, dm in enumerate(date_matches):
        try:
            ev_dt = datetime.strptime(f"{dm.group(1)} {dm.group(2)} {dm.group(3)}", "%B %d %Y")
        except ValueError:
            continue
        if ev_dt < today_dt or ev_dt > end_dt:
            continue

        # Use time match at same index if available, else first one
        tm = time_matches[i] if i < len(time_matches) else (time_matches[0] if time_matches else None)
        start_time, end_time = "00:00", ""
        if tm:
            try:
                start_time = datetime.strptime(tm.group(1).strip(), "%I:%M %p").strftime("%H:%M")
                end_time = datetime.strptime(tm.group(2).strip(), "%I:%M %p").strftime("%H:%M")
            except ValueError:
                pass

        events.append({
            "name": name,
            "date": ev_dt.strftime("%Y-%m-%d"),
            "start_time": start_time,
            "end_time": end_time,
            "location": location,
            "description": desc,
            "host": "The Loading Dock",
            "city": _city_from_location(location) or "Raleigh",
            "topic_tags": [],
            "source_url": url,
        })

    return events


def fetch_loading_dock_events(list_url: str, today: str, end_date: str) -> list[dict]:
    """Scrape The Loading Dock event list, then fetch each detail page."""
    try:
        resp = requests.get(list_url, headers=BROWSER_HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): Loading Dock — {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    seen: set[str] = set()
    detail_urls: list[str] = []
    for a in soup.find_all("a", href=re.compile(r"/new-events/\d{4}/")):
        href = a["href"].strip()
        full = href if href.startswith("http") else f"https://www.theloadingdock.com{href}"
        if full not in seen:
            seen.add(full)
            detail_urls.append(full)

    print(f"  Loading Dock: {len(detail_urls)} event link(s) found")

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")

    events: list[dict] = []
    for url in detail_urls:
        evs = _parse_loading_dock_detail(url, today_dt, end_dt)
        events.extend(evs)
        time.sleep(0.3)

    print(f"  Loading Dock: {len(events)} in-range event(s)")
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


def _norm_location(loc: str) -> str:
    """Lowercase, strip, collapse whitespace, drop trailing punctuation."""
    s = re.sub(r"\s+", " ", str(loc or "").lower()).strip()
    return s.rstrip(".,;:")


class ExistingEvents:
    """Multi-key index of Airtable events for duplicate detection.

    Match priority:
      1. source_url (exact)              — strongest signal
      2. (date, start_time, location)    — same time + place, title may have been edited
      3. (lowercased_name, date)         — fallback when source_url/location missing
    """

    def __init__(self) -> None:
        self.by_source_url: set[str] = set()
        self.by_time_loc: set[tuple[str, str, str]] = set()
        self.by_name_date: set[tuple[str, str]] = set()

    def __len__(self) -> int:
        # Best proxy for "how many records did we index" — name+date covers every record.
        return len(self.by_name_date)

    def add_record(self, fields: dict) -> None:
        name = str(fields.get("Name", "")).lower().strip()
        date = str(fields.get("Date", "")).strip()
        start_time = str(fields.get("Start Time", "")).strip()
        location = _norm_location(fields.get("Location", ""))
        source_url = str(fields.get("Source URL", "")).strip()

        if source_url:
            self.by_source_url.add(source_url)
        if date and start_time and location:
            self.by_time_loc.add((date, start_time, location))
        if name and date:
            self.by_name_date.add((name, date))

    def add_event(self, event: dict) -> None:
        """Mirror an event we just created so subsequent iterations skip it."""
        self.add_record({
            "Name":       event.get("name", ""),
            "Date":       event.get("date", ""),
            "Start Time": event.get("start_time", ""),
            "Location":   event.get("location", ""),
            "Source URL": event.get("source_url", ""),
        })

    def match(self, event: dict) -> str | None:
        """Return a short reason string if event looks like a duplicate, else None."""
        source_url = str(event.get("source_url", "")).strip()
        if source_url and source_url in self.by_source_url:
            return "source_url"

        date = str(event.get("date", "")).strip()
        start_time = str(event.get("start_time", "")).strip()
        location = _norm_location(event.get("location", ""))
        if date and start_time and location and (date, start_time, location) in self.by_time_loc:
            return "same time+location"

        name = str(event.get("name", "")).lower().strip()
        if name and date and (name, date) in self.by_name_date:
            return "name+date"

        return None


def get_existing_events() -> ExistingEvents:
    """Fetch all Airtable events and build a multi-key dedup index."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params: dict = {"fields[]": ["Name", "Date", "Start Time", "Location", "Source URL"]}
    existing = ExistingEvents()

    while True:
        resp = requests.get(AIRTABLE_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for record in data.get("records", []):
            existing.add_record(record.get("fields", {}))
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset

    return existing


def load_orgs() -> dict[str, str]:
    """Return {normalized_org_name: record_id} for all rows in Organizations."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params: dict = {}
    orgs: dict[str, str] = {}
    while True:
        resp = requests.get(AIRTABLE_ORGS_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for record in data.get("records", []):
            name = record.get("fields", {}).get("Organization Name", "").strip()
            if name:
                orgs[name.lower()] = record["id"]
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset
    return orgs


def create_org_stub(name: str) -> str:
    """Create a minimal org record and return its record ID."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    resp = requests.post(
        AIRTABLE_ORGS_URL,
        headers=headers,
        json={"fields": {"Organization Name": name}},
        timeout=30,
    )
    resp.raise_for_status()
    rec_id = resp.json()["id"]
    print(f"  NEW ORG: created stub for {name!r} ({rec_id})")
    return rec_id


def resolve_org(host: str, orgs: dict[str, str], fuzzy_threshold: float = 0.82) -> str | None:
    """Return an Airtable record ID for host, creating a stub if no match found.

    Tries exact match first, then fuzzy. Creates a stub org record if nothing
    is close enough, so unrecognised orgs surface in Airtable for manual review.
    Returns None only if host is empty.
    """
    host = host.strip()
    if not host:
        return None

    key = host.lower()

    # 0. Canonical overrides — force specific orgs regardless of exact name
    if "daretoshift" in key:
        canonical = "daretoshift"
        if canonical in orgs:
            print(f"  ORG MATCH (canonical override): {host!r} → 'DareToShift'")
            return orgs[canonical]

    # 1. Exact match
    if key in orgs:
        return orgs[key]

    # 2. Fuzzy match
    best = difflib.get_close_matches(key, orgs.keys(), n=1, cutoff=fuzzy_threshold)
    if best:
        matched_name = best[0]
        print(f"  ORG MATCH (fuzzy): {host!r} → {matched_name!r}")
        return orgs[matched_name]

    # 3. No match — create a stub so the name lands in Airtable
    rec_id = create_org_stub(host)
    orgs[key] = rec_id  # cache so duplicates within this run don't create more stubs
    return rec_id


def format_friendly_date(date_str: str, start_time: str, end_time: str) -> str:
    """Return a human-friendly date string, e.g. 'Wednesday, May 20 from 1pm-5pm'."""
    if not date_str:
        return ""
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        return ""

    date_part = dt.strftime("%A, %B %-d")

    def fmt_time(t: str) -> str:
        if not t or t == "00:00":
            return ""
        try:
            td = datetime.strptime(t, "%H:%M")
            if td.minute == 0:
                return td.strftime("%-I%p").lower()
            return td.strftime("%-I:%M%p").lower()
        except ValueError:
            return ""

    start = fmt_time(start_time)
    end = fmt_time(end_time)

    if start and end:
        return f"{date_part} from {start}-{end}"
    if start:
        return f"{date_part} at {start}"
    return date_part


def _split_location(location: str) -> tuple[str, str]:
    """
    Split a combined location string into (venue_name, street_address).

    Examples:
      "American Underground, 320 Blackwell St, Durham, NC 27701"
        → ("American Underground", "320 Blackwell St, Durham, NC 27701")
      "320 Blackwell St, Durham, NC 27701"
        → ("", "320 Blackwell St, Durham, NC 27701")
      "Frontier RTP"
        → ("Frontier RTP", "")
    """
    if not location:
        return "", ""
    parts = [p.strip() for p in location.split(",")]
    if len(parts) <= 1:
        return location.strip(), ""
    # If first part starts with a digit, the whole thing is an address with no venue name
    if re.match(r"^\d+\s+", parts[0]):
        return "", location.strip()
    # First part is the venue name; the rest is the address
    venue = parts[0]
    address = ", ".join(parts[1:]).strip()
    return venue, address


def _normalize_time(t: str) -> str:
    """
    Normalize any time string to HH:MM (24-hour). Returns empty string if unparseable.

    Handles:
      HH:MM          → pass-through (already correct)
      H:MM           → zero-pad hour
      HH:MM:SS       → strip seconds
      h:MMam/pm      → convert to 24h
      ham / hpm      → hour-only am/pm
      h:MM AM/PM     → convert to 24h (with space)
    """
    t = t.strip()
    if not t or t == "00:00":
        return t

    _FMT_ATTEMPTS = [
        "%H:%M",        # 14:30
        "%H:%M:%S",     # 14:30:00
        "%I:%M%p",      # 2:30PM / 2:30pm
        "%I:%M %p",     # 2:30 PM
        "%I%p",         # 2PM / 2pm
        "%I %p",        # 2 PM
    ]
    normalized = t.upper().replace(".", "").replace(" ", " ")
    for fmt in _FMT_ATTEMPTS:
        try:
            return datetime.strptime(normalized, fmt).strftime("%H:%M")
        except ValueError:
            continue
    return t  # return as-is if nothing matches; will surface as a data issue


def create_event_record(event: dict, orgs: dict[str, str]) -> dict:
    """Write a single event to Airtable, linking Organizer as a record ID."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }
    event.setdefault("is_free", True)
    fields: dict = {
        "Name": str(event.get("name", "")).strip(),
        "Date": str(event.get("date", "")).strip(),
        "Start Time": _normalize_time(str(event.get("start_time", ""))),
        "Location": str(event.get("location", "")).strip(),
        "Location Name": _split_location(str(event.get("location", "")))[0],
        "Location Address": _split_location(str(event.get("location", "")))[1],
        "Description": str(event.get("description", "")).strip(),
        "Source URL": str(event.get("source_url", "")).strip(),
        "Paid": not bool(event["is_free"]),
    }
    org_rec_id = resolve_org(event.get("host", ""), orgs)
    if org_rec_id:
        fields["Organization"] = [org_rec_id]  # linked record field requires an array
    end_time = _normalize_time(str(event.get("end_time", "")))
    if end_time:
        fields["End Time"] = end_time
    tags = event.get("topic_tags")
    if isinstance(tags, list) and tags:
        fields["Topic Tags"] = [
            str(t).strip().strip('"').strip("'")
            for t in tags
            if str(t).strip().strip('"').strip("'") in APPROVED_TAGS
        ]
    fmt = event.get("format")
    if isinstance(fmt, list) and fmt:
        fields["Format"] = [v for v in fmt if v in ALLOWED_FORMAT]
    stage = event.get("stage_focus")
    if isinstance(stage, list) and stage:
        fields["Stage Focus"] = [v for v in stage if v in ALLOWED_STAGE_FOCUS]
    industry = event.get("industry")
    if isinstance(industry, list) and industry:
        fields["Industry"] = [v for v in industry if v in ALLOWED_INDUSTRY]
    city = str(event.get("city", "")).strip()
    if city:
        fields["City"] = city
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


# ── Event enrichment (description, tags, event_type) ─────────────────────────

# Keyword → tag rules applied deterministically before Claude enrichment so
# obvious cases stay tagged even when the model call fails or omits them.
_KEYWORD_TAG_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bcoworking\b", re.I),                                   "Coworking"),
    (re.compile(r"\bai\b|artificial intelligence|machine learning", re.I), "AI & Data"),
    (re.compile(r"\bfundrais", re.I),                                      "Fundraising"),
]


def _seed_keyword_tags(event: dict) -> None:
    """Add tags implied by keywords in the event name/description."""
    text = f"{event.get('name', '')} {event.get('description', '')}"
    tags = list(event.get("topic_tags") or [])
    for pattern, tag in _KEYWORD_TAG_RULES:
        if tag in APPROVED_TAGS and pattern.search(text) and tag not in tags:
            tags.append(tag)
    if tags:
        event["topic_tags"] = tags


_NOISE_URL_RE = re.compile(
    r"https?://\S+(?:\([^)]*\))?",  # bare URLs and markdown-style URL(link) pairs
    re.I,
)
_NOISE_PHRASES_RE = re.compile(
    r"(rsvp|register|coupon|early.bird|ticket|price|pay|sign.?up|must attend|"
    r"does not grant|to attend|see all|exact det|previous speakers?)[^.!?\n]*[.!?\n]?",
    re.I,
)


def _clean_raw_description(text: str) -> str:
    """Strip URLs, registration instructions, and promotional noise from a raw description."""
    text = _NOISE_URL_RE.sub("", text)
    text = _NOISE_PHRASES_RE.sub("", text)
    # Collapse whitespace / stray punctuation left behind
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def _enrich_one(event: dict, client: anthropic.Anthropic) -> dict:
    """Ask Claude to enrich a single event: description, topic_tags, event_type, format, stage_focus, industry."""
    name     = event.get("name", "")
    raw_desc = _clean_raw_description(event.get("description", "").strip())
    location = event.get("location", "")
    host     = event.get("host", "")
    approved = ", ".join(APPROVED_TAGS)
    fmt_opts = ", ".join(ALLOWED_FORMAT)
    stage_opts = ", ".join(ALLOWED_STAGE_FOCUS)
    industry_opts = ", ".join(ALLOWED_INDUSTRY)

    prompt = (
        f"Given this event, return a JSON object with exactly six keys:\n"
        f'- "description": 1-2 sentences (20-50 words), third person, plain language. '
        f"Describe what actually happens at the event and who it's for. "
        f"Do not mention registration, ticket prices, URLs, speaker name-drops, or promotional language. "
        f"If the raw description is unhelpful or empty, write one from scratch based on the event name and host.\n"
        f'- "topic_tags": JSON array of 1-3 tags chosen strictly from: [{approved}]. '
        f"Pick the most specific tags that match.\n"
        f'- "event_type": single most specific tag from the topic_tags list (must appear in topic_tags)\n'
        f'- "format": JSON array of one or more values strictly from: [{fmt_opts}]. '
        f"Assign all that meaningfully apply — e.g. a workshop with networking gets both. "
        f"Reason from the event title, description, and host org name.\n"
        f'- "stage_focus": JSON array of one or more values strictly from: [{stage_opts}]. '
        f"Use multiple if the event genuinely serves multiple stages; assign all four if truly stage-agnostic.\n"
        f'- "industry": JSON array of one or more values strictly from: [{industry_opts}]. '
        f'Use "no_specific_industry" only if nothing else applies — never combine it with specific tags. '
        f"Reason from event title, description, and host org name.\n\n"
        f"Event name: {name}\n"
        f"Raw description: {raw_desc[:600] if raw_desc else '(none)'}\n"
        f"Location: {location}\n"
        f"Host: {host}\n\n"
        f"Return only valid JSON, no markdown fences."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=700,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            b.text for b in response.content
            if hasattr(b, "text") and b.type == "text"
        ).strip()
        if not raw:
            raise ValueError(
                f"empty response (stop_reason={response.stop_reason!r}, "
                f"blocks={[type(b).__name__ for b in response.content]})"
            )
        # Strip markdown fences if the model ignored instructions
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        data = json.loads(raw)
        if isinstance(data.get("description"), str) and data["description"].strip():
            event["description"] = data["description"].strip()
        if isinstance(data.get("topic_tags"), list) and data["topic_tags"]:
            seeded = [t for t in (event.get("topic_tags") or []) if t in APPROVED_TAGS]
            claude_tags = [t for t in data["topic_tags"] if t in APPROVED_TAGS]
            merged: list[str] = []
            for t in [*seeded, *claude_tags]:
                if t not in merged:
                    merged.append(t)
            event["topic_tags"] = merged[:3]
        if isinstance(data.get("event_type"), str) and data["event_type"] in APPROVED_TAGS:
            event["event_type"] = data["event_type"]
        else:
            event["event_type"] = (event.get("topic_tags") or [None])[0]

        # Validate and store format
        raw_fmt = data.get("format")
        if isinstance(raw_fmt, list):
            valid = [v for v in raw_fmt if v in ALLOWED_FORMAT]
            invalid = [v for v in raw_fmt if v not in ALLOWED_FORMAT]
            if invalid:
                print(f"    WARNING: Skipping invalid format value(s) for {name!r}: {invalid}")
            if valid:
                event["format"] = valid

        # Validate and store stage_focus
        raw_stage = data.get("stage_focus")
        if isinstance(raw_stage, list):
            valid = [v for v in raw_stage if v in ALLOWED_STAGE_FOCUS]
            invalid = [v for v in raw_stage if v not in ALLOWED_STAGE_FOCUS]
            if invalid:
                print(f"    WARNING: Skipping invalid stage_focus value(s) for {name!r}: {invalid}")
            if valid:
                event["stage_focus"] = valid

        # Validate and store industry
        raw_industry = data.get("industry")
        if isinstance(raw_industry, list):
            valid = [v for v in raw_industry if v in ALLOWED_INDUSTRY]
            invalid = [v for v in raw_industry if v not in ALLOWED_INDUSTRY]
            if invalid:
                print(f"    WARNING: Skipping invalid industry value(s) for {name!r}: {invalid}")
            # Enforce: no_specific_industry must not be combined with specific tags
            if "no_specific_industry" in valid and len(valid) > 1:
                print(f"    WARNING: Dropping no_specific_industry from {name!r} — combined with specific tags")
                valid = [v for v in valid if v != "no_specific_industry"]
            if valid:
                event["industry"] = valid

    except Exception as exc:
        print(f"    WARNING: Enrichment failed for {name!r} — {exc}")
        event.setdefault("event_type", (event.get("topic_tags") or [None])[0])
    return event


def enrich_events(events: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """Enrich all events: description, topic_tags, event_type via Claude."""
    for ev in events:
        _enrich_one(ev, client)
        time.sleep(0.1)
    print(f"  Enriched {len(events)} event(s)")
    return events


def _rescue_start_time(event: dict, client: anthropic.Anthropic) -> bool:
    """
    Fetch the event's source URL and ask Claude to extract the start (and end)
    time. Updates event in-place. Returns True if a real time was found.
    """
    url = event.get("source_url", "").strip()
    if not url:
        return False
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
        text = BeautifulSoup(resp.text, "html.parser").get_text(" ", strip=True)[:6000]
    except Exception as exc:
        print(f"    WARNING: Could not fetch {url} for time rescue — {exc}")
        return False

    prompt = (
        f"The following is text from an event page. "
        f"Extract the event start time and end time. "
        f"Return ONLY a JSON object with two keys: "
        f'"start_time" (HH:MM in 24-hour format, or empty string if not found) and '
        f'"end_time" (HH:MM in 24-hour format, or empty string if not found). '
        f"Do not include any other text.\n\n"
        f"Page text:\n{text}"
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=60,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        data = json.loads(raw)
        start = str(data.get("start_time", "")).strip()
        end   = str(data.get("end_time", "")).strip()
        if start and start != "00:00":
            event["start_time"] = start
            if end and end != "00:00":
                event["end_time"] = end
            return True
    except Exception as exc:
        print(f"    WARNING: Time rescue Claude call failed for {event.get('name')!r} — {exc}")
    return False


def rescue_missing_times(events: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """
    For events with start_time == '00:00' or empty, attempt to fetch the real
    time from the source page. Events where time rescue fails are dropped so
    they never reach Airtable with a bogus midnight time.
    Returns the filtered list (rescued + events that never needed rescuing).
    """
    needs_rescue = [e for e in events if not e.get("start_time") or e["start_time"] == "00:00"]
    fine         = [e for e in events if e.get("start_time") and e["start_time"] != "00:00"]

    if not needs_rescue:
        return events

    print(f"\nTime rescue: {len(needs_rescue)} event(s) missing a start time…")
    rescued = []
    dropped = []
    for ev in needs_rescue:
        print(f"  Rescuing: {ev.get('name')!r}")
        found = _rescue_start_time(ev, client)
        if found:
            print(f"    → found {ev['start_time']}")
            rescued.append(ev)
        else:
            print(f"    → no time found, dropping from Airtable push")
            dropped.append(ev)
        time.sleep(0.2)

    if dropped:
        print(f"  Dropped {len(dropped)} event(s) with unresolvable start times.")

    return fine + rescued


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

    print("[1/15] Lila Learning…")
    all_events.extend(fetch_lila_events(today, end_date))

    print("\n[2/15] Luma — Raleigh-Durham Startup Week…")
    all_events.extend(fetch_luma_events("https://lu.ma/raleighdurhamstartupweek", today, end_date))

    print("\n[3/15] Luma — Triangle Startup Calendar…")
    all_events.extend(fetch_luma_events("https://luma.com/calendar/cal-e7mpB5yqt2phl0T", today, end_date))

    meetup_sources = [
        ("triangle-startup-collective", "https://www.meetup.com/triangle-startup-collective/"),
        ("founderslocal",               "https://www.meetup.com/founderslocal/"),
        ("daretoshift",                 "https://www.meetup.com/daretoshift/"),
        ("raleigh-startup-founder-101", "https://www.meetup.com/raleigh-startup-founder-101/"),
        ("triangle-techbreakfast",      "https://www.meetup.com/triangle-techbreakfast/"),
    ]
    for idx, (label, url) in enumerate(meetup_sources, start=4):
        print(f"\n[{idx}/15] Meetup — {label}…")
        all_events.extend(fetch_meetup_events(url, today, end_date))

    print("\n[9/15] CEDNC…")
    all_events.extend(fetch_cednc_events("https://cednc.org/events/", today, end_date))

    print("\n[10/15] First Flight Venture Center…")
    all_events.extend(fetch_ffvc_events("https://launch.ffvcnc.org/events", client, today, end_date))

    print("\n[11/15] echo — Durham (Playwright + Claude)…")
    all_events.extend(fetch_echo_events("https://www.echo-nc.org/", client, today, end_date))

    print("\n[12/15] Bullhouse…")
    all_events.extend(fetch_luma_events("https://luma.com/bullhouse", today, end_date))

    print("\n[13/15] Luma — ADVAgo…")
    all_events.extend(fetch_luma_events("https://luma.com/calendar/cal-jNLpChoAwyqDeSV", today, end_date))

    print("\n[14/15] The Loading Dock…")
    all_events.extend(fetch_loading_dock_events("https://www.theloadingdock.com/new-events", today, end_date))

    print("\n[15/15] 1 Million Cups — Durham (Playwright + Claude)…")
    all_events.extend(fetch_1mc_events(
        "https://www.1millioncups.com/s/account/0014W00002AqQfOQAV/durham-nc",
        client, today, end_date,
    ))

    print(f"\nTotal events found across all sources: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    for ev in all_events:
        _seed_keyword_tags(ev)
        if re.search(r"1 million cups", ev.get("name", ""), re.I):
            ev["host"] = "echo"

    print("\nEnriching events via Claude (description, tags, event_type)…")
    all_events = enrich_events(all_events, client)

    all_events = rescue_missing_times(all_events, client)

    print("Computing friendly dates…")
    for ev in all_events:
        ev["friendly_date"] = format_friendly_date(ev["date"], ev["start_time"], ev["end_time"])

    for ev in all_events:
        ev["name"] = _strip_emojis(ev["name"])

    print("Fetching organizations from Airtable…")
    orgs = load_orgs()
    print(f"  {len(orgs)} organization(s) loaded.")

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

        dup_reason = existing.match(event)
        if dup_reason:
            print(f"  SKIP (duplicate via {dup_reason}): {event['name']} on {event['date']}")
            skipped += 1
            continue

        try:
            create_event_record(event, orgs)
            print(f"  ADDED: {event['name']} on {event['date']}")
            existing.add_event(event)
            added += 1
            time.sleep(0.25)  # Airtable 5 req/s limit
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            print(f"  ERROR adding {event.get('name')!r}: {exc}  —  {body[:300]}")
            errors += 1

    print(f"\nFinished. Added: {added} | Skipped: {skipped} | Errors: {errors}")


if __name__ == "__main__":
    main()
