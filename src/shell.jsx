import React from 'react'

export const { useState, useMemo, useEffect, useRef } = React

// ──────────────────────── date helpers ────────────────────────
export const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
export const DOW_SHORT = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
export const DOW_FULL = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

export const TODAY = new Date()
export const TODAY_START = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate())

export function parseDate(s) { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d) }
export function isPast(dateStr) { return parseDate(dateStr) < TODAY_START }
export function sameDay(a, b) { return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate() }
export function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x }
export function startOfWeek(d) { const x = new Date(d); x.setDate(x.getDate() - x.getDay()); x.setHours(0, 0, 0, 0); return x }
export function startOfMonth(d) { return new Date(d.getFullYear(), d.getMonth(), 1) }
export function fmtTime(t) {
  if (!t) return ""
  const [h, m] = t.split(":").map(Number)
  const period = h >= 12 ? "pm" : "am"
  const h12 = (h + 11) % 12 + 1
  return m ? `${h12}:${String(m).padStart(2, "0")}${period}` : `${h12}${period}`
}
export function fmtTimeRange(s, e) { return `${fmtTime(s)}–${fmtTime(e)}` }
export function durationHours(s, e) {
  const [sh, sm] = s.split(":").map(Number)
  const [eh, em] = e.split(":").map(Number)
  return (eh * 60 + em - (sh * 60 + sm)) / 60
}

// ──────────────────────── filter helpers ────────────────────────
export const ALL_CITIES = ["Chapel Hill", "Durham", "Raleigh", "RTP"]
export const ALL_TYPES = ["Talk", "Panel", "Workshop", "Happy Hour", "Networking", "Demo Day"]
export const ALL_AUDIENCES = ["Founders", "Engineers", "Designers", "Investors"]
export const ALL_TOPICS = ["AI", "fundraising", "hardware", "design", "networking", "happy hour"]

// ──────────────────────── tag palette (shared) ────────────────────────
export const ACCENT_PALETTE = [
  { dot: "#FFB648", soft: "#FFE9C2", deep: "#8C5400" }, // amber
  { dot: "#FC7777", soft: "#FDDADA", deep: "#B30202" }, // coral
  { dot: "#B577FC", soft: "#E6D3FE", deep: "#5A04C0" }, // violet
  { dot: "#1BE0B0", soft: "#C7F5E6", deep: "#006B65" }, // mint
  { dot: "#009DE0", soft: "#C9E9F7", deep: "#003D69" }, // cyan
]
export const TAG_PALETTE = ACCENT_PALETTE.map(p => ({ bg: p.soft, fg: p.deep }))
export function hashIndex(str, mod) {
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h % mod
}

// Fixed city→color mapping so the calendar builds a learnable visual grammar.
export const CITY_COLORS = {
  "Raleigh":     ACCENT_PALETTE[4], // cyan   — brand/capital
  "Durham":      ACCENT_PALETTE[0], // amber  — warm, energetic
  "Chapel Hill": ACCENT_PALETTE[2], // violet — academic
  "RTP":         ACCENT_PALETTE[3], // mint   — tech/research
}

export function eventStyle(event) {
  return CITY_COLORS[event.city]
    || ACCENT_PALETTE[hashIndex((event.city || "").toLowerCase(), ACCENT_PALETTE.length)]
}
export function cityStyle(city) {
  return CITY_COLORS[city]
    || ACCENT_PALETTE[hashIndex((city || "").toLowerCase(), ACCENT_PALETTE.length)]
}
export function tagStyle(tag) {
  return TAG_PALETTE[hashIndex(tag.toLowerCase(), TAG_PALETTE.length)]
}
export function uniqueCities(events) {
  return [...new Set(events.map(e => e.city).filter(Boolean))].sort()
}

export function topTags(events, n = 8) {
  const counts = {}
  for (const e of events) {
    for (const t of (e.topic_tags || [])) {
      const key = t.toLowerCase()
      counts[key] = (counts[key] || 0) + 1
    }
  }
  return Object.entries(counts)
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, n)
    .map(([tag, count]) => ({ tag, count }))
}

export function applyFilters(events, f, search) {
  return events.filter((e) => {
    if (f.cities.length && !f.cities.includes(e.city)) return false
    if (f.types.length && !f.types.includes(e.event_type)) return false
    if (f.audiences.length && !(e.audience || []).some((a) => f.audiences.map(x => x.toLowerCase()).includes(a.toLowerCase()))) return false
    if (f.topics.length && !(e.topic_tags || []).some((t) => f.topics.map((x) => x.toLowerCase()).includes(t.toLowerCase()))) return false
    if (f.free === 'free' && e.is_free === false) return false
    if (f.free === 'paid' && e.is_free !== false) return false
    if (search) {
      const q = search.toLowerCase()
      const hay = (e.name + " " + e.description + " " + e.location + " " + (e.topic_tags || []).join(" ")).toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

// ──────────────────────── SF-3 Search & Filter Popover ────────────────────────
const SearchFilterPopover = ({ events, filters, setFilters, search, setSearch, resultCount, onClose }) => {
  const inputRef = useRef(null)
  const tags = useMemo(() => topTags(events, 8), [events])
  const cities = useMemo(() => [...new Set(events.map(e => e.city).filter(Boolean))].sort(), [events])
  const activeTags = filters.topics.map(t => t.toLowerCase())
  const activeCities = filters.cities

  const toggle = (tag) => setFilters(f => ({
    ...f,
    topics: f.topics.map(x => x.toLowerCase()).includes(tag.toLowerCase())
      ? f.topics.filter(x => x.toLowerCase() !== tag.toLowerCase())
      : [...f.topics, tag],
  }))
  const toggleCity = (city) => setFilters(f => ({
    ...f,
    cities: f.cities.includes(city) ? f.cities.filter(x => x !== city) : [...f.cities, city],
  }))
  const clearAll = () => { setSearch(''); setFilters({ cities: [], types: [], audiences: [], topics: [], free: 'all' }) }

  const hasAny = search || activeTags.length > 0 || activeCities.length > 0

  useEffect(() => {
    if (inputRef.current) inputRef.current.focus()
  }, [])

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <>
      <div onClick={onClose} style={{ position: 'fixed', inset: 0, zIndex: 49 }} />
      <div
        onClick={e => e.stopPropagation()}
        style={{
          position: 'absolute', top: 'calc(100% + 6px)', right: 0,
          width: 340, zIndex: 50,
          background: 'var(--paper)',
          border: '1px solid var(--line)',
          boxShadow: '0 8px 32px rgba(0,61,105,0.14)',
          animation: 'sfPopover 140ms cubic-bezier(.2,.8,.2,1)',
        }}
      >
        {/* Search row */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 12px', borderBottom: '1px solid var(--line)' }}>
          <span style={{ color: 'var(--muted)', display: 'flex', alignItems: 'center', flexShrink: 0 }}><SearchIcon /></span>
          <input
            ref={inputRef}
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search events…"
            style={{
              flex: 1, border: 'none', outline: 'none', background: 'transparent',
              fontSize: 13, fontFamily: 'var(--font-sans)', color: 'var(--ink)',
            }}
          />
          {search && (
            <button onClick={() => setSearch('')} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 2, color: 'var(--muted)', display: 'flex', alignItems: 'center' }}>
              <XIcon />
            </button>
          )}
        </div>

        {/* Topics */}
        <div style={{ padding: '12px 14px 10px' }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 7 }}>Topics</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {tags.map(({ tag }) => {
              const active = activeTags.includes(tag.toLowerCase())
              const c = tagStyle(tag)
              return (
                <button key={tag} onClick={() => toggle(tag)} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 4,
                  padding: '5px 9px', fontSize: 11, fontWeight: 700,
                  fontFamily: 'var(--font-mono)', cursor: 'pointer',
                  background: active ? c.fg : c.bg,
                  color: active ? '#fff' : c.fg,
                  border: `1.5px solid ${active ? c.fg : 'transparent'}`,
                  whiteSpace: 'nowrap', transition: 'all 100ms',
                }}>
                  #{tag.replace(/\s+/g, '')}
                </button>
              )
            })}
          </div>
        </div>

        {/* City */}
        <div style={{ padding: '0 14px 10px', borderTop: '1px solid var(--line)' }}>
          <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: '0.13em', textTransform: 'uppercase', color: 'var(--muted)', margin: '10px 0 7px' }}>City</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
            {cities.map(city => {
              const active = activeCities.includes(city)
              const cs = cityStyle(city)
              return (
                <button key={city} onClick={() => toggleCity(city)} style={{
                  display: 'inline-flex', alignItems: 'center', gap: 5,
                  padding: '5px 10px', fontSize: 12, fontWeight: 700,
                  fontFamily: 'inherit', cursor: 'pointer',
                  background: active ? cs.dot : cs.soft,
                  color: active ? '#fff' : cs.deep,
                  border: `1.5px solid ${active ? cs.dot : 'transparent'}`,
                  whiteSpace: 'nowrap', transition: 'all 100ms',
                }}>
                  <span style={{ width: 6, height: 6, borderRadius: '50%', background: active ? 'rgba(255,255,255,0.8)' : cs.dot, flexShrink: 0 }} />
                  {city}
                </button>
              )
            })}
          </div>
        </div>

        {/* Commit row — shown when any filter/search is active */}
        {hasAny && (
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', borderTop: '1px solid var(--line)' }}>
            <button onClick={clearAll} style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: 'var(--muted)', fontSize: 12, fontWeight: 700, fontFamily: 'inherit', padding: 0,
            }}>Clear all</button>
            <button onClick={onClose} style={{
              background: 'var(--ink)', color: '#fff', border: 'none', cursor: 'pointer',
              fontSize: 12, fontWeight: 800, fontFamily: 'inherit', padding: '7px 14px',
            }}>View {resultCount} result{resultCount !== 1 ? 's' : ''} →</button>
          </div>
        )}
      </div>
    </>
  )
}

// ──────────────────────── small UI atoms ────────────────────────
export const TopBar = ({ device, view, setView, onSubmit, onRecommend, onSearch, searchOpen, setSearchOpen, savedCount, filterOpen, setFilterOpen, totalActiveFilters, events, filters, setFilters, search, setSearch, resultCount }) => {
  const [infoOpen, setInfoOpen] = useState(false)
  const [popoverOpen, setPopoverOpen] = useState(false)
  const isMobile = device === "mobile"

  if (isMobile) {
    return (
      <div style={{ background: "var(--paper)", borderBottom: "1px solid var(--line)" }}>
        {/* Row 1: Logo + info + search + submit */}
        <div style={{ display: "flex", alignItems: "center", padding: "12px 14px 8px", gap: 8 }}>
          <Logomark size={28} />
          <span style={{
            fontSize: 14, fontWeight: 900, letterSpacing: "-0.01em",
            color: "var(--ink)", flex: 1, minWidth: 0,
            overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
          }}>Triangle Startup Events</span>
          <button onClick={() => setInfoOpen(v => !v)} aria-label="About this calendar" style={iconBtn(true)}>
            <InfoIcon />
          </button>
          <button onClick={() => setSearchOpen(!searchOpen)} aria-label="Search" style={iconBtn(true)}>
            <SearchIcon />
          </button>
          <button onClick={onSubmit} aria-label="Submit event" style={iconBtn(true)}>
            <PlusIcon />
          </button>
        </div>
        {/* Row 2: View toggle only (no Filters button — TODO: mobile SF-3 bottom sheet) */}
        <div style={{ display: "flex", gap: 6, padding: "0 14px 10px", alignItems: "stretch" }}>
          <div style={{ flex: 1 }}>
            <ViewToggle view={view} setView={setView} isMobile={true} fullWidth={true} />
          </div>
        </div>
        {/* Info popup */}
        {infoOpen && (
          <>
            <div onClick={() => setInfoOpen(false)} style={{ position: "absolute", inset: 0, zIndex: 49 }} />
            <div style={{
              position: "absolute", right: 14, top: 98, zIndex: 50,
              width: 260, background: "var(--paper)",
              border: "1px solid var(--line)", boxShadow: "var(--shadow-2)",
              padding: "14px", fontSize: 12, color: "var(--ink-2)", lineHeight: 1.6,
              animation: "tseFadeScale 120ms var(--ease-out)",
            }}>
              Curated by <a href="https://timscales.com" target="_blank" rel="noopener noreferrer" style={{ color: "var(--ink)", fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 2 }}>Tim Scales</a> · All events are free, in-person in the Triangle, and designed for startup founders and their teams.
            </div>
          </>
        )}
      </div>
    )
  }

  return (
    <div style={{
      display: "flex", alignItems: "center", justifyContent: "space-between",
      padding: "16px 28px",
      borderBottom: "1px solid var(--line)",
      background: "var(--paper)",
      gap: 20,
      flexWrap: "nowrap",
    }}>
      {/* Logo + title (no tagline) */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 0 }}>
        <Logomark size={36} />
        <span style={{ fontSize: 20, fontWeight: 900, letterSpacing: "-0.02em", color: "var(--ink)", whiteSpace: "nowrap" }}>
          Triangle Startup Events
        </span>
      </div>

      {/* View toggle */}
      <ViewToggle view={view} setView={setView} isMobile={false} />

      {/* Right: Search & Filter · Submit an Event · Recommend for me */}
      <div style={{ display: "flex", alignItems: "center", gap: 8, position: "relative" }}>
        <button
          onClick={() => setPopoverOpen(v => !v)}
          aria-label="Search and filter events"
          style={{
            display: "inline-flex", alignItems: "center", gap: 6,
            padding: "9px 14px", fontSize: 13, fontWeight: 800,
            fontFamily: "inherit", cursor: "pointer",
            background: popoverOpen || totalActiveFilters > 0 ? "var(--ink)" : "var(--paper)",
            color: popoverOpen || totalActiveFilters > 0 ? "#fff" : "var(--ink-2)",
            border: `1px solid ${popoverOpen || totalActiveFilters > 0 ? "var(--ink)" : "var(--line)"}`,
            transition: "all 120ms",
          }}>
          <SearchIcon />
          Search & Filter
          {totalActiveFilters > 0 && (
            <span style={{
              display: "inline-flex", alignItems: "center", justifyContent: "center",
              width: 16, height: 16, borderRadius: "50%",
              background: "var(--rdsw-blue)", color: "#fff",
              fontSize: 9, fontWeight: 900, letterSpacing: 0,
            }}>{totalActiveFilters}</span>
          )}
        </button>

        <button onClick={onSubmit} style={{
          display: "inline-flex", alignItems: "center",
          padding: "9px 14px", fontSize: 13, fontWeight: 800,
          fontFamily: "inherit", cursor: "pointer",
          background: "var(--paper)", color: "var(--ink-2)",
          border: "1px solid var(--line)",
        }}>Submit an Event</button>

        <button onClick={onRecommend} style={{
          display: "inline-flex", alignItems: "center", gap: 6,
          padding: "9px 16px", fontSize: 13, fontWeight: 800,
          fontFamily: "inherit", cursor: "pointer",
          background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)",
          border: "none",
        }}>
          <SparkleIcon />
          Recommend for me
        </button>

        {popoverOpen && (
          <SearchFilterPopover
            events={events}
            filters={filters}
            setFilters={setFilters}
            search={search}
            setSearch={setSearch}
            resultCount={resultCount}
            onClose={() => setPopoverOpen(false)}
          />
        )}
      </div>
    </div>
  )
}

export const Logomark = ({ size = 36 }) => {
  const p = Math.max(2, size * 0.16);
  const gap = Math.max(1, size * 0.06);
  const b = (size - p * 2 - gap) / 2;
  return (
    <div style={{ width: size, height: size, background: "var(--rdsw-blue)", position: "relative", boxSizing: "border-box" }}>
      <div style={{ position: "absolute", top: p, left: (size - b) / 2, width: b, height: b, background: "var(--rdsw-blue-dark)" }} />
      <div style={{ position: "absolute", top: p + b + gap, left: p, width: b, height: b, background: "var(--rdsw-blue-dark)" }} />
      <div style={{ position: "absolute", top: p + b + gap, left: p + b + gap, width: b, height: b, background: "var(--rdsw-blue-dark)" }} />
    </div>
  );
};


export const ViewToggle = ({ view, setView, isMobile, fullWidth }) => {
  const views = ["Month", "List"]
  return (
    <div style={{
      display: fullWidth ? "flex" : "inline-flex",
      border: "1px solid var(--line)",
      background: "var(--paper-2)",
      padding: 2,
      gap: 2,
      width: fullWidth ? "100%" : undefined,
      boxSizing: "border-box",
    }}>
      {views.map((v) => {
        const active = view === v
        return (
          <button key={v}
          onClick={() => setView(v)}
          style={{
            flex: fullWidth ? 1 : "none",
            padding: isMobile ? "8px 12px" : "8px 18px",
            fontSize: isMobile ? 12 : 13,
            fontWeight: 800,
            letterSpacing: "0.02em",
            background: active ? "var(--ink)" : "transparent",
            color: active ? "#fff" : "var(--ink-3)",
            border: 0,
            cursor: "pointer",
            fontFamily: "inherit",
            transition: "background 120ms"
          }}>
            {v}
          </button>)
      })}
    </div>)
}

export const iconBtn = (isMobile) => ({
  width: isMobile ? 36 : 38, height: isMobile ? 36 : 38,
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "var(--paper)", border: "1px solid var(--line)", cursor: "pointer", padding: 0,
  color: "var(--ink-3)"
})

export const ctaBtn = {
  background: "var(--accent-mint)",
  color: "var(--rdsw-blue-dark)",
  border: 0,
  padding: "10px 16px",
  fontSize: 13,
  fontWeight: 800,
  letterSpacing: "0.01em",
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "background 120ms"
}

export const ghostBtn = {
  background: "var(--paper)",
  color: "var(--ink-2)",
  border: "1px solid var(--line)",
  padding: "10px 16px",
  fontSize: 13,
  fontWeight: 700,
  letterSpacing: "0.01em",
  fontFamily: "inherit",
  cursor: "pointer",
  transition: "background 120ms"
}

export const SearchIcon = () =>
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="11" cy="11" r="7" /><path d="m21 21-4.3-4.3" />
  </svg>

export const PlusIcon = () =>
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
    <path d="M12 5v14M5 12h14" />
  </svg>

export const ChevronLeft = () =>
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="m15 18-6-6 6-6" /></svg>

export const ChevronRight = () =>
<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round"><path d="m9 18 6-6-6-6" /></svg>

export const XIcon = () =>
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>

export const PinIcon = () =>
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M20 10c0 7-8 13-8 13s-8-6-8-13a8 8 0 0 1 16 0Z" /><circle cx="12" cy="10" r="3" /></svg>

export const ExternalIcon = () =>
<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 3h6v6" /><path d="M10 14 21 3" /><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" /></svg>

export const StarIcon = ({ filled }) =>
<svg width="12" height="12" viewBox="0 0 24 24" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth="2" strokeLinejoin="round"><polygon points="12 2 15 8.5 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 9 8.5 12 2" /></svg>

export const FunnelIcon = () =>
<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3" />
  </svg>

export const InfoIcon = () =>
<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10" /><path d="M12 16v-4" /><path d="M12 8h.01" />
  </svg>

export const SparkleIcon = () =>
<svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
    <path d="M12 2l2.4 7.2L22 12l-7.6 2.8L12 22l-2.4-7.2L2 12l7.6-2.8z" />
  </svg>

export const BookmarkIcon = ({ filled }) =>
<svg width="14" height="14" viewBox="0 0 24 24"
    fill={filled ? "currentColor" : "none"}
    stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="m19 21-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v16z"/>
  </svg>
