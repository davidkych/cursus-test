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
} from '@mdi/js'
import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox from '@/components/CardBox.vue'
import FormCheckRadio from '@/components/FormCheckRadio.vue'
import FormCheckRadioGroup from '@/components/FormCheckRadioGroup.vue'
import FormField from '@/components/FormField.vue'
import FormControl from '@/components/FormControl.vue'
import BaseButton from '@/components/BaseButton.vue'
import BaseButtons from '@/components/BaseButtons.vue'
import LayoutGuest from '@/layouts/LayoutGuest.vue'

const form = reactive({
  username: '',
  gender: '',
  dob: '',
  password: '',
  passwordConfirm: '',
  email: '',
  emailConfirm: '',
  acceptedTerms: false,
})

const router = useRouter()
const errorMsg = ref('')

const submit = () => {
  errorMsg.value = ''

  if (form.password !== form.passwordConfirm) {
    errorMsg.value = 'Passwords do not match'
    return
  }
  if (form.email !== form.emailConfirm) {
    errorMsg.value = 'E-mails do not match'
    return
  }
  if (!form.gender) {
    errorMsg.value = 'Please select your gender'
    return
  }
  if (!form.dob) {
    errorMsg.value = 'Please enter your date of birth'
    return
  }
  if (!form.acceptedTerms) {
    errorMsg.value = 'Please accept the terms & conditions'
    return
  }

  // basic checks passed – navigate away (no real signup yet)
  router.push('/dashboard')
}
</script>

<template>
  <LayoutGuest>
    <SectionFullScreen v-slot="{ cardClass }" bg="purplePink">
      <CardBox :class="cardClass" is-form @submit.prevent="submit">
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

        <template #footer>
          <BaseButtons>
            <BaseButton type="submit" color="info" label="Register" />
            <BaseButton to="/login" color="info" outline label="Go to login" />
          </BaseButtons>
        </template>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>
