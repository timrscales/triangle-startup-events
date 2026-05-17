import React from 'react'
import { ChevronLeft, ChevronRight } from '../icons.jsx'
import { formatMonthYear, formatWeekLabel, startOfWeek, parseDate } from '../utils.js'

export default function PeriodNav({ view, cursor, onPrev, onNext, onToday, eventCount }) {
  function label() {
    const d = parseDate(cursor) || new Date()
    if (view === 'month') return formatMonthYear(d)
    if (view === 'week') return formatWeekLabel(startOfWeek(d))
    return 'Upcoming Events'
  }

  return (
    <div className="periodnav">
      {view !== 'list' && (
        <>
          <button className="periodnav__btn" onClick={onPrev} aria-label="Previous">
            <ChevronLeft />
          </button>
          <button className="periodnav__btn" onClick={onNext} aria-label="Next">
            <ChevronRight />
          </button>
        </>
      )}
      <button className="periodnav__today" onClick={onToday}>
        Today
      </button>
      <span className="periodnav__label">{label()}</span>
      {eventCount != null && (
        <span className="periodnav__count">
          {eventCount} event{eventCount !== 1 ? 's' : ''}
        </span>
      )}
    </div>
  )
}
