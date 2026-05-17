import React, { useState } from 'react'
import { X, Check } from '../icons.jsx'

const INITIAL = {
  name: '',
  date: '',
  start_time: '',
  location: '',
  url: '',
  description: '',
  organizer: '',
}

export default function SubmitModal({ onClose }) {
  const [form, setForm] = useState(INITIAL)
  const [errors, setErrors] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [success, setSuccess] = useState(false)

  function update(key, val) {
    setForm(f => ({ ...f, [key]: val }))
    if (errors[key]) setErrors(e => ({ ...e, [key]: null }))
  }

  function validate() {
    const errs = {}
    if (!form.name.trim()) errs.name = 'Event name is required'
    if (!form.date) errs.date = 'Date is required'
    if (!form.url.trim()) errs.url = 'Event URL is required'
    return errs
  }

  async function submit(e) {
    e.preventDefault()
    const errs = validate()
    if (Object.keys(errs).length) { setErrors(errs); return }
    setSubmitting(true)
    // In production this would POST to an API or Airtable form.
    // For now, simulate a network delay.
    await new Promise(r => setTimeout(r, 800))
    setSubmitting(false)
    setSuccess(true)
  }

  if (success) {
    return (
      <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
        <div className="modal">
          <div className="modal__success">
            <div className="modal__success-icon">
              <Check size={24} />
            </div>
            <h3>Thanks for the submission!</h3>
            <p>We'll review your event and add it to the calendar if it's a good fit for the Triangle startup community.</p>
            <button className="modal__submit" style={{ marginTop: 8 }} onClick={onClose}>
              Done
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="modal-overlay" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Submit an event">
        <div className="modal__header">
          <h2 className="modal__title">Submit an Event</h2>
          <button className="modal__close" onClick={onClose} aria-label="Close">
            <X />
          </button>
        </div>

        <form onSubmit={submit}>
          <div className="modal__body">
            <div className="form-group">
              <label className="form-label">Event Name *</label>
              <input
                className="form-input"
                value={form.name}
                onChange={e => update('name', e.target.value)}
                placeholder="e.g. Triangle Founders Happy Hour"
              />
              {errors.name && <span className="form-error">{errors.name}</span>}
            </div>

            <div className="form-group">
              <label className="form-label">Date *</label>
              <input
                className="form-input"
                type="date"
                value={form.date}
                onChange={e => update('date', e.target.value)}
              />
              {errors.date && <span className="form-error">{errors.date}</span>}
            </div>

            <div className="form-group">
              <label className="form-label">Start Time</label>
              <input
                className="form-input"
                type="time"
                value={form.start_time}
                onChange={e => update('start_time', e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Location</label>
              <input
                className="form-input"
                value={form.location}
                onChange={e => update('location', e.target.value)}
                placeholder="Venue name and city"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Organizer</label>
              <input
                className="form-input"
                value={form.organizer}
                onChange={e => update('organizer', e.target.value)}
                placeholder="Who's running this event?"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Event URL *</label>
              <input
                className="form-input"
                type="url"
                value={form.url}
                onChange={e => update('url', e.target.value)}
                placeholder="https://..."
              />
              {errors.url && <span className="form-error">{errors.url}</span>}
            </div>

            <div className="form-group">
              <label className="form-label">Description</label>
              <textarea
                className="form-textarea"
                value={form.description}
                onChange={e => update('description', e.target.value)}
                placeholder="What will attendees do or learn?"
              />
            </div>
          </div>

          <div className="modal__footer">
            <button type="button" className="modal__cancel" onClick={onClose}>
              Cancel
            </button>
            <button type="submit" className="modal__submit" disabled={submitting}>
              {submitting ? 'Submitting...' : 'Submit Event'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
