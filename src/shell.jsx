// Triangle Startup Events — date/filter/color helpers + UI atoms
// Mirrors design/reference/app-shell.jsx, converted to ES modules.

import React from 'react'

export const TODAY = new Date()

// ── Date helpers ──────────────────────────────────────────────────────────────
export const MONTHS = ["January","February","March","April","May","June","July","August","September","October","November","December"]
export const DOW_SHORT = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"]
export const DOW_FULL = ["Sunday","Monday","Tuesday","Wednesday","Thursday","Friday","Saturday"]

export function parseDate(s) { const [y,m,d] = s.split("-").map(Number); return new Date(y, m-1, d); }
export function sameDay(a, b) { return a.getFullYear()===b.getFullYear() && a.getMonth()===b.getMonth() && a.getDate()===b.getDate(); }
export function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate()+n); return x; }
export function startOfWeek(d) { const x = new Date(d); x.setDate(x.getDate()-x.getDay()); x.setHours(0,0,0,0); return x; }
export function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1); }

export function fmtTime(t) {
  if (!t || t === "00:00") return ""
  const [h, m] = t.split(":").map(Number)
  const period = h >= 12 ? "pm" : "am"
  const h12 = (h + 11) % 12 + 1
  return m ? `${h12}:${String(m).padStart(2,"0")}${period}` : `${h12}${period}`
}
export function fmtTimeRange(s, e) {
  const a = fmtTime(s), b = fmtTime(e)
  return a && b ? `${a}–${b}` : a || ""
}
export function durationHours(s, e) {
  const [sh, sm] = s.split(":").map(Number)
  const [eh, em] = e.split(":").map(Number)
  return (eh * 60 + em - (sh * 60 + sm)) / 60
}

// ── Filter helpers ────────────────────────────────────────────────────────────
export const ALL_CITIES = ["Raleigh","Durham","Chapel Hill","RTP"]
export const ALL_TYPES = ["Talk","Panel","Workshop","Happy Hour","Networking","Demo Day"]
export const ALL_AUDIENCES = ["Founders","Engineers","Designers","Investors"]

export function topTags(events, n = 8) {
  const counts = {}
  for (const e of events)
    for (const t of (e.topic_tags || [])) { const k = t.toLowerCase(); counts[k] = (counts[k]||0)+1; }
  return Object.entries(counts)
    .sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]))
    .slice(0, n)
    .map(([tag, count]) => ({ tag, count }))
}

export function applyFilters(events, f, search) {
  return events.filter(e => {
    if (f.cities.length && !f.cities.includes(e.city)) return false
    if (f.types.length && !f.types.includes(e.event_type)) return false
    if (f.audiences.length && !(e.audience||[]).some(a => f.audiences.includes(a))) return false
    if (f.topics.length && !(e.topic_tags||[]).some(t => f.topics.map(x=>x.toLowerCase()).includes(t.toLowerCase()))) return false
    if (search) {
      const q = search.toLowerCase()
      const hay = (e.name+" "+e.description+" "+e.location+" "+(e.topic_tags||[]).join(" ")).toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

// ── Color system ──────────────────────────────────────────────────────────────
// Events are colored by their primary (first) topic tag so the chip in the
// filter bar always matches the pill/block on the calendar.
export const ACCENT_PALETTE = [
  { dot: "#FFB648", soft: "#FFE9C2", deep: "#E68A00" }, // amber
  { dot: "#FC7777", soft: "#FDDADA", deep: "#E10505" }, // coral
  { dot: "#B577FC", soft: "#E6D3FE", deep: "#6B05E1" }, // violet
  { dot: "#1BE0B0", soft: "#C7F5E6", deep: "#009F97" }, // mint
  { dot: "#009DE0", soft: "#C9E9F7", deep: "#003D69" }, // cyan
]
export const TAG_PALETTE = ACCENT_PALETTE.map(p => ({ bg: p.soft, fg: p.deep }))

export function hashIndex(str, mod) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h % mod
}
export function eventStyle(event) {
  const primary = (event.topic_tags && event.topic_tags[0]) || event.event_type || ""
  return ACCENT_PALETTE[hashIndex(primary.toLowerCase(), ACCENT_PALETTE.length)]
}
export function tagStyle(tag) {
  return TAG_PALETTE[hashIndex(tag.toLowerCase(), TAG_PALETTE.length)]
}

// ── UI atoms ──────────────────────────────────────────────────────────────────
export const iconBtn = (isMobile) => ({
  width: isMobile ? 36 : 38, height: isMobile ? 36 : 38,
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "var(--paper)", border: "1px solid var(--line)", cursor: "pointer", padding: 0,
  color: "var(--ink-3)",
})

export const ctaBtn = {
  background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)", border: 0,
  padding: "10px 16px", fontSize: 13, fontWeight: 800, letterSpacing: "0.01em",
  fontFamily: "inherit", cursor: "pointer", transition: "background 120ms",
}

export const SearchIcon = () =>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/>
  </svg>

export const PlusIcon = () =>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
    <path d="M12 5v14M5 12h14"/>
  </svg>

export const ChevronLeft = () =>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="m15 18-6-6 6-6"/>
  </svg>

export const ChevronRight = () =>
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round">
    <path d="m9 18 6-6-6-6"/>
  </svg>

export const XIcon = () =>
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
    <path d="M18 6 6 18M6 6l12 12"/>
  </svg>

export const PinIcon = () =>
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 10c0 7-8 13-8 13s-8-6-8-13a8 8 0 0 1 16 0Z"/><circle cx="12" cy="10" r="3"/>
  </svg>

export const ExternalIcon = () =>
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
  </svg>

export const StarIcon = ({ filled }) =>
  <svg width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinejoin="round">
    <polygon points="12 2 15 8.5 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 9 8.5 12 2"/>
  </svg>

export const Logomark = ({ size = 36 }) =>
  <div style={{
    width: size, height: size, background: "var(--rdsw-blue)",
    display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr",
    gap: Math.max(1, size * 0.06), padding: Math.max(2, size * 0.16),
    boxSizing: "border-box",
  }}>
    <div style={{ background: "var(--rdsw-blue-dark)" }} />
    <div />
    <div style={{ background: "var(--rdsw-blue-dark)" }} />
    <div style={{ background: "var(--rdsw-blue-dark)" }} />
  </div>

export const ViewToggle = ({ view, setView, isMobile }) => {
  const views = ["Month", "Week", "List"]
  return (
    <div style={{ display: "inline-flex", border: "1px solid var(--line)", background: "var(--paper-2)", padding: 2, gap: 2 }}>
      {views.map(v => {
        const active = view === v
        return (
          <button key={v} onClick={() => setView(v)} style={{
            padding: isMobile ? "8px 12px" : "8px 18px",
            fontSize: isMobile ? 12 : 13, fontWeight: 800, letterSpacing: "0.02em",
            background: active ? "var(--ink)" : "transparent",
            color: active ? "#fff" : "var(--ink-3)",
            border: 0, cursor: "pointer", fontFamily: "inherit", transition: "background 120ms",
          }}>{v}</button>
        )
      })}
    </div>
  )
}

export const TopBar = ({ device, view, setView, onSubmit, searchOpen, setSearchOpen }) => {
  const isMobile = device === "mobile"
  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: isMobile ? "12px 16px" : "16px 28px",
      borderBottom: "1px solid var(--line)", background: "var(--paper)",
      gap: isMobile ? 10 : 20, flexWrap: isMobile ? "wrap" : "nowrap",
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
        <Logomark size={isMobile ? 30 : 36} />
        <div style={{ display: "flex", flexDirection: "column", lineHeight: 1, minWidth: 0 }}>
          <span style={{ fontSize: isMobile ? 14 : 16, fontWeight: 900, letterSpacing: "-0.01em", color: "var(--ink)", whiteSpace: "nowrap" }}>
            Triangle Startup Events
          </span>
          {!isMobile && (
            <span style={{ fontSize: 12, color: "var(--muted)", marginTop: 4, fontWeight: 500 }}>
              Free, in-person events for founders &amp; their teams in the Raleigh-Durham area
            </span>
          )}
        </div>
      </div>

      <ViewToggle view={view} setView={setView} isMobile={isMobile} />

      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <button onClick={() => setSearchOpen(!searchOpen)} aria-label="Search" style={iconBtn(isMobile)}>
          <SearchIcon />
        </button>
        {!isMobile && <button onClick={onSubmit} style={ctaBtn}>Submit an Event</button>}
        {isMobile && (
          <button onClick={onSubmit} aria-label="Submit event" style={iconBtn(true)}>
            <PlusIcon />
          </button>
        )}
      </div>
    </div>
  )
}
