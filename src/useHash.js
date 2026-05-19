import { useState, useEffect, useCallback } from 'react'

function parseHash() {
  const params = new URLSearchParams(window.location.hash.slice(1))
  return {
    view:   params.get('view')   || 'List',
    date:   params.get('date')   || null,
    cities: params.get('cities') ? params.get('cities').split(',').filter(Boolean) : [],
    topics: params.get('topics') ? params.get('topics').split(',').filter(Boolean) : [],
    q:      params.get('q')      || '',
    event:  params.get('event')  || null,
  }
}

function buildHash(s) {
  const p = new URLSearchParams()
  if (s.view && s.view !== 'List') p.set('view', s.view)
  if (s.date)                       p.set('date', s.date)
  if (s.cities && s.cities.length)  p.set('cities', s.cities.join(','))
  if (s.topics && s.topics.length)  p.set('topics', s.topics.join(','))
  if (s.q)                          p.set('q', s.q)
  if (s.event)                      p.set('event', s.event)
  const str = p.toString()
  return str ? `#${str}` : '#'
}

export function useHash() {
  const [hash, setHashState] = useState(parseHash)

  useEffect(() => {
    const onHashChange = () => setHashState(parseHash())
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  const setHash = useCallback((updater) => {
    const current = parseHash()
    const next = typeof updater === 'function' ? updater(current) : { ...current, ...updater }
    const newHash = buildHash(next)
    if (window.location.hash !== newHash) {
      window.history.pushState(null, '', newHash)
      setHashState(next)
    }
  }, [])

  return [hash, setHash]
}
