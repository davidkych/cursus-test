<template>
  <!-- Simple status message while the browser is redirected -->
  <div class="flex items-center justify-center min-h-screen">
    <p class="text-lg">Redirecting to login…</p>
  </div>
</template>

<script setup>
/*
 * Redirect the browser through Static Web App Easy-Auth:
 *   1.  /.auth/login/aad                – start AAD sign-in flow
 *   2.  ?post_login_redirect_uri=...    – where Azure will send the user back
 *
 * Keeping provider & redirect URI in constants avoids hard-coding
 * the values throughout the codebase and eases future adjustments.
 */
const AUTH_PROVIDER      = 'aad';
const POST_LOGIN_REDIRECT = '/account/main';

window.location.href =
  `/.auth/login/${AUTH_PROVIDER}?post_login_redirect_uri=` +
  encodeURIComponent(POST_LOGIN_REDIRECT);
</script>
