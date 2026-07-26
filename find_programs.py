#!/usr/bin/env python3
"""Find Triangle-area startup accelerators, grants, and programs and sync to Airtable."""
from __future__ import annotations

import json
import os
import re
import sys
import time
from urllib.parse import urlparse

import anthropic
import requests
from playwright.sync_api import sync_playwright

from find_events import (
    ALLOWED_INDUSTRY,
    BROWSER_HEADERS,
    _strip_emojis,
    create_org_stub,
    load_orgs,
    resolve_org,
)

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")
AIRTABLE_API_KEY  = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID  = "apprt7MFT8PcVhFY4"
AIRTABLE_PROGRAMS_URL = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/tblyikQu0nqYi43YN"
AIRTABLE_ORGS_URL     = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/Organizations"

ALLOWED_PROGRAM_TYPE   = ["Accelerator", "Incubator", "Bootcamp", "Competition", "Grant", "Fellowship"]
ALLOWED_STAGE_SERVED   = ["Idea Stage", "Building", "Early Traction", "Scaling"]
ALLOWED_WHAT_YOU_OFFER = [
    "Funding",
    "Investor access",
    "Mentorship",
    "Curriculum",
    "Network/community",
    "Customer/pilot access",
    "Workspace/facilities",
]
ALLOWED_GEO_SCOPE       = ["Triangle-Local", "NC-Regional", "National", "Global"]
ALLOWED_COST            = ["Free", "Equity Only", "Cash Fee", "Equity + Cash Fee"]
ALLOWED_LOCATION_REMOTE = ["In-person", "Remote", "Hybrid"]

# Curated by hand — add new sources here as you discover them.
# Triangle-local sources are prioritized; national ones are secondary.
SOURCES = [
    ("NC IDEA",                  "https://ncidea.org/programs/"),
    ("CED",                      "https://cednc.org/programs/"),
    ("First Flight VC",          "https://ffvcnc.org/programs/"),
    ("RIoT",                     "https://www.rtp-riot.org/riot-accelerator-program"),
    ("American Underground",     "https://americanunderground.com/programs/"),
    ("Duke I&E",                 "https://entrepreneurship.duke.edu/"),
    ("Launch Chapel Hill",       "https://launchchapelhill.com/"),
    ("NC State Entrepreneurship","https://entrepreneurship.ncsu.edu/"),
    ("gener8tor",                "https://www.gener8tor.com/programs"),
    # National staples:
    ("Y Combinator",             "https://www.ycombinator.com/apply"),
    ("Techstars",                "https://www.techstars.com/accelerators"),
    ("MassChallenge",            "https://masschallenge.org/programs/"),
]


# ── Extraction helpers ─────────────────────────────────────────────────────────

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
        print(f"  WARNING: Could not parse JSON array:\n  {text[:400]}")
    return []


# ── Fetching ───────────────────────────────────────────────────────────────────

def fetch_programs_from_page(label: str, url: str, client: anthropic.Anthropic) -> list[dict]:
    """Render page with Playwright, extract programs via Claude."""
    print(f"  Launching Playwright for {label}…")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(user_agent=BROWSER_HEADERS["User-Agent"])
            page.goto(url, timeout=30000)
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)
            text  = page.inner_text("body")
            links = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
            browser.close()
    except Exception as exc:
        print(f"  SKIP (Playwright failed): {label} — {exc}")
        return []

    lines     = [l for l in text.splitlines() if l.strip()]
    page_text = "\n".join(lines)[:12000]

    if links:
        prog_links = [l for l in dict.fromkeys(links) if l != url and l.startswith("http")]
        if prog_links:
            page_text += "\n\nLINKS ON PAGE:\n" + "\n".join(prog_links[:80])

    if not page_text.strip() or len(page_text) < 80:
        print(f"  SKIP: {label} page returned no content")
        return []

    print(f"  {label} page: {len(page_text)} chars — sending to Claude…")

    prompt = (
        f"Extract all startup programs a founder can apply to from this page content for '{label}'. "
        f"Only include programs that have a defined application process or intake (accelerators, "
        f"incubators, grants, fellowships, competitions, bootcamps). "
        f"Skip generic services, consulting offerings, or programs without an application. "
        f"Skip programs clearly irrelevant to startup founders. "
        f"Return ONLY a valid JSON array starting with [ and ending with ]. "
        f"Each object must have: "
        f"name (string, program name), "
        f"program_url (string, specific program page URL if present in LINKS ON PAGE, else use {url!r}), "
        f"description (string, raw description of the program from the page), "
        f"who_its_for (string, one short phrase describing target applicant), "
        f"application_deadline (string, YYYY-MM-DD if a specific deadline is visible, else null), "
        f"host (string, name of the organization running this program). "
        f"Return [] if no applicable programs found.\n\n"
        f"Page content:\n{page_text}"
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        print(f"  ERROR: Claude call failed for {label} — {exc}")
        return []

    raw = "".join(
        b.text for b in response.content
        if hasattr(b, "type") and b.type == "text"
    )
    programs = _parse_json_array(raw)
    print(f"  {label}: {len(programs)} program(s) extracted by Claude")
    return programs


# ── Enrichment ─────────────────────────────────────────────────────────────────

def _enrich_program(program: dict, client: anthropic.Anthropic) -> dict:
    """One Claude call per program to classify and clean it."""
    name        = program.get("name", "")
    raw_desc    = program.get("description", "")
    who         = program.get("who_its_for", "")
    host        = program.get("host", "")
    type_opts   = ", ".join(ALLOWED_PROGRAM_TYPE)
    stage_opts  = ", ".join(ALLOWED_STAGE_SERVED)
    offer_opts  = ", ".join(ALLOWED_WHAT_YOU_OFFER)
    geo_opts    = ", ".join(ALLOWED_GEO_SCOPE)
    cost_opts   = ", ".join(ALLOWED_COST)
    loc_opts    = ", ".join(ALLOWED_LOCATION_REMOTE)
    ind_opts    = ", ".join(ALLOWED_INDUSTRY)

    offer_defs = (
        "Funding — gives cash or investment (grant, prize, or equity). In-kind credits alone do not count. "
        "Investor access — demo day, investor pitch sessions, VC/angel network access. "
        "Mentorship — 1:1 mentors, coaching, advisors, office hours. "
        "Curriculum — structured workshops, modules, cohort curriculum, courses. "
        "Network/community — peer cohort, alumni network, community, partner network. "
        "Customer/pilot access — pilot opportunities, first-customer intros, corporate/partner pilots. "
        "Workspace/facilities — physical desk, office, lab, coworking, or prototyping space."
    )

    prompt = (
        f"Given this startup program, return a JSON object with exactly these keys:\n"
        f'- "description": 1-2 sentences, third person, plain language. '
        f"Describe what the program is and who it serves. No registration/URL/marketing language.\n"
        f'- "who_its_for": one short phrase describing the target applicant\n'
        f'- "program_type": one value strictly from [{type_opts}]\n'
        f'- "stage_served": JSON array of values from [{stage_opts}]\n'
        f'- "what_you_offer": JSON array of values from [{offer_opts}]. '
        f"Definitions: {offer_defs}\n"
        f'- "geographic_scope": one value strictly from [{geo_opts}]. '
        f"Triangle-Local = primarily serves the NC Research Triangle area.\n"
        f'- "cost": one value strictly from [{cost_opts}]\n'
        f'- "industry": JSON array of values from [{ind_opts}]. '
        f'Use "no_specific_industry" only if nothing else applies.\n'
        f'- "location_remote": one value strictly from [{loc_opts}]\n'
        f'- "funding_provided": integer dollars if program gives cash/grant/prize, else null\n'
        f'- "equity_required": true if program takes equity, false otherwise\n\n'
        f"Program name: {name}\n"
        f"Host: {host}\n"
        f"Who it's for: {who}\n"
        f"Raw description: {raw_desc[:600] if raw_desc else '(none)'}\n\n"
        f"Return only valid JSON, no markdown fences."
    )

    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=800,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = "".join(
            b.text for b in response.content
            if hasattr(b, "type") and b.type == "text"
        ).strip()
        if not raw:
            raise ValueError("empty response from Claude")
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.S).strip()
        data = json.loads(raw)

        # Apply enrichment, filtering each list/value against allowed lists
        if isinstance(data.get("description"), str) and data["description"].strip():
            program["description"] = data["description"].strip()
        if isinstance(data.get("who_its_for"), str) and data["who_its_for"].strip():
            program["who_its_for"] = data["who_its_for"].strip()

        ptype = data.get("program_type")
        if isinstance(ptype, str) and ptype in ALLOWED_PROGRAM_TYPE:
            program["program_type"] = ptype

        stage = data.get("stage_served")
        if isinstance(stage, list):
            program["stage_served"] = [v for v in stage if v in ALLOWED_STAGE_SERVED]

        offer = data.get("what_you_offer")
        if isinstance(offer, list):
            program["what_you_offer"] = [v for v in offer if v in ALLOWED_WHAT_YOU_OFFER]

        geo = data.get("geographic_scope")
        if isinstance(geo, str) and geo in ALLOWED_GEO_SCOPE:
            program["geographic_scope"] = geo

        cost = data.get("cost")
        if isinstance(cost, str) and cost in ALLOWED_COST:
            program["cost"] = cost

        industry = data.get("industry")
        if isinstance(industry, list):
            valid = [v for v in industry if v in ALLOWED_INDUSTRY]
            if "no_specific_industry" in valid and len(valid) > 1:
                valid = [v for v in valid if v != "no_specific_industry"]
            program["industry"] = valid

        loc_remote = data.get("location_remote")
        if isinstance(loc_remote, str) and loc_remote in ALLOWED_LOCATION_REMOTE:
            program["location_remote"] = loc_remote

        funding = data.get("funding_provided")
        if isinstance(funding, int):
            program["funding_provided"] = funding
        elif funding is None:
            program["funding_provided"] = None

        equity = data.get("equity_required")
        if isinstance(equity, bool):
            program["equity_required"] = equity

    except Exception as exc:
        print(f"    WARNING: Enrichment failed for {name!r} — {exc}")

    return program


# ── Dedup index ────────────────────────────────────────────────────────────────

def _norm_url(url: str) -> str:
    """Normalize a URL for dedup: lowercase, strip trailing slash, drop query/fragment."""
    parsed = urlparse(url.lower().strip())
    return parsed.scheme + "://" + parsed.netloc + parsed.path.rstrip("/")


class ExistingPrograms:
    """Multi-key index of Airtable programs for duplicate detection."""

    def __init__(self) -> None:
        self.by_url:      set[str]              = set()
        self.by_name_org: set[tuple[str, str]]  = set()

    def add_record(self, fields: dict, record_id: str) -> None:
        prog_url = fields.get("Program URL", "").strip()
        name     = str(fields.get("Program Name", "")).lower().strip()
        org_list = fields.get("Organization") or []
        org_id   = org_list[0] if org_list else ""

        if prog_url:
            self.by_url.add(_norm_url(prog_url))
        if name and org_id:
            self.by_name_org.add((name, org_id))

    def match(self, program: dict, org_rec_id: str) -> str | None:
        """Return reason string if duplicate, else None."""
        prog_url = program.get("program_url", "").strip()
        if prog_url and _norm_url(prog_url) in self.by_url:
            return "program_url"
        name = str(program.get("name", "")).lower().strip()
        if name and org_rec_id and (name, org_rec_id) in self.by_name_org:
            return "name+org"
        return None

    def add_program(self, program: dict, org_rec_id: str) -> None:
        """Mirror a program we just created so subsequent iterations skip it."""
        prog_url = program.get("program_url", "").strip()
        name     = str(program.get("name", "")).lower().strip()
        if prog_url:
            self.by_url.add(_norm_url(prog_url))
        if name and org_rec_id:
            self.by_name_org.add((name, org_rec_id))


def get_existing_programs() -> ExistingPrograms:
    """Fetch all Airtable programs and build a multi-key dedup index."""
    headers = {"Authorization": f"Bearer {AIRTABLE_API_KEY}"}
    params: dict = {"fields[]": ["Program Name", "Program URL", "Organization"]}
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


# ── Writing ────────────────────────────────────────────────────────────────────

def create_program_record(program: dict, orgs: dict[str, str]) -> dict:
    """Write a single program to Airtable. Insert-only — never updates existing records."""
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type":  "application/json",
    }

    host       = program.get("host", "")
    org_rec_id = resolve_org(host, orgs) if host else None

    fields: dict = {
        "Program Name": _strip_emojis(str(program.get("name", "")).strip()),
        "Status":       "Unverified",
    }

    if org_rec_id:
        fields["Organization"] = [org_rec_id]

    prog_url = str(program.get("program_url", "")).strip()
    if prog_url:
        fields["Program URL"] = prog_url

    desc = str(program.get("description", "")).strip()
    if desc:
        fields["Description"] = desc

    who = str(program.get("who_its_for", "")).strip()
    if who:
        fields["Who It's For"] = who

    deadline = program.get("application_deadline")
    if deadline and isinstance(deadline, str) and re.match(r"\d{4}-\d{2}-\d{2}", deadline):
        fields["Application Open/Deadline"] = deadline

    loc_remote = program.get("location_remote")
    if isinstance(loc_remote, str) and loc_remote in ALLOWED_LOCATION_REMOTE:
        fields["Location/Remote"] = loc_remote

    resp = requests.post(AIRTABLE_PROGRAMS_URL, headers=headers, json={"fields": fields}, timeout=30)
    resp.raise_for_status()
    time.sleep(0.25)
    return resp.json()


def is_valid_program(program: dict) -> bool:
    """Require non-empty name and program_url."""
    if not isinstance(program, dict):
        return False
    name = str(program.get("name", "")).strip()
    url  = str(program.get("program_url", "")).strip()
    return bool(name and url)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    if not ANTHROPIC_API_KEY:
        sys.exit("ERROR: ANTHROPIC_API_KEY is not set.")
    if not AIRTABLE_API_KEY:
        sys.exit("ERROR: AIRTABLE_API_KEY is not set.")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print("Triangle Startup Programs — discovery run\n")
    all_programs: list[dict] = []

    for idx, (label, url) in enumerate(SOURCES, start=1):
        print(f"\n[{idx}/{len(SOURCES)}] {label}…")
        programs = fetch_programs_from_page(label, url, client)
        # Ensure host is set from the source label if Claude left it blank
        for p in programs:
            p.setdefault("host", label)
        all_programs.extend(programs)
        time.sleep(0.25)

    print(f"\nTotal programs found across all sources: {len(all_programs)}")

    if not all_programs:
        print("Nothing to add.")
        return

    print("\nEnriching programs via Claude…")
    enriched: list[dict] = []
    for prog in all_programs:
        enriched.append(_enrich_program(prog, client))
        time.sleep(0.1)
    all_programs = enriched
    print(f"  Enriched {len(all_programs)} program(s)")

    print("Fetching organizations from Airtable…")
    orgs = load_orgs()
    print(f"  {len(orgs)} organization(s) loaded.")

    print("Fetching existing programs from Airtable…")
    existing = get_existing_programs()

    added = skipped = errors = 0

    for program in all_programs:
        if not is_valid_program(program):
            name = program.get("name", "unknown") if isinstance(program, dict) else "unknown"
            print(f"  SKIP (invalid — missing name or url): {name!r}")
            skipped += 1
            continue

        # Pre-resolve org to check dedup by name+org
        host       = program.get("host", "")
        org_rec_id = resolve_org(host, orgs) if host else ""

        dup_reason = existing.match(program, org_rec_id or "")
        if dup_reason:
            print(f"  SKIP (duplicate via {dup_reason}): {program['name']!r}")
            skipped += 1
            continue

        try:
            create_program_record(program, orgs)
            print(f"  ADDED: {program['name']!r}")
            existing.add_program(program, org_rec_id or "")
            added += 1
            time.sleep(0.25)
        except requests.HTTPError as exc:
            body = exc.response.text if exc.response is not None else ""
            print(f"  ERROR adding {program.get('name')!r}: {exc}  —  {body[:300]}")
            errors += 1

    print(f"\nFinished. Added: {added} | Skipped: {skipped} | Errors: {errors}")


if __name__ == "__main__":
    main()
