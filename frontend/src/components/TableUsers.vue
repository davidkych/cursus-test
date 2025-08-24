<!-- frontend/src/components/TableUsers.vue -->
<script setup>
import { computed } from 'vue'
import { mdiEye, mdiTrashCan } from '@mdi/js'
import BaseButton from '@/components/BaseButton.vue'
import BaseIcon from '@/components/BaseIcon.vue'
import TableCheckboxCell from '@/components/TableCheckboxCell.vue'

/**
 * Props
 * - rows: array of user items (see admin_users API)
 * - page: current page (1-based)
 * - totalPages: total pages
 * - hasPrev / hasNext: booleans
 * - loading: boolean
 */
const props = defineProps({
  rows: { type: Array, default: () => [] },
  page: { type: Number, default: 1 },
  totalPages: { type: Number, default: 1 },
  hasPrev: { type: Boolean, default: false },
  hasNext: { type: Boolean, default: false },
  loading: { type: Boolean, default: false },
})

const emit = defineEmits(['change-page', 'request-delete'])

/* ───────────────────────── Avatar resolver ─────────────────────────
   Prefer SAS when custom; otherwise map built-in /assets/propics/*.png */
const avatarFiles = import.meta.glob('@/assets/propics/*.png', {
  eager: true,
  import: 'default',
})
const avatarMap = Object.entries(avatarFiles).reduce((acc, [path, url]) => {
  const m = path.match(/\/(\d+)\.png$/)
  if (m) acc[Number(m[1])] = url
  return acc
}, /** @type {Record<number, string>} */ ({}))

const fallbackAvatar = computed(() => {
  const ids = Object.keys(avatarMap).map(Number).sort((a, b) => a - b)
  return ids.length ? avatarMap[ids[0]] : ''
})

function resolveAvatarUrl(row) {
  if (row?.profile_pic_type === 'custom' && row?.avatar_url) {
    return row.avatar_url
  }
  const id = Number(row?.profile_pic_id) || 1
  return avatarMap[id] || fallbackAvatar.value
}

/* ───────────────────────── Utilities ───────────────────────── */
function safe(val, fallback = '—') {
  if (val === null || val === undefined || val === '') return fallback
  return String(val)
}

function calcAge(dobIso) {
  if (!dobIso) return ''
  try {
    const d = new Date(dobIso)
    if (Number.isNaN(d.getTime())) return ''
    const now = new Date()
    let age = now.getFullYear() - d.getFullYear()
    const m = now.getMonth() - d.getMonth()
    if (m < 0 || (m === 0 && now.getDate() < d.getDate())) {
      age--
    }
    return String(age)
  } catch {
    return ''
  }
}

/* ───────────────────────── Pagination model ─────────────────────────
   Produce a compact page list like: [1, 2, '…', 9, 10, 11, '…', 20] */
const pageList = computed(() => {
  const total = Math.max(1, props.totalPages || 1)
  const cur = Math.min(Math.max(1, props.page || 1), total)
  const span = 1 // neighbors on each side

  const pages = new Set([1, total, cur])
  for (let i = 1; i <= span; i++) {
    pages.add(cur - i)
    pages.add(cur + i)
  }
  // Always include first 2 and last 2 for nicer feel (bounded)
  pages.add(2)
  pages.add(total - 1)

  const arr = [...pages].filter((p) => p >= 1 && p <= total).sort((a, b) => a - b)

  // Insert ellipses where gaps > 1
  const out = []
  for (let i = 0; i < arr.length; i++) {
    out.push(arr[i])
    if (i < arr.length - 1 && arr[i + 1] - arr[i] > 1) out.push('…')
  }
  return out
})

/* ───────────────────────── Handlers ───────────────────────── */
function goFirst() {
  if (props.page > 1 && !props.loading) emit('change-page', 1)
}
function goPrev() {
  if (props.hasPrev && !props.loading) emit('change-page', props.page - 1)
}
function goNext() {
  if (props.hasNext && !props.loading) emit('change-page', props.page + 1)
}
function goLast() {
  if (props.page < props.totalPages && !props.loading) emit('change-page', props.totalPages)
}
function goPage(p) {
  if (typeof p === 'number' && p >= 1 && p <= props.totalPages && p !== props.page && !props.loading) {
    emit('change-page', p)
  }
}
</script>

<template>
  <div class="overflow-x-auto">
    <table class="w-full whitespace-nowrap">
      <thead>
        <tr>
          <th class="px-4 py-3 w-10">
            <!-- header checkbox placeholder; no select-all for now -->
            <span class="sr-only">Select</span>
          </th>
          <th class="px-4 py-3">Avatar</th>
          <th class="px-4 py-3 text-left">Username</th>
          <th class="px-4 py-3 text-left">Gender</th>
          <th class="px-4 py-3 text-left">Date of Birth (Age)</th>
          <th class="px-4 py-3 text-left">Country</th>
          <th class="px-4 py-3 text-left">Email</th>
          <th class="px-4 py-3 text-right">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="row in rows"
          :key="row.id || row.username"
          class="border-t border-gray-100 dark:border-slate-700"
        >
          <!-- checkbox (functionless) -->
          <TableCheckboxCell />

          <!-- avatar -->
          <td class="px-4 py-3">
            <div class="flex items-center">
              <img
                :src="resolveAvatarUrl(row)"
                alt="avatar"
                class="w-8 h-8 rounded-full object-cover"
                loading="lazy"
              />
            </div>
          </td>

          <!-- username -->
          <td class="px-4 py-3 font-medium text-gray-800 dark:text-gray-100">
            {{ safe(row.username) }}
          </td>

          <!-- gender -->
          <td class="px-4 py-3">
            {{ row?.gender === 'male' || row?.gender === 'female' ? row.gender : '—' }}
          </td>

          <!-- dob (age) -->
          <td class="px-4 py-3">
            <template v-if="row?.dob">
              {{ row.dob }}<span v-if="calcAge(row.dob)"> ({{ calcAge(row.dob) }})</span>
            </template>
            <template v-else>—</template>
          </td>

          <!-- country -->
          <td class="px-4 py-3">
            {{ safe(row?.country) }}
          </td>

          <!-- email -->
          <td class="px-4 py-3">
            <a v-if="row?.email" class="text-blue-600 hover:underline" :href="`mailto:${row.email}`">
              {{ row.email }}
            </a>
            <span v-else>—</span>
          </td>

          <!-- actions (eye preserved; trash now emits request-delete) -->
          <td class="px-4 py-3 text-right">
            <div class="inline-flex space-x-2">
              <BaseButton :icon="mdiEye" color="info" small outline />
              <BaseButton
                :icon="mdiTrashCan"
                color="danger"
                small
                outline
                :disabled="loading"
                @click="$emit('request-delete', row)"
                title="Delete account"
              />
            </div>
          </td>
        </tr>

        <!-- pagination row (last row) -->
        <tr class="border-t border-gray-100 dark:border-slate-700">
          <td :colspan="8" class="px-4 py-3">
            <div class="flex flex-wrap items-center justify-center gap-2">
              <button
                class="px-3 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 disabled:opacity-50"
                :disabled="!hasPrev || loading"
                @click="goFirst"
                title="First"
              >
                « First
              </button>
              <button
                class="px-3 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 disabled:opacity-50"
                :disabled="!hasPrev || loading"
                @click="goPrev"
                title="Previous"
              >
                ‹ Prev
              </button>

              <button
                v-for="p in pageList"
                :key="'p-'+p"
                class="px-3 py-1 text-sm rounded border border-gray-300 dark:border-slate-600"
                :class="[
                  p === page ? 'bg-gray-900 text-white dark:bg-slate-200 dark:text-slate-900' : 'bg-transparent',
                  p === '…' ? 'pointer-events-none opacity-60' : ''
                ]"
                :disabled="p === '…' || loading"
                @click="goPage(p)"
              >
                {{ p }}
              </button>

              <button
                class="px-3 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 disabled:opacity-50"
                :disabled="!hasNext || loading"
                @click="goNext"
                title="Next"
              >
                Next ›
              </button>
              <button
                class="px-3 py-1 text-sm rounded border border-gray-300 dark:border-slate-600 disabled:opacity-50"
                :disabled="page >= totalPages || loading"
                @click="goLast"
                title="Last"
              >
                Last »
              </button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
