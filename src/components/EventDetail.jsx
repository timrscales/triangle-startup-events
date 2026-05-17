import React, { useEffect } from 'react'
import { X, MapPin, Clock, ExternalLink, Share, Calendar } from '../icons.jsx'
import { getTypeColors, formatTime } from '../utils.js'

export default function EventDetail({ event, onClose }) {
  const colors = getTypeColors(event.event_type)

  useEffect(() => {
    function onKey(e) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])

  function handleShare() {
    if (navigator.share) {
      navigator.share({ title: event.name, url: window.location.href })
    } else {
      navigator.clipboard.writeText(window.location.href).then(() => {
        // silent copy
      })
    }
  }

  const timeStr = [formatTime(event.start_time), formatTime(event.end_time)]
    .filter(Boolean)
    .join(' – ')

  return (
    <div className="detail-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <aside className="detail-panel">
        <div className="detail-panel__type-bar" style={{ background: colors.dot }} />

        <div className="detail-panel__header">
          <span style={{
            fontSize: 11,
            fontWeight: 700,
            letterSpacing: '.06em',
            textTransform: 'uppercase',
            color: colors.deep,
            background: colors.soft,
            padding: '3px 8px',
          }}>
            {event.event_type || 'Event'}
          </span>
          <button className="detail-panel__close" onClick={onClose} aria-label="Close">
            <X />
          </button>
        </div>

        <div className="detail-panel__body">
          {event.editors_pick && (
            <span className="editors-pick-badge">Editor's Pick</span>
          )}

          <h2 className="detail-panel__name">{event.name}</h2>

          <div className="detail-panel__meta">
            {event.friendly_date && (
              <div className="detail-panel__meta-row">
                <Calendar />
                <span>{event.friendly_date}</span>
              </div>
            )}
            {!event.friendly_date && (timeStr || event.date) && (
              <div className="detail-panel__meta-row">
                <Clock />
                <span>{event.date}{timeStr ? ` · ${timeStr}` : ''}</span>
              </div>
            )}
            {event.location && (
              <div className="detail-panel__meta-row">
                <MapPin />
                <span>{event.location}</span>
              </div>
            )}
            {event.organizer && (
              <div className="detail-panel__meta-row">
                <span style={{ width: 13 }} />
                <span style={{ color: 'var(--muted)', fontSize: 12 }}>
                  Hosted by {event.organizer}
                </span>
              </div>
            )}
          </div>

          {event.description && (
            <p className="detail-panel__description">{event.description}</p>
          )}

          {event.topic_tags && event.topic_tags.length > 0 && (
            <div className="detail-panel__tags">
              {event.topic_tags.map(tag => (
                <span key={tag} className="detail-panel__tag">#{tag}</span>
              ))}
            </div>
          )}

          <div className="detail-panel__actions">
            {event.source_url && (
              <a
                className="detail-panel__rsvp"
                href={event.source_url}
                target="_blank"
                rel="noopener noreferrer"
              >
                RSVP / Register
              </a>
            )}
            <button className="detail-panel__share" onClick={handleShare} aria-label="Share">
              <Share />
            </button>
          </div>
        </div>
      </aside>
    </div>
  )
}
