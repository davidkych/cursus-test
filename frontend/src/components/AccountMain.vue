<template>
  <div class="min-h-screen flex flex-col items-center justify-center">
    <template v-if="user">
      <h1 class="text-3xl font-bold mb-4">Welcome, {{ user.userDetails }}</h1>
      <p class="mb-6 text-lg">You’re now authenticated via AAD.</p>

      <button
        class="px-6 py-3 bg-gray-600 text-white rounded-xl shadow hover:bg-gray-700"
        @click="logout"
      >
        Logout
      </button>
    </template>

    <template v-else>
      <p class="text-lg">Loading user profile…</p>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';

const user = ref(null);

onMounted(async () => {
  try {
    const rsp  = await fetch('/.auth/me', { credentials: 'include' });
    const json = await rsp.json();
    user.value = json.clientPrincipal || null;
  } catch (_) {
    user.value = null;
  }
});

function logout () {
  window.location.href = '/.auth/logout?post_logout_redirect_uri=/';
}
</script>
