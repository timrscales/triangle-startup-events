// Triangle Startup Events — root app + DetailPanel + SubmitModal + PeriodNav + Footer
// Mirrors design/reference/app-main.jsx, converted to ES modules with URL hash routing.

import React, { useState, useMemo, useEffect } from 'react'
import { useHash } from './useHash.js'
import {
  TODAY, MONTHS, DOW_FULL,
  parseDate, sameDay, addDays, startOfWeek,
  applyFilters, eventStyle, tagStyle,
  ALL_CITIES, ALL_TYPES, ALL_AUDIENCES,
  TopBar, ChevronLeft, ChevronRight, XIcon, PinIcon, ExternalIcon, StarIcon,
  iconBtn, ctaBtn,
} from './shell.jsx'
import { FilterBar, MonthView, WeekView, ListView, TypeChip, PickBadge } from './views.jsx'

// ── Fixture data (shown when real events aren't injected) ─────────────────────
const FIXTURE = [
  {
    id: "e01", name: "Triangle Startup Collective — June Meeting",
    date: "2026-06-04", start_time: "17:45", end_time: "20:30",
    location: "Raleigh Founded, 509 W North St, Raleigh", city: "Raleigh",
    event_type: "Panel", audience: ["Founders"],
    topic_tags: ["networking", "panel discussion", "community"],
    description: "Monthly meetup featuring startup founders and teams with a panel of experts for practical conversations about building companies from the ground up.",
    source_url: "https://www.meetup.com/triangle-startup-collective/",
    friendly_date: "Thursday, June 4 · 5:45pm–8:30pm",
    host: "Triangle Startup Collective", editors_pick: true,
  },
  {
    id: "e02", name: "AI Tinkerers Triangle",
    date: "2026-06-08", start_time: "18:00", end_time: "20:00",
    location: "Loading Dock, 807 E Main St, Durham", city: "Durham",
    event_type: "Workshop", audience: ["Engineers", "Founders"],
    topic_tags: ["AI & data", "workshop"],
    description: "Monthly hands-on session for builders shipping with LLMs. Bring a laptop and a half-built idea. Lightning demos, open hacking, and pizza.",
    source_url: "https://aitinkerers.org/triangle",
    friendly_date: "Monday, June 8 · 6:00pm–8:00pm",
    host: "AI Tinkerers", editors_pick: true,
  },
  {
    id: "e03", name: "Pitch Practice Workshop",
    date: "2026-06-10", start_time: "09:00", end_time: "12:00",
    location: "First Flight Venture Center, Research Triangle Park", city: "RTP",
    event_type: "Workshop", audience: ["Founders"],
    topic_tags: ["fundraising", "pitch practice"],
    description: "Three-hour intensive on your 2-minute pitch. Live feedback from operators who've raised $10M+. Bring a deck or just an idea.",
    source_url: "https://lu.ma/pitch-practice",
    friendly_date: "Wednesday, June 10 · 9:00am–12:00pm",
    host: "First Flight Venture Center",
  },
  {
    id: "e04", name: "Demo Night: Spring Cohort Showcase",
    date: "2026-06-18", start_time: "18:00", end_time: "21:00",
    location: "American Underground, 201 W Main St, Durham", city: "Durham",
    event_type: "Demo Day", audience: ["Founders", "Investors"],
    topic_tags: ["demo day", "fundraising"],
    description: "Twelve startups, three minutes each. Live Q&A after. Investors, operators, and the merely curious — all welcome.",
    source_url: "https://lu.ma/demo-night",
    friendly_date: "Thursday, June 18 · 6:00pm–9:00pm",
    host: "American Underground", editors_pick: true,
  },
]

// ── Data normalization ─────────────────────────────────────────────────────────
// Maps Airtable event shape → prototype shape.
// Airtable uses `organizer`; the prototype uses `host`.
function cityFromLocation(loc) {
  if (!loc) return "Triangle"
  const l = loc.toLowerCase()
  if (l.includes("raleigh")) return "Raleigh"
  if (l.includes("durham")) return "Durham"
  if (l.includes("chapel hill")) return "Chapel Hill"
  if (l.includes("cary")) return "Cary"
  if (l.includes("research triangle") || l.includes(" rtp")) return "RTP"
  return "Triangle"
}

function normalizeEvent(raw, i) {
  return {
    id:           raw.id || `evt-${i}`,
    name:         raw.name || "",
    date:         raw.date || "",
    start_time:   raw.start_time || "00:00",
    end_time:     raw.end_time   || "",
    location:     raw.location   || "",
    city:         raw.city       || cityFromLocation(raw.location),
    event_type:   raw.event_type || "Talk",
    audience:     Array.isArray(raw.audience) ? raw.audience : [],
    topic_tags:   Array.isArray(raw.topic_tags) ? raw.topic_tags : [],
    description:  raw.description  || "",
    source_url:   raw.source_url   || "",
    friendly_date: raw.friendly_date || "",
    host:         raw.host || raw.organizer || "",
    editors_pick: raw.editors_pick || false,
  }
}

function getRawEvents() {
  try {
    const raw = window.__EVENTS__
    if (Array.isArray(raw) && raw.length > 0) return raw
  } catch (_) {}
  return FIXTURE
}

// ── Detail panel ──────────────────────────────────────────────────────────────
const DetailPanel = ({ event, onClose, device }) => {
  const isMobile = device === "mobile"
  const style = eventStyle(event)

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  const content = (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", background: "var(--paper)" }}>
      <div style={{
        background: style.soft, padding: isMobile ? "16px 16px 18px" : "22px 24px 24px",
        borderBottom: `3px solid ${style.dot}`, position: "relative",
      }}>
        <button onClick={onClose} aria-label="Close" style={{
          position: "absolute", top: 12, right: 12,
          width: 32, height: 32, background: "rgba(255,255,255,0.85)", border: 0, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink)",
        }}>
          <XIcon />
        </button>
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 10 }}>
          <TypeChip style={style} type={event.event_type} />
          {event.editors_pick && <PickBadge />}
        </div>
        <h2 style={{
          fontSize: isMobile ? 22 : 28, fontWeight: 900, color: "var(--ink)",
          letterSpacing: "-0.018em", lineHeight: 1.08, margin: 0, paddingRight: 32,
        }}>{event.name}</h2>
        {event.friendly_date && (
          <div style={{ fontSize: 14, fontWeight: 700, color: style.deep, marginTop: 10 }}>
            {event.friendly_date}
          </div>
        )}
      </div>

      <div style={{ flex: 1, overflowY: "auto", padding: isMobile ? "16px" : "24px" }}>
        <DetailRow label="Where">
          <div style={{ display: "flex", alignItems: "flex-start", gap: 8, color: "var(--ink-2)", fontSize: 14, lineHeight: 1.45 }}>
            <span style={{ paddingTop: 2, color: "var(--muted)" }}><PinIcon /></span>
            <div>
              <div style={{ fontWeight: 700 }}>{event.location.split(",")[0]}</div>
              <div style={{ color: "var(--muted)", fontSize: 13 }}>{event.location.split(",").slice(1).join(",").trim()}</div>
            </div>
          </div>
        </DetailRow>

        {event.host && (
          <DetailRow label="Hosted by">
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-2)" }}>{event.host}</div>
          </DetailRow>
        )}

        {event.audience && event.audience.length > 0 && (
          <DetailRow label="For">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {event.audience.map(a => (
                <span key={a} style={{
                  fontSize: 12, fontWeight: 700, color: "var(--ink-3)",
                  background: "var(--paper-2)", padding: "4px 10px", border: "1px solid var(--line)",
                }}>{a}</span>
              ))}
            </div>
          </DetailRow>
        )}

        {event.description && (
          <DetailRow label="About">
            <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.55, margin: 0 }}>
              {event.description}
            </p>
          </DetailRow>
        )}

        {event.topic_tags && event.topic_tags.length > 0 && (
          <DetailRow label="Tags">
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {event.topic_tags.map(t => {
                const c = tagStyle(t)
                return (
                  <span key={t} style={{
                    fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500,
                    color: c.fg, background: c.bg, padding: "3px 8px",
                  }}>#{t.replace(/\s+/g, "")}</span>
                )
              })}
            </div>
          </DetailRow>
        )}
      </div>

      <div style={{ padding: isMobile ? 14 : 18, borderTop: "1px solid var(--line)", background: "var(--paper)", display: "flex", gap: 10 }}>
        {event.source_url && (
          <a href={event.source_url} target="_blank" rel="noopener noreferrer" style={{
            flex: 1, textAlign: "center", textDecoration: "none",
            background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)",
            padding: "13px 18px", fontWeight: 800, fontSize: 14, letterSpacing: "0.01em",
            display: "inline-flex", alignItems: "center", justifyContent: "center", gap: 8,
            transition: "background 120ms",
          }}
          onMouseEnter={e => e.currentTarget.style.background = "var(--accent-mint-deep)"}
          onMouseLeave={e => e.currentTarget.style.background = "var(--accent-mint)"}
          onClick={e => e.stopPropagation()}>
            Learn More &amp; RSVP <ExternalIcon />
          </a>
        )}
        <button
          onClick={() => navigator.clipboard?.writeText(window.location.href)}
          style={{ padding: "13px 16px", fontFamily: "inherit", fontSize: 13, fontWeight: 800, background: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink-2)", cursor: "pointer" }}>
          Share
        </button>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <div style={{ position: "absolute", inset: 0, background: "var(--paper)", zIndex: 30, display: "flex", flexDirection: "column", animation: "tseSlideUp 220ms var(--ease-out)" }}>
        {content}
      </div>
    )
  }
  return (
    <>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(10,10,10,0.18)", zIndex: 20 }} />
      <div style={{ position: "absolute", top: 0, right: 0, bottom: 0, width: 480, zIndex: 30, boxShadow: "var(--shadow-3)", animation: "tseSlideIn 220ms var(--ease-out)" }}>
        {content}
      </div>
    </>
  )
}

const DetailRow = ({ label, children }) => (
  <div style={{ marginBottom: 22 }}>
    <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>
      {label}
    </div>
    {children}
  </div>
)

const SUBMIT_URL = "https://airtable.com/apprt7MFT8PcVhFY4/pagkomS1oueDY2OLn/form"

// ── Submit modal ──────────────────────────────────────────────────────────────
// Unused as of switching to Airtable hosted form — kept in case we want to
// bring back the in-app form later.
const SubmitModal = ({ onClose, device }) => {
  const isMobile = device === "mobile"
  const [form, setForm] = useState({
    name: "", date: "", start_time: "", end_time: "", location: "",
    city: "Raleigh", event_type: "Talk", audience: [], source_url: "", description: "",
  })
  const [submitted, setSubmitted] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const toggleAud = (a) => setForm(f => ({ ...f, audience: f.audience.includes(a) ? f.audience.filter(x => x !== a) : [...f.audience, a] }))

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  const submit = async (e) => {
    e.preventDefault()
    try {
      await fetch('/api/submit-event', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(form) })
    } catch (_) {
      // endpoint not yet configured — show success regardless
    }
    setSubmitted(true)
  }

  return (
    <div style={{
      position: "absolute", inset: 0, zIndex: 40, background: "rgba(10,10,10,0.45)",
      display: "flex", alignItems: "flex-end", justifyContent: "center",
      padding: isMobile ? 0 : 40,
    }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{
        background: "var(--paper)", width: isMobile ? "100%" : 560, maxWidth: "100%",
        maxHeight: "92%", display: "flex", flexDirection: "column",
        animation: "tseSlideUp 240ms var(--ease-out)",
      }}>
        <div style={{
          padding: isMobile ? "16px" : "22px 28px", borderBottom: "1px solid var(--line)",
          display: "flex", alignItems: "center", justifyContent: "space-between",
        }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", color: "var(--muted)", textTransform: "uppercase" }}>Submit</div>
            <h2 style={{ fontSize: isMobile ? 20 : 24, fontWeight: 900, letterSpacing: "-0.015em", margin: "4px 0 0" }}>Add an event</h2>
          </div>
          <button onClick={onClose} aria-label="Close" style={iconBtn(isMobile)}><XIcon /></button>
        </div>

        {submitted ? (
          <div style={{ padding: 40, textAlign: "center" }}>
            <div style={{ width: 56, height: 56, background: "var(--accent-mint-soft)", color: "var(--accent-mint-deep)", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 16 }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5"/></svg>
            </div>
            <h3 style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-0.012em", margin: "0 0 8px" }}>Thanks — we'll take a look.</h3>
            <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 360, margin: "0 auto" }}>
              Submissions are reviewed before going live.
            </p>
            <button onClick={onClose} style={{ ...ctaBtn, marginTop: 20 }}>Close</button>
          </div>
        ) : (
          <form onSubmit={submit} style={{ padding: isMobile ? 16 : "22px 28px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
            <Field label="Event name" required>
              <input required value={form.name} onChange={e => set("name", e.target.value)} placeholder="e.g. AI Tinkerers Monthly" style={inp} />
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr", gap: 10 }}>
              <Field label="Date" required><input required type="date" value={form.date} onChange={e => set("date", e.target.value)} style={inp} /></Field>
              <Field label="Start" required><input required type="time" value={form.start_time} onChange={e => set("start_time", e.target.value)} style={inp} /></Field>
              <Field label="End time"><input type="time" value={form.end_time} onChange={e => set("end_time", e.target.value)} style={inp} /></Field>
            </div>
            <Field label="Location" required>
              <input required value={form.location} onChange={e => set("location", e.target.value)} placeholder="Venue name, address" style={inp} />
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 10 }}>
              <Field label="City"><ModalSelect value={form.city} onChange={v => set("city", v)} options={ALL_CITIES} /></Field>
              <Field label="Event type"><ModalSelect value={form.event_type} onChange={v => set("event_type", v)} options={ALL_TYPES} /></Field>
            </div>
            <Field label="Who is it for?">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {ALL_AUDIENCES.map(a => {
                  const on = form.audience.includes(a)
                  return (
                    <button type="button" key={a} onClick={() => toggleAud(a)} style={{
                      padding: "7px 12px", fontSize: 12, fontWeight: 700, fontFamily: "inherit", cursor: "pointer",
                      background: on ? "var(--rdsw-blue-dark)" : "var(--paper)",
                      color: on ? "#fff" : "var(--ink-2)",
                      border: `1px solid ${on ? "var(--rdsw-blue-dark)" : "var(--line)"}`,
                    }}>{a}</button>
                  )
                })}
              </div>
            </Field>
            <Field label="RSVP / source URL" required>
              <input required type="url" value={form.source_url} onChange={e => set("source_url", e.target.value)} placeholder="https://lu.ma/…" style={inp} />
            </Field>
            <Field label="Description">
              <textarea value={form.description} onChange={e => set("description", e.target.value)} rows={3} placeholder="One or two sentences. What will people get out of it?" style={{ ...inp, resize: "vertical", fontFamily: "inherit" }} />
            </Field>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, padding: "8px 0" }}>
              <strong style={{ color: "var(--ink-2)" }}>Two rules:</strong> the event must be free, and it must be in-person somewhere in the Triangle. Submissions are reviewed before going live.
            </div>
            <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
              <button type="submit" style={{ ...ctaBtn, flex: 1, padding: "14px 18px", fontSize: 14 }}>Submit for review</button>
              <button type="button" onClick={onClose} style={{ padding: "14px 18px", fontFamily: "inherit", fontSize: 13, fontWeight: 800, background: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink-2)", cursor: "pointer" }}>Cancel</button>
            </div>
          </form>
        )}
      </div>
    </div>
  )
}

const Field = ({ label, required, children }) => (
  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-3)" }}>
      {label}{required && <span style={{ color: "var(--accent-coral-deep)", marginLeft: 4 }}>*</span>}
    </span>
    {children}
  </label>
)

const inp = {
  padding: "10px 12px", fontSize: 14, fontFamily: "inherit",
  border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink)",
  outline: "none", width: "100%", boxSizing: "border-box",
}

const ModalSelect = ({ value, onChange, options }) => (
  <select value={value} onChange={e => onChange(e.target.value)} style={{
    ...inp, appearance: "none",
    backgroundImage: 'url("data:image/svg+xml;utf8,<svg xmlns=%27http://www.w3.org/2000/svg%27 width=%2710%27 height=%2710%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%236B7785%27 stroke-width=%273%27><path d=%27m6 9 6 6 6-6%27/></svg>")',
    backgroundRepeat: "no-repeat", backgroundPosition: "right 12px center", paddingRight: 30,
  }}>
    {options.map(o => <option key={o} value={o}>{o}</option>)}
  </select>
)

// ── Period navigator ──────────────────────────────────────────────────────────
const navBtn = {
  width: 32, height: 32, padding: 0, fontFamily: "inherit",
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink-2)", cursor: "pointer",
}

const PeriodNav = ({ view, cursor, setCursor, device, resultCount }) => {
  const isMobile = device === "mobile"
  const label = (() => {
    if (view === "Week") {
      const start = startOfWeek(cursor)
      const end = addDays(start, 6)
      if (start.getMonth() === end.getMonth()) {
        return `${MONTHS[start.getMonth()]} ${start.getDate()}–${end.getDate()}, ${start.getFullYear()}`
      }
      return `${MONTHS[start.getMonth()].slice(0, 3)} ${start.getDate()} – ${MONTHS[end.getMonth()].slice(0, 3)} ${end.getDate()}`
    }
    if (view === "Month") return `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}`
    return "Upcoming events"
  })()

  const move = (n) => {
    if (view === "Month") {
      const next = new Date(cursor); next.setMonth(next.getMonth() + n); setCursor(next)
    } else if (view === "Week") {
      setCursor(addDays(cursor, n * 7))
    }
  }

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: isMobile ? "10px 12px 4px" : "16px 28px 4px", gap: 12,
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h2 style={{ fontSize: isMobile ? 20 : 28, fontWeight: 900, letterSpacing: "-0.018em", color: "var(--ink)", margin: 0, lineHeight: 1.1 }}>
          {label}
        </h2>
        {view !== "List" && (
          <div style={{ display: "inline-flex", gap: 2, marginLeft: 6 }}>
            <button onClick={() => move(-1)} style={navBtn}><ChevronLeft /></button>
            <button onClick={() => move(1)} style={navBtn}><ChevronRight /></button>
            <button onClick={() => setCursor(new Date(TODAY))} style={{
              padding: "0 12px", height: 32, fontSize: 12, fontWeight: 800, letterSpacing: "0.02em",
              fontFamily: "inherit", border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink-2)",
              cursor: "pointer", marginLeft: 4,
            }}>Today</button>
          </div>
        )}
      </div>
      {isMobile && (
        <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>
          {resultCount} {resultCount === 1 ? "event" : "events"}
        </div>
      )}
    </div>
  )
}

// ── Footer ────────────────────────────────────────────────────────────────────
const Footer = ({ device }) => {
  const isMobile = device === "mobile"
  return (
    <div style={{
      padding: isMobile ? "16px 14px" : "20px 28px",
      borderTop: "1px solid var(--line)", background: "var(--paper-2)",
      display: "flex", flexDirection: isMobile ? "column" : "row",
      alignItems: isMobile ? "flex-start" : "center", justifyContent: "space-between",
      gap: 8, fontSize: 12, color: "var(--muted)",
    }}>
      <div>
        Curated by <a href="https://timscales.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--ink-2)", fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 2 }}>Tim Scales</a> · All events are free &amp; in-person.
      </div>
    </div>
  )
}

// ── Root app ──────────────────────────────────────────────────────────────────
export default function TriangleEventsApp({ device = "desktop", cardVariant = "standard" }) {
  const [hash, setHash] = useHash()
  const [searchOpen, setSearchOpen] = useState(false)

  const view   = hash.view   || "List"
  const topics = hash.topics || []
  const search = hash.q      || ""

  const cursor = useMemo(() => {
    if (hash.date) { const [y,m,d] = hash.date.split("-").map(Number); return new Date(y,m-1,d); }
    return new Date(TODAY)
  }, [hash.date])

  const allEvents = useMemo(() => {
    return getRawEvents()
      .map(normalizeEvent)
      .filter(e => e.date)
      .sort((a, b) => a.date < b.date ? -1 : a.date > b.date ? 1 : a.start_time.localeCompare(b.start_time))
  }, [])

  const filters = { cities: [], types: [], audiences: [], topics }

  const filteredAll = useMemo(() => applyFilters(allEvents, filters, search), [allEvents, topics, search])

  const filteredForView = useMemo(() => {
    if (view !== "List") return filteredAll
    const todayMidnight = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate())
    return filteredAll.filter(e => parseDate(e.date) >= todayMidnight)
  }, [filteredAll, view])

  const selected = useMemo(() => hash.event ? allEvents.find(e => e.id === hash.event) || null : null, [hash.event, allEvents])

  const setView    = (v) => setHash(h => ({ ...h, view: v }))
  const setCursor  = (d) => setHash(h => ({ ...h, date: `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,"0")}-${String(d.getDate()).padStart(2,"0")}` }))
  const setSelected = (ev) => setHash(h => ({ ...h, event: ev ? ev.id : null }))
  const setSearch  = (q) => setHash(h => ({ ...h, q: q || null }))
  const setFilters = (updater) => {
    const next = typeof updater === "function" ? updater(filters) : updater
    setHash(h => ({ ...h, topics: next.topics.length ? next.topics : null }))
  }

  return (
    <div style={{
      width: "100%", height: "100%", display: "flex", flexDirection: "column",
      background: "var(--paper)", color: "var(--ink)", fontFamily: "var(--font-sans)",
      position: "relative", overflow: "hidden",
    }}>
      <TopBar device={device} view={view} setView={setView} onSubmit={() => window.open(SUBMIT_URL, "_blank", "noopener,noreferrer")} searchOpen={searchOpen} setSearchOpen={setSearchOpen} />

      <FilterBar
        device={device} events={allEvents}
        filters={filters} setFilters={setFilters}
        search={search} setSearch={setSearch}
        searchOpen={searchOpen} setSearchOpen={setSearchOpen}
        resultCount={filteredForView.length}
      />

      <PeriodNav view={view} cursor={cursor} setCursor={setCursor} device={device} resultCount={filteredForView.length} />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
        {view === "Month" && <MonthView device={device} cursor={cursor} events={filteredForView} onSelectEvent={setSelected} onSelectDay={() => {}} />}
        {view === "Week"  && <WeekView  device={device} cursor={cursor} events={filteredForView} onSelectEvent={setSelected} />}
        {view === "List"  && <ListView  device={device} events={filteredForView} onSelectEvent={setSelected} cardVariant={cardVariant} />}
      </div>

      <Footer device={device} />

      {selected && <DetailPanel event={selected} onClose={() => setSelected(null)} device={device} />}
    </div>
  )
}
