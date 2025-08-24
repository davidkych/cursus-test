<!-- frontend/src/viewsAdmin/UsersView.vue -->
<script setup>
import { ref, onMounted } from 'vue'
import { mdiTableBorder, mdiGithub } from '@mdi/js'

import LayoutAuthenticated from '@/layouts/LayoutAuthenticated.vue'
import SectionMain from '@/components/SectionMain.vue'
import SectionTitleLineWithButton from '@/components/SectionTitleLineWithButton.vue'
import CardBox from '@/components/CardBox.vue'
import CardBoxComponentEmpty from '@/components/CardBoxComponentEmpty.vue'
import BaseButton from '@/components/BaseButton.vue'
import NotificationBar from '@/components/NotificationBar.vue'

import TableUsers from '@/components/TableUsers.vue'
import { listUsers } from '@/services/adminUsers.js'

/* ───────────────────────── state ───────────────────────── */
const loading = ref(false)
const errorMsg = ref('')

const page = ref(1)
const pageSize = 20 // fixed by spec
const total = ref(0)
const totalPages = ref(1)
const hasPrev = ref(false)
const hasNext = ref(false)

const rows = ref([])

/* ───────────────────────── data load ───────────────────── */
async function load() {
  loading.value = true
  errorMsg.value = ''
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
          />
        </template>
        <template v-else>
          <CardBoxComponentEmpty />
        </template>
      </CardBox>
    </SectionMain>
  </LayoutAuthenticated>
</template>
