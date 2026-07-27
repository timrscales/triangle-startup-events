#!/usr/bin/env python3
"""
Grants & Programs sync for Triangle Startup Events.

Architecture (v2 — registry-driven):

  programs.yaml is the source of truth for WHICH programs exist. This script
  never invents program records from scraped pages.

  Per registry program, weekly:
    1. Ensure one Airtable record exists (created as Pending Review).
    2. rolling programs  → verify the link is alive, stamp Last Verified.
    3. cyclical programs → hunt the current application deadline with a
       bounded crawl (max pages + max seconds), using a regex pre-filter so
       Claude is only called on pages that actually mention dates near
       deadline language. Found future deadline → patch Next Deadline /
       Cycle Name / Deadline Type=Fixed. Passed deadline → clear it back to
       Annual - TBD and note the change. Nothing found → leave it alone
       (unknown stays unknown; we never write "Rolling" as a guess).

  Discovery (GrepBeat / NCEEM / WRAL) produces LEADS ONLY, written to
  discovery_leads.json for the approval digest email. Discovery never
  writes to Airtable.

Usage:
  python find_programs.py            # live run
  python find_programs.py --dry-run  # print writes instead of performing them

Required env vars:
  AIRTABLE_API_KEY
  ANTHROPIC_API_KEY
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin, urlparse

import anthropic
import requests
import yaml
from bs4 import BeautifulSoup

# ── Config ────────────────────────────────────────────────────────────────────

AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"

AIRTABLE_PROGRAMS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/tblyikQu0nqYi43YN"
AIRTABLE_ORGS_URL     = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"

CLAUDE_MODEL = "claude-haiku-4-5-20251001"

REGISTRY_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), "programs.yaml")
LEADS_FILE      = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discovery_leads.json")

TODAY      = date.today().isoformat()
TODAY_DATE = date.today()

# Deadline-hunt budgets (Playwright fallback pages take ~5s each, so the
# time budget allows a handful of rendered pages per program)
HUNT_MAX_PAGES   = 6
HUNT_MAX_SECONDS = 50

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Upgrade-Insecure-Requests": "1",
}

ALLOWED_DEADLINE_TYPE = ["Fixed", "Rolling", "Annual - TBD"]

DISCOVERY_SOURCES = [
    ("GrepBeat Calendar",  "https://cj.grepbeat.com/calendar.php"),
    ("NCEEM Accelerators", "https://nceem.org/keyword/accelerator-1"),
    ("NCEEM Funding",      "https://nceem.org/keyword/provides-funding-to-ventures"),
    ("WRAL Accelerators",  "https://startupguide.wraltechwire.com/accelerators-mentorship-programs/"),
    ("WRAL Funding",       "https://startupguide.wraltechwire.com/competitions-grants-other-funding/"),
]

# ── Small utilities ───────────────────────────────────────────────────────────

def _norm_url(url: str) -> str:
    parsed = urlparse(url.lower().strip())
    return parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")


def _registered_domain(url: str) -> str:
    """crude eTLD+1: last two labels of the hostname."""
    host = urlparse(url).netloc.lower().split(":")[0]
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


_DATE_RE = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
    r"\.?\s+\d{1,2}(?:st|nd|rd|th)?(?:,?\s*\d{4})?"
    r"|\b\d{1,2}/\d{1,2}/\d{2,4}\b|\b\d{4}-\d{2}-\d{2}\b",
    re.IGNORECASE,
)
_DEADLINE_KW_RE = re.compile(
    r"deadline|apply\s+by|applications?\s+(?:close|due|open|end)|due\s+date|"
    r"submit\s+by|last\s+day\s+to\s+apply|open\s+until|accepting\s+applications|"
    r"applications?\s+are\s+(?:now\s+)?open",
    re.IGNORECASE,
)
_LINK_SCORES = [
    (re.compile(r"deadline|grant-cycle", re.I), 4),
    (re.compile(r"apply|application|admission", re.I), 3),
    (re.compile(r"cycle|cohort|batch", re.I), 2),
    (re.compile(r"20\d\d", re.I), 2),
    (re.compile(r"register|fellowship|program", re.I), 1),
]


def _deadline_hints(page_text: str) -> list[str]:
    """
    Snippets that mention both a date and deadline language. Scans a sliding
    window of 3 lines because page text often splits label and date
    ("Applications Due:" / "August 24th") across lines.
    """
    lines = [l.strip() for l in page_text.splitlines() if l.strip()]
    hits: list[str] = []
    seen: set[str] = set()
    for i in range(len(lines)):
        window = " ".join(lines[i:i + 3])
        if _DEADLINE_KW_RE.search(window) and _DATE_RE.search(window):
            snippet = window[:200]
            if snippet not in seen:
                seen.add(snippet)
                hits.append(snippet)
        if len(hits) >= 12:
            break
    return hits


def _parse_json_object(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, ValueError):
            pass
    return {}


# ── Page fetching ─────────────────────────────────────────────────────────────

def _fetch_page(url: str) -> tuple[str, list[tuple[str, str]], int]:
    """
    Fetch a page with requests. Returns (text, [(abs_href, anchor_text)], status).
    Returns ("", [], status) on failure.
    """
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=15)
        status = resp.status_code
        if status >= 400:
            return "", [], status
        soup = BeautifulSoup(resp.text, "html.parser")
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"].strip())
            if href.startswith("http"):
                links.append((href, a.get_text(" ", strip=True)[:120]))
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True), links, status
    except Exception:
        return "", [], 0


def _playwright_fetch(url: str, label: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Render a page in a real browser. Uses the full Chromium binary in new
    headless mode (channel='chromium') because the default headless shell has
    a fingerprint that WordPress firewalls (e.g. ncidea.org) block with 403.
    Returns (text, links) or ("", []).
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True, channel="chromium")
            except Exception:
                browser = p.chromium.launch(headless=True)
            page = browser.new_page(locale="en-US")
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            page.wait_for_timeout(1200)
            anchors = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(e => [e.href, (e.textContent || '').trim().slice(0, 120)])",
            )
            text = page.evaluate("document.body ? document.body.innerText : ''")
            browser.close()
            links = [(h, t) for h, t in anchors if isinstance(h, str) and h.startswith("http")]
            return text or "", links
    except Exception as exc:
        print(f"    Playwright failed for {label}: {exc}", flush=True)
        return "", []


def _fetch_page_smart(url: str, label: str) -> tuple[str, list[tuple[str, str]], int]:
    """
    Fetch with requests; fall back to Playwright when blocked (403/406) or when
    the page returns little text (JS-rendered or bot-walled sites like
    ncidea.org and ycombinator.com). Returns (text, links, status).
    """
    text, links, status = _fetch_page(url)
    blocked = status in (403, 406, 429) or (status < 400 and len(text) < 200)
    if blocked:
        pw_text, pw_links = _playwright_fetch(url, label)
        if pw_text:
            return pw_text, pw_links, 200
    return text, links, status


def _is_404_or_gone(text: str) -> bool:
    patterns = [
        re.compile(r"page not found|404 not found|this page (could not|doesn.t|does not) exist", re.I),
        re.compile(r"program (has ended|is no longer|has been discontinued|not available)", re.I),
    ]
    return any(p.search(text[:3000]) for p in patterns)


# ── Deadline hunting ──────────────────────────────────────────────────────────

def _ask_claude_deadline(
    client: anthropic.Anthropic, name: str, url: str, hints: list[str], page_text: str
) -> dict:
    """
    Narrow question: what's the current application deadline for this program?
    Returns {"next_deadline": "YYYY-MM-DD"|"", "cycle_name": str, "closed": bool}.
    """
    prompt = (
        f"Today is {TODAY}. The page below is about the startup program '{name}' ({url}).\n\n"
        f"Question: what is the CURRENT application deadline, if one is stated?\n"
        f"Rules:\n"
        f"- Only report a deadline explicitly stated on the page. Never guess.\n"
        f"- If a date has no year, resolve it to the next occurrence on or after today.\n"
        f"- If the page only shows a PAST cycle's deadline, report it anyway (I compare dates).\n"
        f"- cycle_name is a short cohort label like 'Fall 2026' if stated, else ''.\n"
        f"- closed=true only if the page says applications are closed/ended.\n"
        f"Return ONLY JSON: {{\"next_deadline\": \"YYYY-MM-DD or empty\", "
        f"\"cycle_name\": \"...\", \"closed\": false}}\n\n"
        f"Lines mentioning dates near deadline language:\n"
        + "\n".join(hints[:12])
        + f"\n\nPage text:\n{page_text[:5000]}"
    )
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=120,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        return _parse_json_object(raw)
    except Exception as exc:
        print(f"    WARNING: Claude deadline call failed — {exc}", flush=True)
        return {}


def _rank_links(links: list[tuple[str, str]], base_url: str, extra_domains: set[str]) -> list[str]:
    """Score same-domain links by how likely they lead to deadline info."""
    base_domain = _registered_domain(base_url)
    allowed = {base_domain} | extra_domains
    scored: dict[str, int] = {}
    for href, anchor in links:
        if _registered_domain(href) not in allowed:
            continue
        blob = f"{href} {anchor}"
        score = sum(pts for pat, pts in _LINK_SCORES if pat.search(blob))
        if score > 0:
            key = _norm_url(href)
            scored[key] = max(scored.get(key, 0), score)
    return [u for u, _ in sorted(scored.items(), key=lambda kv: -kv[1])]


def hunt_deadline(program: dict, client: anthropic.Anthropic) -> dict:
    """
    Bounded crawl for a cyclical program's current deadline.
    Returns {"next_deadline": str, "cycle_name": str, "closed": bool,
             "dead_link": bool, "pages_checked": int}
    """
    name = program["name"]
    start_urls = [program["url"]] + list(program.get("hunt_urls", []))
    extra_domains = {_registered_domain(u) for u in start_urls}

    started = time.monotonic()
    queue: list[str] = [u for u in start_urls]
    seen: set[str] = set()
    result = {"next_deadline": "", "cycle_name": "", "closed": False,
              "dead_link": False, "pages_checked": 0}
    best_past = ""  # most recent past deadline seen, as closed-cycle evidence

    while queue:
        if result["pages_checked"] >= HUNT_MAX_PAGES:
            break
        if time.monotonic() - started > HUNT_MAX_SECONDS:
            print(f"    Hunt budget exhausted ({HUNT_MAX_SECONDS}s)", flush=True)
            break

        url = queue.pop(0)
        key = _norm_url(url)
        if key in seen:
            continue
        seen.add(key)

        text, links, status = _fetch_page_smart(url, name)
        is_canonical = url == program["url"]
        if not text:
            # 403/429 is bot-blocking, not a dead program — only true
            # not-found statuses count as dead.
            if is_canonical and status in (404, 410):
                result["dead_link"] = True
            continue
        if is_canonical and _is_404_or_gone(text):
            result["dead_link"] = True

        result["pages_checked"] += 1

        # Regex pre-filter: only pay for Claude when the page mentions
        # dates near deadline language.
        hints = _deadline_hints(text)
        if hints:
            answer = _ask_claude_deadline(client, name, url, hints, text)
            nd = str(answer.get("next_deadline", "") or "").strip()[:10]
            if re.match(r"^\d{4}-\d{2}-\d{2}$", nd):
                try:
                    nd_date = date.fromisoformat(nd)
                except ValueError:
                    nd_date = None
                if nd_date and nd_date >= TODAY_DATE:
                    result["next_deadline"] = nd
                    result["cycle_name"] = str(answer.get("cycle_name", "") or "").strip()[:60]
                    print(f"    Deadline {nd} found on {url}", flush=True)
                    return result
                if nd_date:
                    best_past = max(best_past, nd)
            if answer.get("closed") is True:
                result["closed"] = True

        # Enqueue promising same-domain links (canonical + hunt pages only,
        # so the crawl stays one level deep).
        if url in start_urls:
            for ranked in _rank_links(links, url, extra_domains):
                if ranked not in seen and ranked not in queue:
                    queue.append(ranked)

    if best_past:
        result["closed"] = True
    return result


# ── Airtable ──────────────────────────────────────────────────────────────────

def _at_headers() -> dict:
    return {"Authorization": f"Bearer {AIRTABLE_API_KEY}",
            "Content-Type": "application/json"}


def fetch_airtable_programs() -> list[dict]:
    records, params = [], {}
    while True:
        resp = requests.get(AIRTABLE_PROGRAMS_URL, headers=_at_headers(),
                            params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        records.extend(data.get("records", []))
        if not data.get("offset"):
            return records
        params["offset"] = data["offset"]


def fetch_organizations() -> dict[str, str]:
    """Map of lowercase org name → record id."""
    orgs, params = {}, {"fields[]": ["Organization Name"]}
    while True:
        resp = requests.get(AIRTABLE_ORGS_URL, headers=_at_headers(),
                            params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for r in data.get("records", []):
            name = str(r.get("fields", {}).get("Organization Name", "")).strip()
            if name:
                orgs[name.lower()] = r["id"]
        if not data.get("offset"):
            return orgs
        params["offset"] = data["offset"]


def _match_org(org_name: str, orgs: dict[str, str]) -> str | None:
    key = org_name.lower().strip()
    if key in orgs:
        return orgs[key]
    close = difflib.get_close_matches(key, orgs.keys(), n=1, cutoff=0.85)
    return orgs[close[0]] if close else None


def _find_record(program: dict, records: list[dict]) -> dict | None:
    """Match a registry program to an Airtable record by URL, then name."""
    target_url  = _norm_url(program["url"])
    target_name = program["name"].lower().strip()
    by_name = None
    for r in records:
        f = r.get("fields", {})
        rec_url  = str(f.get("Program URL", "") or "").strip()
        rec_name = str(f.get("Program Name", "") or "").lower().strip()
        if rec_url and _norm_url(rec_url) == target_url:
            return r
        # tolerate legacy "Name — Cycle" display names
        if by_name is None and (rec_name == target_name
                                or rec_name.startswith(target_name + " —")):
            by_name = r
    return by_name


def create_record(program: dict, org_id: str | None, dry_run: bool) -> dict | None:
    """Create the Airtable record. Returns the created record, or None."""
    fields: dict = {
        "Program Name":        program["name"],
        "Description":         str(program.get("description", "")).strip(),
        "Program URL":         program["url"],
        "Program Type":        program["type"],
        "Geographic Scope":    program["geo_scope"],
        "Cost":                program["cost"],
        "Location / Remote":   program["location_remote"],
        "Audience":            program.get("audience", ["All Founders"]),
        "Relocation Required": bool(program.get("relocation_required", False)),
        "Deadline Type":       "Rolling" if program["cadence"] == "rolling" else "Annual - TBD",
        "Status":              "Pending Review",
        "Discovery Source":    "registry",
        "Last Verified":       TODAY,
    }
    if program.get("stage_served"):
        fields["Stage Served"] = program["stage_served"]
    if program.get("what_you_offer"):
        fields["What You Offer"] = program["what_you_offer"]
    if org_id:
        fields["Organization"] = [org_id]

    if dry_run:
        print(f"    [DRY RUN] WOULD CREATE: {program['name']}", flush=True)
        return None
    resp = requests.post(AIRTABLE_PROGRAMS_URL, headers=_at_headers(),
                         json={"fields": fields}, timeout=30)
    if resp.status_code >= 400:
        print(f"    ERROR creating {program['name']!r}: {resp.status_code} {resp.text[:200]}",
              flush=True)
        return None
    print(f"    CREATED (Pending Review): {program['name']}", flush=True)
    time.sleep(0.25)
    return resp.json()


def patch_record(record_id: str, fields: dict, dry_run: bool) -> None:
    if dry_run:
        print(f"    [DRY RUN] WOULD PATCH {record_id}: {fields}", flush=True)
        return
    resp = requests.patch(f"{AIRTABLE_PROGRAMS_URL}/{record_id}",
                          headers=_at_headers(), json={"fields": fields}, timeout=30)
    if resp.status_code >= 400:
        print(f"    ERROR patching {record_id}: {resp.status_code} {resp.text[:200]}",
              flush=True)
        return
    time.sleep(0.25)


def _append_note(existing: str, note: str) -> str:
    stamped = f"[{TODAY}] {note}"
    return (existing.rstrip() + "\n" + stamped) if existing else stamped


# ── Registry sync ─────────────────────────────────────────────────────────────

def load_registry() -> list[dict]:
    with open(REGISTRY_FILE) as f:
        registry = yaml.safe_load(f)
    if not isinstance(registry, list):
        raise ValueError("programs.yaml must be a list of program entries")
    required = ["name", "org", "url", "type", "cadence", "geo_scope",
                "cost", "location_remote", "description"]
    for entry in registry:
        missing = [k for k in required if not entry.get(k)]
        if missing:
            raise ValueError(f"Registry entry {entry.get('name', '?')!r} missing: {missing}")
        if entry["cadence"] not in ("cyclical", "rolling"):
            raise ValueError(f"{entry['name']!r}: cadence must be cyclical or rolling")
    return registry


def sync_program(
    program: dict,
    records: list[dict],
    orgs: dict[str, str],
    client: anthropic.Anthropic,
    counters: dict,
    dry_run: bool,
) -> None:
    name = program["name"]
    record = _find_record(program, records)

    if record is None:
        record = create_record(program, _match_org(program["org"], orgs), dry_run)
        counters["created"] += 1
        if record is None:  # dry-run or create failure — nothing to patch yet
            if program["cadence"] == "cyclical":
                print(f"    (deadline hunt deferred — no record id)", flush=True)
            return
        # Newly created record: continue straight into the deadline hunt below.

    fields       = record.get("fields", {})
    record_id    = record["id"]
    old_deadline = str(fields.get("Next Deadline", "") or "").strip()[:10]
    patch: dict  = {"Last Verified": TODAY}

    if program["cadence"] == "rolling":
        text, _, status = _fetch_page_smart(program["url"], program["name"])
        if status in (404, 410) or (text and _is_404_or_gone(text)):
            patch["Pending Changes"] = _append_note(
                str(fields.get("Pending Changes", "") or ""),
                f"DEAD LINK: {program['url']} returned {status or 'error page'}")
            counters["dead_links"] += 1
            print(f"    DEAD LINK ({status})", flush=True)
        patch_record(record_id, patch, dry_run)
        return

    # Cyclical → hunt
    hunt = hunt_deadline(program, client)
    counters["pages_crawled"] += hunt["pages_checked"]

    if hunt["dead_link"]:
        patch["Pending Changes"] = _append_note(
            str(fields.get("Pending Changes", "") or ""),
            f"DEAD LINK: {program['url']}")
        counters["dead_links"] += 1

    if hunt["next_deadline"]:
        if hunt["next_deadline"] != old_deadline:
            print(f"    DEADLINE: {old_deadline or '(none)'} → {hunt['next_deadline']}"
                  + (f" ({hunt['cycle_name']})" if hunt["cycle_name"] else ""), flush=True)
            patch["Next Deadline"] = hunt["next_deadline"]
            patch["Deadline Type"] = "Fixed"
            if hunt["cycle_name"]:
                patch["Cycle Name"] = hunt["cycle_name"]
            counters["deadlines_set"] += 1
        else:
            print(f"    OK: deadline unchanged ({old_deadline})", flush=True)
    elif old_deadline:
        try:
            stale = date.fromisoformat(old_deadline) < TODAY_DATE
        except ValueError:
            stale = True
        if stale:
            print(f"    CYCLE CLOSED: clearing passed deadline {old_deadline}", flush=True)
            patch["Next Deadline"] = None
            patch["Cycle Name"]    = None
            patch["Deadline Type"] = "Annual - TBD"
            patch["Pending Changes"] = _append_note(
                str(fields.get("Pending Changes", "") or ""),
                f"Cycle closed (deadline {old_deadline} passed); reset to Annual - TBD")
            counters["cycles_closed"] += 1
        else:
            print(f"    OK: keeping future deadline {old_deadline} (not re-confirmed)", flush=True)
    else:
        print(f"    No deadline found ({hunt['pages_checked']} page(s) checked)"
              + (" — page says applications closed" if hunt["closed"] else ""), flush=True)

    patch_record(record_id, patch, dry_run)


# ── Discovery (leads only — never writes to Airtable) ────────────────────────

def _extract_leads(label: str, url: str, text: str, client: anthropic.Anthropic) -> list[dict]:
    prompt = (
        f"The text below is from '{label}' ({url}), a page that mentions startup "
        f"programs, grants, accelerators, and competitions in North Carolina.\n"
        f"List the distinct PROGRAM NAMES mentioned (not events, not articles).\n"
        f"Return ONLY a JSON array: [{{\"name\": \"...\", \"url\": \"program page URL if "
        f"shown, else empty\"}}]. Return [] if none.\n\n"
        f"Text:\n{text[:7000]}"
    )
    try:
        response = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        data = json.loads(raw[raw.find("["):raw.rfind("]") + 1]) if "[" in raw else []
        return [d for d in data if isinstance(d, dict) and d.get("name")]
    except Exception as exc:
        print(f"    WARNING: lead extraction failed for {label} — {exc}", flush=True)
        return []


def run_discovery(registry: list[dict], client: anthropic.Anthropic) -> list[dict]:
    print(f"\n=== Discovery sweep ({len(DISCOVERY_SOURCES)} sources — leads only) ===",
          flush=True)
    known = {p["name"].lower() for p in registry}
    leads: list[dict] = []
    seen_names: set[str] = set()

    for label, url in DISCOVERY_SOURCES:
        print(f"  Scanning {label}…", flush=True)
        text, _, status = _fetch_page(url)
        if not text:
            print(f"    skipped (fetch failed, HTTP {status})", flush=True)
            continue
        for lead in _extract_leads(label, url, text, client):
            name = str(lead["name"]).strip()
            key  = name.lower()
            if key in seen_names or len(name) < 4:
                continue
            # skip anything already in the registry (fuzzy)
            if key in known or difflib.get_close_matches(key, known, n=1, cutoff=0.82):
                continue
            lead_url = str(lead.get("url", "") or "").strip()
            if re.search(r"eepurl\.com|mailchi\.mp|campaign-archive", lead_url):
                lead_url = ""
            seen_names.add(key)
            leads.append({"name": name, "url": lead_url, "source": label, "seen": TODAY})
        time.sleep(0.3)

    print(f"  {len(leads)} new lead(s)", flush=True)
    return leads


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not AIRTABLE_API_KEY or not ANTHROPIC_API_KEY:
        print("ERROR: AIRTABLE_API_KEY and ANTHROPIC_API_KEY must be set")
        sys.exit(1)

    registry = load_registry()
    print(f"Registry: {len(registry)} program(s) loaded from programs.yaml", flush=True)

    print("Fetching Airtable state…", flush=True)
    records = fetch_airtable_programs()
    orgs    = fetch_organizations()
    print(f"  {len(records)} program record(s), {len(orgs)} organization(s)", flush=True)

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    counters = {"created": 0, "deadlines_set": 0, "cycles_closed": 0,
                "dead_links": 0, "pages_crawled": 0}

    print(f"\n=== Syncing {len(registry)} registry programs ===", flush=True)
    for i, program in enumerate(registry, 1):
        print(f"\n  [{i}/{len(registry)}] {program['name']}"
              f" ({program['cadence']})", flush=True)
        try:
            sync_program(program, records, orgs, client, counters, args.dry_run)
        except Exception as exc:
            print(f"    ERROR: {exc}", flush=True)

    leads = run_discovery(registry, client)
    if args.dry_run:
        print(f"  [DRY RUN] WOULD WRITE {len(leads)} lead(s) to {LEADS_FILE}", flush=True)
    else:
        with open(LEADS_FILE, "w") as f:
            json.dump(leads, f, indent=2)

    print("\n" + "=" * 60, flush=True)
    print("RUN SUMMARY", flush=True)
    print("=" * 60, flush=True)
    print(f"  Records created:        {counters['created']}", flush=True)
    print(f"  Deadlines set/updated:  {counters['deadlines_set']}", flush=True)
    print(f"  Cycles closed:          {counters['cycles_closed']}", flush=True)
    print(f"  Dead links flagged:     {counters['dead_links']}", flush=True)
    print(f"  Pages crawled:          {counters['pages_crawled']}", flush=True)
    print(f"  Discovery leads:        {len(leads)}", flush=True)


if __name__ == "__main__":
    main()
