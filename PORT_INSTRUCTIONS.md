# Port the prototype into this codebase

The files in `design/reference/` are the design. They are a working React prototype of the new Triangle Startup Events front-end. **Your job is to port them into this build verbatim** — preserving markup structure, class/style values, component boundaries, and interaction behavior — and wire them up to our real data and build pipeline.

This brief is intentionally short. The prototype encodes every visual decision. If you find yourself rewriting JSX or CSS to "clean it up," **stop**. If something looks wrong, ask before changing it.

---

## What you may change

1. **Data source.** The reference uses `data.js` as a fixture (sets `window.TRIANGLE_EVENTS` and `window.PROTO_TODAY`). Replace this with our real scraper output. Match the same event shape:

   ```
   id, name, date (YYYY-MM-DD), start_time (HH:MM), end_time (HH:MM),
   location, city, event_type, audience[], topic_tags[],
   description, source_url, friendly_date, host,
   approved, editors_pick (optional)
   ```

   In production, replace `PROTO_TODAY` with `new Date()`. (It's hardcoded to June 11, 2026 in the prototype so the demo lands mid-month.)

2. **Build integration.** Split files however your toolchain needs (Vite, esbuild, Next, whatever's already here). The reference is plain JSX loaded via inline `<script type="text/babel">` only because the prototype runs from a single HTML file. You'll convert to real ES modules.

3. **The artboard wrapper in `Triangle Events Prototype.html`.** That HTML uses `<DCViewport>`, `<DCSection>`, `<DCArtboard>`, `<IOSDevice>`, and `<TweaksPanel>` to render the app side-by-side at desktop and mobile widths. **Ignore all of that.** It's prototype-only scaffolding. In production, render `<TriangleEventsApp device={...} cardVariant="standard" />` directly into `#root`, switching `device` between `"desktop"` and `"mobile"` via a media-query breakpoint at ~720px (or whatever pattern this repo already uses).

   For the same reason, **don't port** `design-canvas.jsx`, `tweaks-panel.jsx`, or `ios-frame.jsx`. They're not part of the product.

4. **URL hash routing.** The prototype keeps state in component state. In production, persist this in the URL hash so links are shareable: `#view=week&date=2026-06-08&topics=fundraising,ai`. Keys to persist:
   - `view` — `Month` | `Week` | `List`
   - `date` — ISO date of the cursor
   - `topics` — comma-separated active tag filters
   - `q` — search query
   - `event` — selected event id when detail panel is open

5. **Submit form endpoint.** The prototype's submit modal logs to console. Wire it to `POST /api/submit-event` (we'll point that at a Google Sheet or Airtable later).

---

## What you may NOT change

- **Component structure.** Keep `TopBar`, `FilterBar`, `PeriodNav`, `MonthView`, `WeekView`, `ListView`, `EventCard`, `DetailPanel`, `SubmitModal`, `Footer` as separate components with the same prop shapes.
- **Styling.** Use the inline styles and CSS variables from the reference as-is. The CSS custom properties live in `design/reference/assets/colors_and_type.css` — copy that file into your build (e.g. `src/styles/colors_and_type.css`) and import it once at the app root.
- **Color system.** The `ACCENT_PALETTE`, `eventStyle()`, `tagStyle()`, `hashIndex()`, and `topTags()` helpers in `app-shell.jsx` are the source of truth. Events are colored by their primary (first) topic tag — same hash that colors the tag chips, so a coral chip in the filter bar matches coral pills on the calendar. Don't introduce a separate type-based color scheme.
- **Filter bar = top-8 tag chips only.** No City filter, no Audience filter, no Event Type filter. Just `topTags(events, 8)` rendered as toggleable hashtag chips.
- **Today = cyan circle on the date number** in all three views. The Month grid also gives today's cell a cyan border and faint cyan tint.
- **Square corners by default.** Borders only — no rounded "left-border accent" cards. No gradients. Shadows only on hover.
- **Week view: 8am–8pm, fits without scrolling.** Don't change the time range or add vertical scroll to the grid.
- **List view shows upcoming events only** (today and later). Past events are not shown.

---

## Component map

The reference is split into 3 source files. Port them as separate modules with the same boundaries:

| File | Exports |
|---|---|
| `app-shell.jsx` | Date helpers (`parseDate`, `sameDay`, `addDays`, `startOfWeek`, `fmtTime`, `fmtTimeRange`, `durationHours`), filter helpers (`applyFilters`, `topTags`), color system (`ACCENT_PALETTE`, `TAG_PALETTE`, `eventStyle`, `tagStyle`, `hashIndex`), small UI atoms (`TopBar`, `ViewToggle`, `Logomark`, icon components, `iconBtn`, `ctaBtn`) |
| `app-views.jsx` | `FilterBar`, `MonthView`, `MonthEventPill`, `WeekView`, `WeekBlock`, `ListView`, `EventCard`, `TypeChip`, `PickBadge` |
| `app-main.jsx` | `DetailPanel`, `DetailRow`, `SubmitModal`, `PeriodNav`, `Footer`, `TriangleEventsApp` (the root component) |

`data.js` is fixture data — replace with real data source.

---

## Diff-based acceptance

After porting, render the output side-by-side with the prototype at desktop (1440×900) and mobile (390×844) widths. Screenshot both. **Any visible delta is a bug.** Specifically check:

- [ ] TopBar: logo + title + view toggle + search icon + green Submit button (or `+` on mobile)
- [ ] FilterBar: 8 colored hashtag chips, "Filter" eyebrow on the left, result count on the right
- [ ] PeriodNav: month/week label + prev/next arrows + "Today" pill
- [ ] Month view: 7×6 grid, up to 3 pills per day, "+N more" overflow, today cell has cyan border + filled cyan date circle
- [ ] Week view: 8am–8pm gutter, day-of-week header with cyan circle on today, events as absolute-positioned blocks with 3px colored left border
- [ ] List view: grouped by date with sticky headers, three card variants (compact/standard/visual) — standard is the default
- [ ] Detail panel: tinted header (primary tag color), event name, friendly date, Where / Hosted by / For / About / Tags rows, sticky footer with mint "RSVP on host's site" button
- [ ] Submit modal: name / date / start / end / location / city / event type / audience / URL / description fields; confirmation screen on success
- [ ] Mobile: iOS-style mini month calendar with dots, single-column list, full-screen detail sheet from bottom
- [ ] Escape key closes detail panel and submit modal
- [ ] All filters and view selection persist in URL hash

---

## If you're unsure

The reference is the spec. If the brief contradicts the reference, the reference wins. If you can't tell what something should do, ask — don't guess.
