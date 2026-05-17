import React from 'react'
import { monthGrid, formatDateKey, todayKey, groupByDate } from '../utils.js'
import { getTypeColors } from '../utils.js'

const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MAX_PILLS = 3

export default function MonthView({ cursor, events, onSelectEvent, onSelectDate }) {
  const cursorDate = cursor ? new Date(...cursor.split('-').map((v,i) => i === 1 ? +v-1 : +v)) : new Date()
  const grid = monthGrid(cursorDate)
  const today = todayKey()
  const byDate = groupByDate(events)
  const curMonth = cursorDate.getMonth()

  return (
    <div className="calendar-area">
      <div className="month-grid">
        {DOW_LABELS.map(d => (
          <div key={d} className="month-grid__header">{d}</div>
        ))}
        {grid.map((date, i) => {
          const key = formatDateKey(date)
          const dayEvents = byDate.get(key) || []
          const isToday = key === today
          const isCurrentMonth = date.getMonth() === curMonth
          const extra = dayEvents.length - MAX_PILLS

          return (
            <div
              key={i}
              className={`month-cell${!isCurrentMonth ? ' other-month' : ''}${isToday ? ' today' : ''}`}
              onClick={() => onSelectDate && onSelectDate(key)}
            >
              <div className="month-cell__day">{date.getDate()}</div>
              {dayEvents.slice(0, MAX_PILLS).map(ev => {
                const colors = getTypeColors(ev.event_type)
                return (
                  <div
                    key={ev.id}
                    className="month-pill"
                    style={{ borderLeftColor: colors.dot, background: colors.soft }}
                    onClick={e => { e.stopPropagation(); onSelectEvent(ev) }}
                    title={ev.name}
                  >
                    <span className="month-pill__dot" style={{ background: colors.dot }} />
                    <span className="month-pill__label">{ev.name}</span>
                  </div>
                )
              })}
              {extra > 0 && (
                <div
                  className="month-more"
                  onClick={e => { e.stopPropagation(); onSelectDate && onSelectDate(key) }}
                >
                  +{extra} more
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
