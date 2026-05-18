// Triangle Startup Events — FilterBar, views, and event cards
// Mirrors design/reference/app-views.jsx, converted to ES modules.

import React, { useState, useMemo } from 'react'
import {
  TODAY, MONTHS, DOW_SHORT, DOW_FULL,
  parseDate, sameDay, addDays, startOfMonth, startOfWeek,
  fmtTime, fmtTimeRange, durationHours,
  eventStyle, tagStyle, topTags,
  ChevronRight, XIcon, PinIcon, StarIcon, iconBtn,
} from './shell.jsx'

// ── Filter bar ────────────────────────────────────────────────────────────────
export const FilterBar = ({ device, filters, setFilters, search, setSearch, searchOpen, setSearchOpen, resultCount, events }) => {
  const isMobile = device === "mobile"
  const tags = useMemo(() => topTags(events, 8), [events])
  const activeTags = filters.topics.map(t => t.toLowerCase())

  const toggle = (val) => {
    setFilters(f => ({
      ...f,
      topics: f.topics.map(x => x.toLowerCase()).includes(val.toLowerCase())
        ? f.topics.filter(x => x.toLowerCase() !== val.toLowerCase())
        : [...f.topics, val],
    }))
  }
  const clearAll = () => setFilters({ cities: [], types: [], audiences: [], topics: [] })

  return (
    <div style={{ borderBottom: "1px solid var(--line)", background: "var(--paper)", padding: isMobile ? "10px 12px" : "12px 28px" }}>
      {searchOpen && (
        <div style={{ marginBottom: 10, display: "flex", gap: 8 }}>
          <input
            autoFocus
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search events, hosts, locations…"
            style={{
              flex: 1, padding: "10px 14px", fontSize: 14, fontFamily: "inherit",
              border: "1px solid var(--line)", outline: "none", color: "var(--ink)",
            }}
            onFocus={e => e.target.style.borderColor = "var(--rdsw-blue)"}
            onBlur={e => e.target.style.borderColor = "var(--line)"}
          />
          <button onClick={() => { setSearch(""); setSearchOpen(false); }} style={iconBtn(isMobile)}><XIcon /></button>
        </div>
      )}
      <div style={{
        display: "flex", alignItems: "center", gap: 8,
        flexWrap: isMobile ? "nowrap" : "wrap",
        overflowX: isMobile ? "auto" : "visible",
        paddingBottom: isMobile ? 2 : 0,
      }}>
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", marginRight: 4, flexShrink: 0 }}>
          Filter
        </span>
        {tags.map(({ tag }) => {
          const active = activeTags.includes(tag)
          const c = tagStyle(tag)
          return (
            <button key={tag} onClick={() => toggle(tag)} style={{
              display: "inline-flex", alignItems: "center", gap: 4,
              padding: "6px 10px", fontSize: 12, fontWeight: 500,
              fontFamily: "var(--font-mono)", cursor: "pointer",
              background: active ? c.fg : c.bg,
              color: active ? "#fff" : c.fg,
              border: `1px solid ${active ? c.fg : "transparent"}`,
              whiteSpace: "nowrap", transition: "background 120ms", flexShrink: 0,
            }}>
              #{tag.replace(/\s+/g, "")}
            </button>
          )
        })}
        {filters.topics.length > 0 && (
          <button onClick={clearAll} style={{
            background: "transparent", border: 0, color: "var(--muted)",
            fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
            textDecoration: "underline", textUnderlineOffset: 3, padding: "6px 4px", flexShrink: 0,
          }}>Clear</button>
        )}
        {!isMobile && (
          <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
            {resultCount} event{resultCount !== 1 ? "s" : ""}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Month view ────────────────────────────────────────────────────────────────
export const MonthView = ({ device, cursor, events, onSelectEvent, onSelectDay }) => {
  const isMobile = device === "mobile"
  const first = startOfMonth(cursor)
  const gridStart = addDays(first, -first.getDay())
  const days = Array.from({ length: 42 }, (_, i) => addDays(gridStart, i))

  if (isMobile) return <MonthViewMobile cursor={cursor} events={events} days={days} onSelectEvent={onSelectEvent} onSelectDay={onSelectDay} />

  return (
    <div style={{ padding: "16px 28px 24px", display: "flex", flexDirection: "column", gap: 12, flex: 1, minHeight: 0 }}>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 6 }}>
        {DOW_SHORT.map(d => (
          <div key={d} style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", padding: "4px 8px" }}>{d}</div>
        ))}
      </div>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gridAutoRows: "minmax(0, 1fr)", gap: 6, flex: 1, minHeight: 0 }}>
        {days.map((d, i) => {
          const inMonth = d.getMonth() === cursor.getMonth()
          const isToday = sameDay(d, TODAY)
          const dayEvents = events.filter(e => sameDay(parseDate(e.date), d))
            .sort((a, b) => a.start_time.localeCompare(b.start_time))
          return (
            <div key={i} style={{
              border: `1px solid ${isToday ? "var(--rdsw-blue)" : "var(--line)"}`,
              background: isToday ? "rgba(0,157,224,0.04)" : "var(--paper)",
              padding: 8, display: "flex", flexDirection: "column", gap: 4,
              minHeight: 0, minWidth: 0, overflow: "hidden",
              opacity: inMonth ? 1 : 0.4,
              cursor: dayEvents.length ? "pointer" : "default",
            }} onClick={() => dayEvents.length && onSelectDay(d)}>
              <div style={{
                display: "flex", justifyContent: "space-between", alignItems: "center",
                fontSize: 12, fontWeight: 800, color: isToday ? "var(--rdsw-blue-dark)" : "var(--ink-2)",
              }}>
                <span style={{
                  display: "inline-flex", alignItems: "center", justifyContent: "center",
                  width: isToday ? 22 : "auto", height: isToday ? 22 : "auto",
                  background: isToday ? "var(--rdsw-blue-dark)" : "transparent",
                  color: isToday ? "#fff" : "inherit",
                  borderRadius: isToday ? "50%" : 0,
                }}>{d.getDate()}</span>
                {d.getDate() === 1 && (
                  <span style={{ fontSize: 10, color: "var(--muted)", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.1em" }}>
                    {MONTHS[d.getMonth()].slice(0, 3)}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1 }}>
                {dayEvents.slice(0, 2).map(e => (
                  <MonthEventPill key={e.id} event={e} onClick={ev => { ev.stopPropagation(); onSelectEvent(e); }} />
                ))}
                {dayEvents.length > 2 && (
                  <div style={{ fontSize: 11, color: "var(--muted)", fontWeight: 700, padding: "2px 4px" }}>
                    +{dayEvents.length - 2} more
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

const MonthEventPill = ({ event, onClick }) => {
  const style = eventStyle(event)
  return (
    <div onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "3px 5px", cursor: "pointer",
      borderLeft: `3px solid ${style.dot}`, background: style.soft,
      fontSize: 11, lineHeight: 1.2, transition: "transform 120ms",
    }}
    onMouseEnter={e => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={e => e.currentTarget.style.transform = ""}
    >
      <span style={{ fontWeight: 800, color: style.deep, whiteSpace: "nowrap" }}>{fmtTime(event.start_time)}</span>
      <span style={{ fontWeight: 600, color: "var(--ink-2)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {event.name}
      </span>
    </div>
  )
}

const MonthViewMobile = ({ cursor, events, days, onSelectEvent, onSelectDay }) => {
  const [selectedDay, setSelectedDay] = useState(TODAY)
  const dayEvents = events.filter(e => sameDay(parseDate(e.date), selectedDay))
    .sort((a, b) => a.start_time.localeCompare(b.start_time))

  const selectDay = (d) => {
    setSelectedDay(d)
    if (onSelectDay) onSelectDay(d)
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      <div style={{ padding: "10px 12px 8px", borderBottom: "1px solid var(--line)" }}>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", marginBottom: 6 }}>
          {DOW_SHORT.map(d => (
            <div key={d} style={{ fontSize: 10, fontWeight: 800, color: "var(--muted)", textAlign: "center", letterSpacing: "0.1em" }}>{d[0]}</div>
          ))}
        </div>
        <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 2 }}>
          {days.map((d, i) => {
            const inMonth = d.getMonth() === cursor.getMonth()
            const isToday = sameDay(d, TODAY)
            const isSelected = sameDay(d, selectedDay)
            const dEvents = events.filter(e => sameDay(parseDate(e.date), d))
            return (
              <button key={i} onClick={() => selectDay(d)} style={{
                aspectRatio: "1/1",
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                background: isSelected ? "var(--ink)" : "transparent",
                color: isSelected ? "#fff" : (isToday ? "var(--rdsw-blue-dark)" : (inMonth ? "var(--ink-2)" : "var(--muted)")),
                opacity: inMonth ? 1 : 0.45,
                border: isToday && !isSelected ? "1.5px solid var(--rdsw-blue)" : "1px solid transparent",
                fontSize: 13, fontWeight: isToday || isSelected ? 800 : 600,
                cursor: "pointer", padding: 0, fontFamily: "inherit", position: "relative",
              }}>
                {d.getDate()}
                {dEvents.length > 0 && (
                  <div style={{ display: "flex", gap: 2, marginTop: 2 }}>
                    {dEvents.slice(0, 3).map(e => (
                      <span key={e.id} style={{
                        width: 4, height: 4, borderRadius: "50%",
                        background: isSelected ? "#fff" : (eventStyle(e).dot || "var(--rdsw-blue)"),
                      }} />
                    ))}
                  </div>
                )}
              </button>
            )
          })}
        </div>
      </div>
      <div style={{ flex: 1, overflowY: "auto", padding: "12px" }}>
        <div style={{ fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 10 }}>
          {DOW_FULL[selectedDay.getDay()]}, {MONTHS[selectedDay.getMonth()]} {selectedDay.getDate()}
        </div>
        {dayEvents.length === 0 ? (
          <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>No events on this day.</div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {dayEvents.map(e => <EventCard key={e.id} event={e} variant="compact" onClick={() => onSelectEvent(e)} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Week view ─────────────────────────────────────────────────────────────────
export const WeekView = ({ device, cursor, events, onSelectEvent }) => {
  const isMobile = device === "mobile"
  const weekStart = startOfWeek(cursor)
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const HOUR_START = 8, HOUR_END = 20
  const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i)
  const ROW_H = isMobile ? 36 : 44
  const GUTTER = isMobile ? 38 : 54

  return (
    <div style={{ display: "flex", flexDirection: "column", flex: 1, minHeight: 0 }}>
      {/* Day header */}
      <div style={{
        display: "grid", gridTemplateColumns: `${GUTTER}px repeat(7, minmax(0, 1fr))`,
        borderBottom: "1px solid var(--line)", background: "var(--paper)",
        position: "sticky", top: 0, zIndex: 2,
      }}>
        <div />
        {days.map((d, i) => {
          const isToday = sameDay(d, TODAY)
          return (
            <div key={i} style={{ padding: isMobile ? "8px 4px" : "12px 12px", borderLeft: "1px solid var(--line)", textAlign: isMobile ? "center" : "left" }}>
              <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", color: "var(--muted)", textTransform: "uppercase" }}>
                {DOW_SHORT[d.getDay()]}
              </div>
              <div style={{
                fontSize: isMobile ? 16 : 22, fontWeight: 900, letterSpacing: "-0.02em", marginTop: 2,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: isToday ? (isMobile ? 26 : 32) : "auto", height: isToday ? (isMobile ? 26 : 32) : "auto",
                background: isToday ? "var(--rdsw-blue)" : "transparent",
                color: isToday ? "#fff" : "var(--ink)", borderRadius: isToday ? "50%" : 0,
              }}>{d.getDate()}</div>
            </div>
          )
        })}
      </div>
      {/* Grid — fits without scroll (8am–8pm) */}
      <div style={{ flex: 1, overflow: "hidden", position: "relative" }}>
        <div style={{ display: "grid", gridTemplateColumns: `${GUTTER}px repeat(7, minmax(0, 1fr))`, position: "relative" }}>
          <div>
            {hours.map(h => (
              <div key={h} style={{ height: ROW_H, fontSize: 10, color: "var(--muted)", padding: "2px 6px", textAlign: "right", fontWeight: 700 }}>
                {fmtTime(`${String(h).padStart(2,"0")}:00`)}
              </div>
            ))}
          </div>
          {days.map((d, di) => {
            const dEvents = events.filter(e => sameDay(parseDate(e.date), d) && e.start_time && e.start_time !== "00:00")
            return (
              <div key={di} style={{
                borderLeft: "1px solid var(--line)", position: "relative",
                height: hours.length * ROW_H,
                background: sameDay(d, TODAY) ? "rgba(0,157,224,0.03)" : "transparent",
              }}>
                {hours.map(h => (
                  <div key={h} style={{ height: ROW_H, borderBottom: "1px dashed var(--line-2)" }} />
                ))}
                {dEvents.map(e => {
                  const [sh, sm] = e.start_time.split(":").map(Number)
                  const top = ((sh - HOUR_START) + sm / 60) * ROW_H
                  const durH = e.end_time && e.end_time !== "00:00" ? durationHours(e.start_time, e.end_time) : 1
                  const height = Math.max(durH * ROW_H - 2, 26)
                  return (
                    <WeekBlock key={e.id} event={e} top={top} height={height} isMobile={isMobile} onClick={() => onSelectEvent(e)} />
                  )
                })}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

const WeekBlock = ({ event, top, height, isMobile, onClick }) => {
  const style = eventStyle(event)
  return (
    <div onClick={onClick} style={{
      position: "absolute", top, left: 2, right: 2, height,
      background: style.soft, borderLeft: `3px solid ${style.dot}`,
      padding: isMobile ? "3px 4px" : "5px 6px",
      cursor: "pointer", overflow: "hidden",
      display: "flex", flexDirection: "column", gap: 1, transition: "transform 120ms",
    }}
    onMouseEnter={e => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={e => e.currentTarget.style.transform = ""}
    >
      <div style={{ fontSize: isMobile ? 9 : 10, fontWeight: 800, color: style.deep, letterSpacing: "0.02em" }}>
        {fmtTime(event.start_time)}
      </div>
      <div style={{ fontSize: isMobile ? 10 : 11, fontWeight: 700, color: "var(--ink)", lineHeight: 1.2, overflow: "hidden", textOverflow: "ellipsis" }}>
        {event.name}
      </div>
    </div>
  )
}

// ── List view ─────────────────────────────────────────────────────────────────
export const ListView = ({ device, events, onSelectEvent, cardVariant }) => {
  const isMobile = device === "mobile"
  const groups = {}
  events.forEach(e => { (groups[e.date] = groups[e.date] || []).push(e) })
  const sortedDates = Object.keys(groups).sort()

  return (
    <div style={{ flex: 1, overflowY: "auto", padding: isMobile ? "12px" : "20px 28px 40px" }}>
      {sortedDates.length === 0 && (
        <div style={{ padding: 40, textAlign: "center", color: "var(--muted)" }}>
          <div style={{ fontSize: 14, fontWeight: 700 }}>No events match these filters.</div>
          <div style={{ fontSize: 13, marginTop: 6 }}>Try clearing a filter or check back soon.</div>
        </div>
      )}
      {sortedDates.map(date => {
        const d = parseDate(date)
        const isToday = sameDay(d, TODAY)
        return (
          <div key={date} style={{ marginBottom: 24 }}>
            <div style={{
              display: "flex", alignItems: "baseline", gap: 10,
              padding: "8px 0", marginBottom: 10,
              borderBottom: "1px solid var(--line)",
              position: "sticky", top: 0, background: "var(--paper)", zIndex: 1,
            }}>
              <div style={{ fontSize: isMobile ? 18 : 22, fontWeight: 900, color: "var(--ink)", letterSpacing: "-0.015em" }}>
                {MONTHS[d.getMonth()].slice(0, 3)} {d.getDate()}
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
                {DOW_FULL[d.getDay()]}
                {isToday && <span style={{ marginLeft: 8, color: "var(--rdsw-blue)" }}>· Today</span>}
              </div>
              <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
                {groups[date].length} event{groups[date].length !== 1 ? "s" : ""}
              </div>
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "1fr" : (cardVariant === "compact" ? "1fr" : "repeat(auto-fill, minmax(360px, 1fr))"),
              gap: 12,
            }}>
              {groups[date].map(e => (
                <EventCard key={e.id} event={e} variant={cardVariant} onClick={() => onSelectEvent(e)} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// ── Event cards (3 variants) ──────────────────────────────────────────────────
export const EventCard = ({ event, variant = "standard", onClick }) => {
  const style = eventStyle(event)
  if (variant === "compact") return <EventCardCompact event={event} style={style} onClick={onClick} />
  if (variant === "visual")  return <EventCardVisual  event={event} style={style} onClick={onClick} />
  return <EventCardStandard event={event} style={style} onClick={onClick} />
}

const EventCardCompact = ({ event, style, onClick }) => (
  <div onClick={onClick} style={{
    display: "flex", alignItems: "center", gap: 14, padding: "12px 14px",
    background: "var(--paper)", border: "1px solid var(--line)",
    borderLeft: `3px solid ${style.dot}`,
    cursor: "pointer", transition: "transform 120ms, box-shadow 120ms",
  }}
  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)"; }}
  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
    <div style={{ fontSize: 13, fontWeight: 800, color: style.deep, width: 80, flexShrink: 0 }}>
      {fmtTime(event.start_time)}
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 2 }}>
        <span style={{ fontSize: 15, fontWeight: 800, color: "var(--ink)", letterSpacing: "-0.005em" }}>{event.name}</span>
        {event.editors_pick && <PickBadge />}
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
        {event.event_type} · {event.city} · {event.host}
      </div>
    </div>
    <ChevronRight />
  </div>
)

const EventCardStandard = ({ event, style, onClick }) => (
  <div onClick={onClick} style={{
    background: "var(--paper)", border: "1px solid var(--line)",
    padding: 18, cursor: "pointer", display: "flex", flexDirection: "column", gap: 10,
    transition: "transform 120ms, box-shadow 120ms",
  }}
  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)"; }}
  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <TypeChip style={style} type={event.event_type} />
      {event.editors_pick && <PickBadge />}
    </div>
    <h3 style={{ fontSize: 19, fontWeight: 900, color: "var(--ink)", letterSpacing: "-0.012em", lineHeight: 1.15, margin: 0 }}>
      {event.name}
    </h3>
    <div style={{ fontSize: 13, color: "var(--ink-3)", fontWeight: 600, display: "flex", flexDirection: "column", gap: 4 }}>
      <div>{fmtTimeRange(event.start_time, event.end_time)}</div>
      <div style={{ display: "flex", alignItems: "center", gap: 5, color: "var(--muted)" }}>
        <PinIcon /> {event.city} · {event.host}
      </div>
    </div>
    {event.description && (
      <p style={{ fontSize: 13, color: "var(--ink-3)", margin: 0, lineHeight: 1.45,
        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {event.description}
      </p>
    )}
  </div>
)

const EventCardVisual = ({ event, style, onClick }) => {
  const d = parseDate(event.date)
  return (
    <div onClick={onClick} style={{
      display: "flex", background: "var(--paper)", border: "1px solid var(--line)",
      cursor: "pointer", overflow: "hidden", transition: "transform 120ms, box-shadow 120ms",
    }}
    onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)"; }}
    onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = ""; }}>
      <div style={{
        width: 92, flexShrink: 0, background: style.soft, color: style.deep,
        padding: 14, display: "flex", flexDirection: "column", justifyContent: "space-between",
        borderRight: `3px solid ${style.dot}`,
      }}>
        <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" }}>
          {event.event_type}
        </div>
        <div>
          <div style={{ fontSize: 26, fontWeight: 900, letterSpacing: "-0.02em", lineHeight: 1 }}>{d.getDate()}</div>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
            {MONTHS[d.getMonth()].slice(0, 3)} · {fmtTime(event.start_time)}
          </div>
        </div>
      </div>
      <div style={{ padding: 16, flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <h3 style={{ fontSize: 17, fontWeight: 900, color: "var(--ink)", letterSpacing: "-0.012em", lineHeight: 1.15, margin: 0 }}>
            {event.name}
          </h3>
          {event.editors_pick && <PickBadge />}
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600, display: "flex", alignItems: "center", gap: 4 }}>
          <PinIcon /> {event.location.split(",").slice(0, 2).join(",")}
        </div>
        {(event.audience || []).length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
            {event.audience.slice(0, 3).map(a => (
              <span key={a} style={{
                fontSize: 10, fontWeight: 800, color: "var(--ink-3)",
                background: "var(--paper-2)", padding: "2px 7px", letterSpacing: "0.02em",
                border: "1px solid var(--line)",
              }}>{a}</span>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

export const TypeChip = ({ style, type }) => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 5,
    fontSize: 11, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase",
    color: style.deep, background: style.soft, padding: "3px 8px",
  }}>
    <span style={{ width: 6, height: 6, background: style.dot, borderRadius: "50%" }} />
    {type}
  </span>
)

export const PickBadge = () => (
  <span style={{
    display: "inline-flex", alignItems: "center", gap: 3,
    fontSize: 10, fontWeight: 800, letterSpacing: "0.08em", textTransform: "uppercase",
    color: "var(--accent-amber-deep)", background: "var(--accent-amber-soft)", padding: "2px 6px",
  }}>
    <StarIcon filled /> Editor's pick
  </span>
)
