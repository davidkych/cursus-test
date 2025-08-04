<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { mdiAccount, mdiAsterisk, mdiAlertCircle } from '@mdi/js'
import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox from '@/components/CardBox.vue'
import FormCheckRadio from '@/components/FormCheckRadio.vue'
import FormField from '@/components/FormField.vue'
import FormControl from '@/components/FormControl.vue'
import BaseButton from '@/components/BaseButton.vue'
import BaseButtons from '@/components/BaseButtons.vue'
import LayoutGuest from '@/layouts/LayoutGuest.vue'
import { login as apiLogin } from '@/services/auth.js'      // ← NEW

const form = reactive({
  login: 'john.doe',
  pass: 'highly-secure-password-fYjUw-',
  remember: true,
})

const router   = useRouter()
const errorMsg = ref('')
const loading  = ref(false)

const submit = async () => {
  errorMsg.value = ''
  loading.value = true
  try {
    const res = await apiLogin({
      username: form.login,
      password: form.pass,
    })

    // Persist token (simple approach)
    if (form.remember) {
      localStorage.setItem('jwt', res.access_token)
    } else {
      sessionStorage.setItem('jwt', res.access_token)
    }

    router.push('/dashboard')
  } catch (e) {
    errorMsg.value = e.message
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
            {{ errorMsg }}
          </div>
        </template>

        <FormField label="Login" help="Please enter your login">
          <FormControl
            v-model="form.login"
            :icon="mdiAccount"
            name="login"
            autocomplete="username"
          />
        </FormField>

        <FormField label="Password" help="Please enter your password">
          <FormControl
            v-model="form.pass"
            :icon="mdiAsterisk"
            type="password"
            name="password"
            autocomplete="current-password"
          />
        </FormField>

        <FormCheckRadio
          v-model="form.remember"
          name="remember"
          label="Remember"
          :input-value="true"
        />

        <template #footer>
          <BaseButtons>
            <BaseButton
              type="submit"
              color="info"
              :label="loading ? 'Logging in…' : 'Login'"
              :disabled="loading"
            />
            <BaseButton to="/dashboard" color="info" outline label="Back" />
          </BaseButtons>
        </template>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>
