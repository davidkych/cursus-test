import { defineStore } from 'pinia'
import { ref } from 'vue'

const STORAGE_KEY = 'darkMode'       // ‼ single source-of-truth

export const useDarkModeStore = defineStore('darkMode', () => {
  const isEnabled = ref(false)

  /* ───────────────────────── initial load ────────────────────────── */
  if (typeof window !== 'undefined') {
    try {
      const saved = localStorage.getItem(STORAGE_KEY)
      if (saved === '1' || saved === '0') {
        isEnabled.value = saved === '1'
        applyDomClasses(isEnabled.value)
      }
    } catch (_) {
      /* localStorage might be disabled (private-mode etc.) – ignore */
    }
  }

  /* ───────────────────── helper to toggle classes ────────────────── */
  function applyDomClasses(enabled) {
    if (typeof document === 'undefined') return

    document.body.classList[enabled ? 'add' : 'remove']('dark-scrollbars')

    document.documentElement.classList[enabled ? 'add' : 'remove'](
      'dark',
      'dark-scrollbars-compat',
    )
  }

  /* ─────────────────────────── public API ────────────────────────── */
  function set(payload = null) {
    // explicit value or toggle
    isEnabled.value = payload !== null ? payload : !isEnabled.value
    applyDomClasses(isEnabled.value)

    // persist for future tabs / windows
    try {
      localStorage.setItem(STORAGE_KEY, isEnabled.value ? '1' : '0')
    } catch (_) {
      /* ignore */
    }
  }

  return {
    isEnabled,
    set,
  }
})
