import React, { useState, useEffect, useRef } from 'react'

// ── Config ──────────────────────────────────────────────────────────────────
// ── Scoring maps ────────────────────────────────────────────────────────────
const GOAL_KEYWORDS = {
  "Find customers":         ["networking", "demo day", "showcase", "community"],
  "Raise funding":          ["fundraising", "pitch", "demo day", "investor"],
  "Build my team":          ["networking", "design", "engineering", "hiring", "community"],
  "Learn a specific skill": ["workshop", "talk", "engineering", "ai", "pitch"],
  "Find community":         ["networking", "community", "happy hour", "coffee", "social"],
}

const INDUSTRY_KEYWORDS = {
  "AI":          ["ai", "machine learning", "engineering"],
  "Hardware":    ["hardware", "manufacturing"],
  "B2B SaaS":    ["engineering", "ai"],
  "Fintech":     ["fundraising", "engineering"],
  "Healthtech":  ["hardware", "engineering"],
  "Deeptech":    ["hardware", "engineering", "ai"],
}

// Maps UI label → Airtable field value for direct field matching
const INDUSTRY_AIRTABLE = {
  "AI":            "AI",
  "Hardware":      "hardware",
  "B2B SaaS":      "B2B_SaaS",
  "Fintech":       "fintech",
  "Healthtech":    "healthtech",
  "Deeptech":      "deeptech",
  "Climate tech":  "climate_tech",
  "Edtech":        "edtech",
  "Proptech":      "proptech",
  "Supply chain":  "supply_chain",
  "Consumer":      "consumer",
  "Marketplaces":  "marketplaces",
}

const STAGE_AIRTABLE = {
  "Idea stage":     "Idea_Stage",
  "Building":       "Building",
  "Early traction": "Early_Traction",
  "Scaling":        "Scaling",
}

// ── Date helpers ─────────────────────────────────────────────────────────────
function parseEventDate(dateStr) {
  if (!dateStr) return null
  const [y, m, d] = dateStr.split("-").map(Number)
  return new Date(y, m - 1, d)
}

function todayMidnight() {
  const d = new Date()
  d.setHours(0, 0, 0, 0)
  return d
}

// ── Scoring engine ───────────────────────────────────────────────────────────
function scoreEvents(events, answers) {
  const { stage, goals, industries, freeText } = answers
  const today = todayMidnight()

  // Future events only
  const futureEvents = events.filter(ev => {
    const d = parseEventDate(ev.date)
    return d && d >= today
  })

  const freeWords = (freeText || "")
    .toLowerCase()
    .split(/\s+/)
    .filter(w => w.length > 3)

  const scored = futureEvents.map(ev => {
    // Normalize Airtable enum values (underscores → spaces) for keyword matching
    const formatStr  = (ev.format       || []).map(v => v.replace(/_/g, " ")).join(" ")
    const stageStr   = (ev.stage_focus  || []).map(v => v.replace(/_/g, " ")).join(" ")
    const industryStr= (ev.industry     || []).map(v => v.replace(/_/g, " ")).join(" ")

    const blob = [
      ev.name,
      (ev.topic_tags || []).join(" "),
      ev.event_type || "",
      ev.description || "",
      ev.short_description || "",
      stageStr,
      industryStr,
      formatStr,
    ].join(" ").toLowerCase()

    let score = 0
    const reasons = [] // only semantic matches — not time/free bonuses

    // ── Stage: direct field match +3, only if event is stage-specific (≤2 foci)
    if (stage && STAGE_AIRTABLE[stage]) {
      const foci = ev.stage_focus || []
      if (foci.length <= 2 && foci.includes(STAGE_AIRTABLE[stage])) {
        score += 3
        reasons.push("Your stage")
      }
    }

    // ── Goals: keyword match +3 per hit ─────────────────────────────────────
    for (const goal of goals) {
      let hit = false
      for (const kw of (GOAL_KEYWORDS[goal] || [])) {
        if (blob.includes(kw)) { score += 3; hit = true }
      }
      if (hit) reasons.push(goal)
    }

    // ── Industries: direct field match +4, keyword fallback +1 ──────────────
    for (const ind of industries) {
      if (ind === "No specific industry") continue
      let hit = false
      // Direct Airtable field match (stronger signal)
      if (INDUSTRY_AIRTABLE[ind] && (ev.industry || []).includes(INDUSTRY_AIRTABLE[ind])) {
        score += 4; hit = true
      }
      // Keyword match as supplementary signal
      for (const kw of (INDUSTRY_KEYWORDS[ind] || [])) {
        if (blob.includes(kw)) { score += 1; hit = true }
      }
      if (hit) reasons.push(ind)
    }

    // ── Free text: +2 per word hit ───────────────────────────────────────────
    if (freeWords.length > 0) {
      let freeHit = false
      for (const word of freeWords) {
        if (blob.includes(word)) { score += 2; freeHit = true }
      }
      if (freeHit) reasons.push("Your search")
    }

    // ── Time bonus (not a reason tag) ───────────────────────────────────────
    const eventDate = parseEventDate(ev.date)
    if (eventDate) {
      const daysOut = Math.floor((eventDate - today) / 86400000)
      if (daysOut <= 7)  score += 2
      else if (daysOut <= 14) score += 1.5
    }

    // ── Editor's pick: +1 (not a reason tag) ────────────────────────────────
    if (ev.editors_pick) score += 1

    // ── Free event: +0.5 (not a reason tag) ─────────────────────────────────
    if (ev.is_free !== false) score += 0.5

    return { ev, score, reasons }
  })

  // Sort descending
  scored.sort((a, b) => b.score - a.score)

  // Qualification: must have at least one semantic match (reasons.length > 0)
  const qualifying = scored.filter(s => s.reasons.length > 0)

  // Diversity picker: host diversity + format diversity
  function pickDiverse(pool, limit) {
    const picked = []
    const usedHosts = new Set()
    const usedFormats = new Set()

    // Pass 1: host + format diverse
    for (const item of pool) {
      if (picked.length >= limit) break
      const fmt = (item.ev.format || [])[0] || ""
      if (!usedHosts.has(item.ev.host) && (picked.length < 2 || !usedFormats.has(fmt) || !fmt)) {
        picked.push(item)
        usedHosts.add(item.ev.host)
        if (fmt) usedFormats.add(fmt)
      }
    }
    // Pass 2: relax format constraint
    for (const item of pool) {
      if (picked.length >= limit) break
      if (!picked.includes(item) && !usedHosts.has(item.ev.host)) {
        picked.push(item)
        usedHosts.add(item.ev.host)
      }
    }
    // Pass 3: fill remaining
    for (const item of pool) {
      if (picked.length >= limit) break
      if (!picked.includes(item)) picked.push(item)
    }
    return picked
  }

  if (qualifying.length > 0) {
    return { results: pickDiverse(qualifying, 3), isPartialMatch: false }
  }
  if (scored.length > 0) {
    // Nothing qualified — show best upcoming event as a partial match
    return { results: pickDiverse(scored, 1), isPartialMatch: true }
  }
  return { results: [], isPartialMatch: false }
}

// ── Formatting helpers ───────────────────────────────────────────────────────
function fmtEventDate(ev) {
  if (ev.friendly_date) return ev.friendly_date
  if (!ev.date) return ""
  const d = new Date(ev.date + "T00:00:00")
  const dow = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][d.getDay()]
  const mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()]
  const day = d.getDate()
  let s = `${dow}, ${mon} ${day}`
  if (ev.start_time) {
    const fmtT = t => {
      const [h, m] = t.split(":").map(Number)
      const p = h >= 12 ? "pm" : "am"
      const h12 = (h + 11) % 12 + 1
      return m ? `${h12}:${String(m).padStart(2,"0")}${p}` : `${h12}${p}`
    }
    s += ` · ${fmtT(ev.start_time)}`
    if (ev.end_time) s += `–${fmtT(ev.end_time)}`
  }
  if (ev.location) s += ` · ${ev.location}`
  return s
}

// ── Chip ─────────────────────────────────────────────────────────────────────
function Chip({ label, selected, onClick, prefix }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "7px 13px",
        fontSize: 13,
        fontWeight: 700,
        fontFamily: "inherit",
        cursor: "pointer",
        background: selected ? "var(--ink)" : "var(--paper)",
        color: selected ? "#fff" : "var(--ink-2)",
        border: `1px solid ${selected ? "var(--ink)" : "var(--line)"}`,
        transition: "background 100ms, color 100ms, border-color 100ms",
        whiteSpace: "nowrap",
      }}
    >
      {selected && prefix ? `${prefix}${label}` : label}
    </button>
  )
}

// ── Email capture ────────────────────────────────────────────────────────────
// ── Event result card ────────────────────────────────────────────────────────
function EventCard({ result }) {
  const { ev, reasons } = result
  const displayDesc = ev.short_description || ev.description
  return (
    <div style={{ border: "1px solid var(--line)", background: "var(--paper)", padding: "14px 16px" }}>
      <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.01em", color: "var(--ink)", marginBottom: 4 }}>
        {ev.name}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", marginBottom: 8 }}>
        {fmtEventDate(ev)}
        {ev.host && <> · <span style={{ color: "var(--muted)" }}>{ev.host}</span></>}
      </div>
      {displayDesc && (
        <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5, marginBottom: 11 }}>
          {displayDesc}
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10 }}>
        {reasons && reasons.length > 0 ? (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 4, alignItems: "center" }}>
            <span style={{ fontSize: 11, color: "var(--muted)", fontWeight: 600 }}>Matched:</span>
            {reasons.map(r => (
              <span key={r} style={{
                fontSize: 11, fontWeight: 700, color: "var(--rdsw-blue-dark)",
                background: "var(--paper-2)", border: "1px solid var(--line)",
                padding: "2px 7px",
              }}>{r}</span>
            ))}
          </div>
        ) : <span />}
        {ev.source_url && (
          <a href={ev.source_url} target="_blank" rel="noopener noreferrer" style={{
            display: "inline-block", flexShrink: 0,
            background: ev.is_free !== false ? "#00C9A7" : "var(--cta-bg, var(--rdsw-blue))",
            color: ev.is_free !== false ? "#fff" : "var(--cta-fg, #fff)",
            fontSize: 12, fontWeight: 700, padding: "6px 12px",
            textDecoration: "none", borderRadius: 4, whiteSpace: "nowrap",
          }}>
            {ev.is_free !== false ? "Learn More & RSVP" : "View Tickets & Pricing"}
            <svg xmlns="http://www.w3.org/2000/svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ marginLeft: 5, verticalAlign: "middle", marginTop: -2 }}>
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/>
            </svg>
          </a>
        )}
      </div>
    </div>
  )
}

// ── Question divider ─────────────────────────────────────────────────────────
const QDivider = () => (
  <div style={{ borderTop: "1px solid var(--line-2, var(--line))", margin: "0 -28px" }} />
)

// ── Main modal ───────────────────────────────────────────────────────────────
export function RecommendModal({ open, onClose, events }) {
  const [state, setState]             = useState("questionnaire")
  const [stage, setStage]             = useState(null)
  const [goals, setGoals]             = useState([])
  const [freeText, setFreeText]       = useState("")
  const [results, setResults]         = useState([])
  const [isPartialMatch, setIsPartialMatch] = useState(false)
  const overlayRef = useRef(null)

  // Reset each time modal opens
  useEffect(() => {
    if (open) setState("questionnaire")
  }, [open])

  // Escape key
  useEffect(() => {
    if (!open) return
    const handler = e => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, onClose])

  const hasAnswer = stage || goals.length > 0 || freeText.trim().length > 0

  function handleFind() {
    const { results: r, isPartialMatch: partial } = scoreEvents(events, { stage, goals, industries: [], freeText })
    setResults(r)
    setIsPartialMatch(partial)
    setState("results")
  }

  function handleBack() {
    setState("questionnaire")
  }

  function toggleGoal(g) {
    setGoals(prev => prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g])
  }

  if (!open) return null

  const isQuestionnaire = state === "questionnaire"
  const progressPct = isQuestionnaire ? 50 : 100

  const matchCount = isPartialMatch ? 0 : results.length
  const eyebrow = isQuestionnaire
    ? "Personalized for you"
    : isPartialMatch
      ? "No exact matches"
      : `${matchCount} match${matchCount !== 1 ? "es" : ""} found`

  const STAGES = ["Idea stage", "Building", "Early traction", "Scaling"]
  const GOALS  = ["Find customers", "Raise funding", "Build my team", "Learn a specific skill", "Find community"]

  return (
    <div
      ref={overlayRef}
      onClick={e => { if (e.target === overlayRef.current) onClose() }}
      style={{
        position: "fixed", inset: 0, zIndex: 200,
        background: "rgba(10,10,10,0.35)",
        display: "flex", alignItems: "center", justifyContent: "center",
        padding: "20px 16px",
        animation: "tseFadeIn 150ms var(--ease-out, ease)",
      }}
    >
      {/* Modal box */}
      <div style={{
        background: "var(--paper)",
        boxShadow: "var(--shadow-3, 0 8px 40px rgba(0,0,0,0.18))",
        width: "100%", maxWidth: 560, maxHeight: "90vh",
        display: "flex", flexDirection: "column",
        animation: "tseSlideUp 180ms var(--ease-out, ease)",
      }}>

        {/* Header */}
        <div style={{
          padding: "22px 22px 16px", borderBottom: "1px solid var(--line)",
          position: "relative", flexShrink: 0,
        }}>
          {!isQuestionnaire && (
          <div style={{
            fontSize: 11, fontWeight: 800, letterSpacing: "0.14em",
            color: "var(--muted)", marginBottom: 6, textTransform: "uppercase",
          }}>
            {eyebrow}
          </div>
        )}
          <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: "-0.02em", color: "var(--ink)" }}>
            {isQuestionnaire ? "Let's find your events" : "Here are your recommended events"}
          </div>
          <button onClick={onClose} aria-label="Close" style={{
            position: "absolute", top: 18, right: 18,
            width: 32, height: 32,
            display: "inline-flex", alignItems: "center", justifyContent: "center",
            background: "var(--paper)", border: "1px solid var(--line)",
            cursor: "pointer", color: "var(--ink-3)",
          }}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
              <path d="M18 6 6 18M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Progress bar */}
        <div style={{ height: 2, background: "var(--line)", flexShrink: 0 }}>
          <div style={{
            height: "100%", width: `${progressPct}%`,
            background: "var(--rdsw-blue)", transition: "width 300ms ease",
          }} />
        </div>

        {/* Body — scrollable */}
        <div style={{ padding: "0 28px", flex: 1, overflowY: "auto" }}>
          {isQuestionnaire ? (
            <>
              {/* Q1: Stage */}
              <div style={{ padding: "16px 0" }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)", marginBottom: 10 }}>
                  What stage is your startup?
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {STAGES.map(s => (
                    <Chip key={s} label={s} selected={stage === s}
                      onClick={() => setStage(prev => prev === s ? null : s)} />
                  ))}
                </div>
              </div>
              <QDivider />

              {/* Q2: Goals */}
              <div style={{ padding: "16px 0" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 10 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)" }}>What are you focused on right now?</span>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>pick all that apply</span>
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                  {GOALS.map(g => (
                    <Chip key={g} label={g} selected={goals.includes(g)}
                      onClick={() => toggleGoal(g)} prefix="✓ " />
                  ))}
                </div>
              </div>
              <QDivider />

              {/* Q3: Free text */}
              <div style={{ padding: "16px 0" }}>
                <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 10 }}>
                  <span style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)" }}>Anything specific you're looking for?</span>
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>optional</span>
                </div>
                <textarea
                  value={freeText}
                  onChange={e => setFreeText(e.target.value)}
                  placeholder="e.g. looking for a technical co-founder, want to practice my pitch…"
                  rows={2}
                  style={{
                    width: "100%", border: "1px solid var(--line)", background: "var(--paper)",
                    padding: "10px 12px", fontSize: 14, fontFamily: "inherit",
                    color: "var(--ink)", resize: "vertical", outline: "none", boxSizing: "border-box",
                  }}
                />
              </div>
            </>
          ) : (
            /* Results */
            <div style={{ padding: "16px 0" }}>
              {isPartialMatch && (
                <div style={{
                  fontSize: 13, color: "var(--ink-2)", background: "var(--paper-2)",
                  border: "1px solid var(--line)", padding: "10px 14px", marginBottom: 12,
                }}>
                  No events closely matched your answers. Here's the best upcoming option — try broadening your selections.
                </div>
              )}
              {results.length === 0 ? (
                <div style={{ fontSize: 14, color: "var(--muted)", padding: "20px 0" }}>
                  No upcoming events found. Check back soon.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {results.map(r => <EventCard key={r.ev.id} result={r} />)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div style={{
          borderTop: "1px solid var(--line-2, var(--line))",
          padding: "14px 28px 20px",
          display: "flex", justifyContent: "space-between", alignItems: "center",
          flexShrink: 0,
        }}>
          {isQuestionnaire ? (
            <>
              <span />
              <button
                onClick={handleFind}
                disabled={!hasAnswer}
                title={!hasAnswer ? "Answer at least one question to continue" : undefined}
                style={{
                  background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)", border: 0,
                  padding: "10px 18px", fontSize: 13, fontWeight: 800,
                  fontFamily: "inherit", cursor: hasAnswer ? "pointer" : "default",
                  opacity: hasAnswer ? 1 : 0.4, transition: "opacity 150ms",
                }}
              >
                Find my events →
              </button>
            </>
          ) : (
            <>
              <button onClick={handleBack} style={{
                background: "none", border: 0, color: "var(--muted)",
                fontSize: 13, fontFamily: "inherit", cursor: "pointer", padding: "10px 0",
              }}>
                ‹ Adjust answers
              </button>
              <button onClick={onClose} style={{
                background: "var(--accent-mint)", color: "var(--rdsw-blue-dark)", border: 0,
                padding: "10px 18px", fontSize: 13, fontWeight: 800,
                fontFamily: "inherit", cursor: "pointer",
              }}>
                Done
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
