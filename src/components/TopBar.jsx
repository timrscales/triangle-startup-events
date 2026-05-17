import React from 'react'

const VIEWS = [
  { id: 'month', label: 'Month' },
  { id: 'week',  label: 'Week' },
  { id: 'list',  label: 'List' },
]

export default function TopBar({ view, onViewChange, onSubmit }) {
  return (
    <header className="topbar">
      <div className="topbar__wordmark">
        Triangle <span>Startup</span> Events
      </div>

      <nav className="topbar__views">
        {VIEWS.map(v => (
          <button
            key={v.id}
            className={`topbar__view-btn${view === v.id ? ' active' : ''}`}
            onClick={() => onViewChange(v.id)}
          >
            {v.label}
          </button>
        ))}
      </nav>

      <button className="topbar__submit" onClick={onSubmit}>
        + Submit Event
      </button>
    </header>
  )
}
