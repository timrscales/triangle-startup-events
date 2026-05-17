import React, { useRef, useEffect } from 'react'
import {
  startOfWeek, weekDays, formatDateKey, todayKey,
  groupByDate, timeToMinutes, formatTime, getTypeColors
} from '../utils.js'
import { parseDate } from '../utils.js'

const HOUR_START = 7   // 7am
const HOUR_END   = 22  // 10pm
const HOUR_COUNT = HOUR_END - HOUR_START
const HOUR_PX    = 60

const DOW_SHORT = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS_SHORT = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function formatHour(h) {
  if (h === 0) return '12am'
  if (h === 12) return '12pm'
  return h < 12 ? `${h}am` : `${h - 12}pm`
}

export default function WeekView({ cursor, events, onSelectEvent }) {
  const cursorDate = parseDate(cursor) || new Date()
  const weekStart = startOfWeek(cursorDate)
  const days = weekDays(weekStart)
  const today = todayKey()
  const byDate = groupByDate(events)
  const bodyRef = useRef(null)

  // Scroll to 8am on mount
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = (8 - HOUR_START) * HOUR_PX
    }
  }, [])

  return (
    <div className="calendar-area">
      <div className="week-view" style={{ maxHeight: '75vh', overflowY: 'auto' }} ref={bodyRef}>
        {/* Gutter */}
        <div className="week-gutter">
          {/* Header spacer */}
          <div style={{ height: 40, borderBottom: '1px solid var(--line)' }} />
          {Array.from({ length: HOUR_COUNT }, (_, i) => (
            <div key={i} className="week-gutter__hour">
              {formatHour(HOUR_START + i)}
            </div>
          ))}
        </div>

        {/* Day columns */}
        <div className="week-columns">
          {days.map((date, ci) => {
            const key = formatDateKey(date)
            const isToday = key === today
            const dayEvents = byDate.get(key) || []

            return (
              <div key={ci} className="week-col">
                <div className={`week-col__header${isToday ? ' today' : ''}`}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '.04em' }}>
                    {DOW_SHORT[date.getDay()]}
                  </span>
                  <span className="day-num">{date.getDate()}</span>
                </div>

                <div className="week-col__body" style={{ position: 'relative', height: HOUR_COUNT * HOUR_PX }}>
                  {/* Hour grid lines */}
                  {Array.from({ length: HOUR_COUNT }, (_, i) => (
                    <div key={i} className="week-hour-line" />
                  ))}

                  {/* Events */}
                  {dayEvents.map(ev => {
                    const startMin = timeToMinutes(ev.start_time)
                    const endMin = timeToMinutes(ev.end_time)
                    if (startMin === null) return null
                    const top = Math.max(0, (startMin - HOUR_START * 60) / 60 * HOUR_PX)
                    const dur = endMin ? (endMin - startMin) : 60
                    const height = Math.max(20, dur / 60 * HOUR_PX - 2)
                    const colors = getTypeColors(ev.event_type)

                    return (
                      <div
                        key={ev.id}
                        className="week-event"
                        style={{
                          top,
                          height,
                          background: colors.soft,
                          borderLeftColor: colors.dot,
                          color: colors.deep,
                        }}
                        onClick={() => onSelectEvent(ev)}
                        title={ev.name}
                      >
                        <div className="week-event__name">{ev.name}</div>
                        {height > 30 && (
                          <div className="week-event__time">{formatTime(ev.start_time)}</div>
                        )}
                      </div>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
