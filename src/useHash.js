import { useState, useEffect, useCallback } from 'react'

function parseHash() {
  const hash = window.location.hash.slice(1)
  const params = new URLSearchParams(hash)
  return {
    view: params.get('view') || 'list',
    date: params.get('date') || null,
    cities: params.get('cities') ? params.get('cities').split(',').filter(Boolean) : [],
    types: params.get('types') ? params.get('types').split(',').filter(Boolean) : [],
    tags: params.get('tags') ? params.get('tags').split(',').filter(Boolean) : [],
    search: params.get('search') || '',
    event: params.get('event') || null,
  }
}

function buildHash(state) {
  const params = new URLSearchParams()
  if (state.view && state.view !== 'list') params.set('view', state.view)
  if (state.date) params.set('date', state.date)
  if (state.cities && state.cities.length) params.set('cities', state.cities.join(','))
  if (state.types && state.types.length) params.set('types', state.types.join(','))
  if (state.tags && state.tags.length) params.set('tags', state.tags.join(','))
  if (state.search) params.set('search', state.search)
  if (state.event) params.set('event', state.event)
  const str = params.toString()
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
