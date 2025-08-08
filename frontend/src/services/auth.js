// frontend/src/services/auth.js
// Lightweight helper for the /api/auth/* endpoints

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Convert non-2xx fetch responses into thrown Error objects,
 * extracting FastAPI-style detail messages when present.
 */
function handleError(res, fallbackMsg) {
  return res
    .json()
    .catch(() => ({}))
    .then((body) => {
      const d = body?.detail
      let msg = fallbackMsg

      if (typeof d === 'string') {
        msg = d
      } else if (Array.isArray(d)) {
        // FastAPI validation errors
        msg = d
          .map((e) => e?.msg || (typeof e === 'string' ? e : JSON.stringify(e)))
          .join(' • ')
      } else if (d && typeof d === 'object') {
        msg = d.msg || d.error || JSON.stringify(d)
      } else if (body?.message && typeof body.message === 'string') {
        msg = body.message
      }

      throw new Error(msg)
    })
}

/**
 * Register a new user.
 *
 * Expected payload shape (all keys optional except the originals):
 * {
 *   username:           string,
 *   email:              string,
 *   password:           string,
 *   // optional fields we now pass through from the Register form:
 *   gender:             'male'|'female',
 *   dob:                'YYYY-MM-DD',
 *   country:            string,
 *   profile_pic_id:     number,
 *   profile_pic_type:   'default'|'custom',
 *   accepted_terms:     boolean
 * }
 */
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
