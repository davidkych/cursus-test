// frontend/src/services/codes.js
// Service wrapper for code functions metadata + code generation endpoints.
// - Avoids hardcoding API base (uses VITE_API_BASE if provided).
// - Uses plain fetch for OPEN endpoints (no Authorization header) to avoid
//   credentialed CORS requirements during deployment.
// - Returns parsed JSON or throws Error(message) normalized from backend.

// NOTE: Keep authFetch for endpoints that truly require Authorization (e.g., redeem),
// but use plain fetch for the open generation/list endpoints to prevent CORS issues.

const API_BASE = (import.meta.env.VITE_API_BASE || '').replace(/\/+$/, '')

/* ───────────────────────── helpers ───────────────────────── */
function isoSecondsZ(value) {
  // Normalize any input into ISO UTC with seconds, no milliseconds.
  // If parsing fails, return the original (backend will 422 and bubble nicely).
  try {
    const d = new Date(value)
    if (!isNaN(d.getTime())) return d.toISOString().replace(/\.\d{3}Z$/, 'Z')
  } catch { /* noop */ }
  return value
}

/**
 * Normalize non-2xx responses into thrown Error objects with a useful message.
 * Works with FastAPI ValidationError shapes and generic JSON/text bodies.
 */
async function handleError(res, fallbackMsg) {
  // Try JSON first
  try {
    const body = await res.json()
    const d = body?.detail
    if (typeof d === 'string') throw new Error(d)
    if (Array.isArray(d)) {
      // FastAPI 422: [{loc, msg, type}, ...]
      const msg = d.map(e => (e?.msg || e?.error || JSON.stringify(e))).join(' • ')
      throw new Error(msg)
    }
    if (d && typeof d === 'object') {
      throw new Error(d.msg || d.error || JSON.stringify(d))
    }
    if (body?.message && typeof body.message === 'string') {
      throw new Error(body.message)
    }
  } catch {
    // Fall back to text body
    try {
      const text = await res.text()
      if (text && text.trim()) throw new Error(text.trim())
    } catch { /* ignore */ }
  }
  throw new Error(fallbackMsg)
}

/* ───────────────────────── API ───────────────────────── */

/**
 * Fetch UI-friendly function metadata (OPEN endpoint).
 * Uses plain fetch (no Authorization header).
 * @returns {Promise<Array<{key:string,label:string,description:string}>>}
 */
export async function listFunctions() {
  const res = await fetch(`${API_BASE}/api/auth/codes/functions`, {
    method: 'GET',
    headers: { Accept: 'application/json' },
  })
  if (!res.ok) await handleError(res, 'Failed to load function list')
  return res.json()
}

/**
 * Generate batch one-off codes (OPEN endpoint).
 * Uses plain fetch (no Authorization header).
 * @param {{ function: string, expires_at: string, count: number }} payload
 * @returns {Promise<{ count: number, codes: Array<{code:string,type:string,function:string,expires_at:string,created_at:string}> }>}
 */
export async function generateOneOff(payload) {
  const body = JSON.stringify({
    function: String(payload.function || '').trim(),
    expires_at: isoSecondsZ(payload.expires_at),
    count: Number.isFinite(Number(payload.count)) ? Number(payload.count) : 1,
  })
  const res = await fetch(`${API_BASE}/api/auth/codes/generate/oneoff`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      Accept: 'application/json',
    },
    body,
  })
  if (!res.ok) await handleError(res, 'Failed to generate one-off codes')
  return res.json()
}

/**
 * Generate a reusable code (OPEN endpoint).
 * Uses plain fetch (no Authorization header).
 * @param {{ code: string, function: string, expires_at: string }} payload
 * @returns {Promise<{ code:string,type:string,function:string,expires_at:string,created_at:string }>}
 */
export async function generateReusable(payload) {
  const body = JSON.stringify({
    code: String(payload.code || '').trim(),
    function: String(payload.function || '').trim(),
    expires_at: isoSecondsZ(payload.expires_at),
  })
  const res = await fetch(`${API_BASE}/api/auth/codes/generate/reusable`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      Accept: 'application/json',
    },
    body,
  })
  if (!res.ok) await handleError(res, 'Failed to generate reusable code')
  return res.json()
}

/**
 * Generate a single-use code (OPEN endpoint).
 * Uses plain fetch (no Authorization header).
 * @param {{ code: string, function: string, expires_at: string }} payload
 * @returns {Promise<{ code:string,type:string,function:string,expires_at:string,created_at:string }>}
 */
export async function generateSingle(payload) {
  const body = JSON.stringify({
    code: String(payload.code || '').trim(),
    function: String(payload.function || '').trim(),
    expires_at: isoSecondsZ(payload.expires_at),
  })
  const res = await fetch(`${API_BASE}/api/auth/codes/generate/single`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json; charset=utf-8',
      Accept: 'application/json',
    },
    body,
  })
  if (!res.ok) await handleError(res, 'Failed to generate single-use code')
  return res.json()
}
