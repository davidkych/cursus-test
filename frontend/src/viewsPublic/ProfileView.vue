<!-- frontend/src/viewsPublic/ProfileView.vue -->
<script setup>
import { reactive, computed, ref } from 'vue'
import { useMainStore } from '@/stores/main'
import { useAuth } from '@/stores/auth.js'
import {
  mdiAccount,
  mdiMail,
  mdiAsterisk,
  mdiFormTextboxPassword,
  mdiGithub,
  mdiAlertCircle,
  mdiCheckCircle,
} from '@mdi/js'

import SectionMain from '@/components/SectionMain.vue'
import CardBox from '@/components/CardBox.vue'
import BaseDivider from '@/components/BaseDivider.vue'
import FormField from '@/components/FormField.vue'
import FormControl from '@/components/FormControl.vue'
import FormFilePicker from '@/components/FormFilePicker.vue'
import BaseButton from '@/components/BaseButton.vue'
import BaseButtons from '@/components/BaseButtons.vue'
import UserCard from '@/components/UserCard.vue'
import LayoutAuthenticated from '@/layouts/LayoutAuthenticated.vue'
import SectionTitleLineWithButton from '@/components/SectionTitleLineWithButton.vue'

import { changePassword as apiChangePassword, changeEmail as apiChangeEmail, me as apiMe } from '@/services/auth.js'

const mainStore = useMainStore()

/* Login telemetry (from auth store) */
const auth = useAuth()
const lc = computed(() => auth.user?.login_context || null)
const ip = computed(() => lc.value?.ip || '')
const browser = computed(() => {
  const b = lc.value?.ua?.browser || {}
  return [b.name, b.version].filter(Boolean).join(' ')
})
const os = computed(() => {
  const o = lc.value?.ua?.os || {}
  return [o.name, o.version].filter(Boolean).join(' ')
})
const device = computed(() => {
  const u = lc.value?.ua || {}
  if (u.is_bot) return 'Bot'
  if (u.is_mobile) return 'Mobile'
  if (u.is_tablet) return 'Tablet'
  if (u.is_pc) return 'Desktop'
  return ''
})
const country = computed(() => lc.value?.geo?.country_iso2 || '')
const timezone = computed(() => lc.value?.timezone || '')
const localePref = computed(() => lc.value?.locale?.client || lc.value?.locale?.accept_language || '')
const lastLogin = computed(() => {
  const iso = lc.value?.last_login_utc
  return iso ? new Date(iso).toLocaleString() : ''
})

/* Read-only identity (from auth) */
const username = computed(() => auth.user?.username || '')
const email = computed(() => auth.user?.email || '')

/* Change Password form state */
const pwForm = reactive({
  current: '',
  newpwd: '',
  confirm: '',
})
const pwError = ref('')
const pwSuccess = ref('')
const pwLoading = ref(false)

/* Change E-mail form state */
const emForm = reactive({
  current: '',
  email: '',
  confirm: '',
})
const emError = ref('')
const emSuccess = ref('')
const emLoading = ref(false)

/* Helpers */
function resetPwMessages() {
  pwError.value = ''
  pwSuccess.value = ''
}
function resetEmMessages() {
  emError.value = ''
  emSuccess.value = ''
}

/* Submit handlers */
async function submitChangePassword() {
  resetPwMessages()
  if (!pwForm.current) {
    pwError.value = 'Current password is required'
    return
  }
  if (pwForm.newpwd !== pwForm.confirm) {
    pwError.value = 'New password and confirm new password do not match'
    return
  }

  pwLoading.value = true
  try {
    await apiChangePassword({
      current_password: pwForm.current,
      new_password: pwForm.newpwd,
    })
    pwSuccess.value = 'Password updated successfully'
    pwForm.current = ''
    pwForm.newpwd = ''
    pwForm.confirm = ''
  } catch (err) {
    pwError.value = err?.message || 'Password change failed'
  } finally {
    pwLoading.value = false
  }
}

async function submitChangeEmail() {
  resetEmMessages()
  if (!emForm.current) {
    emError.value = 'Current password is required'
    return
  }
  if (!emForm.email || !emForm.confirm) {
    emError.value = 'Please enter the new e-mail and confirm it'
    return
  }
  if (emForm.email !== emForm.confirm) {
    emError.value = 'New e-mail and confirm new e-mail do not match'
    return
  }
  // Basic e-mail shape check (backend also validates)
  if (!/^\S+@\S+\.\S+$/.test(emForm.email)) {
    emError.value = 'Please enter a valid e-mail address'
    return
  }

  emLoading.value = true
  try {
    const res = await apiChangeEmail({
      current_password: emForm.current,
      new_email: emForm.email,
    })
    emSuccess.value = 'E-mail updated successfully'
    // Refresh profile so read-only e-mail reflects the change
    try {
      const profile = await apiMe()
      auth.setUser(profile)
    } catch (_) { /* ignore refresh errors */ }

    emForm.current = ''
    emForm.email = ''
    emForm.confirm = ''
  } catch (err) {
    emError.value = err?.message || 'E-mail change failed'
  } finally {
    emLoading.value = false
  }
}

/* No-op for the extra avatar Submit button */
function noopAvatarSubmit(evt) {
  if (evt && typeof evt.preventDefault === 'function') evt.preventDefault()
  // intentionally left blank
}
</script>

<template>
  <LayoutAuthenticated>
    <SectionMain>
      <SectionTitleLineWithButton :icon="mdiAccount" title="Profile" main>
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

      <UserCard class="mb-6" />

      <!-- Reworked layout: telemetry panel moved into the LEFT column above Avatar -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <!-- LEFT COLUMN: Telemetry panel → Avatar -->
        <div class="space-y-6">
          <!-- Telemetry panel (moved here) -->
          <CardBox v-if="lc">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-2">
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Last login:</span> <span class="text-gray-800 dark:text-gray-100">{{ lastLogin || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">IP:</span> <span class="text-gray-800 dark:text-gray-100">{{ ip || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Browser:</span> <span class="text-gray-800 dark:text-gray-100">{{ browser || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">OS:</span> <span class="text-gray-800 dark:text-gray-100">{{ os || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Device:</span> <span class="text-gray-800 dark:text-gray-100">{{ device || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Country:</span> <span class="text-gray-800 dark:text-gray-100">{{ country || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Timezone:</span> <span class="text-gray-800 dark:text-gray-100">{{ timezone || '—' }}</span></div>
              <div><span class="font-semibold text-gray-700 dark:text-gray-200">Locale:</span> <span class="text-gray-800 dark:text-gray-100">{{ localePref || '—' }}</span></div>
            </div>
          </CardBox>

          <!-- Avatar card with extra no-op Submit button -->
          <CardBox>
            <FormField label="Avatar" help="Max 500kb">
              <div class="flex items-center gap-3">
                <FormFilePicker label="Upload" />
                <BaseButton color="info" label="Submit" @click="noopAvatarSubmit" />
              </div>
            </FormField>
          </CardBox>
        </div>

        <!-- RIGHT COLUMN: Identity (read-only) + Change Password + Change E-mail -->
        <div class="space-y-6">
          <!-- Read-only identity block -->
          <CardBox>
            <FormField label="Username" help="Username is not changeable.">
              <FormControl :icon="mdiAccount" :model-value="username" readonly disabled />
            </FormField>
            <FormField label="E-mail" help="Registered e-mail (read-only).">
              <FormControl :icon="mdiMail" :model-value="email" readonly disabled />
            </FormField>
          </CardBox>

          <!-- Change Password -->
          <CardBox is-form @submit.prevent="submitChangePassword">
            <!-- messages -->
            <template v-if="pwError">
              <div class="mb-4 flex items-center text-sm text-red-600">
                <BaseButton :icon="mdiAlertCircle" color="danger" rounded-full small class="mr-2 pointer-events-none" />
                <span class="break-words">{{ pwError }}</span>
              </div>
            </template>
            <template v-if="pwSuccess">
              <div class="mb-4 flex items-center text-sm text-emerald-600">
                <BaseButton :icon="mdiCheckCircle" color="success" rounded-full small class="mr-2 pointer-events-none" />
                <span class="break-words">{{ pwSuccess }}</span>
              </div>
            </template>

            <FormField label="Current password" help="Required to continue">
              <FormControl
                v-model="pwForm.current"
                :icon="mdiAsterisk"
                name="current_password"
                type="password"
                required
                autocomplete="current-password"
              />
            </FormField>

            <BaseDivider />

            <FormField label="New password">
              <FormControl
                v-model="pwForm.newpwd"
                :icon="mdiFormTextboxPassword"
                name="new_password"
                type="password"
                autocomplete="new-password"
              />
            </FormField>

            <FormField label="Confirm new password">
              <FormControl
                v-model="pwForm.confirm"
                :icon="mdiFormTextboxPassword"
                name="confirm_new_password"
                type="password"
                autocomplete="new-password"
              />
            </FormField>

            <template #footer>
              <BaseButtons>
                <BaseButton
                  type="submit"
                  color="info"
                  :label="pwLoading ? 'Changing…' : 'Change password'"
                  :disabled="pwLoading"
                />
              </BaseButtons>
            </template>
          </CardBox>

          <!-- Change E-mail -->
          <CardBox is-form @submit.prevent="submitChangeEmail">
            <!-- messages -->
            <template v-if="emError">
              <div class="mb-4 flex items-center text-sm text-red-600">
                <BaseButton :icon="mdiAlertCircle" color="danger" rounded-full small class="mr-2 pointer-events-none" />
                <span class="break-words">{{ emError }}</span>
              </div>
            </template>
            <template v-if="emSuccess">
              <div class="mb-4 flex items-center text-sm text-emerald-600">
                <BaseButton :icon="mdiCheckCircle" color="success" rounded-full small class="mr-2 pointer-events-none" />
                <span class="break-words">{{ emSuccess }}</span>
              </div>
            </template>

            <FormField label="Current password" help="Required to continue">
              <FormControl
                v-model="emForm.current"
                :icon="mdiAsterisk"
                name="current_password_email"
                type="password"
                required
                autocomplete="current-password"
              />
            </FormField>

            <BaseDivider />

            <FormField label="New e-mail">
              <FormControl
                v-model="emForm.email"
                :icon="mdiMail"
                type="email"
                name="new_email"
                autocomplete="email"
              />
            </FormField>

            <FormField label="Confirm new e-mail">
              <FormControl
                v-model="emForm.confirm"
                :icon="mdiMail"
                type="email"
                name="confirm_new_email"
                autocomplete="email"
              />
            </FormField>

            <template #footer>
              <BaseButtons>
                <BaseButton
                  type="submit"
                  color="info"
                  :label="emLoading ? 'Changing…' : 'Change email'"
                  :disabled="emLoading"
                />
              </BaseButtons>
            </template>
          </CardBox>
        </div>
      </div>
    </SectionMain>
  </LayoutAuthenticated>
</template>
