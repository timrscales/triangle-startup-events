import React, { useState, useMemo } from 'react'
import {
  TAG_PALETTE, hashIndex,
  Logomark, XIcon, ExternalIcon, PinIcon, SearchIcon, FunnelIcon,
  iconBtn,
} from './shell.jsx'

const ORGS = (window.__ORGS__ || []).filter(o => o.name)

// ── color helpers ─────────────────────────────────────────────────────────────

function typeStyle(t) {
  return TAG_PALETTE[hashIndex(t.toLowerCase(), TAG_PALETTE.length)]
}

const STAGE_COLORS = {
  'Exploring':      { bg: '#F1F3F6', fg: '#3D4754' },
  'Validating':     { bg: '#FFE9C2', fg: '#8C5400' },
  'Building':       { bg: '#C9E9F7', fg: '#003D69' },
  'Growing':        { bg: '#C7F5E6', fg: '#006B65' },
  'Seed Funding':   { bg: '#FDDADA', fg: '#B30202' },
  'Growth Funding': { bg: '#E6D3FE', fg: '#5A04C0' },
}
const STAGE_ORDER = ['Exploring', 'Validating', 'Building', 'Growing', 'Seed Funding', 'Growth Funding']

function stageStyle(s) {
  return STAGE_COLORS[s] || { bg: '#F1F3F6', fg: '#3D4754' }
}

// ── data helpers ──────────────────────────────────────────────────────────────

function allTypes(orgs) {
  const counts = {}
  for (const o of orgs) for (const t of (o.org_types || [])) counts[t] = (counts[t] || 0) + 1
  return Object.entries(counts).sort((a, b) => b[1] - a[1]).map(([t]) => t)
}

function allStages(orgs) {
  const seen = new Set()
  for (const o of orgs) for (const s of (o.stage_focus || [])) seen.add(s)
  return STAGE_ORDER.filter(s => seen.has(s))
}

function filtered(orgs, types, stages, search) {
  return orgs.filter(o => {
    if (types.length && !types.some(t => (o.org_types || []).includes(t))) return false
    if (stages.length && !stages.some(s => (o.stage_focus || []).includes(s))) return false
    if (search) {
      const q = search.toLowerCase()
      const hay = [o.name, o.description, ...(o.org_types || [])].join(' ').toLowerCase()
      if (!hay.includes(q)) return false
    }
    return true
  })
}

// ── small shared atoms ────────────────────────────────────────────────────────

const Chip = ({ label, active, style: extra, onClick }) => {
  const s = typeStyle(label)
  return (
    <button
      onClick={onClick}
      style={{
        display: 'inline-flex', alignItems: 'center',
        padding: '4px 10px', fontSize: 11, fontWeight: 800, fontFamily: 'inherit',
        letterSpacing: '0.04em', cursor: 'pointer', border: 0,
        background: active ? s.fg : s.bg,
        color: active ? '#fff' : s.fg,
        transition: 'background 100ms, color 100ms',
        ...extra,
      }}
    >{label}</button>
  )
}

const StageChip = ({ label, small }) => {
  const s = stageStyle(label)
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center',
      padding: small ? '2px 7px' : '3px 9px',
      fontSize: small ? 10 : 11, fontWeight: 700, fontFamily: 'inherit',
      background: s.bg, color: s.fg,
    }}>{label}</span>
  )
}

const LinkBtn = ({ href, icon, label }) => (
  <a href={href} target="_blank" rel="noopener noreferrer" style={{
    display: 'inline-flex', alignItems: 'center', gap: 6,
    padding: '8px 14px', fontSize: 12, fontWeight: 800,
    color: 'var(--ink-3)', textDecoration: 'none',
    border: '1px solid var(--line)', background: 'var(--paper-2)',
    fontFamily: 'inherit',
    transition: 'background 100ms',
  }}
    onMouseEnter={e => e.currentTarget.style.background = 'var(--line)'}
    onMouseLeave={e => e.currentTarget.style.background = 'var(--paper-2)'}
  >
    {icon}{label}
  </a>
)

// ── icons ─────────────────────────────────────────────────────────────────────

const LinkedInIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="currentColor">
    <path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-2-2 2 2 0 0 0-2 2v7h-4v-7a6 6 0 0 1 6-6z"/>
    <rect x="2" y="9" width="4" height="12"/><circle cx="4" cy="4" r="2"/>
  </svg>
)

const InstagramIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="2" y="2" width="20" height="20" rx="5" ry="5"/><path d="M16 11.37A4 4 0 1 1 12.63 8 4 4 0 0 1 16 11.37z"/><line x1="17.5" y1="6.5" x2="17.51" y2="6.5"/>
  </svg>
)

const GlobeIcon = () => (
  <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/>
    <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
  </svg>
)

const CalendarIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <rect x="3" y="4" width="18" height="18" rx="2" ry="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>
  </svg>
)

const ProgramIcon = () => (
  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/><path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>
  </svg>
)

// ── FilterSidebar ─────────────────────────────────────────────────────────────

const FilterSidebar = ({ types, filterTypes, toggleType, stages, filterStages, toggleStage, count, total, onClear, isMobile }) => (
  <div style={{ padding: isMobile ? '0' : '0 16px' }}>
    <div style={{
      fontSize: 11, fontWeight: 800, letterSpacing: '0.12em',
      textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 12,
    }}>
      Showing {count} of {total}
    </div>

    {(filterTypes.length > 0 || filterStages.length > 0) && (
      <button onClick={onClear} style={{
        display: 'block', marginBottom: 14, fontSize: 11, fontWeight: 800,
        color: 'var(--rdsw-blue)', background: 'none', border: 'none',
        cursor: 'pointer', padding: 0, fontFamily: 'inherit',
        letterSpacing: '0.04em',
      }}>Clear all filters</button>
    )}

    <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>Organization Type</div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 20 }}>
      {types.map(t => (
        <Chip key={t} label={t} active={filterTypes.includes(t)} onClick={() => toggleType(t)} />
      ))}
    </div>

    <div style={{ fontSize: 11, fontWeight: 900, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--ink-3)', marginBottom: 8 }}>Stage Focus</div>
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5 }}>
      {stages.map(s => {
        const active = filterStages.includes(s)
        const sc = stageStyle(s)
        return (
          <button key={s} onClick={() => toggleStage(s)} style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '4px 10px', fontSize: 11, fontWeight: 800, fontFamily: 'inherit',
            cursor: 'pointer', border: 0,
            background: active ? sc.fg : sc.bg,
            color: active ? '#fff' : sc.fg,
            transition: 'background 100ms',
          }}>{s}</button>
        )
      })}
    </div>
  </div>
)

// ── OrgCard ───────────────────────────────────────────────────────────────────

const OrgCard = ({ org, selected, onClick }) => {
  const [hovered, setHovered] = useState(false)
  const types = org.org_types || []
  const visibleTypes = types.slice(0, 2)
  const extraTypes = types.length - 2

  return (
    <div
      onClick={onClick}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        padding: '16px', cursor: 'pointer',
        border: selected
          ? '2px solid var(--rdsw-blue)'
          : hovered ? '1px solid var(--rdsw-blue)' : '1px solid var(--line)',
        background: selected ? 'var(--paper)' : hovered ? 'var(--paper-2)' : 'var(--paper)',
        boxShadow: hovered && !selected ? 'var(--shadow-2)' : 'none',
        transition: 'border 120ms, box-shadow 120ms',
        display: 'flex', flexDirection: 'column', gap: 10,
        minHeight: 140,
      }}
    >
      {/* Name + type chips */}
      <div>
        <div style={{ fontWeight: 900, fontSize: 14, letterSpacing: '-0.01em', lineHeight: 1.2, marginBottom: 7, color: 'var(--ink)' }}>
          {org.name}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
          {visibleTypes.map(t => {
            const s = typeStyle(t)
            return (
              <span key={t} style={{ padding: '2px 7px', fontSize: 10, fontWeight: 800, background: s.bg, color: s.fg, letterSpacing: '0.04em' }}>
                {t}
              </span>
            )
          })}
          {extraTypes > 0 && (
            <span style={{ padding: '2px 7px', fontSize: 10, fontWeight: 800, background: 'var(--paper-2)', color: 'var(--muted)' }}>
              +{extraTypes}
            </span>
          )}
        </div>
      </div>

      {/* Description */}
      {org.description && (
        <p style={{
          fontSize: 12, color: 'var(--ink-3)', lineHeight: 1.55, margin: 0,
          display: '-webkit-box', WebkitLineClamp: 3, WebkitBoxOrient: 'vertical',
          overflow: 'hidden',
        }}>{org.description}</p>
      )}

      {/* Footer: events + programs count */}
      <div style={{ display: 'flex', gap: 10, marginTop: 'auto' }}>
        {org.event_count > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>
            <CalendarIcon />{org.event_count} event{org.event_count !== 1 ? 's' : ''}
          </span>
        )}
        {org.program_count > 0 && (
          <span style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', fontWeight: 600 }}>
            <ProgramIcon />{org.program_count} program{org.program_count !== 1 ? 's' : ''}
          </span>
        )}
        {org.website && (
          <a
            href={org.website} target="_blank" rel="noopener noreferrer"
            onClick={e => e.stopPropagation()}
            style={{ marginLeft: 'auto', fontSize: 11, color: 'var(--rdsw-blue)', fontWeight: 700, textDecoration: 'none', display: 'flex', alignItems: 'center', gap: 3 }}
          >
            Visit <ExternalIcon />
          </a>
        )}
      </div>
    </div>
  )
}

// ── OrgDetailPanel ────────────────────────────────────────────────────────────

const OrgDetailPanel = ({ org, onClose, isMobile }) => {
  const initials = org.name.split(' ').slice(0, 2).map(w => w[0]).join('').toUpperCase()

  return (
    <div style={{
      width: isMobile ? '100%' : 340, flexShrink: 0,
      borderLeft: isMobile ? 'none' : '1px solid var(--line)',
      overflowY: 'auto', background: 'var(--paper)',
      padding: '24px 24px 32px',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 44, height: 44, background: 'var(--rdsw-blue)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 14, fontWeight: 900, color: '#fff', flexShrink: 0,
          }}>{initials}</div>
          <div>
            <div style={{ fontWeight: 900, fontSize: 15, letterSpacing: '-0.01em', lineHeight: 1.2 }}>{org.name}</div>
            {org.address && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'var(--muted)', marginTop: 3 }}>
                <PinIcon />{org.address}
              </div>
            )}
          </div>
        </div>
        <button onClick={onClose} style={{ ...iconBtn(true), border: 0, flexShrink: 0 }}><XIcon /></button>
      </div>

      {/* Type chips */}
      {(org.org_types || []).length > 0 && (
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 5, marginBottom: 14 }}>
          {org.org_types.map(t => {
            const s = typeStyle(t)
            return <span key={t} style={{ padding: '3px 9px', fontSize: 11, fontWeight: 800, background: s.bg, color: s.fg }}>{t}</span>
          })}
        </div>
      )}

      {/* Stage focus */}
      {(org.stage_focus || []).length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 6 }}>Stage Focus</div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {STAGE_ORDER.filter(s => org.stage_focus.includes(s)).map(s => <StageChip key={s} label={s} small />)}
          </div>
        </div>
      )}

      {/* Description */}
      {org.description && (
        <p style={{ fontSize: 13, color: 'var(--ink-3)', lineHeight: 1.65, margin: '0 0 18px' }}>{org.description}</p>
      )}

      {/* Links */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 20 }}>
        {org.website && <LinkBtn href={org.website} icon={<GlobeIcon />} label="Website" />}
        {org.linkedin && <LinkBtn href={org.linkedin} icon={<LinkedInIcon />} label="LinkedIn" />}
        {org.instagram && <LinkBtn href={org.instagram} icon={<InstagramIcon />} label="Instagram" />}
      </div>

      {/* Upcoming Events */}
      {(org.event_names || []).length > 0 && (
        <div style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            Upcoming Events
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {org.event_names.map((name, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 7,
                fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.4,
              }}>
                <span style={{ marginTop: 4, flexShrink: 0 }}><CalendarIcon /></span>
                {name}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Programs */}
      {(org.program_names || []).length > 0 && (
        <div>
          <div style={{ fontSize: 10, fontWeight: 900, letterSpacing: '0.12em', textTransform: 'uppercase', color: 'var(--muted)', marginBottom: 8 }}>
            Programs
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            {org.program_names.map((name, i) => (
              <div key={i} style={{
                display: 'flex', alignItems: 'flex-start', gap: 7,
                fontSize: 12, color: 'var(--ink-2)', lineHeight: 1.4,
              }}>
                <span style={{ marginTop: 3, flexShrink: 0 }}><ProgramIcon /></span>
                {name}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── OrgsApp (root) ────────────────────────────────────────────────────────────

export default function OrgsApp({ device }) {
  const isMobile = device === 'mobile'

  const [selected, setSelected] = useState(null)
  const [filterTypes, setFilterTypes] = useState([])
  const [filterStages, setFilterStages] = useState([])
  const [search, setSearch] = useState('')
  const [searchOpen, setSearchOpen] = useState(false)
  const [filterOpen, setFilterOpen] = useState(false)

  const types  = useMemo(() => allTypes(ORGS), [])
  const stages = useMemo(() => allStages(ORGS), [])
  const results = useMemo(() => filtered(ORGS, filterTypes, filterStages, search), [filterTypes, filterStages, search])

  const totalFilters = filterTypes.length + filterStages.length

  const toggleType  = t => setFilterTypes(prev  => prev.includes(t)  ? prev.filter(x => x !== t)  : [...prev, t])
  const toggleStage = s => setFilterStages(prev => prev.includes(s) ? prev.filter(x => x !== s) : [...prev, s])
  const clearAll    = () => { setFilterTypes([]); setFilterStages([]) }

  const selectOrg = org => setSelected(prev => prev?.id === org.id ? null : org)

  // Detect grid columns
  const cols = isMobile ? 1 : selected ? 2 : 3

  return (
    <div style={{
      display: 'flex', flexDirection: 'column', height: '100vh',
      fontFamily: 'var(--font-sans)', background: 'var(--paper)', color: 'var(--ink)',
      overflow: 'hidden',
    }}>

      {/* ── Top bar ── */}
      <div style={{
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: isMobile ? '12px 14px' : '16px 28px',
        borderBottom: '1px solid var(--line)',
        background: 'var(--paper)', gap: 16, flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, minWidth: 0 }}>
          <Logomark size={isMobile ? 28 : 36} />
          <div style={{ minWidth: 0 }}>
            <div style={{ fontSize: isMobile ? 14 : 16, fontWeight: 900, letterSpacing: '-0.01em', whiteSpace: 'nowrap' }}>
              Triangle Startup Resource Guide
            </div>
            {!isMobile && (
              <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 3, fontWeight: 500 }}>
                Organizations, accelerators &amp; resources for founders in the Triangle
              </div>
            )}
          </div>
        </div>

        <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexShrink: 0 }}>
          <a href="/" style={{
            display: 'inline-flex', alignItems: 'center',
            padding: '0 12px', height: 36, fontSize: 12, fontWeight: 800,
            fontFamily: 'var(--font-sans)', textDecoration: 'none',
            background: 'var(--paper-2)', color: 'var(--ink-3)',
            border: '1px solid var(--line)',
          }}>← Events</a>
          <button
            onClick={() => setSearchOpen(v => !v)}
            style={{
              ...iconBtn(isMobile),
              background: searchOpen ? 'var(--ink)' : 'var(--paper)',
              color: searchOpen ? '#fff' : 'var(--ink-3)',
              border: `1px solid ${searchOpen ? 'var(--ink)' : 'var(--line)'}`,
            }}
          ><SearchIcon /></button>
          {!isMobile && (
            <button
              onClick={() => setFilterOpen(v => !v)}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: 5,
                padding: '0 12px', height: 36, fontSize: 12, fontWeight: 800,
                fontFamily: 'inherit', cursor: 'pointer',
                background: totalFilters > 0 ? 'var(--ink)' : 'var(--paper-2)',
                color: totalFilters > 0 ? '#fff' : 'var(--ink-2)',
                border: `1px solid ${totalFilters > 0 ? 'var(--ink)' : 'var(--line)'}`,
              }}
            >
              <FunnelIcon />
              Filters
              {totalFilters > 0 && (
                <span style={{
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  width: 16, height: 16, borderRadius: '50%',
                  background: 'var(--rdsw-blue)', color: '#fff',
                  fontSize: 9, fontWeight: 900,
                }}>{totalFilters}</span>
              )}
            </button>
          )}
          {isMobile && (
            <button
              onClick={() => setFilterOpen(true)}
              style={{
                ...iconBtn(true),
                background: totalFilters > 0 ? 'var(--ink)' : 'var(--paper)',
                color: totalFilters > 0 ? '#fff' : 'var(--ink-3)',
                border: `1px solid ${totalFilters > 0 ? 'var(--ink)' : 'var(--line)'}`,
              }}
            ><FunnelIcon /></button>
          )}
        </div>
      </div>

      {/* ── Search bar ── */}
      {searchOpen && (
        <div style={{ padding: isMobile ? '10px 14px' : '10px 28px', borderBottom: '1px solid var(--line)', background: 'var(--paper-2)', flexShrink: 0 }}>
          <input
            autoFocus
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, type, or description…"
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '9px 14px', fontSize: 13,
              border: '1px solid var(--line)', background: 'var(--paper)',
              fontFamily: 'inherit', color: 'var(--ink)', outline: 'none',
            }}
          />
        </div>
      )}

      {/* ── Desktop filter bar (collapsible below topbar) ── */}
      {!isMobile && filterOpen && (
        <div style={{
          borderBottom: '1px solid var(--line)', background: 'var(--paper-2)',
          padding: '16px 28px', flexShrink: 0,
        }}>
          <FilterSidebar
            types={types} filterTypes={filterTypes} toggleType={toggleType}
            stages={stages} filterStages={filterStages} toggleStage={toggleStage}
            count={results.length} total={ORGS.length} onClear={clearAll}
          />
        </div>
      )}

      {/* ── Body ── */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>

        {/* Org grid */}
        <main style={{
          flex: 1, overflowY: 'auto',
          padding: isMobile ? '14px' : '24px 28px',
        }}>
          {/* Count header */}
          <div style={{
            fontSize: 11, fontWeight: 800, letterSpacing: '0.1em',
            textTransform: 'uppercase', color: 'var(--muted)',
            marginBottom: 16,
          }}>
            {results.length} organization{results.length !== 1 ? 's' : ''}
            {(filterTypes.length > 0 || filterStages.length > 0 || search) ? (
              <> · <button onClick={() => { clearAll(); setSearch('') }} style={{ fontSize: 11, fontWeight: 800, color: 'var(--rdsw-blue)', background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: 'inherit', letterSpacing: '0.1em', textTransform: 'uppercase' }}>Clear</button></>
            ) : null}
          </div>

          <div style={{
            display: 'grid',
            gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))`,
            gap: isMobile ? 10 : 14,
            alignContent: 'start',
          }}>
            {results.map(org => (
              <OrgCard
                key={org.id}
                org={org}
                selected={selected?.id === org.id}
                onClick={() => selectOrg(org)}
              />
            ))}
            {results.length === 0 && (
              <div style={{
                gridColumn: '1 / -1', padding: '48px 0',
                textAlign: 'center', color: 'var(--muted)', fontSize: 14,
              }}>
                No organizations match your filters.
              </div>
            )}
          </div>
        </main>

        {/* Desktop detail panel */}
        {selected && !isMobile && (
          <OrgDetailPanel org={selected} onClose={() => setSelected(null)} />
        )}
      </div>

      {/* Mobile detail panel (bottom sheet) */}
      {selected && isMobile && (
        <>
          <div
            onClick={() => setSelected(null)}
            style={{ position: 'fixed', inset: 0, zIndex: 39, background: 'rgba(0,0,0,0.3)' }}
          />
          <div style={{
            position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 40,
            background: 'var(--paper)', borderTop: '1px solid var(--line)',
            maxHeight: '82vh', overflowY: 'auto',
            animation: 'tseFadeScale 150ms var(--ease-out)',
          }}>
            <OrgDetailPanel org={selected} onClose={() => setSelected(null)} isMobile />
          </div>
        </>
      )}

      {/* Mobile filter drawer (bottom sheet) */}
      {filterOpen && isMobile && (
        <>
          <div onClick={() => setFilterOpen(false)} style={{ position: 'fixed', inset: 0, zIndex: 49, background: 'rgba(0,0,0,0.3)' }} />
          <div style={{
            position: 'fixed', bottom: 0, left: 0, right: 0, zIndex: 50,
            background: 'var(--paper)', borderTop: '1px solid var(--line)',
            maxHeight: '80vh', overflowY: 'auto', padding: '20px',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
              <span style={{ fontWeight: 900, fontSize: 14 }}>Filters</span>
              <button onClick={() => setFilterOpen(false)} style={{ ...iconBtn(true), border: 0 }}><XIcon /></button>
            </div>
            <FilterSidebar
              types={types} filterTypes={filterTypes} toggleType={toggleType}
              stages={stages} filterStages={filterStages} toggleStage={toggleStage}
              count={results.length} total={ORGS.length}
              onClear={clearAll} isMobile
            />
          </div>
        </>
      )}
    </div>
  )
}
