<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  mdiAccount,
  mdiAsterisk,
  mdiAlertCircle,
  mdiCheck,
} from '@mdi/js'

import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox           from '@/components/CardBox.vue'
import FormField         from '@/components/FormField.vue'
import FormControl       from '@/components/FormControl.vue'
import FormCheckRadio    from '@/components/FormCheckRadio.vue'
import BaseButton        from '@/components/BaseButton.vue'
import BaseButtons       from '@/components/BaseButtons.vue'
import LayoutGuest       from '@/layouts/LayoutGuest.vue'

import { useAuth } from '@/stores/auth.js'

/* ────────────────────────── constants ─────────────────────────────── */
const IDENTIFIER_KEY = 'login.identifier'
const REMEMBER_KEY   = 'login.remember'

/* ────────────────────────── form model ─────────────────────────────── */
const form = reactive({
  /** Username *or* e-mail. We still post it as `username` to the API for now. */
  identifier: '',
  password: '',
  remember: false,
})

/* ───────────────────────────── logic ───────────────────────────────── */
const router   = useRouter()
const errorMsg = ref('')
const loading  = ref(false)

const auth = useAuth()

/** Load remembered identifier on mount (if opted-in previously) */
onMounted(() => {
  // If already logged in, bounce to dashboard (nice-to-have; guard also covers this)
  if (auth.isAuthenticated) {
    router.replace('/public/dashboard')
    return
  }

  try {
    const remembered = localStorage.getItem(REMEMBER_KEY)
    if (remembered === '1') {
      form.remember   = true
      form.identifier = localStorage.getItem(IDENTIFIER_KEY) || ''
    }
  } catch (_) { /* ignore storage errors */ }
})

const submit = async () => {
  errorMsg.value = ''
  loading.value  = true
  try {
    // Treat identifier as "username or email" — backend accepts it as `username` field
    await auth.login({ username: form.identifier, password: form.password })

    // remember-me behavior
    try {
      if (form.remember) {
        localStorage.setItem(REMEMBER_KEY, '1')
        localStorage.setItem(IDENTIFIER_KEY, form.identifier)
      } else {
        localStorage.removeItem(REMEMBER_KEY)
        localStorage.removeItem(IDENTIFIER_KEY)
      }
    } catch (_) { /* ignore storage errors */ }

    // ── redirect fixed: go to public dashboard ───────────────
    router.push('/public/dashboard')
  } catch (err) {
    errorMsg.value = err?.message || 'Login failed'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <LayoutGuest>
    <SectionFullScreen v-slot="{ cardClass }" bg="purplePink">
      <CardBox :class="cardClass" is-form @submit.prevent="submit">
        <!-- error banner -->
        <template v-if="errorMsg">
          <div class="mb-4 flex items-center text-sm text-red-600">
            <BaseButton
              :icon="mdiAlertCircle"
              color="danger"
              rounded-full
              small
              class="mr-2 pointer-events-none"
            />
            <span class="break-words">{{ errorMsg }}</span>
          </div>
        </template>

        <!-- IDENTIFIER (username or e-mail) -->
        <FormField label="Username or E-mail">
          <FormControl
            v-model="form.identifier"
            :icon="mdiAccount"
            name="identifier"
            autocomplete="username"
            required
          />
        </FormField>

        <!-- PASSWORD -->
        <FormField label="Password">
          <FormControl
            v-model="form.password"
            :icon="mdiAsterisk"
            type="password"
            name="password"
            autocomplete="current-password"
            required
          />
        </FormField>

        <!-- REMEMBER ME -->
        <FormCheckRadio
          v-model="form.remember"
          name="remember"
          :input-value="true"
          label="Remember me"
          :icon="mdiCheck"
          class="mb-2"
        />

        <!-- buttons -->
        <template #footer>
          <BaseButtons>
            <BaseButton
              type="submit"
              color="info"
              :label="loading ? 'Logging in…' : 'Login'"
              :disabled="loading"
            />
            <BaseButton to="/register" color="info" outline label="Go to register" />
          </BaseButtons>
        </template>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>
