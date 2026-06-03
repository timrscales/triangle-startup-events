# Triangle Startup Events — Claude Code Context

## What this is

A curated calendar + resource guide for startup founders in the NC Research Triangle (Raleigh, Durham, Chapel Hill, RTP). Two pages, one repo:

- **`/` (index.html)** — filterable events calendar (Month / Week / List views)
- **`/orgs.html`** — Organizations directory (filter by type + stage focus)

Live at **events.timscales.com** (GitHub Pages, custom domain via `cname` in deploy.yml).

## Tech stack

- **React 18 + Vite** (no Next, no Router, no Tailwind)
- **Inline styles only** — no CSS-in-JS, no utility classes. CSS custom properties in `src/styles/colors_and_type.css` are the design system.
- **Hash routing** for the calendar (`#view=week&date=2026-06-08` etc). No React Router.
- **MPA build** — two entry points: `index.html` → `src/main.jsx`, `orgs.html` → `src/orgs-main.jsx`
- **Airtable** as the database (base ID: `apprt7MFT8PcVhFY4`)
- **Data injected at build time** — placeholders `__EVENTS_JSON__`, `__ORG_PROFILES_JSON__`, `__ORGS_JSON__` are replaced by the Python step in deploy.yml. No runtime API calls from the browser.

## Source file map

| File | Purpose |
|---|---|
| `src/shell.jsx` | Date helpers, color system, shared atoms (TopBar, Logomark, icons, ViewToggle) |
| `src/views.jsx` | FilterBar, MonthView, WeekView, ListView, EventCard |
| `src/App.jsx` | DetailPanel, OrgPanel, DayPopover, root TriangleEventsApp component |
| `src/OrgsApp.jsx` | Organizations directory (search, filter, card grid, detail panel) |
| `src/main.jsx` | Entry point for events calendar |
| `src/orgs-main.jsx` | Entry point for organizations page |
| `src/styles/colors_and_type.css` | All CSS variables — colors, type scale, spacing, shadows, motion |
| `src/styles/app.css` | Global resets + keyframe animations |

## Airtable schema (base: apprt7MFT8PcVhFY4)

**Organizations** (`tblXRcsfRnBG3sQgl`)
Fields: Organization Name, Website, Description, Address, Logo, Events (linked), Programs (linked), Organization Type (multi-select), Stage Focus (multi-select), Geography, LinkedIn, Instagram, Founded Year, Status, Archived

Organization Type options: Accelerator, Coworking, Educational, Funding Source, Government, Incubator, Media, Mentor Network, Networking, Service Provider

Stage Focus options (ordered): Exploring → Validating → Building → Growing → Seed Funding → Growth Funding

**Events** (`tblT0CD7h3pVLc5ul`)
Fields: Name, Organization (linked), Date, Start Time, End Time, Location, City (single-select), Topic Tags (multi-select), Description, Source URL, Approved, Archived, Paid, Short description (AI), Location Name, Location Address

City options: Raleigh, Durham, Chapel Hill, RTP — each has a fixed color (cyan, amber, violet, mint respectively)

**Programs** (`tblyikQu0nqYi43YN`)
Fields: Program Name, Description, Who It's For, Location/Remote, Application Open/Deadline, Cohort Start Date, Program URL, Status, Organization (linked)

**Contacts** (`tblcBohaIzzq6vWBB`) — not yet used in the front-end

## Color system

Defined in `src/shell.jsx`, consumed everywhere:

```js
ACCENT_PALETTE = [amber, coral, violet, mint, cyan]  // 5 colors
CITY_COLORS = { Raleigh: cyan, Durham: amber, "Chapel Hill": violet, RTP: mint }
hashIndex(str, mod)  // deterministic string → palette index
tagStyle(tag)        // tag string → { bg, fg }
eventStyle(event)    // event → CITY_COLORS[city] or hash fallback
```

For the orgs page, org type chips use `TAG_PALETTE[hashIndex(type)]`. Stage focus chips use fixed semantic colors (defined in OrgsApp.jsx).

## Hard constraints — do not change without asking

1. **Inline styles only.** No Tailwind, no styled-components, no CSS modules.
2. **Square corners by default** — the brand is geometric. `border-radius` only where explicitly set.
3. **No React Router.** Hash routing for calendar state; plain `href` for page navigation.
4. **`minmax(0, 1fr)` in CSS grid** — never bare `1fr` in repeat(7, ...) day grids. Day cells need `min-width: 0`.
5. **No runtime Airtable calls.** Data is injected at build time. If you need new data fields, add them to the Python injection step in `deploy.yml`.
6. **Week view: 8am–8pm, no vertical scroll.**
7. **List view: upcoming events only** (today and later).

## Deploy pipeline

```
git push → GitHub Actions (deploy.yml)
  1. npm ci + npm run build  (Vite MPA → dist/)
  2. Python: fetch Airtable → inject JSON into dist/index.html + dist/orgs.html
  3. peaceiris/actions-gh-pages → push dist/ to gh-pages branch
  4. GitHub Pages serves at events.timscales.com
```

Trigger manually: Actions → "Deploy Event Calendar" → Run workflow.

The daily.yml workflow runs `find_events.py` (the scraper) on a cron — this discovers new events via Luma/Meetup/etc, enriches them with Claude Haiku, and writes to Airtable. The deploy.yml runs separately to publish whatever is in Airtable.

## Scraper (find_events.py)

Pulls from ~12 sources. Requires env vars:
- `AIRTABLE_API_KEY`
- `ANTHROPIC_API_KEY`

Deduplicates against existing Airtable records before writing. Run locally with those vars set.

## Current known issues / next priorities

- The orgs page `__ORGS_JSON__` placeholder needs the `dist/orgs.html` to exist after build — confirmed via MPA vite config, should work on first deploy.
- Contacts table is populated but not exposed in the UI yet.
- Programs page doesn't exist yet — programs are only shown in the org detail panel.
- The events TopBar "Organizations" link points to `/orgs.html` (works on GitHub Pages, works locally via `vite preview`).
