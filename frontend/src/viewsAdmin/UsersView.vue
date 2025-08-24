<!-- frontend/src/viewsAdmin/UsersView.vue -->
<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useUserMode } from '@/stores/userMode.js'
import { useAuth } from '@/stores/auth.js'
import { mdiTableBorder, mdiGithub } from '@mdi/js'

import LayoutAuthenticated from '@/layouts/LayoutAuthenticated.vue'
import SectionMain from '@/components/SectionMain.vue'
import SectionTitleLineWithButton from '@/components/SectionTitleLineWithButton.vue'
import CardBox from '@/components/CardBox.vue'
import CardBoxComponentEmpty from '@/components/CardBoxComponentEmpty.vue'
import BaseButton from '@/components/BaseButton.vue'
import NotificationBar from '@/components/NotificationBar.vue'

import TableUsers from '@/components/TableUsers.vue'
import { listUsers, deleteUser, impersonate } from '@/services/adminUsers.js'

/* ───────────────────────── state ───────────────────────── */
const loading = ref(false)
const errorMsg = ref('')
const successMsg = ref('')

const page = ref(1)
const pageSize = 20 // fixed by spec
const total = ref(0)
const totalPages = ref(1)
const hasPrev = ref(false)
const hasNext = ref(false)

const rows = ref([])

/* stores & router */
const router = useRouter()
const userMode = useUserMode()
const auth = useAuth()

/* ───────────────────────── data load ───────────────────── */
async function load() {
  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    const res = await listUsers({ page: page.value, pageSize, includeAvatars: true })
    page.value       = res.page
    total.value      = res.total
    totalPages.value = res.total_pages
    hasPrev.value    = res.has_prev
    hasNext.value    = res.has_next
    rows.value       = Array.isArray(res.items) ? res.items : []
  } catch (err) {
    errorMsg.value = err?.message || 'Failed to load users'
    rows.value = []
  } finally {
    loading.value = false
  }
}

function onChangePage(newPage) {
  const p = Number(newPage) || 1
  if (p === page.value) return
  page.value = Math.max(1, Math.min(p, totalPages.value || 1))
  load()
}

/* ───────────────────────── delete handler ───────────────────── */
async function onRequestDelete(row) {
  if (!row || !row.username) return
  const ok = window.confirm(`Delete user "${row.username}"?\nThis action cannot be undone.`)
  if (!ok) return

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    await deleteUser({ username: row.username, purgeAvatar: true, allowSelf: false })
    successMsg.value = `Deleted "${row.username}".`
    // If it was the last row on the page, step back a page (if possible)
    if (rows.value.length <= 1 && page.value > 1) {
      page.value = page.value - 1
    }
    await load()
  } catch (err) {
    errorMsg.value = err?.message || 'Failed to delete user'
  } finally {
    loading.value = false
  }
}

/* ───────────────────────── impersonate handler ───────────────────── */
async function onRequestImpersonate(row) {
  if (!row || !row.username) return
  const target = row.username

  loading.value = true
  errorMsg.value = ''
  successMsg.value = ''
  try {
    // Call admin API to mint a token for the target user
    const res = await impersonate({ username: target }) // { access_token, token_type }
    const token = res?.access_token
    if (!token) throw new Error('No token returned')

    // Persist token for router guard + set into auth store
    try { localStorage.setItem('auth.token', token) } catch { /* ignore */ }
    auth.token = token

    // Refresh current user profile under the new identity
    await auth.refresh()

    // Switch UI to public mode and navigate to public dashboard
    userMode.setPublic()
    successMsg.value = `Now impersonating "${target}". Redirecting…`
    await router.push('/public/dashboard')
  } catch (err) {
    errorMsg.value = err?.message || 'Failed to impersonate user'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <LayoutAuthenticated>
    <SectionMain>
      <SectionTitleLineWithButton :icon="mdiTableBorder" title="Users" main>
        <BaseButton
          href="https://github.com/justboil/admin-one-vue-tailwind"
          target="_blank"
          :icon="mdiGithub"
          label="Star on GitHub"
          color="contrast"
          rounded-full
          small
        />
      </SectionTitleLineWithButton>

      <NotificationBar v-if="errorMsg" color="danger">
        {{ errorMsg }}
      </NotificationBar>
      <NotificationBar v-if="successMsg" color="info">
        {{ successMsg }}
      </NotificationBar>

      <CardBox class="mb-6" has-table>
        <template v-if="rows.length">
          <TableUsers
            :rows="rows"
            :page="page"
            :total-pages="totalPages"
            :has-prev="hasPrev"
            :has-next="hasNext"
            :loading="loading"
            @change-page="onChangePage"
            @request-delete="onRequestDelete"
            @request-impersonate="onRequestImpersonate"
          />
        </template>
        <template v-else>
          <CardBoxComponentEmpty />
        </template>
      </CardBox>
    </SectionMain>
  </LayoutAuthenticated>
</template>
