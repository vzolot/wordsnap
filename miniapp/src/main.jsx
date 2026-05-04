import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'
import { initSentry, SentryErrorBoundary } from './sentry.js'

initSentry();

const Fallback = () => (
  <div style={{ padding: 32, textAlign: 'center', color: '#666' }}>
    <h2>Something went wrong</h2>
    <p>Reload the page to continue.</p>
  </div>
);

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <SentryErrorBoundary fallback={<Fallback />}>
      <App />
    </SentryErrorBoundary>
  </StrictMode>,
)
