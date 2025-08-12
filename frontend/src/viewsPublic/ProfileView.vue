<!-- frontend/src/viewsPublic/ProfileView.vue -->
<script setup>
import { reactive, computed, ref } from 'vue'
import { useMainStore } from '@/stores/main'
import { useAuth } from '@/stores/auth.js'                    /* ⟨NEW⟩ */
import { redeemCode as apiRedeemCode } from '@/services/auth.js' /* ⟨NEW⟩ */
import { mdiAccount, mdiMail, mdiAsterisk, mdiFormTextboxPassword, mdiGithub } from '@mdi/js'
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

const submitProfile = () => {
  mainStore.setUser(profileForm)
}

const submitPass = () => {
  //
}

/* ⟨NEW⟩ Redeem code form */
const redeemForm = reactive({ code: '' })
const redeemLoading = ref(false)
const redeemError = ref('')
const redeemSuccess = ref('')

const submitRedeem = async () => {
  redeemError.value = ''
  redeemSuccess.value = ''
  if (!redeemForm.code) {
    redeemError.value = 'Please enter a code'
    return
  }
  redeemLoading.value = true
  try {
    const updated = await apiRedeemCode(redeemForm.code)   // returns /me payload
    auth.setUser(updated)                                  // update store & top-bar
    redeemSuccess.value = 'Code redeemed successfully.'
    redeemForm.code = ''
  } catch (err) {
    redeemError.value = err?.message || 'Redeem failed'
  } finally {
    redeemLoading.value = false
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

      <!-- ⟨NEW⟩ Redeem code (left, after avatar) -->
      <div class="mb-6">
        <CardBox class="max-w-md" is-form @submit.prevent="submitRedeem">
          <template v-if="redeemError">
            <div class="mb-3 text-sm text-red-600">
              {{ redeemError }}
            </div>
          </template>
          <template v-if="redeemSuccess && !redeemError">
            <div class="mb-3 text-sm text-green-600">
              {{ redeemSuccess }}
            </div>
          </template>

          <FormField label="Redeem code" help="Case-sensitive">
            <FormControl
              v-model="redeemForm.code"
              name="redeem_code"
              placeholder="Enter your code"
              required
            />
          </FormField>

          <template #footer>
            <BaseButtons>
              <BaseButton
                type="submit"
                color="info"
                :label="redeemLoading ? 'Redeeming…' : 'Redeem'"
                :disabled="redeemLoading"
              />
            </BaseButtons>
          </template>
        </CardBox>
      </div>

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
