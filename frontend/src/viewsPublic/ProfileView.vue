<!-- frontend/src/viewsPublic/ProfileView.vue -->
<script setup>
import { reactive, computed, ref } from 'vue'
import { useMainStore } from '@/stores/main'
import { useAuth } from '@/stores/auth.js'                    /* ⟨NEW⟩ already used */
import { redeemCode as apiRedeemCode, uploadAvatar as apiUploadAvatar } from '@/services/auth.js' /* ⟨NEW⟩ */
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
import UserAvatarCurrentUser from '@/components/UserAvatarCurrentUser.vue'      /* ⟨NEW⟩ */

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

/* ⟨NEW⟩ Upload eligibility & UI state */
const isAdmin   = computed(() => !!auth.user?.is_admin)
const isPremium = computed(() => !!auth.user?.is_premium_member)
const canUpload = computed(() => isAdmin.value || isPremium.value)

const avatarLoading = ref(false)
const avatarError   = ref('')
const avatarSuccess = ref('')

const ACCEPT_PREMIUM = 'image/jpeg,image/jpg,image/png'
const MAX_PREMIUM    = 512 * 1024
const acceptAttr     = computed(() => (isAdmin.value ? 'image/*' : ACCEPT_PREMIUM))

async function handleAvatarChange(e) {
  avatarError.value = ''
  avatarSuccess.value = ''

  // Derive the File from various emitter shapes
  let file = null
  if (e?.target?.files?.length) file = e.target.files[0]
  else if (e?.files?.length) file = e.files[0]
  else if (Array.isArray(e) && e[0]) file = e[0]
  else if (e instanceof File) file = e

  if (!file) {
    avatarError.value = 'No file selected'
    return
  }
  if (!canUpload.value) {
    avatarError.value = 'Premium membership required to upload an avatar'
    return
  }

  if (!isAdmin.value) {
    const typeOk = /^(image\/jpeg|image\/jpg|image\/png)$/i.test(file.type)
    const sizeOk = file.size <= MAX_PREMIUM
    if (!typeOk) { avatarError.value = 'Only JPG/PNG allowed for premium users'; return }
    if (!sizeOk) { avatarError.value = 'Max file size is 512 KB'; return }
  } else {
    // Admin: any image type, no size limit — light guard to avoid obvious non-images
    if (file.type && !file.type.startsWith('image/')) {
      avatarError.value = 'Unsupported file type (expecting an image)'
      return
    }
  }

  avatarLoading.value = true
  try {
    await apiUploadAvatar(file)
    await auth.refresh()            // pull fresh /me with new short-lived SAS URL
    avatarSuccess.value = 'Avatar updated.'
  } catch (err) {
    avatarError.value = err?.message || 'Upload failed'
  } finally {
    avatarLoading.value = false
  }
}

/* ────────────────────────── existing profile forms ────────────────────────── */
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
          <!-- ⟨UPDATED⟩ Avatar box: show current avatar + upload controls -->
          <FormField
            label="Avatar"
            :help="isAdmin ? 'Admins: any image type, no size limit' : (isPremium ? 'JPG/PNG only, under 512 KB' : 'Premium required to upload a custom avatar')"
          >
            <!-- current avatar preview (short-lived SAS used automatically via store) -->
            <div class="mb-3 flex items-center space-x-4">
              <UserAvatarCurrentUser class="w-16 h-16 overflow-hidden rounded-full" />
              <div class="text-sm text-gray-600 dark:text-gray-300">
                <div class="font-medium">Current avatar</div>
                <div v-if="!canUpload" class="text-red-600">Upload locked (Premium required)</div>
                <div v-else-if="isAdmin" class="text-green-700">Admin: upload any image</div>
                <div v-else class="text-gray-500">Premium: JPG/PNG · &lt; 512 KB</div>
              </div>
            </div>

            <!-- file picker (re-using existing component) -->
            <FormFilePicker
              label="Upload"
              name="avatar"
              :accept="acceptAttr"
              :disabled="!canUpload || avatarLoading"
              @change="handleAvatarChange"
            />

            <!-- messages -->
            <div v-if="avatarError" class="mt-2 text-sm text-red-600">
              {{ avatarError }}
            </div>
            <div v-if="avatarSuccess && !avatarError" class="mt-2 text-sm text-green-600">
              {{ avatarSuccess }}
            </div>
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
