import React from 'react'
import ReactDOM from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'
import App from './App'

const BASE = '/app/interview-agent/'

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <BrowserRouter basename={BASE}>
      <App />
    </BrowserRouter>
  </React.StrictMode>,
)
