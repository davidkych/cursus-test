<script setup>
/* ──────────────────────────────────────────────────────────────
   Login page (guest layout)

   • Saves JWT via the Pinia auth store.
   • “Remember” checkbox controls persistence:
       ✓ ON  → token saved in localStorage  (default)
       ☐ OFF → token kept only in-memory – cleared on reload
   • Redirects to /public/dashboard after success.
   ──────────────────────────────────────────────────────────── */
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { mdiAccount, mdiAsterisk, mdiAlertCircle } from '@mdi/js'

import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox           from '@/components/CardBox.vue'
import FormCheckRadio    from '@/components/FormCheckRadio.vue'
import FormField         from '@/components/FormField.vue'
import FormControl       from '@/components/FormControl.vue'
import BaseButton        from '@/components/BaseButton.vue'
import BaseButtons       from '@/components/BaseButtons.vue'
import LayoutGuest       from '@/layouts/LayoutGuest.vue'

import { login as apiLogin }  from '@/services/auth.js'
import { useAuthStore }       from '@/stores/auth.js'        // ← NEW

/* ─────────────── form state ─────────────────────────────── */
const form = reactive({
  login:    '',
  pass:     '',
  remember: true,
})

/* ─────────────── logic ──────────────────────────────────── */
const router   = useRouter()
const auth     = useAuthStore()        // Pinia store
const errorMsg = ref('')
const loading  = ref(false)

const submit = async () => {
  errorMsg.value = ''
  loading.value  = true
  try {
    /* 1. Authenticate */
    const { access_token } = await apiLogin({
      username: form.login,
      password: form.pass,
    })

    /* 2. Persist (or not) according to “Remember” */
    await auth.setToken(access_token)      // hydrates profile + saves to localStorage
    if (!form.remember && typeof localStorage !== 'undefined') {
      localStorage.removeItem('access_token')   // keep token only in-memory
    }

    /* 3. Go to the main dashboard */
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
        <!-- ─── error banner ─── -->
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

        <!-- LOGIN -->
        <FormField label="Login" help="Please enter your username">
          <FormControl
            v-model="form.login"
            :icon="mdiAccount"
            name="login"
            autocomplete="username"
            required
          />
        </FormField>

        <!-- PASSWORD -->
        <FormField label="Password" help="Please enter your password">
          <FormControl
            v-model="form.pass"
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
          label="Remember me"
          :input-value="true"
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
            <BaseButton to="/public/dashboard" color="info" outline label="Back" />
          </BaseButtons>
        </template>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>
