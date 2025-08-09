<!-- frontend/src/components/UserCard.vue -->
<script setup>
import { computed, ref } from 'vue'
import { useMainStore } from '@/stores/main'
import { useAuth } from '@/stores/auth.js'                 /* ⟨NEW⟩ */
import { mdiCheckDecagram } from '@mdi/js'
import BaseLevel from '@/components/BaseLevel.vue'
import UserAvatarCurrentUser from '@/components/UserAvatarCurrentUser.vue'
import CardBox from '@/components/CardBox.vue'
import FormCheckRadio from '@/components/FormCheckRadio.vue'
import PillTag from '@/components/PillTag.vue'

const mainStore = useMainStore()
const userName = computed(() => mainStore.userName)

const userSwitchVal = ref(false)

/* ────────────────────── Login telemetry (same source as ProfileView) ─────── */
const auth = useAuth()
const lc = computed(() => auth.user?.login_context || null)

const ip = computed(() => lc.value?.ip || '')
const lastLoginIso = computed(() => lc.value?.last_login_utc || '')

function timeAgo(iso) {
  if (!iso) return ''
  const then = new Date(iso).getTime()
  const now = Date.now()
  const sec = Math.max(0, Math.floor((now - then) / 1000))
  if (sec < 60) return `${sec}s`
  const min = Math.floor(sec / 60)
  if (min < 60) return `${min} mins`
  const hr = Math.floor(min / 60)
  if (hr < 24) return `${hr} hrs`
  const d = Math.floor(hr / 24)
  return `${d} days`
}
const lastLoginAgo = computed(() => timeAgo(lastLoginIso.value))
</script>

<template>
  <CardBox>
    <BaseLevel type="justify-around lg:justify-center">
      <UserAvatarCurrentUser class="lg:mx-12" />
      <div class="space-y-3 text-center md:text-left lg:mx-12">
        <div class="flex justify-center md:block">
          <FormCheckRadio
            v-model="userSwitchVal"
            name="notifications-switch"
            type="switch"
            label="Notifications"
            :input-value="true"
          />
        </div>
        <h1 class="text-2xl">
          Howdy, <b>{{ userName }}</b>!
        </h1>

        <!-- ⟨UPDATED⟩ use the same telemetry as the details panel -->
        <p v-if="lastLoginIso || ip">
          Last login
          <b>{{ lastLoginAgo || '—' }}</b>
          <template v-if="ip"> from <b>{{ ip }}</b></template>
        </p>

        <div class="flex justify-center md:block">
          <PillTag label="Verified" color="info" :icon="mdiCheckDecagram" />
        </div>
      </div>
    </BaseLevel>
  </CardBox>
</template>
