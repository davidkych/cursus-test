// frontend/src/services/adminUsers.js
// Read-only Admin Users API client + delete user + impersonate (admin-only).
// Uses existing authFetch (injects Bearer token & clears token on 401).
//
// listUsers({ page=1, pageSize=20, includeAvatars=true })
//   → { page, page_size, total, total_pages, has_prev, has_next, items: [...] }
//
// deleteUser({ username, purgeAvatar=true, allowSelf=false })
//   → { status: 'ok', username, was_present, purged_avatar }
//
// impersonate({ username, ttlMinutes })
//   → { access_token, token_type: 'bearer', for_username, actor, expires_in }

import { authFetch } from '@/services/auth.js'

// Prefer an environment variable; fall back to same-origin
const API_BASE = import.meta.env.VITE_API_BASE || ''

/**
 * Lightweight response error normalizer mirroring our FastAPI patterns.
 * Converts a non-2xx Response into a thrown Error with a reasonable message.
 */
async function throwIfNotOk(res, fallbackMsg) {
  if (res.ok) return res
  try {
    const body = await res.json()
    const d = body?.detail
    let msg = fallbackMsg

    if (typeof d === 'string') {
      msg = d
    } else if (Array.isArray(d)) {
      msg = d
        .map((e) => e?.msg || (typeof e === 'string' ? e : JSON.stringify(e)))
        .join(' • ')
    } else if (d && typeof d === 'object') {
      msg = d.msg || d.error || JSON.stringify(d)
    } else if (body?.message && typeof body.message === 'string') {
      msg = body.message
    }

    throw new Error(msg)
  } catch (_) {
    // Body not JSON or parsing failed
    throw new Error(fallbackMsg)
  }
}

/**
 * Fetch a page of users for the admin panel.
 * Server guarantees username ASC ordering and enforces page size cap (20).
 *
 * @param {Object} opts
 * @param {number} [opts.page=1]             1-based page index (min 1)
 * @param {number} [opts.pageSize=20]        desired page size (server caps at 20)
 * @param {boolean} [opts.includeAvatars=true] include short-lived SAS for custom avatars
 * @returns {Promise<{
 *   page: number,
 *   page_size: number,
 *   total: number,
 *   total_pages: number,
 *   has_prev: boolean,
 *   has_next: boolean,
 *   items: Array<{
 *     id: string,
 *     username: string,
 *     email?: string,
 *     gender?: 'male'|'female'|null,
 *     dob?: string|null,
 *     country?: string|null,
 *     profile_pic_id?: number,
 *     profile_pic_type?: 'default'|'custom',
 *     avatar_url?: string|null
 *   }>
 * }>}
 */
export async function listUsers({ page = 1, pageSize = 20, includeAvatars = true } = {}) {
  // Sanitize inputs without hard-coding server policy
  const p = Math.max(1, Number.isFinite(page) ? Math.trunc(page) : 1)
  const ps = Math.max(1, Number.isFinite(pageSize) ? Math.trunc(pageSize) : 20)
  const incAv = includeAvatars ? 1 : 0

  const url = new URL(`${API_BASE}/api/auth/admin/users`, window.location.origin)
  url.searchParams.set('page', String(p))
  url.searchParams.set('page_size', String(ps))
  url.searchParams.set('include_avatars', String(incAv))
  url.searchParams.set('include_total', '1')

  const res = await authFetch(url.toString(), { method: 'GET' })
  await throwIfNotOk(res, 'Failed to load users')
  return res.json()
}

/**
 * Delete a user account by username (admin-only).
 * - Blocks self-deletion by default (server returns 403 unless allowSelf=true).
 * - Purges custom avatar blob by default (purgeAvatar=true).
 *
 * @param {Object} opts
 * @param {string} opts.username
 * @param {boolean} [opts.purgeAvatar=true]
 * @param {boolean} [opts.allowSelf=false]
 * @returns {Promise<{
 *   status: 'ok',
 *   username: string,
 *   was_present: boolean,
 *   purged_avatar: boolean
 * }>}
 */
export async function deleteUser({ username, purgeAvatar = true, allowSelf = false } = {}) {
  if (!username || typeof username !== 'string') {
    throw new Error('username is required')
  }

  const url = new URL(
    `${API_BASE}/api/auth/admin/users/${encodeURIComponent(username)}`,
    window.location.origin,
  )
  url.searchParams.set('purge_avatar', purgeAvatar ? '1' : '0')
  url.searchParams.set('allow_self', allowSelf ? '1' : '0')

  const res = await authFetch(url.toString(), { method: 'DELETE' })
  await throwIfNotOk(res, 'Failed to delete user')
  return res.json()
}

/**
 * Request an impersonation token for a target user (admin-only).
 * The returned token can be fed to the auth store for a seamless switch.
 *
 * @param {Object} opts
 * @param {string} opts.username                   target username
 * @param {number} [opts.ttlMinutes]               optional desired TTL; server clamps
 * @returns {Promise<{
 *   access_token: string,
 *   token_type: 'bearer',
 *   for_username: string,
 *   actor: string,
 *   expires_in: number
 * }>}
 */
export async function impersonate({ username, ttlMinutes } = {}) {
  if (!username || typeof username !== 'string') {
    throw new Error('username is required')
  }

  const payload = { username }
  if (Number.isFinite(ttlMinutes)) {
    payload.ttl_minutes = Math.trunc(ttlMinutes)
  }

  const res = await authFetch(`${API_BASE}/api/auth/admin/impersonate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  await throwIfNotOk(res, 'Failed to impersonate user')
  return res.json()
}
