import React, { useState, useEffect, useRef } from 'react'

// ── Config ─────────────────────────────────────────────────────────────────
// After setting up your Airtable automation (webhook trigger), paste the
// webhook URL here and redeploy. Leave blank to disable email capture.
const AIRTABLE_WEBHOOK_URL = "https://hooks.airtable.com/workflows/v1/genericWebhook/apprt7MFT8PcVhFY4/wfl2olwnrvqPVkJLI/wtrLGuYTufw0UguQF"

// ── Scoring engine ─────────────────────────────────────────────────────────
const GOAL_KEYWORDS = {
  "Find customers":      ["networking", "demo day", "showcase", "community"],
  "Raise funding":       ["fundraising", "pitch", "demo day", "investor"],
  "Build my team":       ["networking", "design", "engineering", "hiring", "community"],
  "Learn a specific skill": ["workshop", "talk", "engineering", "ai", "pitch"],
  "Find community":      ["networking", "community", "happy hour", "coffee", "social"],
}

const INDUSTRY_KEYWORDS = {
  "AI":           ["ai", "machine learning", "engineering"],
  "Hardware":     ["hardware", "manufacturing"],
  "B2B SaaS":     ["engineering", "ai"],
  "Fintech":      ["fundraising", "engineering"],
  "Healthtech":   ["hardware", "engineering"],
  "Deeptech":     ["hardware", "engineering", "ai"],
}

function scoreEvents(events, answers) {
  const { goals, industries, freeText } = answers
  const freeWords = (freeText || "")
    .toLowerCase()
    .split(/\s+/)
    .filter(w => w.length > 3)

  const scored = events.map(ev => {
    const blob = [
      ev.name,
      (ev.topic_tags || []).join(" "),
      ev.event_type || "",
      ev.description || "",
      (ev.stage_focus || []).join(" "),
      (ev.industry || []).join(" "),
      (ev.format || []).join(" "),
    ].join(" ").toLowerCase()

    let score = 0

    // Goals: +3 per keyword hit
    for (const goal of goals) {
      for (const kw of (GOAL_KEYWORDS[goal] || [])) {
        if (blob.includes(kw)) score += 3
      }
    }

    // Industries: +2 per keyword hit
    for (const ind of industries) {
      for (const kw of (INDUSTRY_KEYWORDS[ind] || [])) {
        if (blob.includes(kw)) score += 2
      }
    }

    // Free text: +2 per word hit
    for (const word of freeWords) {
      if (blob.includes(word)) score += 2
    }

    // Editor's pick: +1
    if (ev.editors_pick) score += 1

    // Free event: +0.5
    if (ev.is_free !== false) score += 0.5

    return { ev, score }
  })

  // Sort descending
  scored.sort((a, b) => b.score - a.score)

  // Pick top 3 with host diversity
  const picked = []
  const usedHosts = new Set()
  // First pass: prefer unique hosts
  for (const { ev } of scored) {
    if (picked.length >= 3) break
    if (!usedHosts.has(ev.host)) {
      picked.push(ev)
      usedHosts.add(ev.host)
    }
  }
  // Second pass: fill remaining slots if needed
  if (picked.length < 3) {
    for (const { ev } of scored) {
      if (picked.length >= 3) break
      if (!picked.includes(ev)) picked.push(ev)
    }
  }

  return picked
}

// ── Formatting helpers ──────────────────────────────────────────────────────
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

// ── Chip component ──────────────────────────────────────────────────────────
function Chip({ label, selected, onClick, prefix }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "7px 13px",
        fontSize: 13,
        fontWeight: selected ? 700 : 700,
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

// ── Email capture ───────────────────────────────────────────────────────────
function EmailCapture({ recommendations }) {
  const [name, setName] = useState("")
  const [email, setEmail] = useState("")
  const [subscribe, setSubscribe] = useState(false)
  const [status, setStatus] = useState("idle") // idle | sending | sent | error

  async function handleSend() {
    if (!name.trim() || !email.trim()) return
    setStatus("sending")

    const eventsText = recommendations.map((ev, i) =>
      `${i + 1}. ${ev.name}\n   ${fmtEventDate(ev)}\n   ${ev.source_url || ""}`
    ).join("\n\n")

    try {
      if (AIRTABLE_WEBHOOK_URL) {
        await fetch(AIRTABLE_WEBHOOK_URL, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            email: email.trim(),
            subscribe,
            eventsText,
            events: recommendations.map(ev => ({
              name: ev.name,
              date: fmtEventDate(ev),
              host: ev.host,
              url: ev.source_url,
            })),
          }),
        })
      }
      setStatus("sent")
      setName("")
      setEmail("")
    } catch {
      setStatus("error")
    }
  }

  const inputStyle = {
    border: "1px solid var(--line)",
    background: "var(--paper)",
    padding: "10px 12px",
    fontSize: 14,
    fontFamily: "inherit",
    color: "var(--ink)",
    outline: "none",
    minWidth: 0,
  }

  return (
    <div style={{
      border: "1px dashed var(--line)",
      background: "var(--paper-2)",
      padding: 16,
      marginTop: 12,
    }}>
      <div style={{ fontSize: 13, fontWeight: 800, color: "var(--ink-2)", marginBottom: 10 }}>
        Want us to email you this list?
      </div>
      {status === "sent" ? (
        <div style={{ fontSize: 13, fontWeight: 700, color: "var(--accent-mint-deep)" }}>
          ✓ Sent — check your inbox.
        </div>
      ) : (
        <>
          <div style={{ display: "flex", gap: 7, flexWrap: "wrap", marginBottom: 10 }}>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Your name"
              style={{ ...inputStyle, flex: "1 1 100px" }}
            />
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="Email address"
              style={{ ...inputStyle, flex: "2 1 160px" }}
            />
            <button
              onClick={handleSend}
              disabled={status === "sending" || !name.trim() || !email.trim()}
              style={{
                background: "var(--ink)",
                color: "#fff",
                border: 0,
                padding: "10px 16px",
                fontSize: 13,
                fontWeight: 800,
                fontFamily: "inherit",
                cursor: "pointer",
                opacity: (!name.trim() || !email.trim()) ? 0.5 : 1,
                whiteSpace: "nowrap",
              }}
            >
              {status === "sending" ? "Sending…" : "Send it"}
            </button>
          </div>
          {status === "error" && (
            <div style={{ fontSize: 12, color: "#B30202", marginBottom: 8 }}>
              Something went wrong — try again.
            </div>
          )}
          <label style={{ display: "flex", alignItems: "flex-start", gap: 8, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={subscribe}
              onChange={e => setSubscribe(e.target.checked)}
              style={{ marginTop: 2, flexShrink: 0 }}
            />
            <span style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
              Never miss an event. Subscribe for a free weekly update every Monday.
            </span>
          </label>
        </>
      )}
    </div>
  )
}

// ── Event result card ───────────────────────────────────────────────────────
function EventCard({ ev }) {
  return (
    <div style={{
      border: "1px solid var(--line)",
      background: "var(--paper)",
      padding: "14px 16px",
    }}>
      <div style={{ fontSize: 15, fontWeight: 800, letterSpacing: "-0.01em", color: "var(--ink)", marginBottom: 4 }}>
        {ev.name}
      </div>
      <div style={{ fontSize: 12, fontWeight: 600, color: "var(--ink-3)", marginBottom: 8 }}>
        {fmtEventDate(ev)}
        {ev.host && (
          <> · <span style={{ color: "var(--muted)" }}>{ev.host}</span></>
        )}
      </div>
      {ev.description && (
        <div style={{ fontSize: 13, color: "var(--ink-2)", lineHeight: 1.5, marginBottom: 11 }}>
          {ev.description}
        </div>
      )}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        {ev.city ? (
          <span style={{
            fontSize: 11, fontWeight: 700, color: "var(--ink-3)",
            background: "var(--paper-2)", border: "1px solid var(--line)",
            padding: "3px 7px",
          }}>
            {ev.city}
          </span>
        ) : <span />}
        {ev.source_url && (
          <a
            href={ev.source_url}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "inline-block",
              background: ev.is_free !== false ? "#00C9A7" : "var(--cta-bg, var(--rdsw-blue))",
              color: ev.is_free !== false ? "#fff" : "var(--cta-fg, #fff)",
              fontSize: 12,
              fontWeight: 700,
              padding: "6px 12px",
              textDecoration: "none",
              borderRadius: 4,
              whiteSpace: "nowrap",
            }}
          >
            {ev.is_free !== false ? "Learn More & RSVP" : "View Tickets & Pricing"}
          </a>
        )}
      </div>
    </div>
  )
}

// ── Question divider ────────────────────────────────────────────────────────
const QDivider = () => (
  <div style={{ borderTop: "1px solid var(--line-2, var(--line))", margin: "0 -28px" }} />
)

// ── Main modal ─────────────────────────────────────────────────────────────
export function RecommendModal({ open, onClose, events }) {
  const [state, setState] = useState("questionnaire") // questionnaire | results
  const [stage, setStage] = useState(null)
  const [goals, setGoals] = useState([])
  const [industries, setIndustries] = useState([])
  const [freeText, setFreeText] = useState("")
  const [recommendations, setRecommendations] = useState([])
  const overlayRef = useRef(null)

  // Reset to questionnaire each time modal opens
  useEffect(() => {
    if (open) {
      setState("questionnaire")
    }
  }, [open])

  // Escape key
  useEffect(() => {
    if (!open) return
    const handler = e => { if (e.key === "Escape") onClose() }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [open, onClose])

  function handleFind() {
    const results = scoreEvents(events, { goals, industries, freeText })
    setRecommendations(results)
    setState("results")
  }

  function handleBack() {
    setState("questionnaire")
  }

  function toggleGoal(g) {
    setGoals(prev => prev.includes(g) ? prev.filter(x => x !== g) : [...prev, g])
  }

  function toggleIndustry(ind) {
    if (ind === "No specific industry") {
      setIndustries(prev => prev.includes(ind) ? [] : [ind])
      return
    }
    setIndustries(prev => {
      const without = prev.filter(x => x !== "No specific industry")
      return without.includes(ind) ? without.filter(x => x !== ind) : [...without, ind]
    })
  }

  if (!open) return null

  const isQuestionnaire = state === "questionnaire"
  const progressPct = isQuestionnaire ? 50 : 100

  const STAGES = ["Idea stage", "Building", "Early traction", "Scaling"]
  const GOALS = ["Find customers", "Raise funding", "Build my team", "Learn a specific skill", "Find community"]
  const INDUSTRIES = [
    "Healthtech", "Fintech", "Climate tech", "B2B SaaS", "Edtech", "Proptech",
    "Supply chain", "Consumer", "Marketplaces", "Deeptech", "Hardware", "AI",
    "No specific industry",
  ]

  return (
    <>
      {/* Overlay */}
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
          width: "100%",
          maxWidth: 560,
          maxHeight: "90vh",
          display: "flex",
          flexDirection: "column",
          animation: "tseSlideUp 180ms var(--ease-out, ease)",
          overflowY: "auto",
        }}>

          {/* Header */}
          <div style={{
            padding: "22px 22px 16px",
            borderBottom: "1px solid var(--line)",
            position: "relative",
            flexShrink: 0,
          }}>
            <div style={{
              fontSize: 11, fontWeight: 800, letterSpacing: "0.14em",
              color: "var(--muted)", marginBottom: 6, textTransform: "uppercase",
            }}>
              {isQuestionnaire ? "Personalized for you" : `${recommendations.length} match${recommendations.length !== 1 ? "es" : ""} found`}
            </div>
            <div style={{ fontSize: 24, fontWeight: 900, letterSpacing: "-0.02em", color: "var(--ink)" }}>
              {isQuestionnaire ? "Let's find your events" : "Here are your recommended events"}
            </div>
            <button
              onClick={onClose}
              aria-label="Close"
              style={{
                position: "absolute", top: 18, right: 18,
                width: 32, height: 32,
                display: "inline-flex", alignItems: "center", justifyContent: "center",
                background: "var(--paper)", border: "1px solid var(--line)",
                cursor: "pointer", color: "var(--ink-3)",
              }}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
                <path d="M18 6 6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* Progress bar */}
          <div style={{ height: 2, background: "var(--line)", flexShrink: 0 }}>
            <div style={{
              height: "100%",
              width: `${progressPct}%`,
              background: "var(--rdsw-blue)",
              transition: "width 300ms ease",
            }} />
          </div>

          {/* Body */}
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
                      <Chip
                        key={s}
                        label={s}
                        selected={stage === s}
                        onClick={() => setStage(prev => prev === s ? null : s)}
                      />
                    ))}
                  </div>
                </div>

                <QDivider />

                {/* Q2: Goals */}
                <div style={{ padding: "16px 0" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)" }}>
                      What's your primary goal?
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>pick all that apply</span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {GOALS.map(g => (
                      <Chip
                        key={g}
                        label={g}
                        selected={goals.includes(g)}
                        onClick={() => toggleGoal(g)}
                        prefix="✓ "
                      />
                    ))}
                  </div>
                </div>

                <QDivider />

                {/* Q3: Industry */}
                <div style={{ padding: "16px 0" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)" }}>
                      What's your industry?
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>pick any that fit</span>
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {INDUSTRIES.map(ind => (
                      <Chip
                        key={ind}
                        label={ind}
                        selected={industries.includes(ind)}
                        onClick={() => toggleIndustry(ind)}
                        prefix="✓ "
                      />
                    ))}
                  </div>
                </div>

                <QDivider />

                {/* Q4: Free text */}
                <div style={{ padding: "16px 0" }}>
                  <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 10 }}>
                    <span style={{ fontSize: 14, fontWeight: 800, color: "var(--ink)" }}>
                      Anything specific you're looking for?
                    </span>
                    <span style={{ fontSize: 11, color: "var(--muted)" }}>optional</span>
                  </div>
                  <textarea
                    value={freeText}
                    onChange={e => setFreeText(e.target.value)}
                    placeholder="e.g. looking for a technical co-founder, want to practice my pitch…"
                    rows={2}
                    style={{
                      width: "100%",
                      border: "1px solid var(--line)",
                      background: "var(--paper)",
                      padding: "10px 12px",
                      fontSize: 14,
                      fontFamily: "inherit",
                      color: "var(--ink)",
                      resize: "vertical",
                      outline: "none",
                      boxSizing: "border-box",
                    }}
                  />
                </div>
              </>
            ) : (
              /* Results state */
              <div style={{ padding: "16px 0" }}>
                <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                  {recommendations.length > 0
                    ? recommendations.map(ev => <EventCard key={ev.id} ev={ev} />)
                    : (
                      <div style={{ fontSize: 14, color: "var(--muted)", padding: "20px 0" }}>
                        No strong matches found — try broadening your answers.
                      </div>
                    )
                  }
                </div>
                {recommendations.length > 0 && (
                  <EmailCapture recommendations={recommendations} />
                )}
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{
            borderTop: "1px solid var(--line-2, var(--line))",
            padding: "14px 28px 20px",
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            flexShrink: 0,
          }}>
            {isQuestionnaire ? (
              <>
                <span style={{ fontSize: 12, color: "var(--muted)" }}>Takes about 20 seconds.</span>
                <button
                  onClick={handleFind}
                  style={{
                    background: "var(--accent-mint)",
                    color: "var(--rdsw-blue-dark)",
                    border: 0,
                    padding: "10px 18px",
                    fontSize: 13,
                    fontWeight: 800,
                    fontFamily: "inherit",
                    cursor: "pointer",
                  }}
                >
                  Find my events →
                </button>
              </>
            ) : (
              <>
                <button
                  onClick={handleBack}
                  style={{
                    background: "none",
                    border: 0,
                    color: "var(--muted)",
                    fontSize: 13,
                    fontFamily: "inherit",
                    cursor: "pointer",
                    padding: "10px 0",
                  }}
                >
                  ‹ Adjust answers
                </button>
                <button
                  onClick={onClose}
                  style={{
                    background: "var(--accent-mint)",
                    color: "var(--rdsw-blue-dark)",
                    border: 0,
                    padding: "10px 18px",
                    fontSize: 13,
                    fontWeight: 800,
                    fontFamily: "inherit",
                    cursor: "pointer",
                  }}
                >
                  Done
                </button>
              </>
            )}
          </div>
        </div>
      </div>
    </>
  )
}
