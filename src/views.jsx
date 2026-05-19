import React, { useState, useMemo, useRef, useEffect } from 'react'
import {
  TODAY, MONTHS, DOW_SHORT, DOW_FULL,
  parseDate, sameDay, addDays, startOfWeek, startOfMonth,
  fmtTime, fmtTimeRange, durationHours,
  eventStyle, tagStyle, topTags, uniqueCities,
  iconBtn, XIcon, PinIcon, ChevronRight, StarIcon, FunnelIcon,
} from './shell.jsx'

// ──────────────────────── Filter helpers ────────────────────────
const FilterSection = ({ title, children }) => (
  <div style={{ marginBottom: 20 }}>
    <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", marginBottom: 8 }}>
      {title}
    </div>
    {children}
  </div>
)

const FilterChip = ({ label, active, onToggle }) => (
  <button onClick={onToggle} style={{
    display: "inline-flex", alignItems: "center", gap: 5,
    padding: "7px 12px", fontSize: 12, fontWeight: 700,
    fontFamily: "inherit", cursor: "pointer",
    background: active ? "var(--ink)" : "var(--paper-2)",
    color: active ? "#fff" : "var(--ink-2)",
    border: `1px solid ${active ? "var(--ink)" : "var(--line)"}`,
    whiteSpace: "nowrap", transition: "all 100ms",
  }}>
    {active && <CheckMarkIcon />}
    {label}
  </button>
)

const CheckMarkIcon = () => (
  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
    <path d="M20 6 9 17l-5-5" />
  </svg>
)

// ──────────────────────── Filter bar ────────────────────────
export const FilterBar = ({ device, filters, setFilters, search, setSearch, searchOpen, setSearchOpen, resultCount, view, events, filterOpen, setFilterOpen }) => {
  const isMobile = device === "mobile"
  const tags = useMemo(() => topTags(events, 12), [events])
  const cities = useMemo(() => uniqueCities(events), [events])
  const activeTags = filters.topics.map(t => t.toLowerCase())
  const totalActive = filters.cities.length + filters.types.length + filters.audiences.length + filters.topics.length

  const toggle = (val) => {
    setFilters(f => ({
      ...f,
      topics: f.topics.map(x => x.toLowerCase()).includes(val.toLowerCase())
        ? f.topics.filter(x => x.toLowerCase() !== val.toLowerCase())
        : [...f.topics, val],
    }))
  }
  const clearAll   = () => setFilters({ cities: [], types: [], audiences: [], topics: [] })
  const toggleCity = (v) => setFilters(f => ({ ...f, cities: f.cities.includes(v) ? f.cities.filter(x => x !== v) : [...f.cities, v] }))

  const searchEl = searchOpen ? (
    <div style={{ display: "flex", gap: 8 }}>
      <input
        autoFocus type="text" value={search} onChange={e => setSearch(e.target.value)}
        placeholder="Search events, hosts, locations…"
        style={{ flex: 1, padding: "10px 14px", fontSize: 14, fontFamily: "inherit", border: "1px solid var(--line)", outline: "none", color: "var(--ink)" }}
        onFocus={e => e.target.style.borderColor = "var(--rdsw-blue)"}
        onBlur={e => e.target.style.borderColor = "var(--line)"}
      />
      <button onClick={() => { setSearch(""); setSearchOpen(false) }} style={iconBtn(isMobile)}><XIcon /></button>
    </div>
  ) : null

  if (isMobile) {
    return (
      <>
        {searchOpen && (
          <div style={{ borderBottom: "1px solid var(--line)", background: "var(--paper)", padding: "8px 12px" }}>
            {searchEl}
          </div>
        )}
        {filterOpen && (
          <>
            <div onClick={() => setFilterOpen(false)} style={{
              position: "absolute", inset: 0, background: "rgba(10,10,10,0.45)", zIndex: 40,
              animation: "tseScrim 180ms var(--ease-out)",
            }} />
            <div style={{
              position: "absolute", left: 0, right: 0, bottom: 0, zIndex: 41,
              background: "var(--paper)", maxHeight: "82vh",
              display: "flex", flexDirection: "column",
              boxShadow: "var(--shadow-3)",
              animation: "tseSlideUp 220ms var(--ease-out)",
            }}>
              <div style={{
                padding: "14px 16px 12px", borderBottom: "1px solid var(--line)",
                display: "flex", alignItems: "center", justifyContent: "space-between",
                flexShrink: 0,
              }}>
                <span style={{ fontSize: 17, fontWeight: 900, letterSpacing: "-0.01em", color: "var(--ink)" }}>Filters</span>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  {totalActive > 0 && (
                    <button onClick={clearAll} style={{
                      background: "transparent", border: 0, color: "var(--muted)",
                      fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
                      textDecoration: "underline", textUnderlineOffset: 3, padding: 0,
                    }}>Clear all</button>
                  )}
                  <button onClick={() => setFilterOpen(false)} style={iconBtn(true)}><XIcon /></button>
                </div>
              </div>
              <div style={{ flex: 1, overflowY: "auto", padding: "16px 16px 4px" }}>
                <FilterSection title="Topics">
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {tags.map(({ tag }) => {
                      const active = activeTags.includes(tag)
                      const c = tagStyle(tag)
                      return (
                        <button key={tag} onClick={() => toggle(tag)} style={{
                          display: "inline-flex", alignItems: "center", gap: 4,
                          padding: "6px 10px", fontSize: 11, fontWeight: 700,
                          fontFamily: "var(--font-mono)", cursor: "pointer",
                          background: active ? c.fg : "var(--paper-2)",
                          color: active ? "#fff" : "var(--ink-2)",
                          border: `1.5px solid ${active ? c.fg : "var(--line)"}`,
                          whiteSpace: "nowrap", transition: "all 100ms",
                        }}>
                          {active && <CheckMarkIcon />}
                          #{tag.replace(/\s+/g, "")}
                        </button>
                      )
                    })}
                  </div>
                </FilterSection>
                {cities.length > 0 && (
                  <FilterSection title="City">
                    <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                      {cities.map(c => <FilterChip key={c} label={c} active={filters.cities.includes(c)} onToggle={() => toggleCity(c)} />)}
                    </div>
                  </FilterSection>
                )}
              </div>
              <div style={{ padding: "12px 16px", borderTop: "1px solid var(--line)", flexShrink: 0 }}>
                <button onClick={() => setFilterOpen(false)} style={{
                  width: "100%", padding: "14px", fontFamily: "inherit",
                  fontSize: 14, fontWeight: 800, letterSpacing: "0.01em",
                  background: "var(--ink)", color: "#fff",
                  border: 0, cursor: "pointer",
                }}>
                  {totalActive > 0 ? `Show ${resultCount} result${resultCount !== 1 ? "s" : ""}` : "Done"}
                </button>
              </div>
            </div>
          </>
        )}
      </>
    )
  }

  // Desktop: horizontal chip row
  return (
    <div style={{ borderBottom: "1px solid var(--line)", background: "var(--paper)", padding: "12px 28px" }}>
      {searchEl && <div style={{ marginBottom: 10 }}>{searchEl}</div>}
      <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
        <span style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase", color: "var(--muted)", flexShrink: 0 }}>Filter by</span>
        {cities.map(c => {
          const active = filters.cities.includes(c)
          return (
            <button key={c} onClick={() => toggleCity(c)} style={{
              display: "inline-flex", alignItems: "center",
              padding: "5px 10px", fontSize: 11, fontWeight: 700,
              fontFamily: "inherit", cursor: "pointer",
              background: active ? "var(--ink)" : "var(--paper-2)",
              color: active ? "#fff" : "var(--ink-2)",
              border: `1px solid ${active ? "var(--ink)" : "var(--line)"}`,
              whiteSpace: "nowrap", transition: "all 100ms", flexShrink: 0,
            }}>{c}</button>
          )
        })}
        {cities.length > 0 && <span style={{ width: 1, height: 14, background: "var(--line-2)", flexShrink: 0, alignSelf: "center" }} />}
        {tags.map(({ tag }) => {
          const active = activeTags.includes(tag)
          const c = tagStyle(tag)
          return (
            <button key={tag} onClick={() => toggle(tag)} style={{
              display: "inline-flex", alignItems: "center", gap: 5,
              padding: "5px 10px", fontSize: 11, fontWeight: 700,
              fontFamily: "var(--font-mono)", cursor: "pointer",
              background: active ? c.fg : "var(--paper-2)",
              color: active ? "#fff" : "var(--ink-2)",
              border: `1.5px solid ${active ? c.fg : "var(--line)"}`,
              whiteSpace: "nowrap", transition: "all 100ms", flexShrink: 0,
            }}>
              #{tag.replace(/\s+/g, "")}
            </button>
          )
        })}
        {(filters.topics.length > 0 || filters.cities.length > 0) && (
          <button onClick={clearAll} style={{
            background: "transparent", border: 0, color: "var(--muted)",
            fontSize: 12, fontWeight: 700, cursor: "pointer", fontFamily: "inherit",
            textDecoration: "underline", textUnderlineOffset: 3, padding: "6px 4px", flexShrink: 0,
          }}>Clear</button>
        )}
      </div>
    </div>
  )
}

// ──────────────────────── Month grid ────────────────────────
export const MonthView = ({ device, cursor, events, onSelectEvent, onSelectDay }) => {
  const isMobile = device === "mobile"
  const first = startOfMonth(cursor)
  const gridStart = addDays(first, -first.getDay())
  const lastOfMonth = new Date(cursor.getFullYear(), cursor.getMonth() + 1, 0)
  const weeksNeeded = Math.ceil((lastOfMonth - gridStart) / (7 * 24 * 60 * 60 * 1000) + 1/7)
  const days = Array.from({ length: weeksNeeded * 7 }, (_, i) => addDays(gridStart, i))

  if (isMobile) return <MonthViewMobile cursor={cursor} events={events} days={days} onSelectEvent={onSelectEvent} onSelectDay={onSelectDay} />

  return (
    <div style={{ padding: "16px 28px 24px", display: "flex", flexDirection: "column", gap: 12, flex: 1, minHeight: 0 }}>
      {/* Weekday header */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(7, minmax(0, 1fr))", gap: 6 }}>
        {DOW_SHORT.map((d) => (
          <div key={d} style={{
            fontSize: 11, fontWeight: 800, letterSpacing: "0.14em", textTransform: "uppercase",
            color: "var(--muted)", padding: "4px 8px",
          }}>{d}</div>
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
              padding: 8,
              display: "flex", flexDirection: "column", gap: 4,
              minHeight: 0, minWidth: 0, overflow: "hidden",
              opacity: inMonth ? 1 : 0.4,
              cursor: dayEvents.length ? "pointer" : "default",
            }}
            onClick={(e) => dayEvents.length && onSelectDay(d, e.currentTarget)}
            >
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
                    {MONTHS[d.getMonth()].slice(0,3)}
                  </span>
                )}
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 4, flex: 1, minHeight: 0, overflow: "hidden" }}>
                {dayEvents.length === 0 ? null
                  : dayEvents.length === 1
                    ? <MonthEventPill event={dayEvents[0]} onClick={ev => { ev.stopPropagation(); onSelectEvent(dayEvents[0], ev.currentTarget) }} />
                    : <>
                        <MonthEventThinBar event={dayEvents[0]} onClick={ev => { ev.stopPropagation(); onSelectEvent(dayEvents[0], ev.currentTarget) }} />
                        {dayEvents.length === 2
                          ? <MonthEventThinBar event={dayEvents[1]} onClick={ev => { ev.stopPropagation(); onSelectEvent(dayEvents[1], ev.currentTarget) }} />
                          : <div
                              onClick={(ev) => { ev.stopPropagation(); onSelectDay(d, ev.currentTarget) }}
                              style={{ fontSize: 11, color: "var(--rdsw-blue)", fontWeight: 800, padding: "1px 4px", cursor: "pointer", letterSpacing: "0.01em" }}>
                              +{dayEvents.length - 1} more
                            </div>
                        }
                      </>
                }
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
      display: "flex", flexDirection: "column", gap: 2,
      padding: "5px 7px",
      cursor: "pointer",
      borderLeft: `3px solid ${style.dot}`,
      background: style.soft,
      lineHeight: 1.25,
      transition: "transform 120ms",
      minWidth: 0, overflow: "hidden",
      flexShrink: 1, minHeight: 0,
    }}
    onMouseEnter={e => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={e => e.currentTarget.style.transform = ""}
    >
      <div style={{
        fontSize: 10, fontWeight: 800, color: style.deep,
        letterSpacing: "0.02em", whiteSpace: "nowrap",
        overflow: "hidden", textOverflow: "ellipsis",
      }}>
        {fmtTimeRange(event.start_time, event.end_time)}
      </div>
      <div style={{
        fontSize: 12, fontWeight: 700, color: "var(--ink)",
        display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical",
        overflow: "hidden", wordBreak: "break-word",
      }}>
        {event.name}
      </div>
    </div>
  )
}

const MonthEventThinBar = ({ event, onClick }) => {
  const style = eventStyle(event)
  return (
    <div onClick={onClick} style={{
      display: "flex", alignItems: "center", gap: 6,
      padding: "3px 6px",
      borderLeft: `3px solid ${style.dot}`,
      background: style.soft,
      cursor: "pointer",
      minWidth: 0, overflow: "hidden",
      lineHeight: 1.2,
      transition: "transform 120ms",
    }}
    onMouseEnter={e => e.currentTarget.style.transform = "translateX(2px)"}
    onMouseLeave={e => e.currentTarget.style.transform = ""}
    >
      <span style={{ fontSize: 10, fontWeight: 800, color: style.deep, whiteSpace: "nowrap", flexShrink: 0 }}>
        {fmtTime(event.start_time)}
      </span>
      <span style={{
        fontSize: 11, fontWeight: 700, color: "var(--ink)",
        whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis", minWidth: 0,
      }}>{event.name}</span>
    </div>
  )
}

// ──────────────────────── Month grid — mobile ────────────────────────
const MonthViewMobile = ({ cursor, events, days, onSelectEvent }) => {
  const [selectedDay, setSelectedDay] = useState(TODAY)
  const dayEvents = events.filter(e => sameDay(parseDate(e.date), selectedDay))
    .sort((a,b) => a.start_time.localeCompare(b.start_time))
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
              <button key={i} onClick={() => setSelectedDay(d)} style={{
                height: 36,
                display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                background: isSelected ? "var(--ink)" : "transparent",
                color: isSelected ? "#fff" : (isToday ? "var(--rdsw-blue-dark)" : (inMonth ? "var(--ink-2)" : "var(--muted)")),
                opacity: inMonth ? 1 : 0.45,
                border: isToday && !isSelected ? "1.5px solid var(--rdsw-blue)" : "1px solid transparent",
                fontSize: 13, fontWeight: isToday || isSelected ? 800 : 600,
                cursor: "pointer", padding: 0, fontFamily: "inherit",
                position: "relative",
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
          <div style={{ padding: 24, textAlign: "center", color: "var(--muted)", fontSize: 13 }}>
            No events on this day.
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {dayEvents.map(e => <EventCard key={e.id} event={e} variant="compact" onClick={(el) => onSelectEvent(e, el)} />)}
          </div>
        )}
      </div>
    </div>
  )
}

// ──────────────────────── Week-event overlap layout ────────────────────────
function toMin(t) { const [h, m] = t.split(":").map(Number); return h * 60 + m }

function layoutWeekEvents(events) {
  const items = [...events]
    .sort((a, b) => toMin(a.start_time) - toMin(b.start_time))
    .map(e => ({ event: e, start: toMin(e.start_time), end: toMin(e.end_time), col: 0, totalCols: 1 }))

  for (let i = 0; i < items.length; i++) {
    const used = new Set()
    for (let j = 0; j < i; j++) {
      if (items[j].start < items[i].end && items[j].end > items[i].start) used.add(items[j].col)
    }
    let col = 0
    while (used.has(col)) col++
    items[i].col = col
  }

  for (let i = 0; i < items.length; i++) {
    const maxCol = items.reduce((mx, r) =>
      (r.start < items[i].end && r.end > items[i].start) ? Math.max(mx, r.col) : mx, 0)
    items[i].totalCols = maxCol + 1
  }

  return items
}

// ──────────────────────── Week view ────────────────────────
export const WeekView = ({ device, cursor, events, onSelectEvent }) => {
  const isMobile = device === "mobile"
  const weekStart = startOfWeek(cursor)
  const days = Array.from({ length: 7 }, (_, i) => addDays(weekStart, i))
  const HOUR_START = 8, HOUR_END = 20
  const hours = Array.from({ length: HOUR_END - HOUR_START }, (_, i) => HOUR_START + i)
  const ROW_H = isMobile ? 36 : 44
  const GUTTER = isMobile ? 38 : 54
  const scrollRef = useRef(null)
  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = ROW_H
  }, [])

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
            <div key={i} style={{
              padding: isMobile ? "8px 4px" : "12px 12px",
              borderLeft: "1px solid var(--line)",
              textAlign: isMobile ? "center" : "left",
            }}>
              <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.14em", color: "var(--muted)", textTransform: "uppercase" }}>
                {DOW_SHORT[d.getDay()]}
              </div>
              <div style={{
                fontSize: isMobile ? 16 : 22, fontWeight: 900,
                letterSpacing: "-0.02em", marginTop: 2,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                width: isToday ? (isMobile ? 26 : 32) : "auto", height: isToday ? (isMobile ? 26 : 32) : "auto",
                background: isToday ? "var(--rdsw-blue-dark)" : "transparent",
                color: isToday ? "#fff" : "inherit", borderRadius: isToday ? "50%" : 0,
              }}>{d.getDate()}</div>
            </div>
          )
        })}
      </div>
      {/* Scrollable hour grid */}
      <div ref={scrollRef} style={{ flex: 1, overflowY: "auto", position: "relative" }}>
        <div style={{ display: "grid", gridTemplateColumns: `${GUTTER}px repeat(7, minmax(0, 1fr))`, position: "relative" }}>
          {/* Hour gutter */}
          <div>
            {hours.map(h => (
              <div key={h} style={{ height: ROW_H, fontSize: 10, color: "var(--muted)", padding: "2px 6px", textAlign: "right", fontWeight: 700 }}>
                {fmtTime(`${String(h).padStart(2,"0")}:00`)}
              </div>
            ))}
          </div>
          {/* Day columns */}
          {days.map((d, di) => {
            const dEvents = events.filter(e => sameDay(parseDate(e.date), d))
            return (
              <div key={di} style={{
                borderLeft: "1px solid var(--line)",
                position: "relative", height: hours.length * ROW_H,
                background: sameDay(d, TODAY) ? "rgba(0,157,224,0.03)" : "transparent",
              }}>
                {hours.map(h => (
                  <div key={h} style={{ height: ROW_H, borderBottom: "1px dashed var(--line-2)" }} />
                ))}
                {layoutWeekEvents(dEvents).map(({ event: e, col, totalCols }) => {
                  const [sh, sm] = e.start_time.split(":").map(Number)
                  const top = ((sh - HOUR_START) + sm/60) * ROW_H
                  const height = Math.max(durationHours(e.start_time, e.end_time) * ROW_H - 2, 26)
                  return (
                    <WeekBlock key={e.id} event={e} top={top} height={height} col={col} totalCols={totalCols} isMobile={isMobile} onClick={(el) => onSelectEvent(e, el)} />
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

const WeekBlock = ({ event, top, height, col, totalCols, isMobile, onClick }) => {
  const style = eventStyle(event)
  const L = `calc(${col / totalCols * 100}% + 2px)`
  const R = `calc(${(totalCols - col - 1) / totalCols * 100}% + 2px)`
  return (
    <div onClick={(e) => onClick(e.currentTarget)} style={{
      position: "absolute", top, left: L, right: R, height,
      background: style.soft, borderLeft: `3px solid ${style.dot}`,
      padding: isMobile ? "3px 4px" : "5px 6px",
      cursor: "pointer", overflow: "hidden",
      display: "flex", flexDirection: "column", gap: 1,
      transition: "transform 120ms",
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

// ──────────────────────── List view ────────────────────────
export const ListView = ({ device, events, onSelectEvent, cardVariant }) => {
  const isMobile = device === "mobile"
  const [showPast, setShowPast] = useState(false)
  const today = new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate())
  const pastEvents = events.filter(e => parseDate(e.date) < today)
  const futureEvents = events.filter(e => parseDate(e.date) >= today)
  const visibleEvents = showPast ? events : futureEvents
  const groups = {}
  visibleEvents.forEach(e => { (groups[e.date] = groups[e.date] || []).push(e) })
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
        const isPast = d < new Date(TODAY.getFullYear(), TODAY.getMonth(), TODAY.getDate())
        return (
          <div key={date} style={{ marginBottom: 24 }}>
            <div style={{
              display: "flex", alignItems: "baseline", gap: 10,
              padding: "8px 0", marginBottom: 10,
              borderBottom: "1px solid var(--line)",
              position: "sticky", top: 0, background: "var(--paper)", zIndex: 1,
            }}>
              <div style={{
                fontSize: isMobile ? 18 : 22, fontWeight: 900, color: "var(--ink)",
                letterSpacing: "-0.015em",
              }}>
                {MONTHS[d.getMonth()].slice(0,3)} {d.getDate()}
              </div>
              <div style={{ fontSize: 12, fontWeight: 700, color: "var(--muted)", textTransform: "uppercase", letterSpacing: "0.12em" }}>
                {DOW_FULL[d.getDay()]}
                {sameDay(d, TODAY) && <span style={{ marginLeft: 8, color: "var(--rdsw-blue)" }}>· Today</span>}
              </div>
              <div style={{ marginLeft: "auto", fontSize: 12, color: "var(--muted)" }}>
                {groups[date].length} event{groups[date].length !== 1 ? "s" : ""}
              </div>
            </div>
            <div style={{
              display: "grid",
              gridTemplateColumns: isMobile ? "1fr" : (cardVariant === "compact" ? "1fr" : "repeat(auto-fill, minmax(360px, 1fr))"),
              gap: 12,
              opacity: isPast ? 0.6 : 1,
            }}>
              {groups[date].map(e => (
                <EventCard key={e.id} event={e} variant={cardVariant} onClick={(el) => onSelectEvent(e, el)} />
              ))}
            </div>
          </div>
        )
      })}
      {pastEvents.length > 0 && (
        <div style={{ textAlign: "center", padding: "8px 0 24px" }}>
          <button onClick={() => setShowPast(p => !p)} style={{
            fontFamily: "inherit", fontSize: 12, fontWeight: 800,
            color: "var(--ink-3)", background: "transparent",
            border: "1px solid var(--line)", padding: "8px 16px",
            cursor: "pointer", letterSpacing: "0.04em",
          }}>
            {showPast ? "Hide past events" : `Show ${pastEvents.length} past event${pastEvents.length !== 1 ? "s" : ""}`}
          </button>
        </div>
      )}
    </div>
  )
}

// ──────────────────────── Event card (3 variants) ────────────────────────
export const EventCard = ({ event, variant = "standard", onClick }) => {
  const style = eventStyle(event)
  if (variant === "compact") return <EventCardCompact event={event} style={style} onClick={onClick} />
  if (variant === "visual") return <EventCardVisual event={event} style={style} onClick={onClick} />
  return <EventCardStandard event={event} style={style} onClick={onClick} />
}

const EventCardCompact = ({ event, style, onClick }) => (
  <div onClick={(e) => onClick(e.currentTarget)} style={{
    display: "flex", alignItems: "center", gap: 14, padding: "12px 14px",
    background: "var(--paper)", border: "1px solid var(--line)",
    borderLeft: `3px solid ${style.dot}`,
    cursor: "pointer", transition: "transform 120ms, box-shadow 120ms",
  }}
  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-1px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)" }}
  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "" }}>
    <div style={{ display: "flex", flexDirection: "column", gap: 3, width: 72, flexShrink: 0 }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: style.deep, whiteSpace: "nowrap" }}>
        {fmtTime(event.start_time)}
      </div>
      <div style={{ fontSize: 11, fontWeight: 600, color: "var(--muted)", whiteSpace: "nowrap" }}>
        {event.city}
      </div>
    </div>
    <div style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 2 }}>
        <span style={{ fontSize: 15, fontWeight: 800, color: "var(--ink)", letterSpacing: "-0.005em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{event.name}</span>
        {event.editors_pick && <PickBadge />}
      </div>
      <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {event.host}
      </div>
    </div>
    <ChevronRight />
  </div>
)

const EventCardStandard = ({ event, style, onClick }) => (
  <div onClick={(e) => onClick(e.currentTarget)} style={{
    background: "var(--paper)", border: "1px solid var(--line)",
    padding: 18, cursor: "pointer",
    display: "flex", flexDirection: "column", gap: 10,
    transition: "transform 120ms, box-shadow 120ms",
  }}
  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)" }}
  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "" }}>
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
    <p style={{ fontSize: 13, color: "var(--ink-3)", margin: 0, lineHeight: 1.45,
      display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
      {event.description}
    </p>
  </div>
)

const EventCardVisual = ({ event, style, onClick }) => (
  <div onClick={(e) => onClick(e.currentTarget)} style={{
    display: "flex", background: "var(--paper)", border: "1px solid var(--line)",
    cursor: "pointer", overflow: "hidden",
    transition: "transform 120ms, box-shadow 120ms",
  }}
  onMouseEnter={e => { e.currentTarget.style.transform = "translateY(-2px)"; e.currentTarget.style.boxShadow = "var(--shadow-2)" }}
  onMouseLeave={e => { e.currentTarget.style.transform = ""; e.currentTarget.style.boxShadow = "" }}>
    <div style={{
      width: 92, flexShrink: 0,
      background: style.soft, color: style.deep,
      padding: 14, display: "flex", flexDirection: "column", justifyContent: "space-between",
      borderRight: `3px solid ${style.dot}`,
    }}>
      <div style={{ fontSize: 10, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" }}>
        {event.event_type}
      </div>
      <div>
        <div style={{ fontSize: 26, fontWeight: 900, letterSpacing: "-0.02em", lineHeight: 1 }}>
          {parseDate(event.date).getDate()}
        </div>
        <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.06em", textTransform: "uppercase" }}>
          {MONTHS[parseDate(event.date).getMonth()].slice(0,3)} · {fmtTime(event.start_time)}
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
      <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginTop: 2 }}>
        {event.audience.slice(0, 3).map(a => (
          <span key={a} style={{
            fontSize: 10, fontWeight: 800, color: "var(--ink-3)",
            background: "var(--paper-2)", padding: "2px 7px", letterSpacing: "0.02em",
            border: "1px solid var(--line)",
          }}>{a}</span>
        ))}
      </div>
    </div>
  </div>
)

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
    color: "var(--accent-amber-deep)", background: "var(--accent-amber-soft)",
    padding: "2px 6px",
  }}>
    <StarIcon filled /> Editor's pick
  </span>
)
