<!-- frontend/src/viewsPublic/ProfileView.vue -->
<script setup>
import { reactive, computed, ref } from 'vue'
import { useMainStore } from '@/stores/main'
import { useAuth } from '@/stores/auth.js'                    /* ⟨NEW⟩ */
import {
  mdiAccount,
  mdiMail,
  mdiAsterisk,
  mdiFormTextboxPassword,
  mdiGithub,
  /* ⟨NEW⟩ icons for redeem UI */
  mdiTicketConfirmation,
  mdiCheck,
  mdiAlertCircle,
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

const mainStore = useMainStore()

/* ⟨NEW⟩ Login telemetry (from auth store) */
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

const profileForm = reactive({
  name: mainStore.userName,
  email: mainStore.userEmail,
})

const passwordForm = reactive({
  password_current: '',
  password: '',
  password_confirmation: '',
})

/* ⟨NEW⟩ Redeem code form state */
const redeemForm = reactive({ code: '' })
const redeeming = ref(false)
const redeemError = ref('')
const redeemSuccess = ref('')

const submitProfile = () => {
  mainStore.setUser(profileForm)
}

const submitPass = () => {
  //
}

/* ⟨NEW⟩ Redeem handler */
const submitRedeem = async () => {
  redeemError.value = ''
  redeemSuccess.value = ''
  const code = (redeemForm.code || '').trim()
  if (!code) {
    redeemError.value = 'Please enter a code'
    return
  }
  redeeming.value = true
  try {
    const resp = await auth.redeem(code)
    // Success message varies depending on what changed
    if (resp?.applied) {
      if (resp.is_admin) {
        redeemSuccess.value = 'Admin privileges have been activated.'
      } else if (resp.is_premium_member) {
        redeemSuccess.value = 'Premium membership has been activated.'
      } else {
        redeemSuccess.value = 'Code redeemed successfully.'
      }
    } else {
      redeemSuccess.value = 'Your account already has this feature. No changes needed.'
    }
    redeemForm.code = ''
  } catch (err) {
    redeemError.value = err?.message || 'Failed to redeem code'
  } finally {
    redeeming.value = false
  }
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

      <!-- ⟨NEW⟩ Telemetry panel: shows right after the Howdy greeting -->
      <CardBox v-if="lc" class="mb-6">
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

      <!-- ⟨NEW⟩ Redeem Code card (left, after avatar/telemetry) -->
      <div class="mb-6 max-w-xl">
        <CardBox is-form @submit.prevent="submitRedeem">
          <FormField label="Redeem code" help="Enter your code to unlock features">
            <FormControl
              v-model="redeemForm.code"
              :icon="mdiTicketConfirmation"
              name="redeem_code"
              placeholder="Enter code (e.g. VIP2025)"
              autocomplete="one-time-code"
              required
            />
          </FormField>

          <!-- success / error banners -->
          <template v-if="redeemError">
            <div class="mb-2 flex items-center text-sm text-red-600">
              <BaseButton
                :icon="mdiAlertCircle"
                color="danger"
                rounded-full
                small
                class="mr-2 pointer-events-none"
              />
              <span class="break-words">{{ redeemError }}</span>
            </div>
          </template>
          <template v-if="redeemSuccess">
            <div class="mb-2 flex items-center text-sm text-green-700">
              <BaseButton
                :icon="mdiCheck"
                color="success"
                rounded-full
                small
                class="mr-2 pointer-events-none"
              />
              <span class="break-words">{{ redeemSuccess }}</span>
            </div>
          </template>

          <template #footer>
            <BaseButtons>
              <BaseButton
                type="submit"
                color="info"
                :label="redeeming ? 'Redeeming…' : 'Redeem'"
                :disabled="redeeming"
              />
            </BaseButtons>
          </template>
        </CardBox>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <CardBox is-form @submit.prevent="submitProfile">
          <FormField label="Avatar" help="Max 500kb">
            <FormFilePicker label="Upload" />
          </FormField>

          <FormField label="Name" help="Required. Your name">
            <FormControl
              v-model="profileForm.name"
              :icon="mdiAccount"
              name="username"
              required
              autocomplete="username"
            />
          </FormField>
          <FormField label="E-mail" help="Required. Your e-mail">
            <FormControl
              v-model="profileForm.email"
              :icon="mdiMail"
              type="email"
              name="email"
              required
              autocomplete="email"
            />
          </FormField>

          <template #footer>
            <BaseButtons>
              <BaseButton color="info" type="submit" label="Submit" />
              <BaseButton color="info" label="Options" outline />
            </BaseButtons>
          </template>
        </CardBox>

        <CardBox is-form @submit.prevent="submitPass">
          <FormField label="Current password" help="Required. Your current password">
            <FormControl
              v-model="passwordForm.password_current"
              :icon="mdiAsterisk"
              name="password_current"
              type="password"
              required
              autocomplete="current-password"
            />
          </FormField>

          <BaseDivider />

          <FormField label="New password" help="Required. New password">
            <FormControl
              v-model="passwordForm.password"
              :icon="mdiFormTextboxPassword"
              name="password"
              type="password"
              required
              autocomplete="new-password"
            />
          </FormField>

          <FormField label="Confirm password" help="Required. New password one more time">
            <FormControl
              v-model="passwordForm.password_confirmation"
              :icon="mdiFormTextboxPassword"
              name="password_confirmation"
              type="password"
              required
              autocomplete="new-password"
            />
          </FormField>

          <template #footer>
            <BaseButtons>
              <BaseButton type="submit" color="info" label="Submit" />
              <BaseButton color="info" label="Options" outline />
            </BaseButtons>
          </template>
        </CardBox>
      </div>
    </SectionMain>
  </LayoutAuthenticated>
</template>
