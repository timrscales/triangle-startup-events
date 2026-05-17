import React from 'react'
import { groupByDate, formatListDayHeader, todayKey, formatTime, getTypeColors } from '../utils.js'
import { MapPin, Clock } from '../icons.jsx'

export default function ListView({ events, onSelectEvent }) {
  const today = todayKey()

  if (events.length === 0) {
    return (
      <div className="calendar-area">
        <div className="empty-state">
          <p>No events match your filters.</p>
          <small>Try adjusting your search or filter selections.</small>
        </div>
      </div>
    )
  }

  const byDate = groupByDate(events)
  const sortedDates = [...byDate.keys()].sort()

  return (
    <div className="calendar-area">
      {sortedDates.map(dateKey => {
        const dayEvents = byDate.get(dateKey)
        const isToday = dateKey === today
        const { dow, day, month } = formatListDayHeader(dateKey)

        return (
          <div key={dateKey} className={`list-day${isToday ? ' today' : ''}`}>
            <div className="list-day__header">
              <span className="list-day__dow">{dow}</span>
              <span className="list-day__date">{day}</span>
              <span className="list-day__month">{month}</span>
              {isToday && (
                <span style={{
                  fontSize: 10, fontWeight: 700, letterSpacing: '.06em',
                  textTransform: 'uppercase',
                  color: 'var(--paper)',
                  background: 'var(--rdsw-blue)',
                  padding: '2px 7px',
                  marginLeft: 4,
                }}>
                  Today
                </span>
              )}
            </div>

            <div className="list-cards">
              {dayEvents.map(ev => (
                <EventCard key={ev.id} event={ev} onSelect={() => onSelectEvent(ev)} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function EventCard({ event, onSelect }) {
  const colors = getTypeColors(event.event_type)
  const timeStr = [formatTime(event.start_time), formatTime(event.end_time)]
    .filter(Boolean)
    .join(' – ')

  return (
    <article
      className="event-card"
      style={{ borderLeftColor: colors.dot }}
      onClick={onSelect}
    >
      <div className="event-card__top">
        <span
          className="event-card__type-tag"
          style={{
            color: colors.deep,
            background: colors.soft,
            borderColor: colors.dot,
          }}
        >
          {event.event_type || 'Event'}
        </span>
        {event.editors_pick && (
          <span className="editors-pick-badge">Editor's Pick</span>
        )}
      </div>

      <div className="event-card__name">{event.name}</div>

      <div className="event-card__meta">
        {timeStr && (
          <span className="event-card__meta-item">
            <Clock />
            {timeStr}
          </span>
        )}
        {event.location && (
          <span className="event-card__meta-item">
            <MapPin />
            {event.city || event.location}
          </span>
        )}
        {event.organizer && (
          <span className="event-card__meta-item" style={{ color: 'var(--muted)' }}>
            {event.organizer}
          </span>
        )}
      </div>

      {event.description && (
        <p className="event-card__description">{event.description}</p>
      )}

      {event.topic_tags && event.topic_tags.length > 0 && (
        <div className="event-card__tags">
          {event.topic_tags.slice(0, 5).map(tag => (
            <span key={tag} className="event-card__tag">#{tag}</span>
          ))}
        </div>
      )}

      <div className="event-card__footer">
        <span className="event-card__organizer">
          {event.friendly_date || event.date}
        </span>
        {event.source_url && (
          <a
            className="event-card__rsvp"
            href={event.source_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
          >
            RSVP
          </a>
        )}
      </div>
    </article>
  )
}
