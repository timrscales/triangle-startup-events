import React, { useState, useMemo, useEffect, useCallback, useRef, useLayoutEffect } from 'react'
import {
  TODAY, TODAY_START, MONTHS, DOW_SHORT, DOW_FULL, ALL_CITIES, ALL_TYPES, ALL_AUDIENCES,
  parseDate, sameDay, addDays, startOfWeek, isPast,
  fmtTime, fmtTimeRange, durationHours,
  applyFilters, eventStyle, tagStyle,
  iconBtn, ctaBtn,
  TopBar, XIcon, ExternalIcon, ChevronLeft, ChevronRight, PinIcon, hashIndex,
} from './shell.jsx'
import {
  FilterBar, MonthView, WeekView, ListView,
  PickBadge, PaidBadge,
} from './views.jsx'
import { useHash } from './useHash.js'
import { RecommendModal } from './recommend.jsx'

// ──────────────────────── Data layer ────────────────────────
function stableId(e) {
  const str = `${e.date}|${e.start_time}|${e.name}`
  let h = 0
  for (let i = 0; i < str.length; i++) h = (h * 31 + str.charCodeAt(i)) >>> 0
  return h.toString(36)
}

function parseTimeStr(t) {
  if (!t) return ''
  if (/^\d{2}:\d{2}$/.test(t)) return t
  const m = t.match(/^(\d{1,2})(?::(\d{2}))?\s*(am|pm)$/i)
  if (m) {
    let h = parseInt(m[1])
    const min = m[2] ? parseInt(m[2]) : 0
    if (m[3].toLowerCase() === 'pm' && h !== 12) h += 12
    if (m[3].toLowerCase() === 'am' && h === 12) h = 0
    return `${String(h).padStart(2,'0')}:${String(min).padStart(2,'0')}`
  }
  return t
}

function cityFromLocation(loc) {
  if (!loc) return ''
  if (loc.includes('Research Triangle Park') || loc.includes('Triangle Park')) return 'RTP'
  for (const city of ['Raleigh', 'Durham', 'Chapel Hill', 'Cary']) {
    if (loc.includes(city)) return city
  }
  return ''
}

function normalizeEvent(e) {
  return {
    ...e,
    id: e.id || stableId(e),
    host: e.host || e.organizer || '',
    event_type: e.event_type || '',
    audience: e.audience || [],
    topic_tags: e.topic_tags || [],
    description: e.description || '',
    short_description: e.short_description || '',
    location: e.location || '',
    city: e.city || cityFromLocation(e.location),
    friendly_date: e.friendly_date || '',
    start_time: parseTimeStr(e.start_time),
    end_time: parseTimeStr(e.end_time),
    editors_pick: e.editors_pick || false,
    is_free: e.is_free !== false,
  }
}

const EVENTS = (window.__EVENTS__ || []).map(normalizeEvent)
const ORG_PROFILES = window.ORG_PROFILES || {}

function toISO(d) {
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}

const SUBMIT_URL = "https://airtable.com/apprt7MFT8PcVhFY4/pagkomS1oueDY2OLn/form"

// ──────────────────────── Anchored-popover helpers ────────────────────────

// Element rect in the app root's pre-transform local space.
function localRect(el, root) {
  if (!el || !root) return null
  const er = el.getBoundingClientRect()
  const rr = root.getBoundingClientRect()
  const sx = (rr.width  / root.offsetWidth)  || 1
  const sy = (rr.height / root.offsetHeight) || 1
  return {
    top:    (er.top    - rr.top)  / sy,
    left:   (er.left   - rr.left) / sx,
    bottom: (er.bottom - rr.top)  / sy,
    right:  (er.right  - rr.left) / sx,
    width:  er.width  / sx,
    height: er.height / sy,
  }
}

// Prefers below + left-aligned; flips on either axis when it would clip.
function computeAnchorPos(anchor, w, h, vw, vh, gap = 8, pad = 12) {
  let top = anchor.bottom + gap
  if (top + h > vh - pad) {
    const above = anchor.top - gap - h
    top = above >= pad ? above : Math.max(pad, vh - h - pad)
  }
  let left = anchor.left
  if (left + w > vw - pad) {
    const ra = anchor.right - w
    left = ra >= pad ? ra : Math.max(pad, vw - w - pad)
  }
  return { top: Math.max(pad, top), left: Math.max(pad, left) }
}

// Two-pass render: off-screen (opacity 0) first so useLayoutEffect can measure,
// then snaps to computed position. Falls back to a centered position when
// anchorRect is null (e.g., event opened via URL).
const AnchoredPopover = ({ anchorRect, root, width, onClose, children, ariaLabel }) => {
  const panelRef = useRef(null)
  const [pos, setPos] = useState(null)

  useLayoutEffect(() => {
    if (!panelRef.current || !root) return
    const effective = anchorRect || {
      top: root.offsetHeight * 0.28,
      bottom: root.offsetHeight * 0.28 + 1,
      left: root.offsetWidth / 2 - width / 2,
      right: root.offsetWidth / 2 + width / 2,
      width, height: 0,
    }
    const p = computeAnchorPos(
      effective,
      panelRef.current.offsetWidth,
      panelRef.current.offsetHeight,
      root.offsetWidth,
      root.offsetHeight,
    )
    setPos(p)
  }, [anchorRect, root])

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  return (
    <>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, zIndex: 20 }} />
      <div
        ref={panelRef}
        role="dialog"
        aria-label={ariaLabel}
        onClick={(e) => e.stopPropagation()}
        style={{
          position: "absolute",
          top: pos?.top ?? -9999, left: pos?.left ?? -9999,
          width,
          maxHeight: root ? root.offsetHeight - 24 : "90vh",
          zIndex: 30,
          opacity: pos ? 1 : 0,
          background: "var(--paper)",
          boxShadow: "var(--shadow-3)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
          animation: pos ? "tseFadeScale 160ms var(--ease-out)" : "none",
        }}>
        {children}
      </div>
    </>
  )
}

const HostIcon = () =>
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M3 21h18M5 21V7l7-4 7 4v14M9 9h.01M15 9h.01M9 13h.01M15 13h.01M9 17h.01M15 17h.01"/>
  </svg>

// ──────────────────────── Host helpers ────────────────────────
function getHosts(event) {
  return event.hosts && event.hosts.length ? event.hosts : [event.host]
}

const HostList = ({ event, onSelectOrg }) => {
  const hosts = getHosts(event)
  const linkStyle = {
    fontWeight: 800, color: "var(--ink)",
    cursor: onSelectOrg ? "pointer" : "default",
    borderBottom: onSelectOrg ? "1.5px solid var(--line)" : "none",
    paddingBottom: 1,
    background: "none", border: "none", font: "inherit",
    display: "inline", padding: 0,
  }
  const names = hosts.map((h) => (
    <b key={h} onClick={(e) => { e.stopPropagation(); onSelectOrg && onSelectOrg(h) }} style={linkStyle}>{h}</b>
  ))
  let joined
  if (names.length === 1) {
    joined = names[0]
  } else if (names.length === 2) {
    joined = <>{names[0]} <span style={{ color: "var(--muted)" }}>and</span> {names[1]}</>
  } else {
    joined = <>{names[0]}<span style={{ color: "var(--muted)" }}>, </span>{names[1]}<span style={{ color: "var(--muted)" }}>, and </span>{names[2]}</>
  }
  return (
    <div style={{ fontSize: 14, lineHeight: 1.5 }}>
      <span style={{ color: "var(--muted)" }}>Hosted by </span>{joined}
    </div>
  )
}

// ──────────────────────── Detail panel ────────────────────────
const DetailPanel = ({ event, anchorRect, root, onClose, onSelectOrg, fromOrg, onBackToOrg, device }) => {
  const isMobile = device === "mobile"
  const style = eventStyle(event)

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  const content =
    <div style={{ display: "flex", flexDirection: "column", background: "var(--paper)", maxHeight: "100%", overflow: "hidden" }}>
      <div style={{
        background: style.soft, padding: isMobile ? "16px 16px 18px" : "22px 24px 24px",
        borderBottom: `3px solid ${style.dot}`, position: "relative"
      }}>
        <button onClick={onClose} aria-label="Close" style={{
          position: "absolute", top: 12, right: 12,
          width: 32, height: 32, background: "rgba(255,255,255,0.85)", border: 0, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink)"
        }}>
          <XIcon />
        </button>
        {event.editors_pick && (
          <div style={{ marginBottom: 10 }}><PickBadge /></div>
        )}
        {fromOrg && onBackToOrg && (
          <button onClick={onBackToOrg} style={{
            display: "inline-flex", alignItems: "center", gap: 4,
            background: "transparent", border: 0, cursor: "pointer",
            fontSize: 12, fontWeight: 700, color: style.deep, fontFamily: "inherit",
            padding: "0 0 10px", marginLeft: -2,
          }}>
            <ChevronLeft /> {fromOrg}
          </button>
        )}
        <h2 style={{
          fontSize: isMobile ? 22 : 28, fontWeight: 900, color: "var(--ink)",
          letterSpacing: "-0.018em", lineHeight: 1.08, margin: 0, paddingRight: 32
        }}>{event.name}</h2>
        <div style={{ fontSize: 14, fontWeight: 700, color: style.deep, marginTop: 10 }}>
          {event.friendly_date}
        </div>
      </div>

      <div style={{ overflowY: "auto", padding: isMobile ? "18px 16px" : "24px", display: "flex", flexDirection: "column", gap: 16, minHeight: 0 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ display: "inline-flex", alignItems: "center", height: 20, color: "var(--muted)", flexShrink: 0 }}><HostIcon /></span>
          <div style={{ flex: 1, minWidth: 0 }}>
            <HostList event={event} onSelectOrg={onSelectOrg} />
          </div>
          {event.is_free === false && <PaidBadge />}
        </div>

        <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
          <span style={{ display: "inline-flex", alignItems: "center", height: 20, color: "var(--muted)", flexShrink: 0 }}><PinIcon /></span>
          <div>
            <div style={{ fontWeight: 700, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.4 }}>{event.location.split(",")[0]}</div>
            <div style={{ color: "var(--muted)", fontSize: 13, marginTop: 2, lineHeight: 1.4 }}>{event.location.split(",").slice(1).join(",").trim()}</div>
          </div>
        </div>

        {(event.short_description || event.description) && (
          <p style={{ fontSize: 14, color: "var(--ink-2)", lineHeight: 1.55, margin: "4px 0 0" }}>
            {event.short_description || event.description}
          </p>
        )}

        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, paddingTop: 14, borderTop: "1px solid var(--line)", marginTop: 4 }}>
          {event.topic_tags.map((t) => {
            const c = tagStyle(t)
            return (
              <span key={t} style={{
                fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500,
                color: c.fg, background: c.bg, padding: "3px 8px"
              }}>#{t.replace(/\s+/g, "")}</span>
            )
          })}
        </div>
      </div>

      <div style={{ padding: isMobile ? 14 : 18, borderTop: "1px solid var(--line)", background: "var(--paper)" }}>
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-2)", marginBottom: 10 }}>
          {event.friendly_date}
        </div>
        {event.is_free === false ? (
          <a href={event.source_url} target="_blank" rel="noopener noreferrer" style={{
            display: "flex", textAlign: "center", textDecoration: "none",
            background: "#EF9F27", color: "#412402",
            padding: "13px 18px", fontWeight: 800, fontSize: 14, letterSpacing: "0.01em",
            alignItems: "center", justifyContent: "center", gap: 8,
            transition: "background 120ms"
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = "#D88718"}
          onMouseLeave={(e) => e.currentTarget.style.background = "#EF9F27"}
          onClick={(e) => e.stopPropagation()}>
            View Tickets & Pricing →
          </a>
        ) : (
          <a href={event.source_url} target="_blank" rel="noopener noreferrer" style={{
            display: "flex", textAlign: "center", textDecoration: "none",
            background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)",
            padding: "13px 18px", fontWeight: 800, fontSize: 14, letterSpacing: "0.01em",
            alignItems: "center", justifyContent: "center", gap: 8,
            transition: "background 120ms"
          }}
          onMouseEnter={(e) => e.currentTarget.style.background = "var(--accent-mint-deep)"}
          onMouseLeave={(e) => e.currentTarget.style.background = "var(--accent-mint)"}
          onClick={(e) => e.stopPropagation()}>
            Learn More & RSVP <ExternalIcon />
          </a>
        )}
      </div>
    </div>

  if (isMobile) {
    return (
      <>
        <div onClick={onClose} style={{
          position: "absolute", inset: 0, background: "rgba(10,10,10,0.35)", zIndex: 25,
          animation: "tseScrim 180ms var(--ease-out)"
        }} />
        <div style={{
          position: "absolute", left: 0, right: 0, bottom: 0, maxHeight: "92vh", zIndex: 30,
          background: "var(--paper)", boxShadow: "var(--shadow-3)",
          display: "flex", flexDirection: "column",
          animation: "tseSlideUp 220ms var(--ease-out)"
        }}>{content}</div>
      </>
    )
  }

  return (
    <AnchoredPopover anchorRect={anchorRect} root={root} width={420} onClose={onClose} ariaLabel="Event details">
      {content}
    </AnchoredPopover>
  )
}

// ──────────────────────── Day popover ────────────────────────
const DayPopoverRow = ({ event, onClick }) => {
  const style = eventStyle(event)
  const past = isPast(event.date)
  return (
    <div onClick={onClick} style={{
      display: "flex", flexDirection: "column", gap: 2,
      padding: "9px 11px", cursor: "pointer",
      borderLeft: `3px solid ${style.dot}`, background: style.soft,
      lineHeight: 1.3, transition: "transform 120ms",
      opacity: past ? 0.5 : 1,
    }}
    onMouseEnter={(e) => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={(e) => e.currentTarget.style.transform = ""}
    >
      <div style={{ fontSize: 11, fontWeight: 800, color: style.deep, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
        {fmtTimeRange(event.start_time, event.end_time)}
      </div>
      <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink)", display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {event.name}
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", marginTop: 1 }}>
        {event.host}
      </div>
    </div>
  )
}

const DayPopover = ({ date, anchorRect, root, events, onSelectEvent, onClose, device }) => {
  const isMobile = device === "mobile"
  const content = (
    <div style={{ display: "flex", flexDirection: "column", background: "var(--paper)", maxHeight: "100%", overflow: "hidden" }}>
      <div style={{ padding: "14px 16px 12px", borderBottom: "1px solid var(--line)", position: "relative" }}>
        <button onClick={onClose} aria-label="Close" style={{
          position: "absolute", top: 10, right: 10,
          width: 28, height: 28, background: "var(--paper)", border: "1px solid var(--line)",
          cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink-2)"
        }}><XIcon /></button>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 2 }}>
          {DOW_FULL[date.getDay()]}
        </div>
        <div style={{ fontSize: 20, fontWeight: 900, color: "var(--ink)", letterSpacing: "-0.015em" }}>
          {MONTHS[date.getMonth()]} {date.getDate()}
        </div>
      </div>
      <div style={{ overflowY: "auto", padding: 10, display: "flex", flexDirection: "column", gap: 6, minHeight: 0 }}>
        {events.map((e) => (
          <DayPopoverRow key={e.id} event={e} onClick={(ev) => { ev.stopPropagation(); onSelectEvent(e, ev.currentTarget) }} />
        ))}
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <>
        <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(10,10,10,0.35)", zIndex: 25, animation: "tseScrim 180ms var(--ease-out)" }} />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, maxHeight: "75vh", zIndex: 30, background: "var(--paper)", boxShadow: "var(--shadow-3)", display: "flex", flexDirection: "column", animation: "tseSlideUp 220ms var(--ease-out)" }}>{content}</div>
      </>
    )
  }
  return (
    <AnchoredPopover anchorRect={anchorRect} root={root} width={300} onClose={onClose} ariaLabel="Events this day">
      {content}
    </AnchoredPopover>
  )
}

// ──────────────────────── Org panel ────────────────────────
const LinkIcon = () =>
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M15 3h6v6"/><path d="M10 14 21 3"/><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
  </svg>

const OrgLogo = ({ host, size = 56, logoSrc }) => {
  const initials = host.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]).join("").toUpperCase()
  const colors = [
    { bg: "#003D69", fg: "#fff" },
    { bg: "#FFB648", fg: "#5C3800" },
    { bg: "#B577FC", fg: "#fff" },
    { bg: "#1BE0B0", fg: "#004D47" },
    { bg: "#FC7777", fg: "#fff" },
  ]
  const col = colors[hashIndex(host, colors.length)]

  if (logoSrc) {
    return (
      <div style={{
        height: size, flexShrink: 0,
        background: "#fff",
        border: "1px solid var(--line)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: 6, boxSizing: "border-box",
      }}>
        <img
          src={logoSrc}
          alt={host}
          style={{ height: "100%", width: "auto", maxWidth: size * 3, objectFit: "contain", display: "block" }}
        />
      </div>
    )
  }

  return (
    <div style={{
      width: size, height: size, flexShrink: 0,
      background: col.bg, color: col.fg,
      display: "flex", alignItems: "center", justifyContent: "center",
      fontSize: size * 0.35, fontWeight: 900, letterSpacing: "-0.02em",
    }}>{initials}</div>
  )
}

const OrgEventRow = ({ event, isSource, onClick }) => {
  const style = eventStyle(event)
  return (
    <div onClick={onClick} style={{
      display: "flex", flexDirection: "column", gap: 2,
      padding: "10px 12px", cursor: "pointer",
      borderLeft: `3px solid ${style.dot}`, background: style.soft,
      lineHeight: 1.3, transition: "transform 120ms",
      outline: isSource ? `2px solid ${style.dot}` : "none",
      outlineOffset: -2,
    }}
    onMouseEnter={e => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={e => e.currentTarget.style.transform = ""}
    >
      <div style={{ fontSize: 11, fontWeight: 800, color: style.deep }}>{event.friendly_date}</div>
      <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink)", lineHeight: 1.25, display: "flex", alignItems: "flex-start", gap: 8 }}>
        <span style={{ flex: 1, minWidth: 0 }}>{event.name}</span>
        {event.is_free === false && <span style={{ color: "#854F0B", flexShrink: 0 }}>$</span>}
      </div>
    </div>
  )
}

const OrgPanel = ({ host, allEvents, sourceEventId, onClose, onSelectEvent, device }) => {
  const isMobile = device === "mobile"
  const profile = ORG_PROFILES[host] || {}
  const today = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate())
  const orgEvents = allEvents
    .filter(e => getHosts(e).includes(host) && parseDate(e.date) >= today)
    .sort((a, b) => a.date.localeCompare(b.date))

  const content = (
    <div style={{ display: "flex", flexDirection: "column", background: "var(--paper)", height: "100%", overflow: "hidden" }}>
      <div style={{ padding: isMobile ? "20px 16px" : "28px 28px 24px", borderBottom: "1px solid var(--line)", position: "relative" }}>
        <button onClick={onClose} aria-label="Close" style={{
          position: "absolute", top: 14, right: 14,
          width: 32, height: 32, background: "rgba(255,255,255,0.85)", border: 0, cursor: "pointer",
          display: "flex", alignItems: "center", justifyContent: "center", color: "var(--ink)",
        }}><XIcon /></button>
        <div style={{ display: "flex", alignItems: "flex-start", gap: 16, paddingRight: 36 }}>
          <OrgLogo host={host} size={isMobile ? 48 : 64} logoSrc={profile.logo} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>Organizer</div>
            <h2 style={{ fontSize: isMobile ? 20 : 26, fontWeight: 900, color: "var(--ink)", letterSpacing: "-0.015em", lineHeight: 1.1, margin: 0 }}>{host}</h2>
          </div>
        </div>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        <div style={{ padding: isMobile ? "20px 16px" : "24px 28px", display: "flex", flexDirection: "column", gap: 20 }}>
          {profile.description && (
            <p style={{ margin: 0, fontSize: 14, color: "var(--ink-2)", lineHeight: 1.6 }}>{profile.description}</p>
          )}
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {profile.website && (
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ color: "var(--muted)", flexShrink: 0, display: "flex", alignItems: "center" }}><LinkIcon /></span>
                <a href={profile.website} target="_blank" rel="noopener noreferrer" style={{
                  fontSize: 13, fontWeight: 600, color: "var(--rdsw-blue-dark)",
                  textDecoration: "underline", textUnderlineOffset: 2,
                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                }}>{profile.website.replace(/^https?:\/\//, "")}</a>
              </div>
            )}
            {profile.address && (
              <div style={{ display: "flex", alignItems: "flex-start", gap: 8 }}>
                <span style={{ color: "var(--muted)", flexShrink: 0, paddingTop: 1 }}><PinIcon /></span>
                <span style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.4 }}>{profile.address}</span>
              </div>
            )}
          </div>
          <div style={{ borderTop: "1px solid var(--line)", paddingTop: 20 }}>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 12 }}>
              Upcoming events
            </div>
            {orgEvents.length === 0 ? (
              <div style={{ fontSize: 13, color: "var(--muted)" }}>No upcoming events from this organizer.</div>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
                {orgEvents.map(e => (
                  <OrgEventRow key={e.id} event={e} isSource={e.id === sourceEventId} onClick={() => onSelectEvent(e)} />
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )

  if (isMobile) {
    return (
      <>
        <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(10,10,10,0.35)", zIndex: 25, animation: "tseScrim 180ms var(--ease-out)" }} />
        <div style={{ position: "absolute", left: 0, right: 0, bottom: 0, maxHeight: "92vh", zIndex: 35, background: "var(--paper)", boxShadow: "var(--shadow-3)", display: "flex", flexDirection: "column", animation: "tseSlideUp 220ms var(--ease-out)" }}>{content}</div>
      </>
    )
  }
  return (
    <>
      <div onClick={onClose} style={{ position: "absolute", inset: 0, background: "rgba(10,10,10,0.28)", zIndex: 20, animation: "tseScrim 180ms var(--ease-out)" }} />
      <div style={{
        position: "absolute", top: 0, right: 0, bottom: 0, width: 480, zIndex: 30,
        boxShadow: "var(--shadow-3)",
        animation: "tseSlideIn 220ms var(--ease-out)",
      }}>{content}</div>
    </>
  )
}

// ──────────────────────── Submit modal (unused) ────────────────────────
// Submit button opens Airtable hosted form. Kept in case we want to bring back the in-app form.
// eslint-disable-next-line no-unused-vars
const SubmitModal = ({ onClose, device }) => {
  const isMobile = device === "mobile"
  const [form, setForm] = useState({
    name: "", date: "", start_time: "", end_time: "", location: "",
    city: "Raleigh", event_type: "Talk", audience: [], source_url: "", description: ""
  })
  const [submitted, setSubmitted] = useState(false)
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }))
  const toggleAud = (a) => setForm((f) => ({ ...f, audience: f.audience.includes(a) ? f.audience.filter((x) => x !== a) : [...f.audience, a] }))

  useEffect(() => {
    const onKey = (e) => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", onKey)
    return () => document.removeEventListener("keydown", onKey)
  }, [onClose])

  const submit = (e) => { e.preventDefault(); setSubmitted(true) }

  return (
    <div style={{
      position: "absolute", inset: 0, zIndex: 40,
      background: "rgba(10,10,10,0.45)",
      display: "flex", alignItems: "flex-end", justifyContent: "center",
      padding: isMobile ? 0 : 40
    }} onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} style={{
        background: "var(--paper)",
        width: isMobile ? "100%" : 560, maxWidth: "100%",
        maxHeight: isMobile ? "92%" : "92%",
        display: "flex", flexDirection: "column",
        animation: "tseSlideUp 240ms var(--ease-out)"
      }}>
        <div style={{
          padding: isMobile ? "16px" : "22px 28px", borderBottom: "1px solid var(--line)",
          display: "flex", alignItems: "center", justifyContent: "space-between"
        }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", color: "var(--muted)", textTransform: "uppercase" }}></div>
            <h2 style={{ fontSize: isMobile ? 20 : 24, fontWeight: 900, letterSpacing: "-0.015em", margin: "4px 0 0" }}>Submit an Event</h2>
          </div>
          <button onClick={onClose} aria-label="Close" style={iconBtn(isMobile)}><XIcon /></button>
        </div>

        {submitted ?
          <div style={{ padding: 40, textAlign: "center" }}>
            <div style={{
              width: 56, height: 56, background: "var(--accent-mint-soft)", color: "var(--accent-mint-deep)",
              display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 16
            }}>
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
            </div>
            <h3 style={{ fontSize: 22, fontWeight: 900, letterSpacing: "-0.012em", margin: "0 0 8px" }}>Thanks — we'll take a look.</h3>
            <p style={{ fontSize: 14, color: "var(--ink-3)", maxWidth: 360, margin: "0 auto" }}>
              Submissions are reviewed by Tim before going live. You'll get an email if it's approved.
            </p>
            <button onClick={onClose} style={{ ...ctaBtn, marginTop: 20 }}>Close</button>
          </div> :

          <form onSubmit={submit} style={{ padding: isMobile ? 16 : "22px 28px", overflowY: "auto", display: "flex", flexDirection: "column", gap: 14 }}>
            <Field label="Event name" required>
              <input required value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. AI Tinkerers Monthly" style={inp} />
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr 1fr", gap: 10 }}>
              <Field label="Date" required><input required type="date" value={form.date} onChange={(e) => set("date", e.target.value)} style={inp} /></Field>
              <Field label="Start" required><input required type="time" value={form.start_time} onChange={(e) => set("start_time", e.target.value)} style={inp} /></Field>
              <Field label="End time"><input type="time" value={form.end_time} onChange={(e) => set("end_time", e.target.value)} style={inp} /></Field>
            </div>
            <Field label="Location" required>
              <input required value={form.location} onChange={(e) => set("location", e.target.value)} placeholder="Venue name, address" style={inp} />
            </Field>
            <div style={{ display: "grid", gridTemplateColumns: isMobile ? "1fr" : "1fr 1fr", gap: 10 }}>
              <Field label="City"><Select value={form.city} onChange={(v) => set("city", v)} options={ALL_CITIES} /></Field>
              <Field label="Event type"><Select value={form.event_type} onChange={(v) => set("event_type", v)} options={ALL_TYPES} /></Field>
            </div>
            <Field label="Who is it for?">
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                {ALL_AUDIENCES.map((a) => {
                  const on = form.audience.includes(a)
                  return (
                    <button type="button" key={a} onClick={() => toggleAud(a)} style={{
                      padding: "7px 12px", fontSize: 12, fontWeight: 700, fontFamily: "inherit", cursor: "pointer",
                      background: on ? "var(--rdsw-blue-dark)" : "var(--paper)",
                      color: on ? "#fff" : "var(--ink-2)",
                      border: `1px solid ${on ? "var(--rdsw-blue-dark)" : "var(--line)"}`
                    }}>{a}</button>
                  )
                })}
              </div>
            </Field>
            <Field label="RSVP / source URL" required>
              <input required type="url" value={form.source_url} onChange={(e) => set("source_url", e.target.value)} placeholder="https://luma.com/…" style={inp} />
            </Field>
            <Field label="Description">
              <textarea value={form.description} onChange={(e) => set("description", e.target.value)} rows={3} placeholder="One or two sentences. What will people get out of it?" style={{ ...inp, resize: "vertical", fontFamily: "inherit" }} />
            </Field>
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, padding: "8px 0" }}>
              <strong style={{ color: "var(--ink-2)" }}>The Rules:</strong> Events must be free, in-person somewhere in the Triangle, and designed for startup founders and their teams. Submissions are reviewed before going live.
            </div>
            <div style={{ display: "flex", gap: 10, paddingTop: 4 }}>
              <button type="submit" style={{ ...ctaBtn, flex: 1, padding: "14px 18px", fontSize: 14 }}>Submit for Review</button>
              <button type="button" onClick={onClose} style={{ padding: "14px 18px", fontFamily: "inherit", fontSize: 13, fontWeight: 800, background: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink-2)", cursor: "pointer" }}>Cancel</button>
            </div>
          </form>
        }
      </div>
    </div>
  )
}

const Field = ({ label, required, children }) =>
  <label style={{ display: "flex", flexDirection: "column", gap: 6 }}>
    <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase", color: "var(--ink-3)" }}>
      {label}{required && <span style={{ color: "var(--accent-coral-deep)", marginLeft: 4 }}>*</span>}
    </span>
    {children}
  </label>

const inp = {
  padding: "10px 12px", fontSize: 14, fontFamily: "inherit",
  border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink)",
  outline: "none", width: "100%", boxSizing: "border-box"
}

const Select = ({ value, onChange, options }) =>
  <select value={value} onChange={(e) => onChange(e.target.value)} style={{ ...inp, appearance: "none", backgroundImage: 'url("data:image/svg+xml;utf8,<svg xmlns=%27http://www.w3.org/2000/svg%27 width=%2710%27 height=%2710%27 viewBox=%270 0 24 24%27 fill=%27none%27 stroke=%27%236B7785%27 stroke-width=%273%27><path d=%27m6 9 6 6 6-6%27/></svg>")', backgroundRepeat: "no-repeat", backgroundPosition: "right 12px center", paddingRight: 30 }}>
    {options.map((o) => <option key={o} value={o}>{o}</option>)}
  </select>

// ──────────────────────── Period navigator ────────────────────────
const PeriodNav = ({ view, cursor, setCursor, device, resultCount }) => {
  const isMobile = device === "mobile"
  const label = view === "Week" ?
    (() => {
      const start = startOfWeek(cursor)
      const end = addDays(start, 6)
      if (start.getMonth() === end.getMonth()) {
        return `${MONTHS[start.getMonth()]} ${start.getDate()}–${end.getDate()}, ${start.getFullYear()}`
      }
      return `${MONTHS[start.getMonth()].slice(0, 3)} ${start.getDate()} – ${MONTHS[end.getMonth()].slice(0, 3)} ${end.getDate()}`
    })() :
    view === "Month" ? `${MONTHS[cursor.getMonth()]} ${cursor.getFullYear()}` :
    ""
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
      padding: isMobile ? "10px 12px 4px" : "16px 28px 4px",
      gap: 12
    }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <h2 style={{
          fontSize: isMobile ? 20 : 28, fontWeight: 900, letterSpacing: "-0.018em",
          color: "var(--ink)", margin: 0, lineHeight: 1.1
        }}>{label}</h2>
        {view !== "List" &&
          <div style={{ display: "inline-flex", gap: 2, marginLeft: 6 }}>
            <button onClick={() => move(-1)} style={navBtn}><ChevronLeft /></button>
            <button onClick={() => move(1)} style={navBtn}><ChevronRight /></button>
            <button onClick={() => setCursor(new Date(TODAY))} style={{
              padding: "0 12px", height: 32, fontSize: 12, fontWeight: 800, letterSpacing: "0.02em",
              fontFamily: "inherit", border: "1px solid var(--line)", background: "var(--paper)", color: "var(--ink-2)",
              cursor: "pointer", marginLeft: 4
            }}>Today</button>
          </div>
        }
      </div>
      {isMobile &&
        <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700 }}>
          {resultCount} {resultCount === 1 ? "event" : "events"}
        </div>
      }
    </div>
  )
}

const navBtn = {
  width: 32, height: 32, padding: 0, fontFamily: "inherit",
  display: "inline-flex", alignItems: "center", justifyContent: "center",
  background: "var(--paper)", border: "1px solid var(--line)", color: "var(--ink-2)", cursor: "pointer"
}

// ──────────────────────── Footer ────────────────────────
const Footer = ({ device }) => {
  if (device === "mobile") return null
  const openSubscribe = () => {
    const w = 560, h = 620
    const left = Math.round(window.screenX + (window.outerWidth - w) / 2)
    const top  = Math.round(window.screenY + (window.outerHeight - h) / 2)
    window.open(
      "https://airtable.com/apprt7MFT8PcVhFY4/pagz7K3Bc4Se3QGPC/form",
      "subscribe",
      `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`
    )
  }
  const linkStyle = { color: "var(--ink-2)", fontWeight: 700, textDecoration: "underline", textUnderlineOffset: 2 }
  return (
    <div style={{
      padding: "20px 28px",
      borderTop: "1px solid var(--line)", background: "var(--paper-2)",
      fontSize: 12, color: "var(--muted)",
      display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16,
    }}>
      <div>
        Curated by{" "}
        <a href="https://www.timscales.com" target="_blank" rel="noopener noreferrer" style={linkStyle}>Tim Scales</a>
        {" · "}
        Additions, changes, or questions?{" "}
        <a href="mailto:tim@timscales.com" style={linkStyle}>Send an email</a>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <span>
          <strong style={{ color: "var(--ink-2)", fontWeight: 700 }}>Never miss an event.</strong>{" "}
          Get a free weekly update every Monday.
        </span>
        <button
          onClick={openSubscribe}
          style={{
            background: "#009DE0", color: "#fff", border: 0,
            padding: "10px 16px", fontSize: 13, fontWeight: 800,
            letterSpacing: "0.01em", fontFamily: "inherit",
            cursor: "pointer", transition: "background 120ms",
          }}
          onMouseEnter={e => e.currentTarget.style.background = "#0086C0"}
          onMouseLeave={e => e.currentTarget.style.background = "#009DE0"}
        >
          Subscribe for Free
        </button>
      </div>
    </div>
  )
}

// ──────────────────────── Main app ────────────────────────
export default function TriangleEventsApp({ device = "desktop", cardVariant = "standard" }) {
  const rootRef = useRef(null)
  const isMobile = device === 'mobile'
  const [hash, setHash] = useHash()
  const [searchOpen, setSearchOpen] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)
  const [recommendOpen, setRecommendOpen] = useState(false)
  const [anchorRect, setAnchorRect] = useState(null)
  const [fromOrg, setFromOrg] = useState(null)       // host name when event was opened from OrgPanel
  const [dayPopover, setDayPopover] = useState(null) // { date, anchorRect }
  const [orgPanel, setOrgPanel] = useState(null)     // { host, sourceEventId }

  const view = (hash.view === 'week' || hash.view === 'Week') ? 'Month' : (hash.view || 'Month')
  const cursor = useMemo(() => {
    if (!hash.date) return new Date(TODAY)
    try { return parseDate(hash.date) } catch { return new Date(TODAY) }
  }, [hash.date])

  const filters = useMemo(() => ({
    cities: hash.cities || [],
    types: [], audiences: [],
    topics: hash.topics || [],
    free:   hash.free || 'all',
  }), [hash.cities, hash.topics, hash.free])

  const search = hash.q || ''

  const selected = useMemo(() =>
    hash.event ? EVENTS.find(e => String(e.id) === String(hash.event)) || null : null
  , [hash.event])

  const setView = useCallback((v) => setHash(h => ({ ...h, view: v })), [setHash])
  const setCursor = useCallback((d) => setHash(h => ({ ...h, date: toISO(d) })), [setHash])
  const setFilters = useCallback((updater) => {
    setHash(h => {
      const current = { cities: h.cities || [], types: [], audiences: [], topics: h.topics || [], free: h.free || 'all' }
      const next = typeof updater === 'function' ? updater(current) : { ...current, ...updater }
      return { ...h, cities: next.cities, topics: next.topics, free: next.free }
    })
  }, [setHash])

  const totalActiveFilters = useMemo(() =>
    filters.cities.length + filters.types.length + filters.audiences.length + filters.topics.length
      + (filters.free && filters.free !== 'all' ? 1 : 0),
    [filters]
  )
  const setSearch = useCallback((q) => setHash(h => ({ ...h, q })), [setHash])

  const selectEvent = useCallback((event, anchorEl, sourceOrg) => {
    setDayPopover(null)
    setOrgPanel(null)
    setFromOrg(sourceOrg || null)
    const rect = (anchorEl && rootRef.current && !isMobile)
      ? localRect(anchorEl, rootRef.current) : null
    setAnchorRect(rect)
    setHash(h => ({ ...h, event: event ? event.id : null }))
  }, [setHash, isMobile])

  const closeEvent = useCallback(() => {
    setAnchorRect(null)
    setFromOrg(null)
    setHash(h => ({ ...h, event: null }))
  }, [setHash])

  const selectDay = useCallback((date, anchorEl) => {
    const rect = (anchorEl && rootRef.current && !isMobile)
      ? localRect(anchorEl, rootRef.current) : null
    setDayPopover({ date, anchorRect: rect })
  }, [isMobile])

  const filteredAll = useMemo(() => applyFilters(EVENTS, filters, search), [filters, search])
  const filteredFuture = useMemo(() => filteredAll.filter((e) => parseDate(e.date) >= TODAY_START), [filteredAll])
  const filteredForView = useMemo(() => {
    if (view !== "List") return filteredAll
    return filteredFuture
  }, [filteredAll, filteredFuture, view])

  const dayPopoverEvents = useMemo(() => {
    if (!dayPopover) return []
    return filteredAll
      .filter(e => sameDay(parseDate(e.date), dayPopover.date))
      .sort((a, b) => a.start_time.localeCompare(b.start_time))
  }, [dayPopover, filteredAll])

  return (
    <div ref={rootRef} style={{
      width: "100%", height: "100%",
      display: "flex", flexDirection: "column",
      background: "var(--paper)", color: "var(--ink)",
      fontFamily: "var(--font-sans)",
      position: "relative", overflow: "hidden"
    }}>
      <TopBar
        device={device}
        view={view} setView={setView}
        onSubmit={() => {
          const w = 560, h = 700
          const left = Math.round(window.screenX + (window.outerWidth - w) / 2)
          const top  = Math.round(window.screenY + (window.outerHeight - h) / 2)
          window.open(SUBMIT_URL, "submit_event", `width=${w},height=${h},left=${left},top=${top},resizable=yes,scrollbars=yes`)
        }}
        onRecommend={() => setRecommendOpen(true)}
        searchOpen={searchOpen} setSearchOpen={setSearchOpen}
        filterOpen={filterOpen} setFilterOpen={setFilterOpen}
        totalActiveFilters={totalActiveFilters}
        events={EVENTS}
        filters={filters} setFilters={setFilters}
        search={search} setSearch={setSearch}
        resultCount={filteredFuture.length} />

      <FilterBar
        device={device}
        events={EVENTS}
        filters={filters} setFilters={setFilters}
        search={search} setSearch={setSearch}
        searchOpen={searchOpen} setSearchOpen={setSearchOpen}
        resultCount={filteredForView.length}
        view={view}
        filterOpen={filterOpen} setFilterOpen={setFilterOpen} />

      <PeriodNav view={view} cursor={cursor} setCursor={setCursor} device={device} resultCount={filteredForView.length} />

      <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0, overflow: "hidden" }}>
        {view === "Month" && <MonthView device={device} cursor={cursor} events={filteredForView} onSelectEvent={selectEvent} onSelectDay={selectDay} />}
        {/* WeekView removed from UI; component kept for reference */}
        {/* {view === "Week" && <WeekView device={device} cursor={cursor} events={filteredForView} onSelectEvent={selectEvent} />} */}
        {view === "List" && <ListView device={device} events={filteredForView} onSelectEvent={selectEvent} cardVariant={cardVariant} />}
      </div>

      <Footer device={device} />

      {selected && (
        <DetailPanel
          event={selected}
          anchorRect={anchorRect}
          root={rootRef.current}
          onClose={closeEvent}
          onSelectOrg={(host) => {
            setOrgPanel({ host, sourceEventId: selected.id, fromEvent: selected })
            closeEvent()
          }}
          fromOrg={fromOrg}
          onBackToOrg={fromOrg ? () => {
            setOrgPanel({ host: fromOrg, sourceEventId: selected.id })
            closeEvent()
          } : null}
          device={device}
        />
      )}
      {orgPanel && (
        <OrgPanel
          host={orgPanel.host}
          sourceEventId={orgPanel.sourceEventId}
          allEvents={EVENTS}
          onClose={() => {
            if (orgPanel.fromEvent) {
              setFromOrg(null)
              setAnchorRect(null)
              setHash(h => ({ ...h, event: orgPanel.fromEvent.id }))
            }
            setOrgPanel(null)
          }}
          onSelectEvent={(e) => selectEvent(e, null, orgPanel.host)}
          device={device}
        />
      )}
      {dayPopover && (
        <DayPopover date={dayPopover.date} anchorRect={dayPopover.anchorRect} root={rootRef.current} events={dayPopoverEvents} onSelectEvent={selectEvent} onClose={() => setDayPopover(null)} device={device} />
      )}
      <RecommendModal
        open={recommendOpen}
        onClose={() => setRecommendOpen(false)}
        events={EVENTS}
      />
    </div>
  )
}
