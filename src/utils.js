export const EVENT_TYPES = {
  'Talk':        { dot: '#FFB648', soft: '#FFE9C2', deep: '#E68A00' },
  'Panel':       { dot: '#FC7777', soft: '#FDDADA', deep: '#E10505' },
  'Workshop':    { dot: '#B577FC', soft: '#E6D3FE', deep: '#6B05E1' },
  'Happy Hour':  { dot: '#1BE0B0', soft: '#C7F5E6', deep: '#009F97' },
  'Networking':  { dot: '#009DE0', soft: '#C9E9F7', deep: '#003D69' },
  'Demo Day':    { dot: '#003D69', soft: '#D5DEE6', deep: '#001A2E' },
}

export function getTypeColors(eventType) {
  return EVENT_TYPES[eventType] || { dot: '#6B7785', soft: '#E4E8EE', deep: '#3D4754' }
}

const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const DOW_FULL = ['Sunday', 'Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday']
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June',
                'July', 'August', 'September', 'October', 'November', 'December']
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** Parse a YYYY-MM-DD string as a local Date (no timezone shift) */
export function parseDate(dateStr) {
  if (!dateStr) return null
  const [y, m, d] = dateStr.split('-').map(Number)
  return new Date(y, m - 1, d)
}

/** Format a Date as YYYY-MM-DD */
export function formatDateKey(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/** Today as YYYY-MM-DD */
export function todayKey() {
  return formatDateKey(new Date())
}

/** Format "May 2026" */
export function formatMonthYear(date) {
  return `${MONTHS[date.getMonth()]} ${date.getFullYear()}`
}

/** Format "Week of May 12" */
export function formatWeekLabel(date) {
  const mon = startOfWeek(date)
  return `Week of ${MONTHS_SHORT[mon.getMonth()]} ${mon.getDate()}`
}

/** Monday of the week containing date */
export function startOfWeek(date) {
  const d = new Date(date)
  const day = d.getDay()
  const diff = day === 0 ? -6 : 1 - day
  d.setDate(d.getDate() + diff)
  return d
}

/** Array of 7 dates for the week starting at weekStart */
export function weekDays(weekStart) {
  return Array.from({ length: 7 }, (_, i) => {
    const d = new Date(weekStart)
    d.setDate(d.getDate() + i)
    return d
  })
}

/** First day of the month */
export function startOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth(), 1)
}

/** Last day of the month */
export function endOfMonth(date) {
  return new Date(date.getFullYear(), date.getMonth() + 1, 0)
}

/**
 * Returns 6×7 grid of dates for month calendar.
 * Starts on Sunday of the week containing the first of the month.
 */
export function monthGrid(date) {
  const first = startOfMonth(date)
  const start = new Date(first)
  start.setDate(start.getDate() - start.getDay()) // back to Sunday
  const grid = []
  for (let i = 0; i < 42; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    grid.push(d)
  }
  return grid
}

/** Parse "HH:MM" → minutes since midnight */
export function timeToMinutes(timeStr) {
  if (!timeStr || timeStr === '00:00') return null
  const [h, m] = timeStr.split(':').map(Number)
  return h * 60 + m
}

/** Format "HH:MM" → "5:45pm" */
export function formatTime(timeStr) {
  if (!timeStr || timeStr === '00:00') return ''
  const [h, m] = timeStr.split(':').map(Number)
  const period = h >= 12 ? 'pm' : 'am'
  const hour = h % 12 || 12
  const min = m === 0 ? '' : `:${String(m).padStart(2, '0')}`
  return `${hour}${min}${period}`
}

/** Format a date as "Mon May 12" */
export function formatShortDate(date) {
  return `${DOW[date.getDay()]} ${MONTHS_SHORT[date.getMonth()]} ${date.getDate()}`
}

/** Generate stable event ID from name + date */
export function eventId(event) {
  return event.id || `evt-${btoa(encodeURIComponent(event.name + event.date)).replace(/[^a-zA-Z0-9]/g, '').slice(0, 12)}`
}

/** Extract city from location string */
export function cityFromLocation(location) {
  if (!location) return 'Triangle'
  const lower = location.toLowerCase()
  if (lower.includes('raleigh')) return 'Raleigh'
  if (lower.includes('durham')) return 'Durham'
  if (lower.includes('chapel hill')) return 'Chapel Hill'
  if (lower.includes('cary')) return 'Cary'
  if (lower.includes('research triangle') || lower.includes(' rtp')) return 'RTP'
  return 'Triangle'
}

/** Normalize event from Airtable payload into app shape */
export function normalizeEvent(raw, index) {
  const id = `evt-${index}-${(raw.name || '').replace(/\W+/g, '').slice(0, 8).toLowerCase()}`
  const city = raw.city || cityFromLocation(raw.location)
  const topicTags = Array.isArray(raw.topic_tags) ? raw.topic_tags : []
  const eventType = raw.event_type || inferEventType(raw.name, topicTags)
  return {
    id,
    name: raw.name || '',
    date: raw.date || '',
    start_time: raw.start_time || '',
    end_time: raw.end_time || '',
    location: raw.location || '',
    city,
    event_type: eventType,
    topic_tags: topicTags,
    description: raw.description || '',
    source_url: raw.source_url || '',
    friendly_date: raw.friendly_date || '',
    organizer: raw.organizer || '',
    editors_pick: raw.editors_pick || false,
  }
}

function inferEventType(name, tags) {
  const text = `${name} ${tags.join(' ')}`.toLowerCase()
  if (text.includes('workshop')) return 'Workshop'
  if (text.includes('happy hour') || text.includes('social')) return 'Happy Hour'
  if (text.includes('panel')) return 'Panel'
  if (text.includes('demo day') || text.includes('demo night')) return 'Demo Day'
  if (text.includes('network') || text.includes('mixer') || text.includes('meetup')) return 'Networking'
  return 'Talk'
}

/**
 * Filter events array against current filter state.
 * Returns filtered + sorted (by date then start_time).
 */
export function filterEvents(events, filters) {
  const { search, cities, types, tags } = filters
  const q = search.trim().toLowerCase()
  return events.filter(ev => {
    if (cities.length && !cities.includes(ev.city)) return false
    if (types.length && !types.includes(ev.event_type)) return false
    if (tags.length && !tags.some(t => ev.topic_tags.includes(t))) return false
    if (q) {
      const haystack = `${ev.name} ${ev.description} ${ev.location} ${ev.organizer}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    return true
  })
}

/** Group events by date, returning Map<dateKey, events[]> */
export function groupByDate(events) {
  const map = new Map()
  for (const ev of events) {
    const key = ev.date
    if (!map.has(key)) map.set(key, [])
    map.get(key).push(ev)
  }
  return map
}

/** All unique cities in events list */
export function allCities(events) {
  return [...new Set(events.map(e => e.city).filter(Boolean))].sort()
}

/** All unique event types in events list */
export function allTypes(events) {
  const order = Object.keys(EVENT_TYPES)
  const present = new Set(events.map(e => e.event_type).filter(Boolean))
  return order.filter(t => present.has(t))
}

/** All unique topic tags in events list */
export function allTags(events) {
  const set = new Set()
  events.forEach(e => e.topic_tags.forEach(t => set.add(t)))
  return [...set].sort()
}

/** Format day header for list view */
export function formatListDayHeader(dateKey) {
  const d = parseDate(dateKey)
  return {
    dow: DOW_FULL[d.getDay()].toUpperCase(),
    day: d.getDate(),
    month: MONTHS_SHORT[d.getMonth()],
    year: d.getFullYear(),
  }
}
