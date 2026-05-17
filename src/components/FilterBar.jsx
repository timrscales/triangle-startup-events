import React, { useState, useRef, useEffect } from 'react'
import { Search, ChevronDown, Check, X } from '../icons.jsx'
import { allCities, allTypes, allTags, EVENT_TYPES } from '../utils.js'

function Dropdown({ label, options, selected, onChange, renderOption }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  useEffect(() => {
    if (!open) return
    const handler = (e) => {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const hasSelection = selected.length > 0
  const displayLabel = hasSelection
    ? selected.length === 1 ? selected[0] : `${label} (${selected.length})`
    : label

  function toggle(val) {
    if (selected.includes(val)) {
      onChange(selected.filter(v => v !== val))
    } else {
      onChange([...selected, val])
    }
  }

  return (
    <div className="filter-dropdown" ref={ref}>
      <button
        className={`filter-dropdown__btn${hasSelection ? ' has-selection' : ''}`}
        onClick={() => setOpen(o => !o)}
      >
        {displayLabel}
        <ChevronDown />
      </button>
      {open && (
        <div className="filter-dropdown__menu">
          {options.map(opt => {
            const val = typeof opt === 'string' ? opt : opt.value
            const sel = selected.includes(val)
            return (
              <button
                key={val}
                className={`filter-dropdown__item${sel ? ' selected' : ''}`}
                onClick={() => toggle(val)}
              >
                <span className="filter-dropdown__check">
                  {sel && <Check size={10} />}
                </span>
                {renderOption ? renderOption(opt) : val}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function FilterBar({ events, filters, onFiltersChange }) {
  const cities = allCities(events)
  const types = allTypes(events)
  const tags = allTags(events)

  const hasAnyFilter =
    filters.search ||
    filters.cities.length ||
    filters.types.length ||
    filters.tags.length

  function update(key, val) {
    onFiltersChange({ ...filters, [key]: val })
  }

  function clearAll() {
    onFiltersChange({ search: '', cities: [], types: [], tags: [] })
  }

  return (
    <div className="filterbar">
      <div className="filterbar__search">
        <Search />
        <input
          type="search"
          placeholder="Search events, organizers..."
          value={filters.search}
          onChange={e => update('search', e.target.value)}
        />
        {filters.search && (
          <button onClick={() => update('search', '')} style={{ color: 'var(--muted)' }}>
            <X size={13} />
          </button>
        )}
      </div>

      <Dropdown
        label="City"
        options={cities}
        selected={filters.cities}
        onChange={val => update('cities', val)}
      />

      <Dropdown
        label="Type"
        options={types}
        selected={filters.types}
        onChange={val => update('types', val)}
        renderOption={type => (
          <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{
              width: 8, height: 8, borderRadius: '50%',
              background: EVENT_TYPES[type]?.dot || '#6B7785',
              flexShrink: 0,
            }} />
            {type}
          </span>
        )}
      />

      <Dropdown
        label="Topic"
        options={tags}
        selected={filters.tags}
        onChange={val => update('tags', val)}
      />

      {hasAnyFilter && (
        <button className="filterbar__clear" onClick={clearAll}>
          Clear all
        </button>
      )}
    </div>
  )
}
