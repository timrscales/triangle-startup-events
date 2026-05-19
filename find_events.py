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
AIRTABLE_ORGS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

APPROVED_TAGS = [
    "Networking",
    "Workshop",
    "Pitch Practice",
    "Panel Discussion",
    "Community",
    "Fundraising",
    "Sales",
    "Mentorship",
    "AI & Data",
    "Tech & Product",
    "Life Science",
    "Marketing",
    "Hiring",
    "Legal",
    "Finance",
    "Investor Meetup",
    "Accelerator",
    "Demo Day",
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

    tags = []
    if re.search(r"\bpitch\b|\bpitching\b", text, re.I):
        tags.append("Pitch Practice")
    if re.search(r"\binvest\b", text, re.I):
        tags.append("Investor Meetup")
    if re.search(r"\bnetwork\b", text, re.I):
        tags.append("Networking")
    if re.search(r"\bworkshop\b|\bhands.on\b", text, re.I):
        tags.append("Workshop")
    if re.search(r"\bai\b|artificial intelligence|machine learning", text, re.I):
        tags.append("AI & Data")

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

        tags = []
        if re.search(r"\bai\b|artificial intelligence|machine learning", description, re.I):
            tags.append("AI & Data")
        if re.search(r"\bfundrais", description, re.I):
            tags.append("Fundraising")
        if re.search(r"\bpitch\b|\bpitching\b", description, re.I):
            tags.append("Pitch Practice")

        events.append({
            "name": ev.get("title", "").strip(),
            "date": date_str,
            "start_time": start_time_str,
            "end_time": end_time_str,
            "location": location,
            "topic_tags": list(dict.fromkeys(tags)),
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
    print(f"  1MC: {len(events)} event(s) extracted by Claude")
    return events


# ── CEDNC ─────────────────────────────────────────────────────────────────────

TRIANGLE_TERMS = re.compile(
    r"\b(Raleigh|Durham|Chapel Hill|RTP|Research Triangle|Cary|Morrisville|"
    r"Apex|Wake Forest|Carrboro|Hillsborough|Pittsboro)\b",
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
    NON_TRIANGLE = re.compile(
        r"\bcoastal\b|\btriad\b|\bcharlotte\b|\bgreensboro\b|\bwilmington\b|\basheville\b",
        re.I,
    )
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


# ── First Flight Venture Center ────────────────────────────────────────────────

_FFVC_LOCATION = "First Flight Venture Center, 2 Davis Drive, Research Triangle Park, NC 27709"

_IS_FULL_DATE = re.compile(
    r"^(January|February|March|April|May|June|July|August|September|October|November|December)"
    r" \d{1,2}, \d{4}$"
)
_IS_12H_TIME = re.compile(r"^\d{1,2}:\d{2} [AP]M")
_IS_24H_TIME = re.compile(r"^\d{2}:\d{2} [–\-] \d{2}:\d{2}$")
_IS_MONTH_ABBR = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)$")
_IS_DAY_NUM = re.compile(r"^\d{1,2}$")


def _is_date_or_time(s: str) -> bool:
    return bool(
        _IS_FULL_DATE.match(s) or _IS_12H_TIME.match(s) or _IS_24H_TIME.match(s)
        or _IS_MONTH_ABBR.match(s) or _IS_DAY_NUM.match(s)
    )


def fetch_ffvc_events(calendar_url: str, today: str, end_date: str) -> list[dict]:
    """Parse First Flight Venture Center events from their static events page."""
    try:
        resp = requests.get(calendar_url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  SKIP (fetch failed): FFVC — {exc}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    for tag in soup(["script", "style", "nav", "header", "footer", "noscript"]):
        tag.decompose()
    lines = [l.strip().replace(" ", " ") for l in soup.get_text(separator="\n").splitlines() if l.strip()]

    today_dt = datetime.strptime(today, "%Y-%m-%d")
    end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    events: list[dict] = []

    i = 0
    while i < len(lines) - 1:
        # Event block starts with month abbreviation + day number
        if _IS_MONTH_ABBR.match(lines[i]) and i + 1 < len(lines) and _IS_DAY_NUM.match(lines[i + 1]):
            event_date_str = None
            event_time_str = None
            title = None
            description = None
            k = i + 2

            while k < len(lines):
                line = lines[k]
                # Stop when the next event block starts
                if _IS_MONTH_ABBR.match(line) and k + 1 < len(lines) and _IS_DAY_NUM.match(lines[k + 1]):
                    break
                if _IS_FULL_DATE.match(line) and event_date_str is None:
                    event_date_str = line
                elif _IS_12H_TIME.match(line) and event_time_str is None:
                    event_time_str = line
                elif not _is_date_or_time(line):
                    if title is None and len(line) > 5:
                        title = line
                    elif title is not None and len(line) > 50 and description is None:
                        description = line
                k += 1

            i = k

            if not event_date_str or not title:
                continue
            if re.search(r"\bvirtual\b|\bonline only\b|\bwebinar\b", title, re.I):
                print(f"    SKIP (virtual): {title}")
                continue

            try:
                event_dt = datetime.strptime(event_date_str, "%B %d, %Y")
            except ValueError:
                continue
            if event_dt < today_dt or event_dt > end_dt:
                continue

            start_time, end_time = "00:00", ""
            if event_time_str:
                tm = re.match(r"(\d{1,2}:\d{2} [AP]M) – (\d{1,2}:\d{2} [AP]M)", event_time_str)
                if tm:
                    try:
                        start_time = datetime.strptime(tm.group(1), "%I:%M %p").strftime("%H:%M")
                        end_time = datetime.strptime(tm.group(2), "%I:%M %p").strftime("%H:%M")
                    except ValueError:
                        pass

            tags = []
            if re.search(r"\bpitch\b", title, re.I):
                tags.append("Pitch Practice")
            if re.search(r"\bnetwork\b", title, re.I):
                tags.append("Networking")
            if re.search(r"\bai\b|artificial intelligence", title, re.I):
                tags.append("AI & Data")
            if re.search(r"\bdemo\b", title, re.I):
                tags.append("Demo Day")

            events.append({
                "name": title,
                "date": event_dt.strftime("%Y-%m-%d"),
                "start_time": start_time,
                "end_time": end_time,
                "location": _FFVC_LOCATION,
                "topic_tags": list(dict.fromkeys(tags)),
                "description": description or "",
                "host": "First Flight Venture Center",
                "city": "RTP",
                "source_url": calendar_url,
            })
        else:
            i += 1

    print(f"  FFVC: {len(events)} in-range event(s)")
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


def create_event_record(event: dict, orgs: dict[str, str]) -> dict:
    """Write a single event to Airtable, linking Organizer as a record ID."""
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
    org_rec_id = resolve_org(event.get("host", ""), orgs)
    if org_rec_id:
        fields["Organizer"] = [org_rec_id]  # linked record field requires an array
    end_time = str(event.get("end_time", "")).strip()
    if end_time:
        fields["End Time"] = end_time
    tags = event.get("topic_tags")
    if isinstance(tags, list) and tags:
        fields["Topic Tags"] = [str(t).strip() for t in tags if str(t).strip()]
    city = str(event.get("city", "")).strip()
    if city:
        fields["City"] = city
    event_type = str(event.get("event_type", "")).strip()
    if event_type:
        fields["Event Type"] = event_type
    friendly_date = str(event.get("friendly_date", "")).strip()
    if friendly_date:
        fields["Friendly Date"] = friendly_date
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

def _enrich_one(event: dict, client: anthropic.Anthropic) -> dict:
    """Ask Claude to enrich a single event: description, topic_tags, event_type."""
    name = event.get("name", "")
    raw_desc = event.get("description", "").strip()
    location = event.get("location", "")
    host = event.get("host", "")
    approved = ", ".join(APPROVED_TAGS)

    prompt = (
        f"Given this event, return a JSON object with exactly three keys:\n"
        f'- "description": one sentence (20-35 words), third person, specific details, no marketing fluff. '
        f'If no raw description is provided, write one based on the event name and host.\n'
        f'- "topic_tags": JSON array of 1-3 tags chosen strictly from this list: [{approved}]. '
        f'Pick the most specific tags that match — use "Community" only for purely social gatherings '
        f'with no specific topic. Prefer tags like "Networking", "Workshop", "AI & Data", "Fundraising", etc.\n'
        f'- "event_type": single most specific tag from the same list (must appear in topic_tags)\n\n'
        f"Event name: {name}\n"
        f"Raw description: {raw_desc[:700] if raw_desc else '(none)'}\n"
        f"Location: {location}\n"
        f"Host: {host}\n\n"
        f"Return only valid JSON, no markdown fences."
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if hasattr(b, "text")).strip()
        data = json.loads(raw)
        if isinstance(data.get("description"), str) and data["description"].strip():
            event["description"] = data["description"].strip()
        if isinstance(data.get("topic_tags"), list) and data["topic_tags"]:
            event["topic_tags"] = [t for t in data["topic_tags"] if t in APPROVED_TAGS][:3]
        if isinstance(data.get("event_type"), str) and data["event_type"] in APPROVED_TAGS:
            event["event_type"] = data["event_type"]
        else:
            event["event_type"] = (event.get("topic_tags") or ["Networking"])[0]
    except Exception as exc:
        print(f"    WARNING: Enrichment failed for {name!r} — {exc}")
        event.setdefault("event_type", (event.get("topic_tags") or ["Networking"])[0])
    return event


def enrich_events(events: list[dict], client: anthropic.Anthropic) -> list[dict]:
    """Enrich all events: description, topic_tags, event_type via Claude."""
    for ev in events:
        _enrich_one(ev, client)
        time.sleep(0.1)
    print(f"  Enriched {len(events)} event(s)")
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

    print("[1/10] Lila Learning…")
    all_events.extend(fetch_lila_events(today, end_date))

    print("\n[2/10] Luma — Raleigh-Durham Startup Week…")
    all_events.extend(fetch_luma_events("https://lu.ma/raleighdurhamstartupweek", today, end_date))

    meetup_sources = [
        ("triangle-startup-collective", "https://www.meetup.com/triangle-startup-collective/"),
        ("founderslocal",               "https://www.meetup.com/founderslocal/"),
        ("daretoshift",                 "https://www.meetup.com/daretoshift/"),
        ("raleigh-startup-founder-101", "https://www.meetup.com/raleigh-startup-founder-101/"),
        ("triangle-techbreakfast",      "https://www.meetup.com/triangle-techbreakfast/"),
    ]
    for idx, (label, url) in enumerate(meetup_sources, start=3):
        print(f"\n[{idx}/10] Meetup — {label}…")
        all_events.extend(fetch_meetup_events(url, today, end_date))

    print("\n[8/10] CEDNC…")
    all_events.extend(fetch_cednc_events("https://cednc.org/events/", today, end_date))

    print("\n[9/10] First Flight Venture Center…")
    all_events.extend(fetch_ffvc_events("https://www.ffvcnc.org/ourevents", today, end_date))

    print("\n[10/10] 1 Million Cups — Durham (Playwright + Claude)…")
    all_events.extend(fetch_1mc_events(
        "https://www.1millioncups.com/s/account/0014W00002AqQfOQAV/durham-nc",
        client, today, end_date,
    ))

    print(f"\nTotal events found across all sources: {len(all_events)}")

    if not all_events:
        print("Nothing to add.")
        return

    print("\nEnriching events via Claude (description, tags, event_type)…")
    all_events = enrich_events(all_events, client)

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

        key = (event["name"].lower().strip(), event["date"].strip())
        if key in existing:
            print(f"  SKIP (duplicate): {event['name']} on {event['date']}")
            skipped += 1
            continue

        try:
            create_event_record(event, orgs)
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
