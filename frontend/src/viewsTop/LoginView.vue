<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  mdiAccount,
  mdiAsterisk,
  mdiAlertCircle,
} from '@mdi/js'

import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox           from '@/components/CardBox.vue'
import FormField         from '@/components/FormField.vue'
import FormControl       from '@/components/FormControl.vue'
import BaseButton        from '@/components/BaseButton.vue'
import BaseButtons       from '@/components/BaseButtons.vue'
import LayoutGuest       from '@/layouts/LayoutGuest.vue'

import { login as apiLogin } from '@/services/auth.js'

/* ────────────────────────── form model ─────────────────────────────── */
const form = reactive({
  username: '',
  password: '',
})

/* ───────────────────────────── logic ───────────────────────────────── */
const router   = useRouter()
const errorMsg = ref('')
const loading  = ref(false)

const submit = async () => {
  errorMsg.value = ''
  loading.value  = true
  try {
    await apiLogin(form)
    // ── redirect fixed: go to public dashboard ───────────────
    router.push('/public/dashboard')
  } catch (err) {
    let message = 'Login failed'
    const detail = err?.response?.data?.detail
    if (detail) message = typeof detail === 'string' ? detail : JSON.stringify(detail)
    else if (err.message) message = err.message
    errorMsg.value = message
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

        <!-- USERNAME -->
        <FormField label="Username">
          <FormControl
            v-model="form.username"
            :icon="mdiAccount"
            name="username"
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
