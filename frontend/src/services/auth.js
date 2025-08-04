// frontend/src/services/auth.js
// Lightweight helper for the /api/auth/* endpoints

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''

function handleError(res, fallbackMsg) {
  return res
    .json()
    .catch(() => ({}))
    .then((body) => {
      throw new Error(body.detail || fallbackMsg)
    })
}

export async function register(payload) {
  const res = await fetch(`${API_BASE}/api/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Registration failed')
  return res.json()
}

export async function login(payload) {
  const res = await fetch(`${API_BASE}/api/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Login failed')
  return res.json()
}
