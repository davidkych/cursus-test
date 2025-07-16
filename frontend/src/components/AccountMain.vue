<template>
  <div class="min-h-screen flex flex-col items-center justify-center">
    <h1 class="text-2xl font-bold mb-4">
      <!-- Fallback prevents a blank header before /.auth/me completes -->
      Hello, <span v-if="userName">{{ userName }}</span><span v-else>loading…</span>
    </h1>

    <button
      class="px-4 py-2 rounded bg-blue-600 text-white hover:bg-blue-700 transition"
      @click="logout"
    >
      Logout
    </button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const userName = ref('');

/*
 * Fetch the authenticated user via Static Web App Easy-Auth.
 * Response shape:
 *   {
 *     "clientPrincipal": {
 *       "userDetails": "<name or email>",
 *       ...
 *     }
 *   }
 */
onMounted(async () => {
  try {
    const res = await fetch('/.auth/me');
    if (!res.ok) throw new Error(res.statusText);
    const { clientPrincipal } = await res.json();
    userName.value = clientPrincipal?.userDetails ?? '(unknown user)';
  } catch (err) {
    console.error('Failed to load user info', err);
    userName.value = '(unknown user)';
  }
});

/* ------------------------------------------------------------------ */
/* Log the user out and return to the public home page                */
/* ------------------------------------------------------------------ */
function logout() {
  const REDIRECT_AFTER_LOGOUT = '/';
  window.location.href =
    '/.auth/logout?post_logout_redirect_uri=' +
    encodeURIComponent(REDIRECT_AFTER_LOGOUT);
}
</script>
