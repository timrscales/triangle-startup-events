import React, { useState, useEffect } from 'react'
import { createRoot } from 'react-dom/client'
import './styles/colors_and_type.css'
import './styles/app.css'
import TriangleEventsApp from './App.jsx'

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

  return <TriangleEventsApp device={device} cardVariant="standard" />
}

createRoot(document.getElementById('root')).render(<Root />)
