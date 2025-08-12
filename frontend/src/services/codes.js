// frontend/src/services/codes.js
// Service wrapper for code functions metadata + code generation endpoints.
// - Avoids hardcoding API base (uses VITE_API_BASE if provided).
// - Uses authFetch so bearer token (if present) is included automatically.
// - Returns parsed JSON or throws Error(message) normalized from backend.

import { authFetch } from '@/services/auth.js'

const API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Normalize non-2xx responses into thrown Error objects with a useful message.
 * Mirrors the approach used in services/auth.js without importing internals.
 */
async function handleError(res, fallbackMsg) {
  try {
    const body = await res.json()
    const d = body?.detail
    if (typeof d === 'string') throw new Error(d)
    if (Array.isArray(d)) {
      throw new Error(
        d.map((e) => e?.msg || (typeof e === 'string' ? e : JSON.stringify(e))).join(' • '),
      )
    }
    if (d && typeof d === 'object') throw new Error(d.msg || d.error || JSON.stringify(d))
    if (body?.message && typeof body.message === 'string') throw new Error(body.message)
  } catch {
    /* ignore json parse errors */
  }
  throw new Error(fallbackMsg)
}

/**
 * Fetch UI-friendly function metadata (OPEN endpoint).
 * @returns {Promise<Array<{key:string,label:string,description:string}>>}
 */
export async function listFunctions() {
  const res = await authFetch(`${API_BASE}/api/auth/codes/functions`, { method: 'GET' })
  if (!res.ok) await handleError(res, 'Failed to load function list')
  return res.json()
}

/**
 * Generate batch one-off codes.
 * @param {{ function: string, expires_at: string, count: number }} payload
 * @returns {Promise<{ count: number, codes: Array<{code:string,type:string,function:string,expires_at:string,created_at:string}> }>}
 */
export async function generateOneOff(payload) {
  const res = await authFetch(`${API_BASE}/api/auth/codes/generate/oneoff`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Failed to generate one-off codes')
  return res.json()
}

/**
 * Generate a reusable code.
 * @param {{ code: string, function: string, expires_at: string }} payload
 * @returns {Promise<{ code:string,type:string,function:string,expires_at:string,created_at:string }>}
 */
export async function generateReusable(payload) {
  const res = await authFetch(`${API_BASE}/api/auth/codes/generate/reusable`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Failed to generate reusable code')
  return res.json()
}

/**
 * Generate a single-use code.
 * @param {{ code: string, function: string, expires_at: string }} payload
 * @returns {Promise<{ code:string,type:string,function:string,expires_at:string,created_at:string }>}
 */
export async function generateSingle(payload) {
  const res = await authFetch(`${API_BASE}/api/auth/codes/generate/single`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) await handleError(res, 'Failed to generate single-use code')
  return res.json()
}
