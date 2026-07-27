#!/usr/bin/env python3
"""
Find Triangle-area startup accelerators, grants, and programs and sync to Airtable.

Three-pass discovery:
  Pass 1 — Refresh known records (re-check deadlines for existing programs)
  Pass 2 — Curated source sweep (SOURCES list)
  Pass 3 — Discovery sweep (DISCOVERY_SOURCES)

Run with --dry-run to print what would be created/patched without writing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import date
from urllib.parse import urljoin, urlparse

import anthropic
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from find_events import (
    BROWSER_HEADERS,
    _strip_emojis,
    create_org_stub,
    load_orgs,
    resolve_org,
)

# ── Config ────────────────────────────────────────────────────────────────────

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"
AIRTABLE_TABLE_ID = "tblyikQu0nqYi43YN"
AIRTABLE_PROGRAMS_URL     = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_ID}"
AIRTABLE_META_FIELDS_URL  = (
    f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}"
    f"/tables/{AIRTABLE_TABLE_ID}/fields"
)

TODAY = date.today().isoformat()

# ── Allowed values ────────────────────────────────────────────────────────────

ALLOWED_PROGRAM_TYPE = [
    "Accelerator", "Incubator", "Bootcamp", "Competition", "Grant",
    "Fellowship", "Recognition", "Corporate Program"
]
ALLOWED_STAGE_SERVED   = ["Idea Stage", "Building", "Early Traction", "Scaling"]
ALLOWED_WHAT_YOU_OFFER = [
    "Funding", "Investor access", "Mentorship", "Curriculum",
    "Network/community", "Customer/pilot access", "Workspace/facilities"
]
ALLOWED_GEO_SCOPE       = ["Triangle-Local", "NC-Regional", "National", "Global"]
ALLOWED_COST            = ["Free", "Equity Only", "Cash Fee", "Equity + Cash Fee"]
ALLOWED_LOCATION_REMOTE = ["In-person", "Remote", "Hybrid"]
ALLOWED_AUDIENCE        = [
    "Women Founders", "Black Founders", "Latino Founders", "LGBTQ+ Founders",
    "Student Founders", "Veteran Founders", "All Founders"
]
ALLOWED_DEADLINE_TYPE   = ["Fixed", "Rolling", "Annual - TBD"]
ALLOWED_STATUS          = ["Pending Review", "Approved", "Rejected", "Archived"]

# ── Curated sources ───────────────────────────────────────────────────────────

# Triangle-local
SOURCES_TRIANGLE = [
    ("NC IDEA",                  "https://ncidea.org/programs/"),
    ("CED",                      "https://cednc.org/programs/"),
    ("American Underground",     "https://americanunderground.com/idea-to-entrepreneur/"),
    ("First Flight VC",          "https://ffvcnc.org/programs/"),
    ("RIoT",                     "https://riot.org/startup-accelerator/"),
    ("Launch Chapel Hill",       "https://launchchapelhill.com/"),
    ("Innovate Carolina",        "https://innovate.unc.edu/"),
    ("Duke I&E",                 "https://entrepreneurship.duke.edu/"),
    ("NC State Entrepreneurship","https://entrepreneurship.ncsu.edu/"),
    ("Provident1898",            "https://provident1898.com/"),
    ("Grep-a-Palooza",           "https://www.grepapalooza.com/"),
    ("The Launch Place",         "https://www.thelaunchplace.org/"),
    ("AdvanSE PitchRounds",      "https://www.advanse.org/"),
]

# NC-statewide
SOURCES_NC = [
    ("One NC Small Business Program",
     "https://www.commerce.nc.gov/grants-incentives/technology-funds/one-north-carolina-small-business-program"),
    ("NCBiotech",                "https://www.ncbiotech.org/funding/company-funding"),
    ("NSF I-Corps NC State",     "https://kenan.ncsu.edu/initiative/nc-state-nsf-i-corps-hub-program"),
    ("Joules Accelerator",       "https://www.joulesaccelerator.com/"),
    ("NC TECH Awards",           "https://www.nctech.org/awards/"),
    ("GrepBeat Recognition",     "https://cj.grepbeat.com/calendar.php"),
]

# National (no relocation required unless flagged)
SOURCES_NATIONAL = [
    ("Y Combinator",             "https://www.ycombinator.com/apply"),
    ("Techstars Anywhere",       "https://www.techstars.com/accelerators/anywhere"),
    ("gBETA",                    "https://www.gener8tor.com/gbeta"),
    ("Founder Institute",        "https://fi.co/"),
    ("Black Ambition Prize",     "https://blackambitionprize.com/"),
    ("Tory Burch Foundation",    "https://www.toryburchfoundation.org/programs/"),
    ("Military Founders Lab",    "https://ivmf.syracuse.edu/programs/entrepreneurship/"),
    ("Warrior Rising",           "https://warriorrising.org/apply/"),
    # Corporate (rolling, free, remote)
    ("AWS Activate",             "https://aws.amazon.com/activate/"),
    ("Microsoft for Startups",   "https://www.microsoft.com/en-us/startups"),
    ("NVIDIA Inception",         "https://www.nvidia.com/en-us/deep-learning-ai/startups/"),
    ("Google for Startups",      "https://startup.google.com/"),
]

SOURCES = SOURCES_TRIANGLE + SOURCES_NC + SOURCES_NATIONAL

# ── Discovery sources ─────────────────────────────────────────────────────────

DISCOVERY_SOURCES = [
    ("GrepBeat Calendar",       "https://cj.grepbeat.com/calendar.php"),
    ("GrepBeat Newsletters",    "https://cj.grepbeat.com/newsletters.php"),
    ("NCEEM Accelerators",      "https://nceem.org/keyword/accelerator-1"),
    ("NCEEM Pitch",             "https://nceem.org/keyword/pitch-competition"),
    ("NCEEM Funding",           "https://nceem.org/keyword/provides-funding-to-ventures"),
    ("WRAL Accelerators",       "https://startupguide.wraltechwire.com/accelerators-mentorship-programs/"),
    ("WRAL Funding",            "https://startupguide.wraltechwire.com/competitions-grants-other-funding/"),
]

# ── Schema field specs (printed if Meta API returns 403) ──────────────────────

SCHEMA_FIELD_SPECS = [
    {
        "name": "Status", "type": "singleSelect",
        "options": {"choices": [
            {"name": "Pending Review"}, {"name": "Approved"},
            {"name": "Rejected"},       {"name": "Archived"},
        ]},
    },
    {
        "name": "Next Deadline", "type": "date",
        "options": {"dateFormat": {"name": "iso"}},
    },
    {
        "name": "Deadline Type", "type": "singleSelect",
        "options": {"choices": [
            {"name": "Fixed"}, {"name": "Rolling"}, {"name": "Annual - TBD"},
        ]},
    },
    {"name": "Cycle Name", "type": "singleLineText"},
    {
        "name": "Audience", "type": "multipleSelects",
        "options": {"choices": [
            {"name": "Women Founders"},   {"name": "Black Founders"},
            {"name": "Latino Founders"},  {"name": "LGBTQ+ Founders"},
            {"name": "Student Founders"}, {"name": "Veteran Founders"},
            {"name": "All Founders"},
        ]},
    },
    {
        "name": "Relocation Required", "type": "checkbox",
        "options": {"icon": "check", "color": "greenBright"},
    },
    {
        "name": "Last Verified", "type": "date",
        "options": {"dateFormat": {"name": "iso"}},
    },
    {"name": "Discovery Source", "type": "singleLineText"},
]


def try_create_schema_fields() -> None:
    """
    Attempt to create new schema fields via Airtable Meta API.
    If API key lacks schema permissions (403), print the full field specs
    for manual setup and continue — do not exit.
    """
    if not AIRTABLE_API_KEY:
        return
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type":  "application/json",
    }
    print("Attempting to create schema fields via Airtable Meta API…", flush=True)
    failed_403 = False
    for spec in SCHEMA_FIELD_SPECS:
        try:
            resp = requests.post(
                AIRTABLE_META_FIELDS_URL, headers=headers,
                json=spec, timeout=5,
            )
            if resp.status_code == 403:
                failed_403 = True
                break
            if resp.status_code == 422:
                # Field likely already exists
                err = resp.json().get("error", {}).get("message", "")
                if "already exists" in err.lower() or "DUPLICATE_FIELD" in resp.text:
                    print(f"  {spec['name']!r}: already exists — skipping")
                else:
                    print(f"  {spec['name']!r}: 422 — {err}")
            elif resp.status_code in (200, 201):
                print(f"  {spec['name']!r}: created OK")
            else:
                print(f"  {spec['name']!r}: HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as exc:
            print(f"  {spec['name']!r}: ERROR — {exc}")

    if failed_403:
        print(
            "\n  Meta API returned 403 — API key lacks schema permissions.\n"
            "  Create these fields manually in Airtable:\n"
        )
        for spec in SCHEMA_FIELD_SPECS:
            print(f"  Field: {spec['name']!r}  type={spec['type']}")
            if "options" in spec and "choices" in spec["options"]:
                choices = [c["name"] for c in spec["options"]["choices"]]
                print(f"    Choices: {choices}")
        print()


# ── URL normalization ─────────────────────────────────────────────────────────

def _norm_url(url: str) -> str:
    """Normalize a URL: lowercase, strip trailing slash, drop query/fragment."""
    parsed = urlparse(url.lower().strip())
    return parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")


# ── Dedup index ───────────────────────────────────────────────────────────────

class ExistingPrograms:
    """Multi-key index of Airtable programs for duplicate detection."""

    def __init__(self) -> None:
        # Dedup keys (per spec priority order)
        self.by_url_cycle:      set[tuple[str, str]] = set()  # (norm_url, cycle.lower())
        self.by_name_cycle:     set[tuple[str, str]] = set()  # (name.lower(), cycle.lower())
        self.by_name_deadline:  set[tuple[str, str]] = set()  # (name.lower(), deadline_date)
        # Full records for Pass 1 refresh
        self.records: list[dict] = []

    def add_record(self, fields: dict, record_id: str) -> None:
        prog_url   = str(fields.get("Program URL", "") or "").strip()
        name       = str(fields.get("Program Name", "") or "").lower().strip()
        cycle_name = str(fields.get("Cycle Name", "")   or "").lower().strip()
        deadline   = str(fields.get("Next Deadline", "") or "").strip()[:10]

        if prog_url:
            self.by_url_cycle.add((_norm_url(prog_url), cycle_name))
        if name:
            self.by_name_cycle.add((name, cycle_name))
            if deadline:
                self.by_name_deadline.add((name, deadline))

        self.records.append({"id": record_id, "fields": fields})

    def match(self, program: dict) -> str | None:
        """Return reason string if duplicate, else None."""
        prog_url   = str(program.get("source_url", "") or "").strip()
        cycle_name = str(program.get("cycle_name", "") or "").lower().strip()
        name       = str(program.get("name", "") or "").lower().strip()
        deadline   = str(program.get("next_deadline", "") or "").strip()[:10]

        if prog_url and (_norm_url(prog_url), cycle_name) in self.by_url_cycle:
            return "url+cycle"
        if name and (name, cycle_name) in self.by_name_cycle:
            return "name+cycle"
        if name and deadline and (name, deadline) in self.by_name_deadline:
            return "name+deadline"
        return None

    def register(self, program: dict) -> None:
        """Register a newly created program so subsequent iterations see it."""
        prog_url   = str(program.get("source_url", "") or "").strip()
        name       = str(program.get("name", "") or "").lower().strip()
        cycle_name = str(program.get("cycle_name", "") or "").lower().strip()
        deadline   = str(program.get("next_deadline", "") or "").strip()[:10]

        if prog_url:
            self.by_url_cycle.add((_norm_url(prog_url), cycle_name))
        if name:
            self.by_name_cycle.add((name, cycle_name))
            if deadline:
                self.by_name_deadline.add((name, deadline))


def get_existing_programs() -> ExistingPrograms:
    """Fetch all Airtable programs and build a multi-key dedup index."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params: dict = {
        "fields[]": [
            "Program Name", "Program URL", "Status",
            "Next Deadline", "Cycle Name", "Last Verified",
        ]
    }
    existing = ExistingPrograms()

    while True:
        resp = requests.get(AIRTABLE_PROGRAMS_URL, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for record in data.get("records", []):
            existing.add_record(record.get("fields", {}), record["id"])
        offset = data.get("offset")
        if not offset:
            break
        params["offset"] = offset

    return existing


# ── Airtable write helpers ────────────────────────────────────────────────────

def _at_headers() -> dict:
    return {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type":  "application/json",
    }


def patch_program_record(record_id: str, fields: dict, dry_run: bool = False) -> None:
    """PATCH specific fields on an existing program record."""
    if dry_run:
        print(f"  [DRY RUN] WOULD PATCH {record_id}: {fields}")
        return
    url  = f"{AIRTABLE_PROGRAMS_URL}/{record_id}"
    resp = requests.patch(url, headers=_at_headers(), json={"fields": fields}, timeout=30)
    resp.raise_for_status()
    time.sleep(0.25)


def _program_display_name(name: str, cycle_name: str) -> str:
    """Return 'Name — Cycle' if cycle is non-empty, else just name."""
    name  = _strip_emojis(str(name or "").strip())
    cycle = str(cycle_name or "").strip()
    return f"{name} — {cycle}" if cycle else name


_DATETIME_NAME_RE = re.compile(
    r"^\s*(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}",
    re.IGNORECASE,
)


def is_valid_program(program: dict) -> tuple[bool, str]:
    """Return (True, '') or (False, reason)."""
    if not isinstance(program, dict):
        return False, "not a dict"
    name = str(program.get("name", "") or "").strip()
    url  = str(program.get("source_url", "") or "").strip()
    if not name:
        return False, "empty name"
    if _DATETIME_NAME_RE.match(name):
        return False, "name looks like a datetime string"
    if not url:
        return False, "empty source_url"
    deadline_type = program.get("deadline_type", "")
    next_deadline = str(program.get("next_deadline", "") or "").strip()
    if deadline_type == "Fixed" and not next_deadline:
        return False, "Deadline Type=Fixed but next_deadline is empty"
    reloc = program.get("relocation_required", False)
    prog_name_lower = name.lower()
    if reloc and "y combinator" not in prog_name_lower and "yc" not in prog_name_lower:
        print(f"  WARNING: relocation_required=true for non-YC program {name!r} — setting False")
        program["relocation_required"] = False
    return True, ""


def create_program_record(
    program: dict,
    orgs: dict[str, str],
    discovery_source: str = "",
    dry_run: bool = False,
) -> dict | None:
    """Write a single program to Airtable as Pending Review. Returns API response or None."""
    name       = str(program.get("name", "") or "").strip()
    cycle_name = str(program.get("cycle_name", "") or "").strip()
    display_name = _program_display_name(name, cycle_name)

    host       = str(program.get("host", "") or "").strip()
    org_rec_id = resolve_org(host, orgs) if host else None

    fields: dict = {
        "Program Name":  display_name,
        "Status":        "Pending Review",
        "Last Verified": TODAY,
    }

    if org_rec_id:
        fields["Organization"] = [org_rec_id]

    source_url = str(program.get("source_url", "") or "").strip()
    if source_url:
        fields["Program URL"] = source_url

    desc = str(program.get("description", "") or "").strip()
    if desc:
        fields["Description"] = desc

    who = str(program.get("who_its_for", "") or "").strip()
    if who:
        fields["Who It's For"] = who

    # Deadline fields
    next_deadline  = str(program.get("next_deadline", "")  or "").strip()
    deadline_type  = str(program.get("deadline_type", "")  or "").strip()
    if next_deadline and re.match(r"\d{4}-\d{2}-\d{2}", next_deadline):
        fields["Next Deadline"]        = next_deadline
        fields["Application Deadline"] = next_deadline  # keep legacy field in sync
    if deadline_type in ALLOWED_DEADLINE_TYPE:
        fields["Deadline Type"] = deadline_type
    if cycle_name:
        fields["Cycle Name"] = cycle_name

    # Audience (multi-select)
    audience = program.get("audience", [])
    if isinstance(audience, list):
        valid_audience = [a for a in audience if a in ALLOWED_AUDIENCE]
        if not valid_audience:
            valid_audience = ["All Founders"]
        fields["Audience"] = valid_audience

    # Relocation required
    fields["Relocation Required"] = bool(program.get("relocation_required", False))

    # Program Type (single select)
    program_type = str(program.get("program_type", "") or "").strip()
    if program_type in ALLOWED_PROGRAM_TYPE:
        fields["Program Type"] = program_type

    # Stage Served (multi-select)
    stage = program.get("stage_served", [])
    if isinstance(stage, list):
        valid_stage = [v for v in stage if v in ALLOWED_STAGE_SERVED]
        if valid_stage:
            fields["Stage Served"] = valid_stage

    # What You Offer (multi-select)
    offer = program.get("what_you_offer", [])
    if isinstance(offer, list):
        valid_offer = [v for v in offer if v in ALLOWED_WHAT_YOU_OFFER]
        if valid_offer:
            fields["What You Offer"] = valid_offer

    # Geographic Scope (single select)
    geo = str(program.get("geo_scope", "") or "").strip()
    if geo in ALLOWED_GEO_SCOPE:
        fields["Geographic Scope"] = geo

    # Cost (single select)
    cost = str(program.get("cost", "") or "").strip()
    if cost in ALLOWED_COST:
        fields["Cost"] = cost

    # Location/Remote (single select)
    loc_remote = str(program.get("location_remote", "") or "").strip()
    if loc_remote in ALLOWED_LOCATION_REMOTE:
        fields["Location / Remote"] = loc_remote

    # Discovery Source
    ds = discovery_source or str(program.get("discovery_source", "") or "").strip()
    if ds:
        fields["Discovery Source"] = ds

    if dry_run:
        print(f"  [DRY RUN] WOULD CREATE: {display_name!r}")
        return None

    resp = requests.post(AIRTABLE_PROGRAMS_URL, headers=_at_headers(), json={"fields": fields}, timeout=30)
    resp.raise_for_status()
    time.sleep(0.25)
    return resp.json()


# ── JSON parsing helpers ──────────────────────────────────────────────────────

def _parse_json_array(text: str) -> list[dict]:
    """Extract a JSON array from Claude response text."""
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
    end   = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            data = json.loads(text[start:end + 1])
            if isinstance(data, list):
                return data
        except (json.JSONDecodeError, ValueError):
            pass

    if text:
        print(f"  WARNING: Could not parse JSON array: {text[:300]}")
    return []


def _parse_json_object(text: str) -> dict:
    """Extract a JSON object from Claude response text."""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, ValueError):
        pass
    return {}


# ── Enum validation helper ────────────────────────────────────────────────────

def _validate_enums(program: dict, source_label: str) -> dict:
    """
    Validate all enum fields against their allowed lists.
    Log WARNING for invalid values. Never write unvalidated values.
    Returns the program dict with invalid enum values removed/corrected.
    """
    name = program.get("name", "?")

    # Single-select fields
    for field_key, allowed in [
        ("program_type",    ALLOWED_PROGRAM_TYPE),
        ("geo_scope",       ALLOWED_GEO_SCOPE),
        ("cost",            ALLOWED_COST),
        ("location_remote", ALLOWED_LOCATION_REMOTE),
        ("deadline_type",   ALLOWED_DEADLINE_TYPE),
    ]:
        val = program.get(field_key)
        if val and isinstance(val, str) and val not in allowed:
            print(f"  WARNING: {source_label!r} / {name!r}: invalid {field_key}={val!r} — clearing")
            program[field_key] = ""

    # Multi-select fields
    for field_key, allowed in [
        ("stage_served",   ALLOWED_STAGE_SERVED),
        ("what_you_offer", ALLOWED_WHAT_YOU_OFFER),
        ("audience",       ALLOWED_AUDIENCE),
    ]:
        val = program.get(field_key, [])
        if isinstance(val, list):
            invalid = [v for v in val if v not in allowed]
            if invalid:
                print(f"  WARNING: {source_label!r} / {name!r}: invalid {field_key} values {invalid!r} — dropping")
            program[field_key] = [v for v in val if v in allowed]

    return program


# ── Claude extraction ─────────────────────────────────────────────────────────

_EXTRACTION_SCHEMA = (
    "Return ONLY a valid JSON array. Each element must have these keys:\n"
    "  name (string — program name only, no org prefix),\n"
    "  program_type (one of: {program_types}),\n"
    "  description (1-2 sentences, third person, plain language, no URLs/registration/marketing),\n"
    "  host (string — organization running the program),\n"
    "  stage_served (array from: {stage_served}),\n"
    "  what_you_offer (array from: {what_you_offer}),\n"
    "  geo_scope (one of: {geo_scope} — Triangle-Local=primarily NC Research Triangle area,\n"
    "    NC-Regional=statewide NC, National=US-wide no relocation required, Global=worldwide),\n"
    "  cost (one of: {cost}),\n"
    "  location_remote (one of: {location_remote}),\n"
    "  audience (array from: {audience} — use [\"All Founders\"] if unrestricted),\n"
    "  relocation_required (bool — true ONLY for Y Combinator in-person cohort),\n"
    "  deadline_type (one of: {deadline_type}),\n"
    "  next_deadline (YYYY-MM-DD if a specific deadline is visible, else empty string),\n"
    "  cycle_name (e.g. \"Fall 2026\" or \"Spring 2026\" if a named cohort, else empty string),\n"
    "  source_url (the program's specific page URL — NOT the org homepage unless no better URL exists).\n\n"
    "SCOPE RULES:\n"
    "  IN: Accelerators, incubators, bootcamps, grants, competitions, fellowships,\n"
    "      recognition programs, corporate startup programs with an application.\n"
    "  IN: Triangle-local, NC-statewide, national programs NOT requiring relocation.\n"
    "  IN: Remote/hybrid national programs.\n"
    "  IN: Student-only programs (tag Student Founders in audience).\n"
    "  OUT: Ongoing advisory services with no application (SBTDC counseling, VBOC).\n"
    "  OUT: Programs whose audience is not founders.\n"
    "  OUT: City-bound cohorts outside NC (exception: Y Combinator — keep, relocation_required=true).\n"
    "  NEVER create a record with deadline_type=Fixed and empty next_deadline.\n"
    "  Return [] if no applicable programs found."
)


def _build_extraction_prompt(label: str, url: str, page_text: str) -> str:
    schema = _EXTRACTION_SCHEMA.format(
        program_types=", ".join(ALLOWED_PROGRAM_TYPE),
        stage_served=", ".join(ALLOWED_STAGE_SERVED),
        what_you_offer=", ".join(ALLOWED_WHAT_YOU_OFFER),
        geo_scope=", ".join(ALLOWED_GEO_SCOPE),
        cost=", ".join(ALLOWED_COST),
        location_remote=", ".join(ALLOWED_LOCATION_REMOTE),
        audience=", ".join(ALLOWED_AUDIENCE),
        deadline_type=", ".join(ALLOWED_DEADLINE_TYPE),
    )
    return (
        f"Extract all startup programs a founder can apply to from this page for '{label}' ({url}).\n\n"
        f"{schema}\n\n"
        f"Page content:\n{page_text}"
    )


def _claude_extract_programs(
    label: str, url: str, page_text: str, client: anthropic.Anthropic
) -> list[dict]:
    """Send page_text to Claude; return parsed list of programs."""
    prompt = _build_extraction_prompt(label, url, page_text)
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"  ERROR: Claude call failed for {label!r} — {exc}")
        return []

    raw = "".join(
        b.text for b in response.content
        if hasattr(b, "type") and b.type == "text"
    )
    programs = _parse_json_array(raw)
    return [_validate_enums(p, label) for p in programs]


# ── Page fetching (Playwright) ────────────────────────────────────────────────

def _playwright_fetch(url: str, label: str) -> tuple[str, list[str]]:
    """
    Render a page with Playwright. Returns (page_text, links_on_page).
    Returns ("", []) on failure.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
            page.goto(url, timeout=30000)
            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except Exception:
                pass  # proceed with whatever loaded
            page.wait_for_timeout(1500)
            text  = page.inner_text("body")
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            browser.close()
    except Exception as exc:
        print(f"  SKIP (Playwright failed): {label} — {exc}")
        return "", []

    lines = [l for l in text.splitlines() if l.strip()]
    return "\n".join(lines), list(dict.fromkeys(links))


def _requests_fetch(url: str, label: str) -> str:
    """Fetch a page with requests. Returns page text or '' on failure."""
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "noscript"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    except Exception as exc:
        print(f"  SKIP (fetch failed): {label} — {exc}")
        return ""


def _is_404_or_gone(text: str, status_code: int | None = None) -> bool:
    if status_code and status_code >= 400:
        return True
    patterns = [
        re.compile(r"page not found|404 not found|this page (could not|doesn.t|does not) exist", re.I),
        re.compile(r"program (has ended|is no longer|has been discontinued|not available)", re.I),
        re.compile(r"application (is closed|are closed|period has ended)", re.I),
    ]
    for pat in patterns:
        if pat.search(text[:3000]):
            return True
    return False


def fetch_source_page(label: str, url: str, client: anthropic.Anthropic) -> list[dict]:
    """
    Full pipeline for one curated source:
    1. Playwright render
    2. Claude extraction
    3. Follow program-detail links one level deep
    Returns list of extracted program dicts.
    """
    print(f"  Playwright render: {label}…")
    text, links = _playwright_fetch(url, label)
    if not text or len(text) < 80:
        print(f"  SKIP: {label} returned no content")
        return []

    # Build page_text: body + program-detail links appended
    prog_links = [l for l in links if l != url and l.startswith("http")]
    page_text = text[:12000]
    if prog_links:
        page_text += "\n\nLINKS ON PAGE:\n" + "\n".join(prog_links[:80])

    print(f"  {label}: {len(page_text)} chars — extracting via Claude…")
    programs = _claude_extract_programs(label, url, page_text, client)

    # Follow program-detail links one level deep
    detail_programs: list[dict] = []
    seen_detail_urls: set[str] = {url}
    for prog in programs:
        detail_url = str(prog.get("source_url", "") or "").strip()
        if (
            detail_url
            and detail_url not in seen_detail_urls
            and detail_url.startswith("http")
            and _norm_url(detail_url) != _norm_url(url)
        ):
            seen_detail_urls.add(detail_url)
            detail_text = _requests_fetch(detail_url, f"{label} detail")
            if detail_text and len(detail_text) > 80:
                sub = _claude_extract_programs(label, detail_url, detail_text[:8000], client)
                for s in sub:
                    if s not in programs and s not in detail_programs:
                        detail_programs.append(s)
                time.sleep(0.3)

    all_programs = programs + [p for p in detail_programs if p not in programs]
    for p in all_programs:
        p.setdefault("host", label)
    print(f"  {label}: {len(all_programs)} program(s) extracted")
    return all_programs


# ── Pass 1: Refresh known records ─────────────────────────────────────────────

def _extract_deadline_via_claude(
    program_name: str, url: str, page_text: str, client: anthropic.Anthropic
) -> dict:
    """Ask Claude for just the deadline of a known program. Returns partial dict."""
    prompt = (
        f"Given this page about the program '{program_name}', extract application deadline info.\n"
        f"Return ONLY valid JSON with these keys:\n"
        f"  next_deadline: YYYY-MM-DD if a specific deadline is visible, else empty string\n"
        f"  deadline_type: one of {ALLOWED_DEADLINE_TYPE} or empty string\n"
        f"  cycle_name: named cohort like 'Fall 2026' or empty string\n\n"
        f"Page content:\n{page_text[:6000]}"
    )
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=200,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            b.text for b in response.content
            if hasattr(b, "type") and b.type == "text"
        )
        return _parse_json_object(raw)
    except Exception as exc:
        print(f"    WARNING: Deadline extraction failed for {program_name!r} — {exc}")
        return {}


def pass1_refresh(
    existing: ExistingPrograms,
    client: anthropic.Anthropic,
    counters: dict,
    dry_run: bool,
) -> None:
    """
    Pass 1: Re-fetch each known program's page, re-extract deadline, PATCH if changed.
    Only refreshes programs with Status = 'Approved' or 'Pending Review'.
    """
    refreshable = [
        r for r in existing.records
        if r["fields"].get("Program URL")
        and r["fields"].get("Status", "") in ("Approved", "Pending Review", "Unverified")
    ]
    print(f"\n=== Pass 1: Refreshing {len(refreshable)} known programs ===")

    for i, record in enumerate(refreshable, 1):
        fields      = record["fields"]
        record_id   = record["id"]
        prog_url    = str(fields.get("Program URL", "") or "").strip()
        prog_name   = str(fields.get("Program Name", "") or "").strip()
        old_deadline = str(fields.get("Next Deadline", "") or "").strip()[:10]
        status      = str(fields.get("Status", "") or "").strip()

        print(f"  [{i}/{len(refreshable)}] {prog_name[:60]}…")

        # Try requests first, fall back to Playwright
        try:
            resp = requests.get(prog_url, headers=BROWSER_HEADERS, timeout=15)
            status_code = resp.status_code
            if status_code >= 400:
                print(f"    STALE: HTTP {status_code}")
                counters["stale"] += 1
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "noscript"]):
                tag.decompose()
            page_text = soup.get_text(separator="\n", strip=True)
        except requests.exceptions.ConnectionError:
            print(f"    STALE: Connection error")
            counters["stale"] += 1
            continue
        except Exception as exc:
            print(f"    WARNING: Fetch failed — {exc}; trying Playwright")
            page_text, _ = _playwright_fetch(prog_url, prog_name)
            if not page_text:
                print(f"    STALE: Could not fetch page")
                counters["stale"] += 1
                continue

        if _is_404_or_gone(page_text):
            print(f"    STALE: Page indicates program no longer available")
            counters["stale"] += 1
            # Always update Last Verified even for stale programs
            patch_fields = {"Last Verified": TODAY}
            try:
                patch_program_record(record_id, patch_fields, dry_run)
            except Exception:
                pass
            continue

        extracted = _extract_deadline_via_claude(prog_name, prog_url, page_text, client)
        patch_fields: dict = {"Last Verified": TODAY}

        new_deadline = str(extracted.get("next_deadline", "") or "").strip()[:10]
        new_dtype    = str(extracted.get("deadline_type", "") or "").strip()
        new_cycle    = str(extracted.get("cycle_name", "") or "").strip()

        if new_deadline and re.match(r"\d{4}-\d{2}-\d{2}", new_deadline):
            if new_deadline != old_deadline:
                print(f"    CORRECTED: deadline {old_deadline or '(none)'!r} → {new_deadline!r}")
                patch_fields["Next Deadline"]        = new_deadline
                patch_fields["Application Deadline"] = new_deadline
                counters["corrected"] += 1
            else:
                print(f"    OK: deadline unchanged ({old_deadline})")
        else:
            print(f"    OK: no fixed deadline extracted")

        if new_dtype and new_dtype in ALLOWED_DEADLINE_TYPE:
            patch_fields["Deadline Type"] = new_dtype
        if new_cycle:
            patch_fields["Cycle Name"] = new_cycle

        try:
            patch_program_record(record_id, patch_fields, dry_run)
        except Exception as exc:
            print(f"    WARNING: PATCH failed — {exc}")

        time.sleep(0.2)


# ── Pass 2: Curated source sweep ─────────────────────────────────────────────

def pass2_curated(
    existing: ExistingPrograms,
    orgs: dict[str, str],
    client: anthropic.Anthropic,
    counters: dict,
    dry_run: bool,
) -> None:
    """
    Pass 2: Scrape SOURCES list. New programs → Pending Review.
    Existing programs → check/patch deadline as in Pass 1.
    """
    print(f"\n=== Pass 2: Curated source sweep ({len(SOURCES)} sources) ===")

    for idx, (label, url) in enumerate(SOURCES, 1):
        print(f"\n  [{idx}/{len(SOURCES)}] {label}…")
        programs = fetch_source_page(label, url, client)
        time.sleep(0.25)

        for program in programs:
            ok, reason = is_valid_program(program)
            if not ok:
                print(f"    SKIP (invalid — {reason}): {program.get('name', '?')!r}")
                continue

            dup_reason = existing.match(program)
            if dup_reason:
                # On match for curated source: check if deadline differs, patch if so
                print(f"    KNOWN ({dup_reason}): {program.get('name', '?')!r}")
                _patch_if_deadline_changed(program, existing, orgs, counters, dry_run)
                counters["skipped_dup"] += 1
                continue

            # New program
            try:
                create_program_record(program, orgs, dry_run=dry_run)
                display = _program_display_name(
                    program.get("name", ""), program.get("cycle_name", "")
                )
                print(f"    ADDED: {display!r}")
                existing.register(program)
                counters["created"] += 1
                counters["pending"].append(display)
            except requests.HTTPError as exc:
                body = exc.response.text if exc.response is not None else ""
                print(f"    ERROR adding {program.get('name')!r}: {exc} — {body[:200]}")


def _patch_if_deadline_changed(
    program: dict,
    existing: ExistingPrograms,
    orgs: dict[str, str],
    counters: dict,
    dry_run: bool,
) -> None:
    """
    For a program that already exists, find its record and PATCH if deadline differs.
    May PATCH fields on Approved records but never changes their Status.
    """
    prog_url   = str(program.get("source_url", "") or "").strip()
    prog_name  = str(program.get("name", "") or "").lower().strip()
    cycle_name = str(program.get("cycle_name", "") or "").lower().strip()
    new_deadline = str(program.get("next_deadline", "") or "").strip()[:10]

    # Find the matching record in existing.records
    matching_record = None
    for rec in existing.records:
        rf = rec["fields"]
        rec_url   = str(rf.get("Program URL", "") or "").strip()
        rec_name  = str(rf.get("Program Name", "") or "").lower().strip()
        rec_cycle = str(rf.get("Cycle Name", "") or "").lower().strip()
        if prog_url and rec_url and _norm_url(rec_url) == _norm_url(prog_url) and rec_cycle == cycle_name:
            matching_record = rec
            break
        if prog_name and rec_name == prog_name and rec_cycle == cycle_name:
            matching_record = rec
            break

    if not matching_record:
        return

    old_deadline = str(matching_record["fields"].get("Next Deadline", "") or "").strip()[:10]
    patch_fields: dict = {"Last Verified": TODAY}

    if new_deadline and re.match(r"\d{4}-\d{2}-\d{2}", new_deadline) and new_deadline != old_deadline:
        display = _program_display_name(program.get("name", ""), program.get("cycle_name", ""))
        print(f"    CORRECTED: {display!r} deadline {old_deadline!r} → {new_deadline!r}")
        patch_fields["Next Deadline"]        = new_deadline
        patch_fields["Application Deadline"] = new_deadline
        counters["corrected"] += 1

    # Never change Status
    dtype = str(program.get("deadline_type", "") or "").strip()
    if dtype and dtype in ALLOWED_DEADLINE_TYPE:
        patch_fields["Deadline Type"] = dtype

    try:
        patch_program_record(matching_record["id"], patch_fields, dry_run)
    except Exception as exc:
        print(f"    WARNING: PATCH failed — {exc}")


# ── Pass 3: Discovery sweep ───────────────────────────────────────────────────

def _scrape_grepbeat_calendar(url: str) -> list[dict]:
    """
    Parse GrepBeat calendar HTML. Look for DEADLINE:-prefixed entries
    and program/competition announcements.
    """
    text = _requests_fetch(url, "GrepBeat Calendar")
    if not text:
        return []

    programs: list[dict] = []
    lines = text.splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line.upper().startswith("DEADLINE:") or "DEADLINE:" in line.upper():
            # Look backwards for a program name
            name = ""
            for j in range(max(0, i - 5), i):
                candidate = lines[j].strip()
                if len(candidate) > 10 and not candidate.upper().startswith("DEADLINE"):
                    name = candidate
            deadline_text = re.sub(r"(?i)deadline:\s*", "", line).strip()
            deadline_match = re.search(r"(\d{4}-\d{2}-\d{2}|\w+ \d{1,2},?\s*\d{4})", deadline_text)
            next_deadline = ""
            if deadline_match:
                raw_date = deadline_match.group(1)
                try:
                    from datetime import datetime
                    for fmt in ("%Y-%m-%d", "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y"):
                        try:
                            next_deadline = datetime.strptime(raw_date.strip(), fmt).strftime("%Y-%m-%d")
                            break
                        except ValueError:
                            continue
                except Exception:
                    pass
            if name:
                programs.append({
                    "name": name,
                    "source_url": url,
                    "host": "GrepBeat",
                    "discovery_source": "GrepBeat Calendar",
                    "next_deadline": next_deadline,
                    "deadline_type": "Fixed" if next_deadline else "Annual - TBD",
                    "program_type": "Competition",
                    "description": "",
                    "geo_scope": "NC-Regional",
                    "audience": ["All Founders"],
                    "location_remote": "In-person",
                    "cost": "Free",
                    "stage_served": [],
                    "what_you_offer": [],
                    "cycle_name": "",
                    "relocation_required": False,
                })
    return programs


def _scrape_grepbeat_newsletters(url: str, client: anthropic.Anthropic) -> list[dict]:
    """
    Fetch 10 most recent GrepBeat newsletters, resolve eepurl redirects
    with Playwright, extract program announcements.
    """
    print(f"    Fetching newsletter list…")
    text = _requests_fetch(url, "GrepBeat Newsletters")
    if not text:
        return []

    # Find newsletter links — typically eepurl.com or mailchimp archive links
    newsletter_links: list[str] = []
    try:
        resp = requests.get(url, headers=BROWSER_HEADERS, timeout=20)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        for a in soup.find_all("a", href=re.compile(r"eepurl\.com|mailchi\.mp|us\d+\.campaign-archive")):
            href = a.get("href", "").strip()
            if href and href not in newsletter_links:
                newsletter_links.append(href)
    except Exception as exc:
        print(f"    WARNING: GrepBeat newsletter list fetch failed — {exc}")
        return []

    newsletter_links = newsletter_links[:10]
    print(f"    Found {len(newsletter_links)} newsletter link(s)")

    all_programs: list[dict] = []
    for nl_url in newsletter_links:
        # Resolve eepurl redirect with Playwright
        if "eepurl.com" in nl_url:
            text_body, _ = _playwright_fetch(nl_url, "GrepBeat newsletter")
        else:
            text_body = _requests_fetch(nl_url, "GrepBeat newsletter")

        if not text_body or len(text_body) < 100:
            continue

        # Ask Claude to extract program announcements and DEADLINE: entries
        prompt = (
            f"Extract any startup programs, grants, competitions, or accelerators mentioned "
            f"in this newsletter. Look for DEADLINE: entries and program announcements.\n\n"
            f"Return ONLY a JSON array. Each element has:\n"
            f"  name, description (1-2 sentences), next_deadline (YYYY-MM-DD or ''),\n"
            f"  deadline_type (Fixed/Rolling/Annual - TBD), source_url (link to the program if found).\n"
            f"Return [] if no programs found.\n\n"
            f"Newsletter content:\n{text_body[:8000]}"
        )
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = "".join(
                b.text for b in response.content
                if hasattr(b, "type") and b.type == "text"
            )
            found = _parse_json_array(raw)
            for p in found:
                p.setdefault("host", "")
                p.setdefault("discovery_source", "GrepBeat Newsletters")
                p.setdefault("program_type", "")
                p.setdefault("geo_scope", "NC-Regional")
                p.setdefault("audience", ["All Founders"])
                p.setdefault("location_remote", "")
                p.setdefault("cost", "")
                p.setdefault("stage_served", [])
                p.setdefault("what_you_offer", [])
                p.setdefault("cycle_name", "")
                p.setdefault("relocation_required", False)
                if not p.get("source_url"):
                    p["source_url"] = nl_url
                all_programs.append(p)
        except Exception as exc:
            print(f"    WARNING: Newsletter extraction failed — {exc}")

        time.sleep(0.5)

    return all_programs


def _scrape_nceem(url: str, label: str, client: anthropic.Anthropic) -> list[dict]:
    """Scrape NCEEM keyword directory page and extract programs."""
    text = _requests_fetch(url, label)
    if not text or len(text) < 80:
        return []
    print(f"    {label}: {len(text)} chars — extracting via Claude…")
    return _claude_extract_programs(label, url, text[:10000], client)


def _scrape_wral_guide(url: str, label: str, client: anthropic.Anthropic) -> list[dict]:
    """Scrape a WRAL startup guide page and extract programs."""
    text = _requests_fetch(url, label)
    if not text or len(text) < 80:
        return []
    print(f"    {label}: {len(text)} chars — extracting via Claude…")
    return _claude_extract_programs(label, url, text[:10000], client)


def pass3_discovery(
    existing: ExistingPrograms,
    orgs: dict[str, str],
    client: anthropic.Anthropic,
    counters: dict,
    dry_run: bool,
) -> None:
    """
    Pass 3: Scrape DISCOVERY_SOURCES for new programs.
    All discovered items not matching existing → Pending Review with Discovery Source set.
    """
    print(f"\n=== Pass 3: Discovery sweep ({len(DISCOVERY_SOURCES)} sources) ===")

    all_discovered: list[tuple[str, dict]] = []  # (discovery_source_label, program)

    for label, url in DISCOVERY_SOURCES:
        print(f"\n  Scanning {label}…")
        programs: list[dict] = []

        if label == "GrepBeat Calendar":
            programs = _scrape_grepbeat_calendar(url)
        elif label == "GrepBeat Newsletters":
            programs = _scrape_grepbeat_newsletters(url, client)
        elif label.startswith("NCEEM"):
            programs = _scrape_nceem(url, label, client)
        elif label.startswith("WRAL"):
            programs = _scrape_wral_guide(url, label, client)
        else:
            text, links = _playwright_fetch(url, label)
            if text:
                page_text = text[:10000]
                if links:
                    prog_links = [l for l in links if l.startswith("http")][:40]
                    page_text += "\n\nLINKS:\n" + "\n".join(prog_links)
                programs = _claude_extract_programs(label, url, page_text, client)

        for p in programs:
            p.setdefault("discovery_source", label)
        all_discovered.extend((label, p) for p in programs)
        print(f"  {label}: {len(programs)} item(s) found")
        time.sleep(0.5)

    print(f"\n  Processing {len(all_discovered)} discovered item(s)…")
    for discovery_label, program in all_discovered:
        ok, reason = is_valid_program(program)
        if not ok:
            print(f"    SKIP (invalid — {reason}): {program.get('name', '?')!r}")
            continue

        dup_reason = existing.match(program)
        if dup_reason:
            print(f"    KNOWN ({dup_reason}): {program.get('name', '?')!r}")
            counters["skipped_dup"] += 1
            continue

        try:
            create_program_record(program, orgs, discovery_source=discovery_label, dry_run=dry_run)
            display = _program_display_name(
                program.get("name", ""), program.get("cycle_name", "")
            )
            print(f"    ADDED (Discovery): {display!r}")
            existing.register(program)
            counters["created"] += 1
            counters["pending"].append(f"{display} [via {discovery_label}]")
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            print(f"    ERROR adding {program.get('name')!r}: {exc} — {body[:200]}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Find and sync Triangle startup programs to Airtable."
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be created/patched without writing to Airtable.",
    )
    args = parser.parse_args()

    if not ANTHROPIC_API_KEY:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")
    if not AIRTABLE_API_KEY:
        sys.exit("ERROR: AIRTABLE_API_KEY is not set.")

    if args.dry_run:
        print("=== DRY RUN MODE — no Airtable writes will occur ===\n")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Schema fields are managed manually in Airtable; skip auto-creation

    print("Fetching organizations from Airtable…", flush=True)
    orgs = load_orgs()
    print(f"  {len(orgs)} organization(s) loaded.", flush=True)

    print("Fetching existing programs from Airtable…", flush=True)
    existing = get_existing_programs()
    print(f"  {len(existing.records)} program record(s) indexed.", flush=True)

    counters: dict = {
        "created":     0,
        "corrected":   0,
        "stale":       0,
        "skipped_dup": 0,
        "pending":     [],   # list of display names created as Pending Review
    }

    pass1_refresh(existing, client, counters, args.dry_run)
    pass2_curated(existing, orgs, client, counters, args.dry_run)
    pass3_discovery(existing, orgs, client, counters, args.dry_run)

    # End-of-run digest
    print("\n" + "=" * 60)
    print("RUN SUMMARY")
    print("=" * 60)
    print(f"  Created (Pending Review): {counters['created']}")
    print(f"  Corrected (deadline patched): {counters['corrected']}")
    print(f"  Stale (logged, not archived): {counters['stale']}")
    print(f"  Skipped (duplicate): {counters['skipped_dup']}")
    if args.dry_run:
        print("  [DRY RUN — no records were written]")

    if counters["pending"]:
        print(f"\nPending Review records created ({len(counters['pending'])} total):")
        for name in counters["pending"]:
            print(f"  - {name}")
    else:
        print("\nNo new records created.")


if __name__ == "__main__":
    main()
