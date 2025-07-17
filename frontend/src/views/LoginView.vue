<template>
  <LayoutGuest>
    <!-- Full-screen coloured background (keeps Admin One styling) -->
    <SectionFullScreen bg="purplePink">
      <!-- Simple status card centred on the screen -->
      <CardBox class="text-center py-16">
        <p class="text-lg font-semibold">Redirecting to login…</p>
      </CardBox>
    </SectionFullScreen>
  </LayoutGuest>
</template>

<script setup>
import { onMounted } from 'vue'

import SectionFullScreen from '@/components/SectionFullScreen.vue'
import CardBox           from '@/components/CardBox.vue'
import LayoutGuest       from '@/layouts/LayoutGuest.vue'

/* ------------------------------------------------------------------
 * Configure Easy-Auth redirect.
 * Keep values in constants so they aren’t hard-coded throughout
 * the codebase and are easy to change later.
 * ---------------------------------------------------------------- */
const AUTH_PROVIDER        = 'aad'   // Azure AD provider alias
const POST_LOGIN_REDIRECT  = '/'     // where Azure SWA sends the user back

/* ------------------------------------------------------------------
 * Redirect immediately after the component is mounted.
 * ---------------------------------------------------------------- */
onMounted(() => {
  window.location.href =
    `/.auth/login/${AUTH_PROVIDER}?post_login_redirect_uri=` +
    encodeURIComponent(POST_LOGIN_REDIRECT)
})
</script>
