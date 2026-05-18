import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/colors_and_type.css'
import './styles/app.css'
// TODO: import TriangleEventsApp from './App.jsx' once port is complete

function Root() {
  const [device, setDevice] = useState(
    () => window.matchMedia('(max-width: 720px)').matches ? 'mobile' : 'desktop'
  )

  useEffect(() => {
    const mq = window.matchMedia('(max-width: 720px)')
    const handler = (e) => setDevice(e.matches ? 'mobile' : 'desktop')
    mq.addEventListener('change', handler)
    return () => mq.removeEventListener('change', handler)
  }, [])

  return <div style={{ padding: 40, fontFamily: 'sans-serif' }}>Port in progress — components not yet wired up.</div>
}

createRoot(document.getElementById('root')).render(<Root />)
