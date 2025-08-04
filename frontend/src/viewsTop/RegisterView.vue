<script setup>
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  mdiAccount,
  mdiMail,
  mdiAsterisk,
  mdiCheck,
  mdiAlertCircle,
  mdiCalendar,
  mdiImage,
} from '@mdi/js'

import SectionFullScreen      from '@/components/SectionFullScreen.vue'
import CardBox                from '@/components/CardBox.vue'
import FormCheckRadio         from '@/components/FormCheckRadio.vue'
import FormCheckRadioGroup    from '@/components/FormCheckRadioGroup.vue'
import FormField              from '@/components/FormField.vue'
import FormControl            from '@/components/FormControl.vue'
import BaseButton             from '@/components/BaseButton.vue'
import BaseButtons            from '@/components/BaseButtons.vue'
import LayoutGuest            from '@/layouts/LayoutGuest.vue'
import ProfilePicSelector     from '@/components/ProfilePicSelector.vue'

import countries              from '@/assets/countries.json'
import { register as apiRegister } from '@/services/auth.js'

/* ────────────────────────── form model ─────────────────────────────── */
const form = reactive({
  username: '',
  gender: '',
  dob: '',
  country: '',
  password: '',
  passwordConfirm: '',
  email: '',
  emailConfirm: '',
  profilePicId: 1,
  profilePicType: 'default',
  acceptedTerms: false,
})

/* ────────────────────────── submit logic ───────────────────────────── */
const router   = useRouter()
const errorMsg = ref('')
const loading  = ref(false)

const submit = async () => {
  errorMsg.value = ''
  if (form.password !== form.passwordConfirm) { errorMsg.value = 'Passwords do not match'; return }
  if (form.email !== form.emailConfirm)       { errorMsg.value = 'E-mails do not match';  return }
  if (!form.gender)        { errorMsg.value = 'Please select your gender';                 return }
  if (!form.dob)           { errorMsg.value = 'Please enter your date of birth';           return }
  if (new Date(form.dob) > new Date()) {
    errorMsg.value = 'Date of birth must be in the past'; return
  }
  if (!form.country)       { errorMsg.value = 'Please select your country';                return }
  if (!form.profilePicId)  { errorMsg.value = 'Please pick a profile picture';             return }
  if (!form.acceptedTerms) { errorMsg.value = 'Please accept the terms & conditions';      return }

  loading.value = true
  try {
    await apiRegister({
      /* ── core creds ─────────────────────────────────────────── */
      username:         form.username,
      email:            form.email,
      password:         form.password,
      /* ── avatar (optional) ──────────────────────────────────── */
      profile_pic_id:   form.profilePicId,
      profile_pic_type: form.profilePicType,
      /* ── NEW profile details ────────────────────────────────── */
      gender:           form.gender,
      dob:              form.dob,
      country:          form.country,
      accepted_terms:   form.acceptedTerms,
    })
    router.push('/login')
  } catch (err) {
    let message = 'Registration failed'
    const detail = err?.response?.data?.detail
    if (detail) {
      if (typeof detail === 'string')      message = detail
      else if (Array.isArray(detail))      message = detail.map(e => e.msg ?? JSON.stringify(e)).join(' • ')
      else if (typeof detail === 'object') message = JSON.stringify(detail)
    } else if (err.message) message = err.message
    errorMsg.value = message
  } finally {
    loading.value = false
  }
}

/* ─────────────────────── gallery opener ───────────────────────────── */
function openGallery() {
  window.open('#/propic-gallery', 'propicGallery')
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
        <FormField label="Username" help="Pick a username">
          <FormControl
            v-model="form.username"
            :icon="mdiAccount"
            name="username"
            autocomplete="username"
            required
          />
        </FormField>

        <!-- GENDER -->
        <FormField label="Gender">
          <FormCheckRadioGroup
            v-model="form.gender"
            name="gender"
            type="radio"
            :options="{ male: 'Male', female: 'Female' }"
            required
          />
        </FormField>

        <!-- DATE OF BIRTH -->
        <FormField label="Date of birth">
          <FormControl
            v-model="form.dob"
            :icon="mdiCalendar"
            type="date"
            name="dob"
            required
          />
        </FormField>

        <!-- COUNTRY -->
        <FormField label="Country">
          <FormControl
            v-model="form.country"
            :options="countries"
            placeholder="Select a country"
            required
          />
        </FormField>

        <!-- PROFILE PICTURE -->
        <FormField label="Profile picture">
          <div class="flex items-center gap-2">
            <ProfilePicSelector v-model="form.profilePicId" class="w-24" />
            <BaseButton
              :icon="mdiImage"
              color="info"
              outline
              small
              label="View gallery"
              @click="openGallery"
            />
          </div>
        </FormField>

        <!-- PASSWORD -->
        <FormField label="Password">
          <FormControl
            v-model="form.password"
            :icon="mdiAsterisk"
            type="password"
            name="password"
            autocomplete="new-password"
            required
          />
        </FormField>

        <!-- EMAIL -->
        <FormField label="E-mail">
          <FormControl
            v-model="form.email"
            :icon="mdiMail"
            type="email"
            name="email"
            autocomplete="email"
            required
          />
        </FormField>

        <!-- CONFIRM PASSWORD -->
        <FormField label="Confirm password">
          <FormControl
            v-model="form.passwordConfirm"
            :icon="mdiAsterisk"
            type="password"
            name="passwordConfirm"
            autocomplete="new-password"
            required
          />
        </FormField>

        <!-- CONFIRM EMAIL -->
        <FormField label="Confirm e-mail">
          <FormControl
            v-model="form.emailConfirm"
            :icon="mdiMail"
            type="email"
            name="emailConfirm"
            autocomplete="email"
            required
          />
        </FormField>

        <!-- TERMS -->
        <FormCheckRadio
          v-model="form.acceptedTerms"
          name="terms"
          :input-value="true"
          label="I agree to the terms & conditions"
          :icon="mdiCheck"
        />

        <!-- buttons -->
        <template #footer>
          <BaseButtons>
            <BaseButton
              type="submit"
              color="info"
              :label="loading ? 'Registering…' : 'Register'"
              :disabled="loading"
            />
            <BaseButton to="/login" color="info" outline label="Go to login" />
          </BaseButtons>
        </template>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>
