import React, { useState, useMemo, useCallback } from 'react'
import { useHash } from './useHash.js'
import {
  normalizeEvent, filterEvents, todayKey,
  formatDateKey, startOfWeek, parseDate,
} from './utils.js'
import TopBar from './components/TopBar.jsx'
import FilterBar from './components/FilterBar.jsx'
import PeriodNav from './components/PeriodNav.jsx'
import EventDetail from './components/EventDetail.jsx'
import SubmitModal from './components/SubmitModal.jsx'
import MonthView from './views/MonthView.jsx'
import WeekView from './views/WeekView.jsx'
import ListView from './views/ListView.jsx'

// Fixture data used when no real events are injected
const FIXTURE = [
  {
    id: 'e01',
    name: 'Triangle Startup Collective — June Meeting',
    date: '2026-06-04',
    start_time: '17:45',
    end_time: '20:30',
    location: 'Raleigh Founded, 509 W North St, Raleigh',
    city: 'Raleigh',
    event_type: 'Panel',
    topic_tags: ['networking', 'panel discussion', 'startup founders'],
    description: 'Monthly meetup featuring startup founders sharing hard-won lessons on fundraising, hiring, and scaling a Triangle-area company.',
    source_url: 'https://www.meetup.com/triangle-startup-collective/',
    friendly_date: 'Thursday, June 4 · 5:45pm–8:30pm',
    organizer: 'Triangle Startup Collective',
    editors_pick: true,
  },
  {
    id: 'e02',
    name: 'AI & Product Workshop: Building LLM Applications',
    date: '2026-06-10',
    start_time: '09:00',
    end_time: '12:00',
    location: 'American Underground, 201 W Main St, Durham',
    city: 'Durham',
    event_type: 'Workshop',
    topic_tags: ['AI', 'product', 'LLM', 'workshop'],
    description: 'Hands-on workshop covering how to integrate large language models into production products, with live coding demos and Q&A.',
    source_url: 'https://lu.ma/',
    friendly_date: 'Wednesday, June 10 · 9am–12pm',
    organizer: 'Durham Tech Hub',
    editors_pick: false,
  },
  {
    id: 'e03',
    name: 'RTP Founders Happy Hour',
    date: '2026-06-12',
    start_time: '17:00',
    end_time: '19:00',
    location: 'First Flight Venture Center, RTP',
    city: 'RTP',
    event_type: 'Happy Hour',
    topic_tags: ['networking', 'founders', 'happy hour'],
    description: 'Unstructured networking for Triangle founders, investors, and operators — bring your questions and your business cards.',
    source_url: 'https://ffvc.org/',
    friendly_date: 'Friday, June 12 · 5pm–7pm',
    organizer: 'First Flight Venture Center',
    editors_pick: false,
  },
]

function getRawEvents() {
  try {
    const raw = window.__EVENTS__
    if (Array.isArray(raw) && raw.length > 0) return raw
  } catch (_) {}
  return FIXTURE
}

export default function App() {
  const [hash, setHash] = useHash()
  const [showSubmit, setShowSubmit] = useState(false)
  const [filters, setFilters] = useState({
    search: hash.search || '',
    cities: hash.cities || [],
    types: hash.types || [],
    tags: hash.tags || [],
  })

  const today = todayKey()
  const cursor = hash.date || today
  const view = hash.view || 'list'

  const allEvents = useMemo(() => {
    const raw = getRawEvents()
    return raw
      .map((ev, i) => normalizeEvent(ev, i))
      .filter(ev => ev.date)
      .sort((a, b) => {
        if (a.date < b.date) return -1
        if (a.date > b.date) return 1
        return (a.start_time || '').localeCompare(b.start_time || '')
      })
  }, [])

  const filteredEvents = useMemo(() => filterEvents(allEvents, filters), [allEvents, filters])

  const selectedEvent = useMemo(() => {
    if (!hash.event) return null
    return allEvents.find(e => e.id === hash.event) || null
  }, [hash.event, allEvents])

  const handleFiltersChange = useCallback((next) => {
    setFilters(next)
    setHash(h => ({
      ...h,
      search: next.search || undefined,
      cities: next.cities.length ? next.cities : undefined,
      types: next.types.length ? next.types : undefined,
      tags: next.tags.length ? next.tags : undefined,
    }))
  }, [setHash])

  const handleSelectEvent = useCallback((ev) => {
    setHash(h => ({ ...h, event: ev.id }))
  }, [setHash])

  const handleCloseDetail = useCallback(() => {
    setHash(h => ({ ...h, event: undefined }))
  }, [setHash])

  function navigate(direction) {
    const d = parseDate(cursor) || new Date()
    if (view === 'month') {
      d.setMonth(d.getMonth() + direction)
      d.setDate(1)
    } else if (view === 'week') {
      d.setDate(d.getDate() + direction * 7)
    }
    setHash(h => ({ ...h, date: formatDateKey(d) }))
  }

  function goToday() {
    setHash(h => ({ ...h, date: today }))
  }

  function setView(v) {
    setHash(h => ({ ...h, view: v }))
  }

  // For list view, show all filtered events; for month/week, show all (filter visually per cell)
  const viewEvents = filteredEvents

  return (
    <div className="app">
      <TopBar view={view} onViewChange={setView} onSubmit={() => setShowSubmit(true)} />
      <FilterBar events={allEvents} filters={filters} onFiltersChange={handleFiltersChange} />
      <PeriodNav
        view={view}
        cursor={cursor}
        onPrev={() => navigate(-1)}
        onNext={() => navigate(1)}
        onToday={goToday}
        eventCount={view === 'list' ? viewEvents.length : undefined}
      />

      {view === 'month' && (
        <MonthView
          cursor={cursor}
          events={viewEvents}
          onSelectEvent={handleSelectEvent}
          onSelectDate={(key) => setHash(h => ({ ...h, date: key, view: 'list' }))}
        />
      )}
      {view === 'week' && (
        <WeekView
          cursor={cursor}
          events={viewEvents}
          onSelectEvent={handleSelectEvent}
        />
      )}
      {view === 'list' && (
        <ListView
          events={viewEvents}
          onSelectEvent={handleSelectEvent}
        />
      )}

      {selectedEvent && (
        <EventDetail event={selectedEvent} onClose={handleCloseDetail} />
      )}
      {showSubmit && (
        <SubmitModal onClose={() => setShowSubmit(false)} />
      )}
    </div>
  )
}
